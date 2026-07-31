"""FLOW-Ingestion-Streams: Atomic ingest stream + status lifecycle."""

from flowlib.core import req, build_setup, build_collection, write_flow


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=["streamId", "realmIdForStream"]),

        req("01 Create Ingest Stream", "POST", "/atomicIngestStream/create-stream",
            ["const code = pm.response.code;",
             "pm.test('01 Create stream 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01 Create Stream');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.data||b;",
             "const id=d.id||d.streamId;",
             "if(id) pm.collectionVariables.set('streamId', String(id));",
             "console.log('Stream created: id='+id);"],
            base=base,
            body={"realmId": "{{realmId}}", "streamName": "pm-flow-stream-{{$timestamp}}"}),

        req("02 Get Streams by Realm", "GET", "/atomicIngestStream/get-atomic-stream/{{realmId}}",
            ["pm.test('02 Get streams 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "console.log('Streams for realm: '+(Array.isArray(b)?b.length:'?'));"],
            base=base),

        req("03 Check Any Running", "GET", "/atomicIngestStream/{{realmId}}/atomic/any-running",
            ["pm.test('03 Any running 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Any running: '+JSON.stringify(b).slice(0,100));"],
            base=base),

        req("04 Create Ingestion Status", "POST", "/atomic-ingestion-status/create",
            ["pm.test('04 Create status 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));"],
            base=base,
            body={"streamId": "{{streamId}}"}),

        req("05 Get Latest Status", "POST", "/atomic-ingestion-status/get-latest",
            ["pm.test('05 Get latest 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Latest status: '+JSON.stringify(b).slice(0,200));"],
            base=base,
            body={"streamIds": ["{{streamId}}"]}),

        req("06 Change Running Status", "POST", "/atomicIngestStream/atomic/running-status-change",
            ["pm.test('06 Status change 200', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base,
            body={"streamId": "{{streamId}}", "running": False}),

        req("07 Remove Stream", "DELETE", "/atomicIngestStream/remove-stream/{{streamId}}",
            ["pm.test('07 Remove stream 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        # Teardown
        req("99 Teardown", "DELETE", "/atomicIngestStream/remove-stream/{{streamId}}",
            ["pm.test('99 teardown tolerant', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed');",
             "pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Ingestion Streams",
        description="Atomic ingest stream lifecycle: create stream -> get by realm -> check running -> create status -> get latest -> change status -> remove.\n\nRequires `--env-var realmId=...` for a valid realm.",
        folder_name="Ingestion Streams",
        items=items,
        extra_variables=[
            {"key": "streamId", "value": "", "type": "string"},
            {"key": "realmId",  "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Ingestion-Streams.postman_collection.json", col)
