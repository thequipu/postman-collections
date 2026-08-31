"""FLOW-Realm-CRUD: Full realm lifecycle with 8 datasource types.

Creates ONE schema with 8 datasources:
  DB: Postgres, MySQL, MariaDB, Oracle, Snowflake, Mongo
  File: CSV (S3), Excel (S3)

Fetches entities from each DS, builds schema graph, creates realm/fabric.
Then tests all realm + ingest stream endpoints.
"""

import json

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import (create_schema_graph_step, create_entity_schema_graph_step, KG_ACCEPT,
                           SKIP_CLEANUP_PRE, SKIP_CLEANUP_TEST)

# Real shapeCypher for datatypetesting_mongo (maps the 3 collections). Embedded directly (NOT via
# --env-var, which truncates the multi-line value at the first newline). json.dumps -> valid JS literal.
MONGO_SHAPE_CYPHER = (
    "CREATE\n"
    "  (g2:dt_mongo_group_2 {uri: '$._id', _id: '$._id', id: '$.id', note: '$.note', "
    "f_decimal: '$.f_decimal', f_bool: '$.f_bool', f_boolean: '$.f_boolean', f_date: '$.f_date', "
    "f_isodate: '$.f_isodate', f_timestamp: '$.f_timestamp', f_bindata: '$.f_bindata'}),\n"
    "  (g1:dt_mongo_group_1 {uri: '$._id', _id: '$._id', id: '$.id', note: '$.note', "
    "f_objectid: '$.f_objectid', f_int32: '$.f_int32', f_numberint: '$.f_numberint', "
    "f_int64: '$.f_int64', f_numberlong: '$.f_numberlong', f_double: '$.f_double', "
    "f_numberdecimal: '$.f_numberdecimal'}),\n"
    "  (g3:dt_mongo_group_3 {uri: '$._id', _id: '$._id', id: '$.id', note: '$.note', "
    "f_binary: '$.f_binary', f_array: '$.f_array', f_object: '$.f_object', "
    "f_document: '$.f_document', f_string: '$.f_string', f_null: '$.f_null'});"
)


def _db_ds(step, label, prefix, var_id, var_cat, critical=True):
    """DB datasource creation step."""
    p = prefix + "_" if prefix else ""
    # Critical DS must be created (fail flow otherwise). Non-critical DSs "continue": an
    # unreachable host / missing creds is tolerated (accept 4xx/5xx) — the DS simply won't
    # be created, so its cat var stays empty and 03* skips it (no entities required).
    fail = f"if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}}" if critical else ""
    ok_codes = "[200,201]" if critical else "[200,201,400,500]"
    return req(f"{step} Create {label} DS", "POST", "/datasource",
        [f"const code=pm.response.code;",
         f"pm.test('{step} {label} created or skipped', () => {{ {fail} pm.expect(code).to.be.oneOf({ok_codes}); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const d=b.dataSourceModel||b.data||b;",
         f"if(d.id||d.sourceId) pm.collectionVariables.set('{var_id}', String(d.id||d.sourceId));",
         f"if(d.dataCatalogName) pm.collectionVariables.set('{var_cat}', d.dataCatalogName);",
         f"console.log('{label} DS id='+(d.id||d.sourceId));"],
        base="app_base_url",
        body={"name": f"pm_flow_{label.lower()}_" + "{{$timestamp}}",
              "driverType": "{{" + p + "driverType}}",
              "dbHostName": "{{" + p + "dbHost}}",
              "dbPort": "{{" + p + "dbPort}}",
              "databaseName": "{{" + p + "dbName}}",
              "dbUserName": "{{" + p + "dbUser}}",
              "dbPassword": "{{" + p + "dbPassword}}",
              "aesRandomIV": "{{" + p + "aesRandomIV}}",
              "dbSchema": "{{" + p + "dbSchema}}",
              "driverClassName": "{{" + p + "driverClassName}}",
              "deleted": False})


def _fetch_meta(step, label, cat_var, id_var, base="app_base_url"):
    """Fetch one datasource's metadata and add its entities to the schema graph.

    Contract requested for the realm flow:
      - DS NOT created (cat var empty)      -> skipped (non-critical DSs may be absent).
      - DS created but yields NO entities    -> FAIL the whole flow.
    Accumulates the raw metadata (tagged with its datasource id via _dsId) into _dsMetaList so
    the shared builder emits every DS's tables/columns/entities AND a resolvable dataSourceID.
    """
    return req(f"{step} Fetch {label} Entities", "POST", "/metadata-graph/fetch-data-source",
        [f"const cat=pm.collectionVariables.get('{cat_var}')||'';",
         f"if(!cat){{ pm.test('{step} {label} skipped (DS not created)', ()=>{{}}); return; }}",
         "const code=pm.response.code;",
         f"pm.test('{step} {label} fetch 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step} {label} fetch');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         f"b._dsId = pm.collectionVariables.get('{id_var}');",
         "let all=[]; try{all=JSON.parse(pm.collectionVariables.get('_dsMetaList')||'[]');}catch(e){}",
         "all.push(b); pm.collectionVariables.set('_dsMetaList', JSON.stringify(all));",
         "const tables=(b.hasTableEdges||[]).length;",
         f"pm.test('{step} {label} adds entities to schema', () => {{ if(tables===0){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step} {label} added 0 entities');}} pm.expect(tables, '{label} was created but produced 0 entities').to.be.above(0); }});",
         f"console.log('{label}: '+tables+' entities added to schema');"],
        base=base, body={"uri": "{{" + cat_var + "}}"},
        prerequest=[
            # If the DS wasn't created, don't hit fetch with an empty uri — redirect to health.
            f"const cat=pm.collectionVariables.get('{cat_var}')||'';",
            "if(!cat){ pm.request.method='GET'; pm.request.url = pm.collectionVariables.get('_skip_url')||pm.environment.get('app_base_url')+'/actuator/health'; }",
        ])


