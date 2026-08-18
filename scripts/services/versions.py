"""FLOW-Version-CRUD: Schema version lifecycle with real entities."""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import (create_ds_step, fetch_entities_step,
                           create_schema_graph_step, SETUP_VARS, SETUP_CLEAR_VARS)


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=SETUP_CLEAR_VARS),

        # Setup: DS → Fetch Entities → Schema (we test version CRUD via schema-graph)
        create_ds_step("01a", base),
        fetch_entities_step("01b", base),

        req("01c Create Schema", "POST", "/schema",
            ["const code=pm.response.code;",
             "pm.test('01c Schema 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01c');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.schemaModel||b.data||b;",
             "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
             "if(d.id||d.schemaId) pm.collectionVariables.set('schemaId', String(d.id||d.schemaId));",
             "if(d.prefix) pm.collectionVariables.set('schemaPrefix', d.prefix);"],
            base=base, body={"schemaName": "x"},
            prerequest=[
                "const schemaName='pm_flow_ver_schema_'+Date.now();",
                "const prefix=schemaName.replace(/_/g,'-');",
                "pm.collectionVariables.set('schemaPrefix', prefix);",
                "pm.request.body.raw=JSON.stringify({schemaName:schemaName,prefix:prefix,description:'Version flow dep'});",
            ]),

        # ── Create version + schema graph correctly (version+MinIO, UI/Neo4j, verify) ──
        *create_schema_graph_step("02", base),

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
                "pm.request.body.raw=JSON.stringify({id:vid,versionId:vid,description:'Updated by FLOW',dataSourceIds:dsId?[dsId]:[],defaultVersion:true,latest:true,versionLocked:false,deleted:false});",
            ]),

        req("06 Verify Update", "GET", "/versions?versionId={{versionId}}",
            ["pm.test('06 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.data||b;",
             "pm.test('06 has desc', () => pm.expect(String(d.description||'').length).to.be.above(0));"],
            base=base),

        req("07 Unlock Version", "PUT", "/versions/veriosn-unlock",
            ["pm.test('07 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base, body={"id": 0},
            prerequest=["pm.request.body.raw=JSON.stringify({id:parseInt(pm.collectionVariables.get('versionId'))});"]),

        req("08 Delete Version", "DELETE", "/versions/delete?versionId={{versionId}}",
            ["pm.test('08 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),

        # Cleanup
        req("09 Del Graph", "DELETE", "/schema-graph?prefix={{schemaPrefix}}",
            ["pm.test('09 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("10 Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('10 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("11 Del DS", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('11 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"], base=base),

        req("99 Teardown", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Version CRUD",
        description="Version lifecycle with real entities from datasource.",
        folder_name="Version CRUD", items=items, extra_variables=SETUP_VARS)
    return write_flow("FLOW-Version-CRUD.postman_collection.json", col)
