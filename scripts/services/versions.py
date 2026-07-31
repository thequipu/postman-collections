"""FLOW-Version-CRUD: Schema version lifecycle."""

from flowlib.core import req, build_setup, build_collection, write_flow


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=["realmId", "schemaName", "versionId"]),

        # Create realm + schema as dependencies
        req("01 Create Realm (dep)", "POST", "/realm",
            ["const code = pm.response.code;",
             "pm.test('01 Create realm 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01 Create Realm');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.realmModel||b.data||b;",
             "if(d.id||d.realmId) pm.collectionVariables.set('realmId', String(d.id||d.realmId));"],
            base=base,
            body={"name": "pm-flow-ver-realm-{{$timestamp}}", "description": "Version flow dep"}),

        req("02 Create Schema (dep)", "POST", "/schema",
            ["const code = pm.response.code;",
             "pm.test('02 Create schema 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','02 Create Schema');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.schemaModel||b.data||b;",
             "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
             "console.log('Schema: '+(d.name||d.schemaName));"],
            base=base,
            body={"name": "pm-flow-ver-schema-{{$timestamp}}", "description": "Version flow dep"}),

        req("03 Create Version", "POST", "/versions/create",
            ["const code = pm.response.code;",
             "pm.test('03 Create version 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','03 Create Version');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.data||b;",
             "const id=d.id||d.versionId;",
             "if(id) pm.collectionVariables.set('versionId', String(id));",
             "console.log('Version created: '+id);"],
            base=base,
            body={"schemaName": "{{schemaName}}", "versionName": "pm-flow-version-{{$timestamp}}",
                  "description": "Auto-created by FLOW test"}),

        req("04 Get Version", "GET", "/versions?versionId={{versionId}}",
            ["pm.test('04 Get version 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('04 has version data', () => pm.expect(JSON.stringify(b).length).to.be.above(2));"],
            base=base),

        req("05 Update Version", "PUT", "/versions/update",
            ["pm.test('05 Update version 200', () => pm.response.to.have.status(200));"],
            base=base,
            body={"id": "{{versionId}}", "description": "Updated by FLOW test"}),

        req("06 Delete Version", "DELETE", "/versions/delete?versionId={{versionId}}",
            ["pm.test('06 Delete version 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        # Cleanup deps
        req("07 Delete Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('07 Delete schema 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("08 Delete Realm", "DELETE", "/realm/{{realmId}}?permanent=true",
            ["pm.test('08 Delete realm 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        # Teardown
        req("99 Teardown", "DELETE", "/realm/{{realmId}}?permanent=true",
            ["pm.test('99 teardown tolerant', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed');",
             "pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Version CRUD",
        description="Schema version lifecycle: create realm (dep) -> create schema (dep) -> create version -> get -> update -> delete -> cleanup.",
        folder_name="Version CRUD",
        items=items,
        extra_variables=[
            {"key": "realmId",    "value": "", "type": "string"},
            {"key": "schemaName", "value": "", "type": "string"},
            {"key": "versionId",  "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Version-CRUD.postman_collection.json", col)
