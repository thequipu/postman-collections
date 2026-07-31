"""FLOW-Schema-CRUD: Schema + Version lifecycle (creates a realm as dependency)."""

from flowlib.core import req, build_setup, build_collection, write_flow


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=["realmId", "schemaName", "versionId"]),

        req("01 Create Realm (dep)", "POST", "/realm",
            ["const code = pm.response.code;",
             "pm.test('01 Create realm 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01 Create Realm');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.realmModel||b.data||b; const id=d.id||d.realmId;",
             "if(id) pm.collectionVariables.set('realmId', String(id));",
             "console.log('Realm created id='+id);"],
            base=base,
            body={"name": "pm-flow-schema-realm-{{$timestamp}}", "description": "Schema flow dep"}),

        req("02 List Schemas", "GET", "/schema",
            ["pm.test('02 List schemas 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("03 Create Schema", "POST", "/schema",
            ["const code = pm.response.code;",
             "pm.test('03 Create schema 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','03 Create Schema');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.schemaModel||b.data||b;",
             "const name=d.name||d.schemaName;",
             "if(name) pm.collectionVariables.set('schemaName', name);",
             "console.log('Schema created: '+name);"],
            base=base,
            body={"name": "pm-flow-schema-{{$timestamp}}", "description": "Auto-created by FLOW test"}),

        req("04 Get Schema by Name", "GET", "/schema/name?schemaName={{schemaName}}",
            ["pm.test('04 Get schema 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("05 Delete Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('05 Delete schema 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("06 Delete Realm (cleanup)", "DELETE", "/realm/{{realmId}}?permanent=true",
            ["pm.test('06 Delete realm 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        # Teardown: idempotent cleanup (always runs)
        req("99 Teardown", "DELETE", "/realm/{{realmId}}?permanent=true",
            ["pm.test('99 teardown tolerant', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed');",
             "pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Schema CRUD",
        description="Schema lifecycle: create realm (dep) -> create schema -> get -> delete -> cleanup realm.",
        folder_name="Schema CRUD",
        items=items,
        extra_variables=[
            {"key": "realmId",    "value": "", "type": "string"},
            {"key": "schemaName", "value": "", "type": "string"},
            {"key": "versionId",  "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Schema-CRUD.postman_collection.json", col)
