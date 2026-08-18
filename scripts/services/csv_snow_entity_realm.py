"""FLOW-CSV-Snowflake-EntityLayer: focused 2-DS realm for the sample-data CSV + Snowflake,
built the product way (entities one-by-one via POST /entity) then realm + real ingestion.

Snowflake creds via snow_* env-vars; CSV (sample-data.csv on S3) via s3_* env-vars.
Any stream that does not land rows fails the flow.
"""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import create_entity_schema_graph_step


_SKIP = ["if(pm.environment.get('skip_cleanup')==='true'||pm.collectionVariables.get('skip_cleanup')==='true'){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }"]

_CLEAR = ["dsMetaName", "snowDsId", "snowCat", "csvDsId", "csvCat",
          "schemaName", "schemaId", "schemaPrefix", "versionId",
          "_dsMetaList", "_versionUri", "_versionUriEnc", "_entIdx", "_entCount",
          "realmId", "realmName", "realmReferenceName",
          "_streamCount", "_streamNames", "_nsAttempt", "_ingAttempt"]


def _capture_ds(step, label, id_var, cat_var):
    return [f"const code=pm.response.code;",
            f"pm.test('{step} {label} DS 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
            "let b={}; try{b=pm.response.json();}catch(e){}",
            "const d=b.dataSourceModel||b.data||b;",
            f"if(d.id||d.sourceId) pm.collectionVariables.set('{id_var}', String(d.id||d.sourceId));",
            f"if(d.dataCatalogName) pm.collectionVariables.set('{cat_var}', d.dataCatalogName);",
            f"console.log('{label} DS id='+(d.id||d.sourceId)+' cat='+(d.dataCatalogName||''));"]


def _fetch_into_metalist(step, label, cat_var, id_var, base):
    return req(f"{step} Fetch {label} Entities", "POST", "/metadata-graph/fetch-data-source",
        [f"const cat=pm.collectionVariables.get('{cat_var}')||'';",
         f"if(!cat){{ pm.test('{step} {label} skipped (DS not created)', ()=>{{}}); return; }}",
         "const code=pm.response.code;",
         f"pm.test('{step} {label} fetch 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         f"b._dsId = pm.collectionVariables.get('{id_var}');",
         "let all=[]; try{all=JSON.parse(pm.collectionVariables.get('_dsMetaList')||'[]');}catch(e){}",
         "all.push(b); pm.collectionVariables.set('_dsMetaList', JSON.stringify(all));",
         "const t=(b.hasTableEdges||[]).length;",
         f"pm.test('{step} {label} adds entities', () => {{ if(t===0){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step} 0 entities');}} pm.expect(t, '{label} produced 0 entities').to.be.above(0); }});",
         f"console.log('{label}: '+t+' entities');"],
        base=base, body={"uri": "{{" + cat_var + "}}"},
        prerequest=[
            f"const cat=pm.collectionVariables.get('{cat_var}')||'';",
            "if(!cat){ pm.request.method='GET'; pm.request.url=pm.collectionVariables.get('_skip_url')||pm.environment.get('app_base_url')+'/actuator/health'; }",
        ])


