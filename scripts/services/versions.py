"""FLOW-Version-CRUD: Schema version lifecycle with entities."""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import create_ds_step, fetch_metadata_step, create_schema_step, SETUP_VARS, SETUP_CLEAR_VARS


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=SETUP_CLEAR_VARS),

        # Setup: DS → Metadata → Schema (no version/graph/realm — we test version CRUD)
        create_ds_step("01a", base),
        fetch_metadata_step("01b"),
        create_schema_step("01c", "pm-flow-ver", base),

        # ── Version CRUD ──

        req("02 Create Version", "POST", "/versions/create?schemaName={{schemaName}}",
            ["const code=pm.response.code;",
             "pm.test('02 Version 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','02');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.data||b;",
             "pm.test('02 has id', () => pm.expect(d.id||d.versionId).to.not.be.undefined);",
             "if(d.id||d.versionId) pm.collectionVariables.set('versionId', String(d.id||d.versionId));",
             "console.log('Version id='+(d.id||d.versionId));"],
            base=base, body={"versionName": "v1"},
            prerequest=[
                "const dsId=parseInt(pm.collectionVariables.get('dsId'));",
                "let nodes=[]; try{nodes=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]');}catch(e){}",
                "pm.request.body.raw=JSON.stringify({versionName:'pm-flow-version-'+Date.now(),description:'Auto-created by FLOW',dataSourceIds:dsId?[dsId]:[],nodes:nodes,links:[],defaultVersion:true,latest:true,versionLocked:false,deleted:false});",
            ]),

        req("03 Get Version", "GET", "/versions?versionId={{versionId}}",
            ["pm.test('03 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.data||b;",
             "pm.test('03 id matches', () => pm.expect(String(d.id||d.versionId||'')).to.eql(pm.collectionVariables.get('versionId')));"],
            base=base),

        req("04 Get Version LB", "GET", "/versions/lb?versionId={{versionId}}",
            ["pm.test('04 200', () => pm.response.to.have.status(200));"], base=base),

        req("05 Update Version", "PUT", "/versions/update",
            ["pm.test('05 200', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base, body={"id": 0},
            prerequest=[
                "const vid=parseInt(pm.collectionVariables.get('versionId'));",
                "const dsId=parseInt(pm.collectionVariables.get('dsId'));",
                "pm.request.body.raw=JSON.stringify({id:vid,versionId:vid,description:'Updated by FLOW test',dataSourceIds:dsId?[dsId]:[],defaultVersion:true,latest:true,versionLocked:false,deleted:false});",
            ]),

        req("06 Verify Update", "GET", "/versions?versionId={{versionId}}",
            ["pm.test('06 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.data||b;",
             "pm.test('06 desc check', () => { const desc=String(d.description||''); pm.expect(desc.length).to.be.above(0); });"],
            base=base),

        req("07 Unlock Version", "PUT", "/versions/veriosn-unlock",
            ["pm.test('07 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base, body={"id": 0},
            prerequest=["pm.request.body.raw=JSON.stringify({id:parseInt(pm.collectionVariables.get('versionId'))});"]),

        req("08 Delete Version", "DELETE", "/versions/delete?versionId={{versionId}}",
            ["pm.test('08 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),

        # Cleanup
        req("09 Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('09 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("10 Del DS", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('10 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"], base=base),

        req("99 Teardown", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('99 teardown', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Version CRUD",
        description="Version lifecycle with entities from datasource.\nDS → Metadata → Schema → Version CRUD.",
        folder_name="Version CRUD",
        items=items,
        extra_variables=SETUP_VARS
    )
    return write_flow("FLOW-Version-CRUD.postman_collection.json", col)