def generate():
    base = "app_base_url"

    ds_vars = ["pgDsId", "pgCat", "mysqlDsId", "mysqlCat", "mariaDsId", "mariaCat",
               "oracleDsId", "oracleCat", "snowDsId", "snowCat",
               "mongoDsId", "mongoCat", "csvDsId", "csvCat", "excelDsId", "excelCat"]

    items = [
        build_setup(base, "/actuator/health",
                    clear_vars=ds_vars + ["schemaName", "schemaId", "versionId",
                                          "realmId", "realmName", "realmReferenceName", "versionName", "streamId",
                                          "_allNodes", "_allLinks", "_ingestion_status",
                                          "_dsMetaList", "_graphNodes", "_graphLinks",
                                          "_versionUri", "_versionUriEnc", "awsVersionId", "_streamCount", "_genStreams", "_streamNames",
                                          "_nsAttempt", "_nsUp", "_ingAttempt", "_mongoShape",
                                          "_entIdx", "_entCount",
                                          "excelDsName", "_excelStagedKey", "_excelCols"]),

        # ═══ PHASE 0: Create 8 DataSources ═══

        # DB types
        _db_ds("01a", "Postgres",  "",       "pgDsId",     "pgCat",     critical=True),
        _db_ds("01b", "MySQL",     "mysql",  "mysqlDsId",  "mysqlCat",  critical=False),
        _db_ds("01c", "MariaDB",   "maria",  "mariaDsId",  "mariaCat",  critical=False),
        _db_ds("01d", "Oracle",    "oracle", "oracleDsId", "oracleCat", critical=False),
        _db_ds("01e", "Snowflake", "snow",   "snowDsId",   "snowCat",   critical=False),

        # Mongo (needs shapeParseResult)
        req("01f Create Mongo DS", "POST", "/datasource",
            ["pm.test('01f Mongo 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201,500]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "if(d.id||d.sourceId) pm.collectionVariables.set('mongoDsId', String(d.id||d.sourceId));",
             "if(d.dataCatalogName) pm.collectionVariables.set('mongoCat', d.dataCatalogName);",
             "console.log('Mongo DS id='+(d.id||d.sourceId||'skipped'));"],
            base=base, body={"name": "x"},
            prerequest=[
                "// Mongo needs the REAL shapeCypher (maps collections) + a derived shapeParseResult",
                "// (server 500s on null). Embedded below (json.dumps) — NOT via env-var, which",
                "// truncates the multi-line value at the first newline (stored shapeCypher='CREATE').",
                "// Also record collection->fields in _mongoShape so the schema-graph builder can",
                "// synthesize column nodes (mongo fetch-data-source returns 0 columns).",
                "const SC = " + json.dumps(MONGO_SHAPE_CYPHER) + ";",
                "const mshape={}; const spNodes=[];",
                "const reNode=/\\(g\\d+:(\\w+)\\s*\\{([^}]*)\\}\\)/g; let mm;",
                "while((mm=reNode.exec(SC))!==null){",
                "  const label=mm[1]; const fields=[]; const reP=/(\\w+):\\s*'(\\$[^']*)'/g; let pp;",
                "  while((pp=reP.exec(mm[2]))!==null){ if(pp[1]!=='uri') fields.push(pp[1]); }",
                "  mshape[label]=fields;",
                "  spNodes.push({label:label, prefix:'http://mongo.in/', properties:fields.map(function(f){return {jsonPath:'$.'+f, propertyName:f};}), uriProperty:'$._id', edgeShapes:[]});",
                "}",
                "pm.collectionVariables.set('_mongoShape', JSON.stringify(mshape));",
                "const body = {",
                "  name: 'pm_flow_mongo_' + Date.now(),",
                "  driverType: 'MONGO',",
                "  dbHostName: pm.variables.get('mongo_dbHost') || '207.180.249.216',",
                "  dbPort: parseInt(pm.variables.get('mongo_dbPort') || '27018'),",
                "  databaseName: pm.variables.get('mongo_dbName') || 'datatypetesting_mongo',",
                "  dbUserName: pm.variables.get('mongo_dbUser') || 'quipu_admin',",
                "  dbPassword: pm.variables.get('mongo_dbPassword') || '',",
                "  aesRandomIV: pm.variables.get('mongo_aesRandomIV') || '',",
                "  dbSchema: pm.variables.get('mongo_dbSchema') || 'admin',",
                "  deleted: false,",
                "  shapeCypher: SC,",
                "  shapeParseResult: {shape: {prefix: 'http://mongo.in/', nodes: spNodes, namespace: 'public', shapeType: 'CYPHER_DSL'}, constraints: []}",
                "};",
                "pm.request.body.raw = JSON.stringify(body);",
            ]),

        # CSV (S3). Unlike Excel, the CSV connector's checkConnection builds its S3 client
        # from the request accessKey/secret (not server IAM) and requires a non-empty files[]
        # of EXISTING object keys. Pass real S3 creds via env vars (s3_access_key/s3_secret_key);
        # send them RAW with NO aesRandomIV so the server skips decryption and uses them directly.
        req("01g Create CSV DS", "POST", "/datasource",
            ["pm.test('01g CSV created or skipped', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400,500]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "if(d.id) pm.collectionVariables.set('csvDsId', String(d.id));",
             "if(d.dataCatalogName) pm.collectionVariables.set('csvCat', d.dataCatalogName);",
             "console.log('CSV DS id='+(d.id||'skipped (need s3_access_key/s3_secret_key)'));"],
            base=base, body={"name": "x"},
            prerequest=[
                "// each files[] entry needs columnDetails (null -> server NPE). Default to the",
                "// known sample-data.csv header; override the key via s3_csv_file if needed.",
                "const body = {",
                "  name: 'pm_flow_csv_' + Date.now(),",
                "  driverType: 'CSV',",
                "  bucket: pm.environment.get('s3_csv_bucket') || pm.environment.get('s3_bucket') || 'backupfor173',",
                "  key: pm.environment.get('s3_csv_key') || 'csvfiles',",
                "  region: pm.environment.get('s3_region') || 'ap-south-1',",
                "  accessKey: pm.environment.get('s3_access_key') || '',",
                "  secret: pm.environment.get('s3_secret_key') || '',",
                "  deleted: false,",
                "  files: [{key: pm.environment.get('s3_csv_file') || 'csvfiles/sample-data.csv', columnDetails: [",
                "    {name:'id',type:'INTEGER',nullable:false,primaryKey:true,uniqueKey:true},",
                "    {name:'name',type:'STRING',nullable:true,primaryKey:false,uniqueKey:false},",
                "    {name:'email',type:'STRING',nullable:true,primaryKey:false,uniqueKey:false},",
                "    {name:'age',type:'INTEGER',nullable:true,primaryKey:false,uniqueKey:false},",
                "    {name:'salary',type:'DOUBLE',nullable:true,primaryKey:false,uniqueKey:false},",
                "    {name:'department',type:'STRING',nullable:true,primaryKey:false,uniqueKey:false},",
                "    {name:'hire_date',type:'STRING',nullable:true,primaryKey:false,uniqueKey:false},",
                "    {name:'is_active',type:'STRING',nullable:true,primaryKey:false,uniqueKey:false}",
                "  ]}]",
                "};",
                "pm.request.body.raw = JSON.stringify(body);",
            ]),

        # Excel (S3). Excel MUST be staged first: POST TXN /s3-upload/getExcelHeader converts the
        # source .xlsx -> CSV into the server MinIO at datasource/<datasourceName>/<sheet>.csv and
        # returns the header columns. The DS is then created pointing at that MinIO key. (Skipping the
        # stage step is why a direct /datasource create 400s "connection details invalid".)
        req("01h1 Stage Excel Header (getExcelHeader)", "POST",
            "/s3-upload/getExcelHeader?datasourceName={{excelDsName}}",
            ["const code=pm.response.code;",
             "pm.test('01h1 getExcelHeader 200|400', () => pm.expect(code).to.be.oneOf([200,400]));",
             "if(code===200){ let a=[]; try{a=pm.response.json();}catch(e){}",
             "  if(a[0]&&a[0].key){ pm.collectionVariables.set('_excelStagedKey', a[0].key);",
             "    const hdr=(a[0].content||'').split(',').map(s=>s.trim()).filter(Boolean);",
             "    const cols=hdr.map((n,i)=>({name:n,type:'STRING',nullable:true,primaryKey:i===0,uniqueKey:i===0}));",
             "    pm.collectionVariables.set('_excelCols', JSON.stringify(cols));",
             "    console.log('Excel staged: '+a[0].key+', '+hdr.length+' cols'); } }",
             "else console.log('Excel header stage skipped (need s3 creds) — Excel DS will be skipped');"],
            base="transform_base_url", body={"bucket": "x"},
            prerequest=[
                "pm.collectionVariables.set('excelDsName', 'pm_flow_excel_' + Date.now());",
                "// s3-upload endpoints require this vendor media type (plain application/json -> 415)",
                "pm.request.headers.upsert({key:'Content-Type', value:'application/vnd.quipu.file-upload+json;version=1.0.0'});",
                "const body={bucket: pm.environment.get('s3_excel_bucket')||pm.environment.get('s3_bucket')||'quipu-api-tests', key: pm.environment.get('s3_excel_key')||'excelfiles/Pharma_Drugs_V2.xlsx', region: pm.environment.get('s3_region')||'ap-south-1', accessKey: pm.environment.get('s3_access_key')||'', secret: pm.environment.get('s3_secret_key')||''};",
                "pm.request.body.raw = JSON.stringify(body);",
            ]),

        req("01h Create Excel DS", "POST", "/datasource",
            ["pm.test('01h Excel 2xx|skip', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400,500]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "if(d.id) pm.collectionVariables.set('excelDsId', String(d.id));",
             "if(d.dataCatalogName) pm.collectionVariables.set('excelCat', d.dataCatalogName);",
             "console.log('Excel DS id='+(d.id||'skipped'));"],
            base=base, body={"name": "x"},
            prerequest=[
                "const staged = pm.collectionVariables.get('_excelStagedKey');",
                "let cols=[]; try{cols=JSON.parse(pm.collectionVariables.get('_excelCols')||'[]');}catch(e){}",
                "// If staging didn't happen (no creds), skip the create so it stays non-critical",
                "if(!staged){ pm.request.url=pm.collectionVariables.get('_skip_url'); pm.request.method='GET'; pm.request.auth={type:'noauth'}; return; }",
                "const body = {",
                "  name: pm.collectionVariables.get('excelDsName'),",
                "  driverType: 'EXCEL',",
                "  bucket: pm.environment.get('s3_excel_bucket') || pm.environment.get('s3_bucket') || 'quipu-api-tests',",
                "  key: pm.environment.get('s3_excel_key') || 'excelfiles/Pharma_Drugs_V2.xlsx',",
                "  region: pm.environment.get('s3_region') || 'ap-south-1',",
                "  accessKey: pm.environment.get('s3_access_key') || '',",
                "  secret: pm.environment.get('s3_secret_key') || '',",
                "  deleted: false,",
                "  files: [{key: staged, columnDetails: cols}]",
                "};",
                "pm.request.body.raw = JSON.stringify(body);",
            ]),

        # ═══ PHASE 1: Schema (with prefix) → Fetch Entities → Schema-Graph (version+entities) → Realm ═══

        req("02 Create Schema", "POST", "/schema",
            ["const code=pm.response.code;",
             "pm.test('02 Schema 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','02');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.schemaModel||b.data||b;",
             "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
             "if(d.id||d.schemaId) pm.collectionVariables.set('schemaId', String(d.id||d.schemaId));",
             "if(d.prefix) pm.collectionVariables.set('schemaPrefix', d.prefix);"],
            base=base, body={"schemaName": "x"},
            prerequest=[
                "// prefix = schema name, hyphenated (letters/digits/hyphen) — the schema's ingest-namespace URI.",
                "const schemaName='pm_flow_realm_schema_'+Date.now();",
                "const prefix=schemaName.replace(/_/g,'-');",
                "pm.request.body.raw=JSON.stringify({schemaName:schemaName,prefix:prefix,description:'8-DS fabric'});",
                "pm.collectionVariables.set('schemaPrefix', prefix);",
            ]),

        # Fetch metadata for EVERY created datasource and add its entities to the schema.
        # Each created DS that yields zero entities FAILS the flow (see _fetch_meta).
        _fetch_meta("03a", "Postgres",  "pgCat",     "pgDsId",     base),
        _fetch_meta("03b", "MySQL",     "mysqlCat",  "mysqlDsId",  base),
        _fetch_meta("03c", "MariaDB",   "mariaCat",  "mariaDsId",  base),
        _fetch_meta("03d", "Oracle",    "oracleCat", "oracleDsId", base),
        _fetch_meta("03e", "Snowflake", "snowCat",   "snowDsId",   base),
        _fetch_meta("03f", "Mongo",     "mongoCat",  "mongoDsId",  base),
        _fetch_meta("03g", "CSV",       "csvCat",    "csvDsId",    base),
        _fetch_meta("03h", "Excel",     "excelCat",  "excelDsId",  base),

        # Strict gate: every datasource that was created MUST have contributed entities.
        req("03z Verify All DS Entities", "GET", "/actuator/health",
            ["pm.test('03z health', () => pm.response.to.have.status(200));",
             "let ml=[]; try{ml=JSON.parse(pm.collectionVariables.get('_dsMetaList')||'[]');}catch(e){}",
             "const catVars=['pgCat','mysqlCat','mariaCat','oracleCat','snowCat','mongoCat','csvCat','excelCat'];",
             "const created=catVars.filter(v=>pm.collectionVariables.get(v)).length;",
             "const withEntities=ml.filter(m=>(m.hasTableEdges||[]).length>0).length;",
             "const total=ml.reduce((a,m)=>a+((m.hasTableEdges||[]).length),0);",
             "console.log('DSs created: '+created+', DSs with entities: '+withEntities+', total entities: '+total);",
             "pm.test('03z every created DS added entities', () => { if(withEntities<created||total===0){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','03z entities missing');} pm.expect(withEntities, 'created DSs vs DSs with entities').to.eql(created); pm.expect(total).to.be.above(0); });"],
            base=base),

        # PRODUCT-FAITHFUL: create each business entity one-by-one via POST /entity (server stamps
        # identity/tenant/createdBy + links Node Property -> physical column), then assemble the
        # schema graph from the entity-graph (datasource-subgraph per DS) and save (+versionsModel).
        *create_entity_schema_graph_step("04", base,
            ds_id_vars=("pgDsId", "mysqlDsId", "mariaDsId", "oracleDsId",
                        "snowDsId", "mongoDsId", "csvDsId", "excelDsId")),

        # Resolve the real versionId from the schema right before realm-create. The realm MUST
        # carry a valid versionId, or streams/generate later 400s ("no versionId; cannot resolve
        # schema graph"). Fetching it fresh here is robust regardless of the save-version response.
        req("05b Resolve Version", "GET", "/schema/name?schemaName={{schemaName}}",
            ["const code=pm.response.code;",
             "pm.test('05b 2xx', () => pm.expect(code).to.be.oneOf([200]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.schemaModel||b.data||b; const vs=(d.versions||[]);",
             "const v=vs.find(x=>x.latest)||vs[vs.length-1]||{};",
             "if(v.versionId){pm.collectionVariables.set('versionId', String(v.versionId)); if(v.versionName) pm.collectionVariables.set('versionName', v.versionName);}",
             "// versionId is normally already minted by 04i (POST /schema-graph + versionsModel);",
             "// this is a best-effort refresh — pass on whichever versionId we have.",
             "const vid=pm.collectionVariables.get('versionId');",
             "pm.test('05b has versionId', () => { if(!vid){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','05b no versionId');} pm.expect(vid, 'versionId (from 04i or schema)').to.not.be.undefined; });",
             "console.log('Resolved versionId='+v.versionId+' ('+(v.versionName||'')+') for '+pm.collectionVariables.get('schemaName'));"],
            base=base),

        req("06 Create Realm", "POST", "/realm",
            ["const code=pm.response.code;",
             "pm.test('06 Realm 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','06');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.realmModel||b.data||b;",
             "if(d.id||d.realmId) pm.collectionVariables.set('realmId', String(d.id||d.realmId));",
             "if(d.name||d.realmName) pm.collectionVariables.set('realmName', d.name||d.realmName);",
             "if(d.referenceName) pm.collectionVariables.set('realmReferenceName', d.referenceName);",
             "console.log('Realm id='+(d.id||d.realmId)+', ref='+(d.referenceName||''));"],
            base=base, body={"name":"x"},
            prerequest=["pm.request.body.raw=JSON.stringify({name:'pm_flow_realm_'+Date.now(),description:'8-DS fabric',schemaName:pm.collectionVariables.get('schemaName'),versionId:parseInt(pm.collectionVariables.get('versionId'))});"]),

        # After the realm record is created, bind a Synapse namespace to the schema/version
        # (the UI's second realm-creation call). Skips automatically if step 06 failed.
        req("06b Create Namespace (Synapse)", "POST", "/synapse/namespace/create",
            ["const code=pm.response.code;",
             "pm.test('06b 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','06b namespace create');} pm.expect(code).to.be.oneOf([200,201]); });",
             "if([200,201].includes(code)) console.log('Synapse namespace created for '+pm.collectionVariables.get('realmReferenceName'));"],
            base="kg_base_url", body={"name": ""},
            prerequest=[
                "// Ingest flags default true; type is null unless memoryNamespace=true -> 'MEMORY' (matches UICore).",
                "const memoryNamespace=String(pm.environment.get('memoryNamespace')||'false')==='true';",
                "const ntype=memoryNamespace?'MEMORY':null;",
                "const historic=String(pm.environment.get('requiresHistoricIngest')||'true')==='true';",
                "const vector=String(pm.environment.get('vectorIngestionRequired')||'true')==='true';",
                "const body={name:pm.collectionVariables.get('realmReferenceName'),schemaName:pm.collectionVariables.get('schemaName'),schemaVersion:'v1',requiresHistoricIngest:historic,type:ntype,vectorIngestionRequired:vector};",
                "pm.request.body.raw=JSON.stringify(body);",
            ]),

        # Vectorize the realm (UICore realmVectorization) — non-memory fabrics only.
        # Skips when memoryNamespace=true.
        req("06c Vectorize Realm", "POST", "/schema/vectorize/{{realmReferenceName}}",
            ["const mem=String(pm.environment.get('memoryNamespace')||'false')==='true';",
             "pm.test('06c 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201,202,204]));",
             "console.log(mem?'Vectorize skipped (memory fabric)':'Vectorize triggered for '+pm.collectionVariables.get('realmReferenceName'));"],
            base="nexus_base_url",
            prerequest=[
                "// memory fabrics are not vectorized (matches UICore: if(!memoryFabric) realmVectorization)",
                "if(String(pm.environment.get('memoryNamespace')||'false')==='true'){",
                "  pm.request.method='GET';",
                "  pm.request.url=pm.collectionVariables.get('_skip_url')||pm.environment.get('app_base_url')+'/actuator/health';",
                "}",
            ]),

        # ═══ PHASE 2: Realm API Testing (12 endpoints) ═══

        req("07 List Realms", "GET", "/realm?page=0&size=20",
            ["pm.test('07 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("08 Is Unique", "GET", "/realm/is-unique?realmName={{realmName}}",
            ["pm.test('08 200', () => pm.response.to.have.status(200));"], base=base),
        req("09 Get by ID", "GET", "/realm/{{realmId}}",
            ["pm.test('09 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.realmModel||b.data||b;",
             "pm.test('09 id', () => pm.expect(String(d.id||d.realmId||'')).to.eql(pm.collectionVariables.get('realmId')));"],
            base=base),
        req("10 Get by Name", "GET", "/realm/by-name?realmName={{realmName}}",
            ["pm.test('10 200', () => pm.response.to.have.status(200));"], base=base),
        req("11 Get by Name LB", "GET", "/realm/by-name-lb?realmName={{realmName}}",
            ["pm.test('11 200', () => pm.response.to.have.status(200));"], base=base),
        req("12 All Realms", "GET", "/realm/all-realms-data",
            ["pm.test('12 200', () => pm.response.to.have.status(200));"], base=base),
        req("13 References", "GET", "/realm/references",
            ["pm.test('13 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        # PUT /realm is a FULL replace — the body MUST carry schemaName/versionId/referenceName/
        # type, or the update nulls them and breaks streams/generate ("no versionId"). Read the
        # current realm first, then patch only description so nothing is lost.
        req("14 Update", "PUT", "/realm",
            ["pm.test('14 200', () => pm.response.to.have.status(200));"],
            base=base, body={"id": 0},
            prerequest=[
                "const body={id:parseInt(pm.collectionVariables.get('realmId')),name:pm.collectionVariables.get('realmName'),description:'Updated by FLOW',schemaName:pm.collectionVariables.get('schemaName'),versionId:parseInt(pm.collectionVariables.get('versionId')),referenceName:pm.collectionVariables.get('realmReferenceName'),type:'GRAPH',noSchema:false};",
                "pm.request.body.raw=JSON.stringify(body);",
            ]),
        req("15 Verify Update", "GET", "/realm/{{realmId}}",
            ["pm.test('15 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.realmModel||b.data||b;",
             "pm.test('15 updated', () => pm.expect(String(d.description||'')).to.include('Updated'));",
             "pm.test('15 versionId preserved', () => pm.expect(d.versionId, 'update must not null versionId').to.not.be.null);"],
            base=base),
        req("16 CDC Active", "GET", "/realm/cdc-active-realms",
            ["pm.test('16 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("17 CDC by ID", "GET", "/realm/cdc-active/{{realmId}}",
            ["pm.test('17 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("18 Update CDC", "PUT", "/realm/cdc-status/{{realmId}}?cdcStatus=true",
            ["pm.test('18 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),

        # ═══ PHASE 3: Ingestion ═══

        # Real ingestion chain — ported from scripts/test_single_ds_fabric.py (proven to land data):
        #   19 generate -> 20 verify>0 -> 21 wait namespace UP -> 22 SAVE streams -> 23 event/ingest
        #   -> 24 STRICT verify EVERY table landed rows.
        # Failures fail the ASSERTION (non-zero newman exit) but do NOT set _flow_failed, so the
        # cleanup below still runs and deletes the fabric.
        req("19 Generate Ingest Streams", "POST", "/streams/generate",
            ["pm.test('19 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let arr=[]; try{arr=pm.response.json();}catch(e){}",
             "if(!Array.isArray(arr)) arr=[];",
             "pm.collectionVariables.set('_streamCount', String(arr.length));",
             "// store only the NAMES (small) for the verify step — the full stream payload is NOT",
             "// round-tripped through a collection variable (that corrupts the body -> 400 'Failed to",
             "// read request'). Streams are re-generated + saved+ingested IN-MEMORY at step 22.",
             "pm.collectionVariables.set('_streamNames', JSON.stringify(arr.map(s=>s.name).filter(Boolean)));",
             "console.log('Ingest streams generated: '+arr.length+(arr.length?(' e.g. '+arr[0].name):''));"],
            base="transform_base_url", body={"realmId": 0},
            prerequest=["pm.request.body.raw=JSON.stringify({realmId:parseInt(pm.collectionVariables.get('realmId'))});"]),

        req("20 Verify Streams Generated", "GET", "/actuator/health",
            ["pm.test('20 health', () => pm.response.to.have.status(200));",
             "const n=parseInt(pm.collectionVariables.get('_streamCount')||'0');",
             "console.log(n>0 ? ('Streams generated OK: '+n) : 'STREAM GENERATION FAILED (0 streams)');",
             "pm.test('20 streams generated (>0)', () => pm.expect(n, 'ingest streams generated').to.be.above(0));"],
            base=base),

        # 21 Poll synapse namespace status until UP (create at 06b is async). setNextRequest loop with
        # a ~4s client-side spacer (newman has no sleep); caps at 18 tries (~72s) then proceeds.
        req("21 Wait Namespace UP", "GET", "/synapse/namespace/status?name={{realmReferenceName}}",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "const code=pm.response.code;",
             "let st=''; try{st=(pm.response.json().status||'').toUpperCase();}catch(e){}",
             "const a=parseInt(pm.collectionVariables.get('_nsAttempt')||'0');",
             "console.log('namespace status attempt '+a+': '+st+(code>=500?(' (HTTP '+code+')'):''));",
             "// A 500 here means the tenant has no QuipuSynapse URL configured (getSynapseUrl null) —",
             "// retrying won't help, so stop polling and flag it; the ingest verify (24) reports it once.",
             "if(code>=500){ pm.collectionVariables.set('_nsSynapse500','true'); pm.collectionVariables.unset('_nsAttempt'); console.log('namespace status '+code+' — tenant has no synapse URL; stopping poll'); }",
             "else if(st==='UP'){ pm.collectionVariables.set('_nsUp','true'); pm.collectionVariables.unset('_nsAttempt'); }",
             "else if(a < 30){ pm.collectionVariables.set('_nsAttempt', String(a+1)); postman.setNextRequest('21 Wait Namespace UP'); }",
             "else { pm.collectionVariables.unset('_nsAttempt'); }",
             "pm.test('21 namespace reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,404,500]));"],
            base="kg_base_url",
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "if(parseInt(pm.collectionVariables.get('_nsAttempt')||'0')>0){ const t=Date.now(); while(Date.now()-t<4000){} }",
            ]),

        # 22 SAVE + RUN ingestion IN-MEMORY (mirrors scripts/test_single_ds_fabric.py).
        # Main request re-generates the streams; the test then stamps realmId and posts them to
        # create-streams (SAVE, required) and event/ingest (RUN) via sendRequest with the array held
        # in the script scope — NEVER through a collection variable (that corrupts the 29-stream body
        # -> 400 'Failed to read request').
        req("22 Save + Run Ingestion", "POST", "/streams/generate",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "pm.test('22 regen 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let arr=[]; try{arr=pm.response.json();}catch(e){}",
             "if(!Array.isArray(arr)) arr=[];",
             "const rid=parseInt(pm.collectionVariables.get('realmId'));",
             "arr.forEach(s=>{ s.realmId=rid; });",
             "const app=pm.environment.get('app_base_url'); const txn=pm.environment.get('transform_base_url');",
             "const hdr={'Authorization':'Bearer '+(pm.collectionVariables.get('access_token')||pm.environment.get('access_token')),'X-TENANT-ID':pm.environment.get('tenant_id'),'Content-Type':'application/json'};",
             "const raw=JSON.stringify(arr);",
             "pm.sendRequest({url:app+'/atomicIngestStream/create-streams', method:'POST', header:hdr, body:{mode:'raw', raw:raw}}, (e1,r1)=>{",
             "  pm.test('22 create-streams 2xx', () => pm.expect(r1 && r1.code, 'create-streams code').to.be.oneOf([200,201]));",
             "  console.log('create-streams: '+(r1?r1.code:e1));",
             "  pm.sendRequest({url:txn+'/event/ingest?truncate=false&seedSequenceFromJournal=false&forceIngest=true', method:'POST', header:hdr, body:{mode:'raw', raw:raw}}, (e2,r2)=>{",
             "    pm.test('22 event/ingest 2xx', () => pm.expect(r2 && r2.code, 'event/ingest code').to.be.oneOf([200,201,204]));",
             "    console.log('event/ingest: '+(r2?r2.code:e2));",
             "  });",
             "});"],
            base="transform_base_url", body={"realmId": 0},
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "pm.request.body.raw=JSON.stringify({realmId:parseInt(pm.collectionVariables.get('realmId'))});",
            ]),

        # 24 STRICT verify: EVERY table must land rows or the flow FAILS. Polls stats up to ~18x
        # (~72s), re-firing event/ingest once mid-way (forceIngest=true).
        req("24 Verify Tables Landed", "GET", "/synapse/namespace/stats?namespace={{realmReferenceName}}",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "// If synapse isn't configured for the tenant (status was 500), the stats endpoint 500s too —",
             "// stop retrying and report the ROOT cause once, instead of 18 identical 0-rows lines.",
             "if(pm.response.code>=500 || pm.collectionVariables.get('_nsSynapse500')==='true'){ pm.collectionVariables.unset('_ingAttempt'); console.log('namespace stats '+pm.response.code+' — tenant has no QuipuSynapse URL; ingestion cannot be verified'); pm.test('24 synapse configured for tenant (namespace stats reachable)', () => pm.expect(pm.response.code, 'stats endpoint 500 = tenant QuipuSynapseDetails.synapseUrl is null').to.be.below(500)); return; }",
             "let expected=[]; try{expected=JSON.parse(pm.collectionVariables.get('_streamNames')||'[]');}catch(e){}",
             "let landed={}; try{(pm.response.json().labels||[]).forEach(l=>{ if((l.count||0)>0) landed[l.label]=l.count; });}catch(e){}",
             "const missing=expected.filter(n=>!(n in landed));",
             "const a=parseInt(pm.collectionVariables.get('_ingAttempt')||'0');",
             "console.log('ingest verify attempt '+a+' landed='+JSON.stringify(landed)+' missing='+JSON.stringify(missing));",
             "const done=(expected.length>0 && missing.length===0) || a>=30;",
             "if(!done){ pm.collectionVariables.set('_ingAttempt', String(a+1)); postman.setNextRequest('24 Verify Tables Landed'); return; }",
             "pm.collectionVariables.unset('_ingAttempt');",
             "if(missing.length===0 && expected.length>0){ console.log('INGESTION VALIDATED: '+expected.length+' tables, rows='+JSON.stringify(landed)); }",
             "else { console.log('DATAFLOW FAILED: '+missing.length+'/'+expected.length+' stream(s) did not land: '+JSON.stringify(missing)); }",
             "// ANY stream that does not land rows fails this assertion -> whole dataflow marked FAILED",
             "// (non-zero newman exit; run_realm_full propagates it). Cleanup still runs (no _flow_failed).",
             "pm.test('24 all '+expected.length+' table(s) ingested rows (missing: '+JSON.stringify(missing)+')', () => { pm.expect(expected.length, 'expected tables').to.be.above(0); pm.expect(missing, 'tables with 0 rows').to.eql([]); });"],
            base="kg_base_url",
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "const a=parseInt(pm.collectionVariables.get('_ingAttempt')||'0');",
                "// re-fire ingestion once mid-way: re-generate streams then event/ingest (in-memory).",
                "if(a===8){ const rid=parseInt(pm.collectionVariables.get('realmId')); const txn=pm.environment.get('transform_base_url'); const app=pm.environment.get('app_base_url'); const hdr={'Authorization':'Bearer '+(pm.collectionVariables.get('access_token')||pm.environment.get('access_token')),'X-TENANT-ID':pm.environment.get('tenant_id'),'Content-Type':'application/json'};",
                "  pm.sendRequest({url:txn+'/streams/generate', method:'POST', header:hdr, body:{mode:'raw', raw:JSON.stringify({realmId:rid})}}, (e,r)=>{ let arr=[]; try{arr=r.json();}catch(x){} if(!Array.isArray(arr))arr=[]; arr.forEach(s=>{s.realmId=rid;}); const raw=JSON.stringify(arr); pm.sendRequest({url:app+'/atomicIngestStream/create-streams',method:'POST',header:hdr,body:{mode:'raw',raw:raw}},()=>{ pm.sendRequest({url:txn+'/event/ingest?truncate=false&seedSequenceFromJournal=false&forceIngest=true',method:'POST',header:hdr,body:{mode:'raw',raw:raw}},()=>{}); }); }); }",
                "if(a>0){ const t=Date.now(); while(Date.now()-t<4000){} }",
            ]),

        # ═══ PHASE 4: Cleanup (all steps honor skip_cleanup=true / run_realm_full.py --keep) ═══

        # Realm teardown mirrors UICore: delete realm -> remove Synapse namespace -> delete vector
        # collections (referenceName + referenceName_schema). Delete mode via `hardDelete` env:
        #   hardDelete=false (default) -> permanent=false (soft; UI's default deleteById).
        #   hardDelete=true            -> permanent=true (needs the memory_space migration V42-V44;
        #                                  otherwise the server 500s on the missing table).
        req("25 Del Realm", "DELETE", "/realm/{{realmId}}",
            [SKIP_CLEANUP_TEST, "pm.test('25 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE + [
                "const hard=String(pm.environment.get('hardDelete')||'false')==='true';",
                "pm.request.url=pm.environment.get('app_base_url')+'/realm/'+pm.collectionVariables.get('realmId')+'?permanent='+hard;",
            ]),
        req("25b Remove Namespace (Synapse)", "DELETE",
            "/synapse/namespace/remove?name={{realmReferenceName}}&permanent=true",
            [SKIP_CLEANUP_TEST, "pm.test('25b ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base="kg_base_url", prerequest=SKIP_CLEANUP_PRE),
        req("25c Del Vector Collection", "POST",
            "/vector-client/delete-collection?collectionName={{realmReferenceName}}",
            [SKIP_CLEANUP_TEST, "pm.test('25c ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base="kg_base_url", prerequest=SKIP_CLEANUP_PRE),
        req("25d Del Vector Collection (schema)", "POST",
            "/vector-client/delete-collection?collectionName={{realmReferenceName}}_schema",
            [SKIP_CLEANUP_TEST, "pm.test('25d ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base="kg_base_url", prerequest=SKIP_CLEANUP_PRE),
        req("26 Verify Del", "GET", "/realm/{{realmId}}",
            [SKIP_CLEANUP_TEST,
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.realmModel||b.data||b;",
             "const hard=String(pm.environment.get('hardDelete')||'false')==='true';",
             "pm.test('26 removed', () => pm.expect(pm.response.code===200 ? (hard ? false : !!d.deleted) : [400,404,500].includes(pm.response.code)).to.be.true);"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("27 Del Graph", "DELETE", "/schema-graph?schemaId={{schemaId}}",
            [SKIP_CLEANUP_TEST, "pm.test('27 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("28 Del Version", "DELETE", "/versions/delete?versionId={{versionId}}",
            [SKIP_CLEANUP_TEST, "pm.test('28 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("29 Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            [SKIP_CLEANUP_TEST, "pm.test('29 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("30 Del PG", "DELETE", "/datasource/{{pgDsId}}",
            [SKIP_CLEANUP_TEST, "pm.test('30 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("31 Del MySQL", "DELETE", "/datasource/{{mysqlDsId}}",
            [SKIP_CLEANUP_TEST, "pm.test('31 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("32 Del Maria", "DELETE", "/datasource/{{mariaDsId}}",
            [SKIP_CLEANUP_TEST, "pm.test('32 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("33 Del Oracle", "DELETE", "/datasource/{{oracleDsId}}",
            [SKIP_CLEANUP_TEST, "pm.test('33 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("34 Del Snow", "DELETE", "/datasource/{{snowDsId}}",
            [SKIP_CLEANUP_TEST, "pm.test('34 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("35 Del Mongo", "DELETE", "/datasource/{{mongoDsId}}",
            [SKIP_CLEANUP_TEST, "pm.test('35 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("36 Del CSV", "DELETE", "/datasource/{{csvDsId}}",
            [SKIP_CLEANUP_TEST, "pm.test('36 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),
        req("37 Del Excel", "DELETE", "/datasource/{{excelDsId}}",
            [SKIP_CLEANUP_TEST, "pm.test('37 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404,500]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE + [
                "// Excel DS is optional (created only with S3 creds); skip delete if it was never created",
                "if(!pm.collectionVariables.get('excelDsId')){ pm.request.url=pm.collectionVariables.get('_skip_url'); pm.request.method='GET'; pm.request.auth={type:'noauth'}; }",
            ]),

        req("99 Teardown", "DELETE", "/realm/{{realmId}}",
            [SKIP_CLEANUP_TEST,
             "pm.test('99 teardown', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False, prerequest=SKIP_CLEANUP_PRE + [
                "const hard=String(pm.environment.get('hardDelete')||'false')==='true';",
                "if(pm.collectionVariables.get('realmId')) pm.request.url=pm.environment.get('app_base_url')+'/realm/'+pm.collectionVariables.get('realmId')+'?permanent='+hard;",
            ]),
    ]

    col = build_collection(
        name="FLOW - Realm CRUD (8-DS Fabric)",
        description="Full realm with 8 datasource types: Postgres, MySQL, MariaDB, Oracle, Snowflake, Mongo, CSV, Excel.\n\n"
                    "Requires env-vars per DS type + S3 config for CSV/Excel.",
        folder_name="Realm CRUD (8-DS)",
        items=items,
        extra_variables=[{"key": k, "value": "", "type": "string"} for k in
            ds_vars + ["schemaName", "schemaId", "schemaPrefix", "versionId", "realmId",
                       "realmName", "realmReferenceName", "versionName", "streamId", "_allNodes", "_allLinks", "_ingestion_status",
                       "_dsMetaList", "_graphNodes", "_graphLinks", "_versionUri", "_versionUriEnc", "awsVersionId", "_streamCount", "_genStreams", "_streamNames",
                       "_nsAttempt", "_nsUp", "_ingAttempt", "_mongoShape",
                       "_entIdx", "_entCount",
                       "excelDsName", "_excelStagedKey", "_excelCols"]]
    )
    return write_flow("FLOW-Realm-CRUD.postman_collection.json", col)
