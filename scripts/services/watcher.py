"""FLOW-Watcher-CRUD: Watcher lifecycle on Application Service."""

from flowlib.core import req, build_setup, build_collection, write_flow


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=["watcherId"]),

        req("01 Create Watcher", "POST", "/watcher",
            ["const code = pm.response.code;",
             "pm.test('01 Create watcher 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01 Create Watcher');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.data||b;",
             "const id=d.id||d.watcherId;",
             "if(id) pm.collectionVariables.set('watcherId', String(id));",
             "console.log('Watcher created: '+id);"],
            base=base,
            body={"name": "pm-flow-watcher-{{$timestamp}}", "namespace": "{{realm}}"}),

        req("02 List Watchers", "GET", "/watcher",
            ["pm.test('02 List watchers 200', () => pm.response.to.have.status(200));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "console.log('Watchers: '+(Array.isArray(b)?b.length:'?'));"],
            base=base),

        req("03 Get Watcher by ID", "GET", "/watcher/{{watcherId}}",
            ["pm.test('03 Get watcher 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('03 has watcher data', () => pm.expect(JSON.stringify(b).length).to.be.above(2));"],
            base=base),

        req("04 Pause Watcher", "PUT", "/watcher/{{watcherId}}/pause",
            ["pm.test('04 Pause 200', () => pm.expect(pm.response.code).to.be.oneOf([200,202]));"],
            base=base),

        req("05 Resume Watcher", "PUT", "/watcher/{{watcherId}}/resume",
            ["pm.test('05 Resume 200', () => pm.expect(pm.response.code).to.be.oneOf([200,202]));"],
            base=base),

        req("06 Delete Watcher", "DELETE", "/watcher/{{watcherId}}",
            ["pm.test('06 Delete watcher 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        # Teardown
        req("99 Teardown", "DELETE", "/watcher/{{watcherId}}",
            ["pm.test('99 teardown tolerant', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed');",
             "pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Watcher CRUD",
        description="Watcher lifecycle: create -> list -> get -> pause -> resume -> delete.\n\nUses `{{realm}}` from environment for watcher namespace.",
        folder_name="Watcher CRUD",
        items=items,
        extra_variables=[
            {"key": "watcherId", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Watcher-CRUD.postman_collection.json", col)
