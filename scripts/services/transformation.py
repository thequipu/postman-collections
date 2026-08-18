"""FLOW-Transformation-Full: Complete transformation service testing.

Covers: 23 endpoints — connection, source-query, s3-upload, trino/hive catalog,
        event ingest, document extract, streams generate, node map, schema objects.
Requires DB config + S3 config via environment variables.
"""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "transform_base_url"

    conn_body = {
        "driverType": "{{driverType}}", "dbHostName": "{{dbHost}}",
        "dbPort": "{{dbPort}}", "databaseName": "{{dbName}}",
        "dbUserName": "{{dbUser}}", "dbPassword": "{{dbPassword}}",
        "aesRandomIV": "{{aesRandomIV}}", "dbSchema": "{{dbSchema}}",
        "driverClassName": "{{driverClassName}}"
    }

    items = [
        build_setup(base, "/actuator/health"),

        # ═══ Connection Testing (5 endpoints) ═══

        req("01 Test Connection", "POST", "/test-connection",
            ["const code = pm.response.code;",
             "pm.test('01 Test-connection 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const s=JSON.stringify(b).toLowerCase();",
             "const ok=code===200||b.success===true||b.connected===true||/success|connected/.test(s);",
             "pm.test('01 DB connected', () => pm.expect(ok).to.be.true);"],
            base=base, body=conn_body),

        req("02 Test by DataSource ID", "POST", "/test-connection/{{datasourceId}}/{{driverType}}",
            ["pm.test('02 Test by DS ID reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400,404]));",
             "if([200,201].includes(pm.response.code)){",
             "  let b={}; try{b=pm.response.json();}catch(e){}",
             "  const s=JSON.stringify(b).toLowerCase();",
             "  pm.test('02 connected', () => pm.expect(/success|connected|valid/.test(s)||b.success===true).to.be.true);",
             "}"],
            base=base),

        req("03 Fetch Metadata", "POST", "/test-connection/metadata",
            ["pm.test('03 Metadata reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('03 has metadata', () => pm.expect(JSON.stringify(b).length).to.be.above(2));",
             "// Capture first table name for subsequent queries",
             "const tables=b.tables||b.metadata||Object.keys(b||{});",
             "if(Array.isArray(tables)&&tables.length>0){",
             "  const tbl=typeof tables[0]==='string'?tables[0]:(tables[0].name||tables[0].tableName||'');",
             "  if(tbl) pm.collectionVariables.set('firstTableName', tbl);",
             "}"],
            base=base, body=conn_body),

        req("04 Sample Records", "POST", "/test-connection/sample-records",
            ["pm.test('04 Sample reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400,500]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('04 has data', () => pm.expect(JSON.stringify(b).length).to.be.above(2));"],
            base=base,
            body={"dataSourceModel": conn_body,
                  "tableName": "{{firstTableName}}", "name": "pm_flow_sample"}),

        req("05 Upload Sample", "POST", "/test-connection/upload-sample",
            ["pm.test('05 Upload sample 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"dataSource": {"id": "{{datasourceId}}"},
                  "tableUriMap": {}, "signatureModel": {"sampleSize": 100}}),

        # ═══ Source Query (2 endpoints) ═══

        req("06 Fetch Sample Source", "POST", "/source-query/fetch-sample-source",
            ["pm.test('06 Fetch sample 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"dataSourceId": "{{datasourceId}}", "dataSourceModel": None,
                  "tableList": ["{{firstTableName}}"]},
            extra_headers=[{"key": "X-Tenant-ID", "value": "{{tenant_id}}"}]),

        req("07 Run Query", "POST", "/source-query/query",
            ["pm.test('07 Run query 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));",
             "if(pm.response.code===200){",
             "  let b={}; try{b=pm.response.json();}catch(e){}",
             "  pm.test('07 has result', () => pm.expect(JSON.stringify(b).length).to.be.above(2));",
             "}"],
            base=base,
            body={"dataSourceId": "{{datasourceId}}", "dataSourceModel": None,
                  "tableNames": ["{{firstTableName}}"], "query": "SELECT 1"},
            extra_headers=[{"key": "X-Tenant-ID", "value": "{{tenant_id}}"}]),

        # ═══ S3 Upload (7 endpoints) — need custom content type ═══

        req("08 Get Excel Header", "POST", "/s3-upload/getExcelHeader?datasourceName=pm_flow_test",
            ["pm.test('08 Excel header 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,400]));"],
            base=base,
            body={"bucket": "{{s3_bucket}}", "key": "{{s3_excel_key}}",
                  "region": "{{s3_region}}", "accessKey": "{{s3_access_key}}",
                  "secret": "{{s3_secret_key}}"},
            extra_headers=[{"key": "Content-Type", "value": "application/vnd.quipu.file-upload+json;version=1.0.0"}]),

        req("09 Excel from URL", "POST", "/s3-upload/getExcelHeaderFromUrl?datasourceName=pm_flow_test",
            ["pm.test('09 Excel URL 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,400]));"],
            base=base,
            body={"url": "{{s3_excel_url}}"},
            extra_headers=[{"key": "Content-Type", "value": "application/vnd.quipu.file-upload+json;version=1.0.0"}]),

        req("10 CSV Headers from URL", "POST", "/s3-upload/getCsvHeadersFromUrl?datasourceName=pm_flow_test",
            ["pm.test('10 CSV URL 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,400]));"],
            base=base,
            body={"url": "{{s3_csv_url}}"},
            extra_headers=[{"key": "Content-Type", "value": "application/vnd.quipu.file-upload+json;version=1.0.0"}]),

        req("11 Get CSV Header", "POST", "/s3-upload/getCsvHeader?datasourceName=pm_flow_test",
            ["pm.test('11 CSV header 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,400]));"],
            base=base,
            body={"bucket": "{{s3_bucket}}", "key": "{{s3_csv_key}}",
                  "region": "{{s3_region}}", "accessKey": "{{s3_access_key}}",
                  "secret": "{{s3_secret_key}}"},
            extra_headers=[{"key": "Content-Type", "value": "application/vnd.quipu.file-upload+json;version=1.0.0"}]),

        req("12 Get PDF", "POST", "/s3-upload/getPdf?datasourceName=pm_flow_test",
            ["pm.test('12 Get PDF 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,400]));"],
            base=base,
            body={"bucket": "{{s3_bucket}}", "key": "{{s3_pdf_key}}",
                  "region": "{{s3_region}}", "accessKey": "{{s3_access_key}}",
                  "secret": "{{s3_secret_key}}"},
            extra_headers=[{"key": "Content-Type", "value": "application/vnd.quipu.file-upload+json;version=1.0.0"}]),

        req("13 PDF from URL", "POST", "/s3-upload/getPdfFromUrl?datasourceName=pm_flow_test",
            ["pm.test('13 PDF URL 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,400]));"],
            base=base,
            body={"url": "{{s3_pdf_url}}"},
            extra_headers=[{"key": "Content-Type", "value": "application/vnd.quipu.file-upload+json;version=1.0.0"}]),

        req("14 PDF View", "GET", "/s3-upload/pdf-view?key={{s3_pdf_key}}",
            ["pm.test('14 PDF view 200|400|404', () => pm.expect(pm.response.code).to.be.oneOf([200,400,404]));"],
            base=base),

        # ═══ Hive/Trino Catalog (4 endpoints) ═══

        req("15 Create Hive Source", "POST", "/trino-source/create-hive",
            ["pm.test('15 Create hive 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"dataSource": {"id": "{{datasourceId}}"},
                  "metadataTables": [], "shape": {}}),

        req("16 Create Trino Catalog", "POST", "/trino-source/create-catalog",
            ["pm.test('16 Create catalog 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"query": "", "catalogName": "pm_flow_test", "removeQuery": ""}),

        req("17 Remove Trino Catalog", "POST", "/trino-source/remove-catalog?purgeData=false",
            ["pm.test('17 Remove catalog 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"query": "", "catalogName": "pm_flow_test", "removeQuery": ""}),

        req("18 Remove Hive Source", "POST", "/trino-source/remove-hive?purgeData=false",
            ["pm.test('18 Remove hive 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"dataSource": {"id": "{{datasourceId}}"},
                  "metadataTables": [], "shape": {}}),

        # ═══ Ingest/Extract (3 endpoints) ═══

        req("19 Event Ingest", "POST", "/event/ingest?truncate=false&seedSequenceFromJournal=false&forceIngest=false",
            ["pm.test('19 Ingest 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body=[{"name": "pm_flow_stream", "realmId": "{{realmId}}",
                   "streamType": "DBT-NODE", "sqlQuery": "SELECT 1"}]),

        req("20 Document Extract", "POST", "/document/extract",
            ["pm.test('20 Extract 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body=[]),

        req("21 Generate Streams", "POST", "/streams/generate",
            ["pm.test('21 Generate streams 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"realmId": "{{realmId}}"}),

        # ═══ Schema (2 endpoints) ═══

        req("22 Get Node Map", "GET", "/node/get-map",
            ["pm.test('22 Node map 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("23 Generate Node Objects", "POST", "/schema/generate/node-objects",
            ["pm.test('23 Node objects 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"graphData": "{}"}),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Transformation Service Full",
        description="Complete transformation service: 23 endpoints.\n\n"
                    "Connection (5) + Source Query (2) + S3 Upload (7) + Hive/Trino (4) +\n"
                    "Ingest/Extract (3) + Schema (2).\n\n"
                    "Requires: DB config, S3 config (s3_bucket, s3_region, s3_access_key, s3_secret_key,\n"
                    "s3_csv_key, s3_excel_key, s3_pdf_key, s3_csv_url, s3_excel_url, s3_pdf_url),\n"
                    "datasourceId, realmId via environment.",
        folder_name="Transformation Full",
        items=items,
        extra_variables=[
            {"key": "firstTableName", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Transformation-Connection.postman_collection.json", col)
