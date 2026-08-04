"""FLOW-Entity360-CRUD: Entity 360 configuration lifecycle."""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import full_setup_steps, cleanup_steps, SETUP_VARS, SETUP_CLEAR_VARS


def generate():
    base = "app_base_url"
    items = [
        build_setup(base, "/actuator/health",
                    clear_vars=SETUP_CLEAR_VARS + ["e360Id", "pathId"]),
        *full_setup_steps("01", "pm-flow-e360", include_realm=False, base=base),

        req("02 Create Entity360", "POST", "/entity-360?versionsId={{versionId}}",
            ["const code=pm.response.code;",
             "pm.test('02 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','02');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.data||b;",
             "if(d.id||d.entity360Id) pm.collectionVariables.set('e360Id', String(d.id||d.entity360Id));",
             "if(d.pathId) pm.collectionVariables.set('pathId', String(d.pathId));"],
            base=base, body={"namedEntity": "pm-flow-e360-{{$timestamp}}", "description": "FLOW"}),
        req("03 Get", "GET", "/entity-360?namedEntity=pm-flow-e360&versionsId={{versionId}}",
            ["pm.test('03 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("04 Get All", "GET", "/entity-360/all?versionsId={{versionId}}",
            ["pm.test('04 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("05 By VersionIds", "GET", "/entity-360/all/versionIds?versionsIds={{versionId}}",
            ["pm.test('05 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("06 ERFlow", "GET", "/entity-360/erflow-enabled",
            ["pm.test('06 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("07 Flow Info", "GET", "/entity-360/entity-360-flow-info?versionsId={{versionId}}&pathId={{pathId}}",
            ["pm.test('07 200|204|404', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("08 Vector Search", "GET", "/entity-360/vector-search-with-status?versionId={{versionId}}",
            ["pm.test('08 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("09 Get by ID", "GET", "/entity-360/entity360entity/{{e360Id}}",
            ["pm.test('09 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("10 By PathID", "GET", "/entity-360/entity360-path-id?pathId={{pathId}}",
            ["pm.test('10 200|204|404', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("11 Update", "PUT", "/entity-360?versionsId={{versionId}}",
            ["pm.test('11 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base, body={"id":0},
            prerequest=["pm.request.body.raw=JSON.stringify({id:parseInt(pm.collectionVariables.get('e360Id')),namedEntity:'pm-flow-e360-updated',description:'Updated'});"]),
        req("12 Delete", "DELETE", "/entity-360/{{e360Id}}",
            ["pm.test('12 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),

        *cleanup_steps(13, include_realm=False, base=base),
        req("99 Teardown", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]
    col = build_collection(name="FLOW - Entity360 CRUD", description="Entity360 with entities.", folder_name="Entity360 CRUD",
        items=items, extra_variables=SETUP_VARS + [{"key":k,"value":"","type":"string"} for k in ["e360Id","pathId"]])
    return write_flow("FLOW-Entity360-CRUD.postman_collection.json", col)
