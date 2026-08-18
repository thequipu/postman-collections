"""FLOW-CSV-EntityLayer: single CSV datasource realm, built the product way (entities one-by-one
via POST /entity), then real ingestion. Isolates CSV to test ingestion on its own.

CSV (S3) via s3_* env-vars; columns via s3_csv_columns (JSON) or default sample-data.
"""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import create_entity_schema_graph_step
from services.csv_snow_entity_realm import _capture_ds, _fetch_into_metalist, _realm_ingest_steps, _SKIP

_CLEAR = ["dsMetaName", "csvDsId", "csvCat", "schemaName", "schemaId", "schemaPrefix", "versionId",
          "_dsMetaList", "_versionUri", "_versionUriEnc", "_entIdx", "_entCount",
          "realmId", "realmName", "realmReferenceName", "_streamCount", "_streamNames",
          "_nsAttempt", "_ingAttempt"]


def generate():
    base = "app_base_url"
    items = [
        build_setup(base, "/actuator/health", clear_vars=_CLEAR),

        # ── CSV DS (S3; columnDetails from s3_csv_columns or default sample-data) ──
        req("01a Create CSV DS", "POST", "/datasource",
            _capture_ds("01a", "CSV", "csvDsId", "csvCat"),
            base=base, body={"name": "x"},
            prerequest=[
                "const g=k=>pm.environment.get(k)||pm.variables.get(k)||'';",
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
                "region:g('s3_region')||'ap-south-1',accessKey:g('s3_access_key'),secret:g('s3_secret_key'),deleted:false,"
                "files:[{key:g('s3_csv_file')||'csvfiles/sample-data.csv',columnDetails:cols}]};",
                "pm.request.body.raw=JSON.stringify(body);",
            ]),
        _fetch_into_metalist("01b", "CSV", "csvCat", "csvDsId", base),

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
                "const sn='pm_flow_csv_'+Date.now(); const prefix=sn.replace(/_/g,'-');",
                "pm.collectionVariables.set('schemaPrefix', prefix);",
                "pm.request.body.raw=JSON.stringify({schemaName:sn,prefix:prefix,description:'CSV-only entity-layer'});",
            ]),

        # ── Entities one-by-one → assemble → save ──
        *create_entity_schema_graph_step("03", base, ds_id_vars=("csvDsId",)),

        # ── Realm + ingestion ──
        *_realm_ingest_steps(base),

        # ── Cleanup ──
        req("20 Del Realm", "DELETE", "/realm/{{realmId}}?permanent=false",
            ["pm.test('20 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, skip_on_fail=False, prerequest=_SKIP),
        req("21 Remove Namespace", "DELETE", "/synapse/namespace/remove?name={{realmReferenceName}}&permanent=true",
            ["pm.test('21 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base="kg_base_url", skip_on_fail=False, prerequest=_SKIP),
        req("22 Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('22 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, skip_on_fail=False, prerequest=_SKIP),
        req("99 Teardown (Del CSV DS)", "DELETE", "/datasource/{{csvDsId}}",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False, prerequest=_SKIP),
    ]
    col = build_collection(
        name="FLOW - CSV-only Entity-Layer Realm",
        description="Single CSV datasource realm via one-by-one POST /entity, then real ingestion. "
                    "CSV via s3_* env-vars; columns via s3_csv_columns (JSON).",
        folder_name="CSV Entity Realm", items=items,
        extra_variables=[{"key": k, "value": "", "type": "string"} for k in _CLEAR])
    return write_flow("FLOW-CSV-EntityLayer.postman_collection.json", col)
