"""FLOW-DataSource-Extended: Extended DS endpoints + CSV/Excel/PDF datasource via S3.

Covers: is-unique, get-by-ids, get-sources, get-by-type, graph-ids,
        CSV datasource (S3), Excel datasource (S3), PDF datasource (S3),
        update-signature, keys, bulk-delete.

Requires: DB config + S3 config (s3_bucket, s3_region, s3_access_key, s3_secret_key,
          s3_csv_key, s3_excel_key, s3_pdf_key) via env-var or secrets.
"""

from flowlib.core import req, build_setup, build_collection, write_flow


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health",
                    clear_vars=["dsId", "dsName", "csvDsId", "excelDsId", "pdfDsId"]),

        # ── Create a DB DataSource for basic testing ──

        req("01 Create DB DataSource", "POST", "/datasource",
            ["const code = pm.response.code;",
             "pm.test('01 Create DS 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "const id=d.id||d.sourceId;",
             "if(id) pm.collectionVariables.set('dsId', String(id));",
             "if(d.name) pm.collectionVariables.set('dsName', d.name);",
             "if(d.driverType) pm.collectionVariables.set('driverType', d.driverType);"],
            base=base,
            body={"name": "pm-flow-dsext-{{$timestamp}}",
                  "driverType": "{{driverType}}", "dbHostName": "{{dbHost}}",
                  "dbPort": "{{dbPort}}", "databaseName": "{{dbName}}",
                  "dbUserName": "{{dbUser}}", "dbPassword": "{{dbPassword}}",
                  "aesRandomIV": "{{aesRandomIV}}", "dbSchema": "{{dbSchema}}",
                  "driverClassName": "{{driverClassName}}", "deleted": False}),

        # ── Extended Read Endpoints ──

        req("02 Is Unique (false)", "GET", "/datasource/is-unique?name={{dsName}}",
            ["pm.test('02 Is unique 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("03 Get by IDs", "GET", "/datasource/ids?sourceIds={{dsId}}",
            ["pm.test('03 Get by IDs 200', () => pm.response.to.have.status(200));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "pm.test('03 has results', () => pm.expect(JSON.stringify(b).length).to.be.above(2));"],
            base=base),

        req("04 Get Sources", "GET", "/datasource/sources",
            ["pm.test('04 Get sources 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("05 Get by Type", "GET", "/datasource/get-dataSources-by-type/{{driverType}}",
            ["pm.test('05 By type 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("06 Get Graph IDs", "GET", "/datasource/get-graph-ids",
            ["pm.test('06 Graph IDs 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("07 Get by ID (alternate)", "GET", "/datasource/id?sourceId={{dsId}}",
            ["pm.test('07 Get DS alt 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "pm.test('07 id matches', () => pm.expect(String(d.id||d.sourceId||'')).to.eql(pm.collectionVariables.get('dsId')));"],
            base=base),

        req("08 Get DS (paginated)", "GET", "/datasource?page=0&size=20",
            ["pm.test('08 List DS 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('08 has paginated content', () => pm.expect(b.content||b.data).to.not.be.undefined);"],
            base=base),

        req("09 Update Signature Presence", "PUT", "/datasource/update-signature-presence",
            ["pm.test('09 Update sig presence 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base, body={"id": 0},
            prerequest=[
                "pm.request.body.raw = JSON.stringify({ id: parseInt(pm.collectionVariables.get('dsId')), signaturePresence: true });",
            ]),

        req("10 Update Signature", "POST", "/datasource/update-signature",
            ["pm.test('10 Update sig 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base, body={"id": 0},
            prerequest=[
                "pm.request.body.raw = JSON.stringify({ id: parseInt(pm.collectionVariables.get('dsId')) });",
            ]),

        req("11 Get Keys from S3", "POST", "/datasource/keys",
            ["pm.test('11 Keys 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"bucket": "{{s3_bucket}}", "prefix": "config/test-files/"}),

        # ── CSV DataSource via S3 ──

        req("12 Create CSV DataSource", "POST", "/datasource",
            ["pm.test('12 Create CSV DS 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "if(d.id) pm.collectionVariables.set('csvDsId', String(d.id));",
             "console.log('CSV DS created id='+d.id);"],
            base=base,
            body={"name": "pm-flow-csv-{{$timestamp}}", "driverType": "CSV",
                  "bucket": "{{s3_bucket}}", "key": "{{s3_csv_key}}",
                  "region": "{{s3_region}}", "accessKey": "{{s3_access_key}}",
                  "secret": "{{s3_secret_key}}", "deleted": False}),

        req("13 Verify CSV DS", "GET", "/datasource/id?sourceId={{csvDsId}}",
            ["pm.test('13 CSV DS 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "pm.test('13 driverType is CSV', () => pm.expect(String(d.driverType||'')).to.eql('CSV'));"],
            base=base),

        # ── Excel DataSource via S3 ──

        req("14 Create Excel DataSource", "POST", "/datasource",
            ["pm.test('14 Create Excel DS 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "if(d.id) pm.collectionVariables.set('excelDsId', String(d.id));",
             "console.log('Excel DS created id='+d.id);"],
            base=base,
            body={"name": "pm-flow-excel-{{$timestamp}}", "driverType": "EXCEL",
                  "bucket": "{{s3_bucket}}", "key": "{{s3_excel_key}}",
                  "region": "{{s3_region}}", "accessKey": "{{s3_access_key}}",
                  "secret": "{{s3_secret_key}}", "deleted": False}),

        req("15 Verify Excel DS", "GET", "/datasource/id?sourceId={{excelDsId}}",
            ["pm.test('15 Excel DS 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "pm.test('15 driverType is EXCEL', () => pm.expect(String(d.driverType||'')).to.eql('EXCEL'));"],
            base=base),

        # ── PDF DataSource via S3 ──

        req("16 Create PDF DataSource", "POST", "/datasource",
            ["pm.test('16 Create PDF DS 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "if(d.id) pm.collectionVariables.set('pdfDsId', String(d.id));",
             "console.log('PDF DS created id='+d.id);"],
            base=base,
            body={"name": "pm-flow-pdf-{{$timestamp}}", "driverType": "PDF",
                  "bucket": "{{s3_bucket}}", "key": "{{s3_pdf_key}}",
                  "region": "{{s3_region}}", "accessKey": "{{s3_access_key}}",
                  "secret": "{{s3_secret_key}}", "deleted": False}),

        req("17 Verify PDF DS", "GET", "/datasource/id?sourceId={{pdfDsId}}",
            ["pm.test('17 PDF DS 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "pm.test('17 driverType is PDF', () => pm.expect(String(d.driverType||'')).to.eql('PDF'));"],
            base=base),

        # ── Cleanup ──

        req("18 Delete DB DataSource", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('18 Delete DB DS 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("19 Delete CSV DataSource", "DELETE", "/datasource/{{csvDsId}}",
            ["pm.test('19 Delete CSV DS 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("20 Delete Excel DataSource", "DELETE", "/datasource/{{excelDsId}}",
            ["pm.test('20 Delete Excel DS 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("21 Delete PDF DataSource", "DELETE", "/datasource/{{pdfDsId}}",
            ["pm.test('21 Delete PDF DS 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("99 Teardown", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('99 teardown', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed');",
             "pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - DataSource Extended",
        description="Extended DataSource endpoints + CSV/Excel/PDF datasource creation via S3.\n\n"
                    "Requires: DB config + S3 config (s3_bucket, s3_region, s3_access_key, s3_secret_key,\n"
                    "s3_csv_key, s3_excel_key, s3_pdf_key) via env-var or secrets.",
        folder_name="DataSource Extended",
        items=items,
        extra_variables=[
            {"key": "dsId",       "value": "", "type": "string"},
            {"key": "dsName",     "value": "", "type": "string"},
            {"key": "csvDsId",    "value": "", "type": "string"},
            {"key": "excelDsId",  "value": "", "type": "string"},
            {"key": "pdfDsId",    "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-DataSource-Extended.postman_collection.json", col)
