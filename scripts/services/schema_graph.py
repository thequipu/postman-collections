"""FLOW-SchemaGraph-CRUD: Schema graph operations with entities."""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import (create_ds_step, fetch_metadata_step, create_schema_step,
                           create_version_step, fetch_graph_step, SETUP_VARS, SETUP_CLEAR_VARS)


def generate():
    base = "app_base_url"
    items = [
        build_setup(base, "/actuator/health", clear_vars=SETUP_CLEAR_VARS),
        create_ds_step("01a", base),
        fetch_metadata_step("01b"),
        create_schema_step("01c", "pm-flow-sg", base),
        create_version_step("01d", base),
        fetch_graph_step("01e", base),

        # ── Schema Graph CRUD (test the graph endpoints) ──
        req("02 Save Graph", "POST", "/schema-graph",
            ["pm.test('02 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));"],
            base=base, body={"versionUri":"","nodes":[],"links":[]},
            prerequest=[
                "let n=[]; let l=[];",
                "try{n=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]');}catch(e){}",
                "try{l=JSON.parse(pm.collectionVariables.get('_graphLinks')||'[]');}catch(e){}",
                "console.log('Saving: '+n.length+' entities');",
                "pm.request.body.raw=JSON.stringify({versionUri:pm.collectionVariables.get('schemaName')+'Version#v',nodes:n,links:l,schemaName:pm.collectionVariables.get('schemaName')});"]),
        req("03 Get Graph", "GET", "/schema-graph?versionUri={{schemaName}}Version%23v",
            ["pm.test('03 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("04 Get by Name", "GET", "/schema-graph/by-name?schemaName={{schemaName}}",
            ["pm.test('04 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("05 Update Graph", "PUT", "/schema-graph",
            ["pm.test('05 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base, body={"versionUri":"","nodes":[],"links":[]},
            prerequest=[
                "let n=[]; try{n=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]');}catch(e){}",
                "n.push({id:'test_update',label:'updated_by_flow',type:'entity'});",
                "pm.request.body.raw=JSON.stringify({versionUri:pm.collectionVariables.get('schemaName')+'Version#v',nodes:n,links:[],schemaName:pm.collectionVariables.get('schemaName')});"]),
        req("06 Copy Version", "POST", "/schema-graph/copy-version",
            ["pm.test('06 200|201|400', () => pm.expect(pm.response.code).to.be.oneOf([200,201,204,400]));"],
            base=base, body={"sourceVersionUri":"","targetVersionName":"v2"},
            prerequest=["pm.request.body.raw=JSON.stringify({sourceVersionUri:pm.collectionVariables.get('schemaName')+'Version#v',targetVersionName:'pm-flow-sg-copy-'+Date.now()});"]),
        req("07 Delete Graph", "DELETE", "/schema-graph?prefix={{schemaName}}",
            ["pm.test('07 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),

        # Cleanup
        req("08 Del Version", "DELETE", "/versions/delete?versionId={{versionId}}",
            ["pm.test('08 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("09 Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('09 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("10 Del DS", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('10 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"], base=base),
        req("99 Teardown", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]
    col = build_collection(name="FLOW - Schema Graph CRUD", description="Schema graph with entities.", folder_name="Schema Graph CRUD",
        items=items, extra_variables=SETUP_VARS)
    return write_flow("FLOW-SchemaGraph-CRUD.postman_collection.json", col)
