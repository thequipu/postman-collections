"""FLOW-Schema-CRUD: Schema lifecycle with entities from datasource."""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import (create_ds_step, fetch_metadata_step, create_version_step,
                           fetch_graph_step, save_graph_step, SETUP_VARS, SETUP_CLEAR_VARS)


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=SETUP_CLEAR_VARS),

        # Setup: DS → Metadata
        create_ds_step("01a", base),
        fetch_metadata_step("01b"),

        # ── Schema CRUD ──
        req("02 List Schemas", "GET", "/schema",
            ["pm.test('02 200', () => pm.response.to.have.status(200));"], base=base),

        req("03 Create Schema", "POST", "/schema",
            ["const code=pm.response.code;",
             "pm.test('03 Schema 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','03');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.schemaModel||b.data||b;",
             "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
             "if(d.id||d.schemaId) pm.collectionVariables.set('schemaId', String(d.id||d.schemaId));",
             "console.log('Schema: '+(d.name||d.schemaName));"],
            base=base,
            body={"schemaName": "pm-flow-schema-{{$timestamp}}", "description": "Auto-created by FLOW"}),

        # Create version with entities from metadata
        create_version_step("03b", base),
        fetch_graph_step("03c", base),
        save_graph_step("03d", base),

        req("04 Get Schema by Name", "GET", "/schema/name?schemaName={{schemaName}}",
            ["pm.test('04 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.schemaModel||b.data||b;",
             "pm.test('04 name matches', () => pm.expect(String(d.name||d.schemaName||'')).to.eql(pm.collectionVariables.get('schemaName')));"],
            base=base),

        req("05 Update Schema", "PUT", "/schema",
            ["pm.test('05 200', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base, body={"id": 0},
            prerequest=[
                "pm.request.body.raw=JSON.stringify({id:parseInt(pm.collectionVariables.get('schemaId')),schemaName:pm.collectionVariables.get('schemaName'),description:'Updated by FLOW test'});",
            ]),

        req("06 Verify Update", "GET", "/schema/name?schemaName={{schemaName}}",
            ["pm.test('06 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.schemaModel||b.data||b;",
             "pm.test('06 has desc', () => pm.expect(String(d.description||'').length).to.be.above(0));"],
            base=base),

        # Cleanup
        req("07 Del Graph", "DELETE", "/schema-graph?prefix={{schemaName}}",
            ["pm.test('07 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("08 Del Version", "DELETE", "/versions/delete?versionId={{versionId}}",
            ["pm.test('08 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("09 Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('09 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("10 Del DS", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('10 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"], base=base),

        req("99 Teardown", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Schema CRUD",
        description="Schema lifecycle with entities from datasource.",
        folder_name="Schema CRUD", items=items, extra_variables=SETUP_VARS)
    return write_flow("FLOW-Schema-CRUD.postman_collection.json", col)
