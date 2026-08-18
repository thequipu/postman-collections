"""FLOW-Namespace-CRUD: Namespace + source management."""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import (full_setup_steps, cleanup_steps, realm_delete_prereq,
                           SETUP_VARS, SETUP_CLEAR_VARS)


def generate():
    base = "app_base_url"
    items = [
        build_setup(base, "/actuator/health",
                    clear_vars=SETUP_CLEAR_VARS + ["nsId", "nsName", "sourceId"]),
        *full_setup_steps("01", "pm_flow_ns", include_realm=True, base=base),

        req("02 List All", "GET", "/namespace/all",
            ["pm.test('02 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("03 Create Namespace", "POST", "/namespace?realmId={{realmId}}",
            ["const code=pm.response.code;",
             "pm.test('03 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','03');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.data||b;",
             "if(d.id||d.namespaceId) pm.collectionVariables.set('nsId', String(d.id||d.namespaceId));",
             "if(d.name||d.namespaceName) pm.collectionVariables.set('nsName', d.name||d.namespaceName);"],
            base=base, body={"name": "pm_flow_ns_{{$timestamp}}", "description": "FLOW"}),
        req("04 Get by Realm", "GET", "/namespace?realmId={{realmId}}&page=0&size=20",
            ["pm.test('04 200', () => pm.response.to.have.status(200));"], base=base),
        req("05 Get by ID", "GET", "/namespace/{{nsId}}?realmId={{realmId}}",
            ["pm.test('05 200', () => pm.response.to.have.status(200));"], base=base),
        req("06 Context", "GET", "/namespace/{{nsId}}/context",
            ["pm.test('06 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("07 By Name Context", "GET", "/namespace/by-name/{{nsName}}/context",
            ["pm.test('07 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("08 Add Source", "POST", "/namespace/{{nsId}}/source",
            ["pm.test('08 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.data||b;",
             "if(d.id||d.sourceId) pm.collectionVariables.set('sourceId', String(d.id||d.sourceId));"],
            base=base, body={"dataSourceId": 0, "name": "pm_flow_source"},
            prerequest=["pm.request.body.raw=JSON.stringify({dataSourceId:parseInt(pm.collectionVariables.get('dsId')),name:'pm_flow_source'});"]),
        req("09 List Sources", "GET", "/namespace/{{nsId}}/source",
            ["pm.test('09 200', () => pm.response.to.have.status(200));"], base=base),
        req("10 By Name Source", "GET", "/namespace/by-name/{{nsName}}/source",
            ["pm.test('10 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("11 Remove Source", "DELETE", "/namespace/{{nsId}}/source/{{sourceId}}",
            ["pm.test('11 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("12 Delete Namespace", "DELETE", "/namespace/{{nsId}}?realmId={{realmId}}",
            ["pm.test('12 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),

        *cleanup_steps(13, include_realm=True, base=base),
        req("99 Teardown", "DELETE", "/realm/{{realmId}}",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False, prerequest=realm_delete_prereq()),
    ]
    col = build_collection(name="FLOW - Namespace CRUD", description="Namespace with entities.", folder_name="Namespace CRUD",
        items=items, extra_variables=SETUP_VARS + [{"key":k,"value":"","type":"string"} for k in ["nsId","nsName","sourceId"]])
    return write_flow("FLOW-Namespace-CRUD.postman_collection.json", col)
