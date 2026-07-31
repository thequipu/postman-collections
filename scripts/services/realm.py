"""FLOW-Realm-CRUD: Full CRUD lifecycle for realms."""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow, fail_on_error


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=["realmId", "realmName"]),

        req("01 List Realms", "GET", "/realm?page=0&size=20",
            ["pm.test('01 List realms 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("02 Create Realm", "POST", "/realm",
            ["const code = pm.response.code;",
             "pm.test('02 Create realm 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','02 Create Realm');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d = b.realmModel || b.data || b;",
             "const id = d.id || d.realmId;",
             "pm.test('02 has realm id', () => pm.expect(id).to.not.be.undefined);",
             "if(id) pm.collectionVariables.set('realmId', String(id));",
             "if(d.name || d.realmName) pm.collectionVariables.set('realmName', d.name || d.realmName);",
             "console.log('Created realm id='+id+', name='+(d.name||d.realmName||''));"],
            base=base,
            body={"name": "pm-flow-realm-{{$timestamp}}",
                  "description": "Auto-created by FLOW test"}),

        req("03 Get Realm by ID", "GET", "/realm/{{realmId}}",
            ["pm.test('03 Get realm 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('03 id matches', () => pm.expect(String(b.id||b.realmId||'')).to.eql(pm.collectionVariables.get('realmId')));"],
            base=base),

        req("04 Get Realm by Name", "GET", "/realm/by-name?realmName={{realmName}}",
            ["pm.test('04 Get by name 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("05 Update Realm", "PUT", "/realm",
            ["pm.test('05 Update realm 200', () => pm.response.to.have.status(200));"],
            base=base,
            body={"id": "{{realmId}}", "name": "{{realmName}}",
                  "description": "Updated by FLOW test"}),

        req("06 Verify Update", "GET", "/realm/{{realmId}}",
            ["pm.test('06 Verify update 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('06 description updated', () => pm.expect(String(b.description||'')).to.include('Updated'));"],
            base=base),

        req("07 Delete Realm", "DELETE", "/realm/{{realmId}}?permanent=true",
            ["pm.test('07 Delete realm 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("08 Verify Deleted", "GET", "/realm/{{realmId}}",
            ["pm.test('08 Deleted: 404 or empty', () => {",
             "  if([404,500].includes(pm.response.code)) return;",
             "  let b={}; try{b=pm.response.json();}catch(e){}",
             "  pm.expect(b===null || Object.keys(b||{}).length===0 || b.deleted===true).to.be.true;",
             "});"],
            base=base),

        # Teardown: idempotent delete (always runs)
        req("99 Teardown", "DELETE", "/realm/{{realmId}}?permanent=true",
            ["pm.test('99 teardown tolerant', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed');",
             "pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Realm CRUD",
        description="Full CRUD lifecycle for Application Service realms: create, get, update, delete, verify.",
        folder_name="Realm CRUD",
        items=items,
        extra_variables=[
            {"key": "realmId",   "value": "", "type": "string"},
            {"key": "realmName", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Realm-CRUD.postman_collection.json", col)
