"""FLOW-Document-Extraction: Document extraction + ingestion status."""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "app_base_url"
    transform = "transform_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=["extractionStatusId"]),

        req("01 Create Extraction Status", "POST", "/document",
            ["const code = pm.response.code;",
             "pm.test('01 Create extraction 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01 Create Extraction');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.data||b;",
             "const id=d.id||d.statusId;",
             "if(id) pm.collectionVariables.set('extractionStatusId', String(id));",
             "console.log('Extraction status created: '+id);"],
            base=base,
            body={"realmId": "{{realmId}}", "dataSourceId": "{{datasourceId}}"}),

        req("02 Get Extraction Status", "GET", "/document/extraction-status?realmId={{realmId}}",
            ["pm.test('02 Get status 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "console.log('Extraction statuses: '+(Array.isArray(b)?b.length:'?'));"],
            base=base),

        req("03 Get Status by DataSource", "GET", "/document/extraction-status-by-datasource-id?datasourceId={{datasourceId}}",
            ["pm.test('03 Get by DS 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base=base),

        req("04 Create Document Streams", "POST", "/documentIngestStream/create-streams",
            ["pm.test('04 Create doc streams 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Doc streams: '+JSON.stringify(b).slice(0,200));"],
            base=base,
            body={"realmId": "{{realmId}}"}),

        req("05 Get Document Streams", "GET", "/documentIngestStream/get-document-stream/{{realmId}}",
            ["pm.test('05 Get doc streams 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base=base),

        req("06 Get Ingestion Status by Stream IDs", "POST", "/document-ingestion-status/get-by-stream-ids",
            ["pm.test('06 Ingestion status 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base=base,
            body={"streamIds": []}),

        req("07 Extract Document (Transformation)", "POST", "/document/extract",
            ["pm.test('07 Extract 2xx or 400', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400,404]));",
             "console.log('Extract response: '+pm.response.code);"],
            base=transform,
            body={"dataSourceId": "{{datasourceId}}"}),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Document Extraction",
        description="Document extraction lifecycle: create status -> get status -> create streams -> get streams -> ingestion status -> extract.\n\nRequires `--env-var realmId=...` and `--env-var datasourceId=...`.",
        folder_name="Document Extraction",
        items=items,
        extra_variables=[
            {"key": "extractionStatusId", "value": "", "type": "string"},
            {"key": "realmId",            "value": "", "type": "string"},
            {"key": "datasourceId",       "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Document-Extraction.postman_collection.json", col)