def _realm_ingest_steps(base):
    return [
        req("06 Create Realm", "POST", "/realm",
            ["const code=pm.response.code;",
             "pm.test('06 Realm 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','06');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.realmModel||b.data||b;",
             "if(d.id||d.realmId) pm.collectionVariables.set('realmId', String(d.id||d.realmId));",
             "if(d.name||d.realmName) pm.collectionVariables.set('realmName', d.name||d.realmName);",
             "if(d.referenceName) pm.collectionVariables.set('realmReferenceName', d.referenceName);",
             "console.log('Realm id='+(d.id||d.realmId)+' ref='+d.referenceName);"],
            base=base, body={"name": "x"},
            prerequest=[
                "pm.request.body.raw=JSON.stringify({name:'pm_flow_csvsnow_realm_'+Date.now(),description:'CSV+Snowflake fabric',schemaName:pm.collectionVariables.get('schemaName'),versionId:parseInt(pm.collectionVariables.get('versionId'))});",
            ]),
        req("07 Create Namespace (Synapse)", "POST", "/synapse/namespace/create",
            ["const code=pm.response.code;",
             "pm.test('07 namespace 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','07');} pm.expect(code).to.be.oneOf([200,201]); });"],
            base="kg_base_url", body={"name": "x"},
            prerequest=[
                "const historic=String(pm.environment.get('requiresHistoricIngest')||'true')!=='false';",
                "const vector=String(pm.environment.get('vectorIngestionRequired')||'true')!=='false';",
                "pm.request.body.raw=JSON.stringify({name:pm.collectionVariables.get('realmReferenceName'),schemaName:pm.collectionVariables.get('schemaName'),schemaVersion:'v1',requiresHistoricIngest:historic,type:null,vectorIngestionRequired:vector});",
            ]),
        req("08 Generate Ingest Streams", "POST", "/streams/generate",
            ["pm.test('08 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let arr=[]; try{arr=pm.response.json();}catch(e){} if(!Array.isArray(arr)) arr=[];",
             "pm.collectionVariables.set('_streamCount', String(arr.length));",
             "pm.collectionVariables.set('_streamNames', JSON.stringify(arr.map(s=>s.name).filter(Boolean)));",
             "console.log('streams generated: '+arr.length+(arr.length?(' e.g. '+arr[0].name):''));"],
            base="transform_base_url", body={"realmId": 0},
            prerequest=["pm.request.body.raw=JSON.stringify({realmId:parseInt(pm.collectionVariables.get('realmId'))});"]),
        req("09 Verify Streams Generated", "GET", "/actuator/health",
            ["pm.test('09 health', () => pm.response.to.have.status(200));",
             "const n=parseInt(pm.collectionVariables.get('_streamCount')||'0');",
             "pm.test('09 streams generated (>0)', () => pm.expect(n).to.be.above(0));"],
            base=base),
        req("10 Wait Namespace UP", "GET", "/synapse/namespace/status?name={{realmReferenceName}}",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "let st=''; try{st=(pm.response.json().status||'').toUpperCase();}catch(e){}",
             "const a=parseInt(pm.collectionVariables.get('_nsAttempt')||'0');",
             "console.log('namespace status attempt '+a+': '+st);",
             "if(st==='UP'){ pm.collectionVariables.unset('_nsAttempt'); }",
             "else if(a<18){ pm.collectionVariables.set('_nsAttempt', String(a+1)); postman.setNextRequest('10 Wait Namespace UP'); }",
             "else { pm.collectionVariables.unset('_nsAttempt'); }",
             "pm.test('10 namespace reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base="kg_base_url",
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "if(parseInt(pm.collectionVariables.get('_nsAttempt')||'0')>0){ const t=Date.now(); while(Date.now()-t<4000){} }",
            ]),
        req("11 Save + Run Ingestion", "POST", "/streams/generate",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "pm.test('11 regen 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let arr=[]; try{arr=pm.response.json();}catch(e){} if(!Array.isArray(arr)) arr=[];",
             "const rid=parseInt(pm.collectionVariables.get('realmId')); arr.forEach(s=>{ s.realmId=rid; });",
             "const app=pm.environment.get('app_base_url'); const txn=pm.environment.get('transform_base_url');",
             "const hdr={'Authorization':'Bearer '+(pm.collectionVariables.get('access_token')||pm.environment.get('access_token')),'X-TENANT-ID':pm.environment.get('tenant_id'),'Content-Type':'application/json'};",
             "const raw=JSON.stringify(arr);",
             "pm.sendRequest({url:app+'/atomicIngestStream/create-streams', method:'POST', header:hdr, body:{mode:'raw', raw:raw}}, (e1,r1)=>{",
             "  pm.test('11 create-streams 2xx', () => pm.expect(r1 && r1.code).to.be.oneOf([200,201]));",
             "  console.log('create-streams: '+(r1?r1.code:e1));",
             "  pm.sendRequest({url:txn+'/event/ingest?truncate=false&seedSequenceFromJournal=false&forceIngest=true', method:'POST', header:hdr, body:{mode:'raw', raw:raw}}, (e2,r2)=>{",
             "    pm.test('11 event/ingest 2xx', () => pm.expect(r2 && r2.code).to.be.oneOf([200,201,204]));",
             "    console.log('event/ingest: '+(r2?r2.code:e2));",
             "  });",
             "});"],
            base="transform_base_url", body={"realmId": 0},
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "pm.request.body.raw=JSON.stringify({realmId:parseInt(pm.collectionVariables.get('realmId'))});",
            ]),
        req("12 Verify Tables Landed", "GET", "/synapse/namespace/stats?namespace={{realmReferenceName}}",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "let expected=[]; try{expected=JSON.parse(pm.collectionVariables.get('_streamNames')||'[]');}catch(e){}",
             "let landed={}; try{(pm.response.json().labels||[]).forEach(l=>{ if((l.count||0)>0) landed[l.label]=l.count; });}catch(e){}",
             "const missing=expected.filter(n=>!(n in landed));",
             "const a=parseInt(pm.collectionVariables.get('_ingAttempt')||'0');",
             "console.log('ingest verify attempt '+a+' landed='+JSON.stringify(landed)+' missing='+JSON.stringify(missing));",
             "const done=(expected.length>0 && missing.length===0) || a>=18;",
             "if(!done){ pm.collectionVariables.set('_ingAttempt', String(a+1)); postman.setNextRequest('12 Verify Tables Landed'); return; }",
             "pm.collectionVariables.unset('_ingAttempt');",
             "if(missing.length===0 && expected.length>0){ console.log('INGESTION VALIDATED: '+expected.length+' tables, rows='+JSON.stringify(landed)); }",
             "else { console.log('DATAFLOW FAILED: '+missing.length+'/'+expected.length+' stream(s) did not land: '+JSON.stringify(missing)); }",
             "pm.test('12 all '+expected.length+' table(s) ingested rows (missing: '+JSON.stringify(missing)+')', () => { pm.expect(expected.length).to.be.above(0); pm.expect(missing, 'tables with 0 rows').to.eql([]); });"],
            base="kg_base_url",
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "if(parseInt(pm.collectionVariables.get('_ingAttempt')||'0')>0){ const t=Date.now(); while(Date.now()-t<4000){} }",
            ]),
    ]


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=_CLEAR),

        # ── Snowflake DS (JDBC; dbPort omitted — snowflake has none) ──
        req("01a Create Snowflake DS", "POST", "/datasource",
            _capture_ds("01a", "Snowflake", "snowDsId", "snowCat"),
            base=base, body={"name": "x"},
            prerequest=[
                "const g=k=>pm.variables.get(k)||pm.environment.get(k)||'';",
                "const body={name:'pm_flow_snow_'+Date.now(),driverType:'SNOWFLAKE',dbHostName:g('snow_dbHost'),"
                "databaseName:g('snow_dbName'),dbUserName:g('snow_dbUser'),dbPassword:g('snow_dbPassword'),"
                "aesRandomIV:g('snow_aesRandomIV'),dbSchema:g('snow_dbSchema'),"
                "driverClassName:g('snow_driverClassName')||'net.snowflake.client.jdbc.SnowflakeDriver',deleted:false};",
                "const port=String(g('snow_dbPort')).trim(); if(port!==''&&!isNaN(port)){ body.dbPort=parseInt(port); }",
                "pm.request.body.raw=JSON.stringify(body);",
            ]),
        _fetch_into_metalist("01b", "Snowflake", "snowCat", "snowDsId", base),

        # ── CSV DS (sample-data.csv on S3, columnDetails required or server NPE) ──
        req("01c Create CSV DS", "POST", "/datasource",
            _capture_ds("01c", "CSV", "csvDsId", "csvCat"),
            base=base, body={"name": "x"},
            prerequest=[
                "const g=k=>pm.environment.get(k)||pm.variables.get(k)||'';",
                "// columnDetails: from env-var s3_csv_columns (JSON) if provided, else default to sample-data.",
                "let cols=null; try{cols=JSON.parse(g('s3_csv_columns'));}catch(e){}",
                "if(!Array.isArray(cols)||!cols.length){ cols=["
                "{name:'id',type:'INTEGER',nullable:false,primaryKey:true,uniqueKey:true},"
                "{name:'name',type:'STRING',nullable:true,primaryKey:false,uniqueKey:false},"
                "{name:'email',type:'STRING',nullable:true,primaryKey:false,uniqueKey:false},"
                "{name:'age',type:'INTEGER',nullable:true,primaryKey:false,uniqueKey:false},"
                "{name:'salary',type:'DOUBLE',nullable:true,primaryKey:false,uniqueKey:false},"
                "{name:'department',type:'STRING',nullable:true,primaryKey:false,uniqueKey:false},"
                "{name:'hire_date',type:'STRING',nullable:true,primaryKey:false,uniqueKey:false},"
                "{name:'is_active',type:'STRING',nullable:true,primaryKey:false,uniqueKey:false}]; }",
                "const body={name:'pm_flow_csv_'+Date.now(),driverType:'CSV',"
                "bucket:g('s3_csv_bucket')||'quipu-api-tests',key:g('s3_csv_key')||'csvfiles',"
                "region:g('s3_region')||'eu-central-1',accessKey:g('s3_access_key'),secret:g('s3_secret_key'),deleted:false,"
                "files:[{key:g('s3_csv_file')||'csvfiles/sample-data.csv',columnDetails:cols}]};",
                "pm.request.body.raw=JSON.stringify(body);",
            ]),
        _fetch_into_metalist("01d", "CSV", "csvCat", "csvDsId", base),

        # ── Schema ──
        req("02 Create Schema", "POST", "/schema",
            ["const code=pm.response.code;",
             "pm.test('02 Schema 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','02');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.schemaModel||b.data||b;",
             "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
             "if(d.id||d.schemaId) pm.collectionVariables.set('schemaId', String(d.id||d.schemaId));",
             "if(d.prefix) pm.collectionVariables.set('schemaPrefix', d.prefix);"],
            base=base, body={"schemaName": "x"},
            prerequest=[
                "const sn='pm_flow_csvsnow_'+Date.now(); const prefix=sn.replace(/_/g,'-');",
                "pm.collectionVariables.set('schemaPrefix', prefix);",
                "pm.request.body.raw=JSON.stringify({schemaName:sn,prefix:prefix,description:'CSV+Snowflake entity-layer'});",
            ]),

        # ── Entities one-by-one (POST /entity) across BOTH DS → assemble → save ──
        *create_entity_schema_graph_step("03", base, ds_id_vars=("snowDsId", "csvDsId")),

        # ── Realm + ingestion ──
        *_realm_ingest_steps(base),

        # ── Cleanup (honors skip_cleanup) ──
        req("20 Del Realm", "DELETE", "/realm/{{realmId}}?permanent=false",
            ["pm.test('20 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, skip_on_fail=False, prerequest=_SKIP),
        req("21 Remove Namespace", "DELETE", "/synapse/namespace/remove?name={{realmReferenceName}}&permanent=true",
            ["pm.test('21 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base="kg_base_url", skip_on_fail=False, prerequest=_SKIP),
        req("22 Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('22 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, skip_on_fail=False, prerequest=_SKIP),
        req("23 Del Snowflake DS", "DELETE", "/datasource/{{snowDsId}}",
            ["pm.test('23 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, skip_on_fail=False, prerequest=_SKIP),
        req("99 Teardown (Del CSV DS)", "DELETE", "/datasource/{{csvDsId}}",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False, prerequest=_SKIP),
    ]

    col = build_collection(
        name="FLOW - CSV + Snowflake Entity-Layer Realm",
        description="Focused 2-DS realm (sample-data CSV + Snowflake) built via one-by-one POST /entity, "
                    "then real ingestion. Snowflake creds via snow_* env-vars; CSV via s3_* env-vars.",
        folder_name="CSV+Snowflake Entity Realm", items=items,
        extra_variables=[{"key": k, "value": "", "type": "string"} for k in _CLEAR])
    return write_flow("FLOW-CSV-Snowflake-EntityLayer.postman_collection.json", col)
