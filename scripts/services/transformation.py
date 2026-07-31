"""FLOW-Transformation-Connection: DB connection and query validation."""

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

        req("01 Test Connection", "POST", "/test-connection",
            ["pm.test('01 Test connection 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const s=JSON.stringify(b).toLowerCase();",
             "const ok=pm.response.code===200||b.success===true||b.connected===true||/success|connected/.test(s);",
             "pm.test('01 DB connected', () => { if(!ok){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01 Test Connection');} pm.expect(ok).to.be.true; });"],
            base=base, body=conn_body),

        req("02 Fetch Metadata", "POST", "/test-connection/metadata",
            ["pm.test('02 Metadata 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('02 has metadata', () => pm.expect(JSON.stringify(b).length).to.be.above(2));"],
            base=base, body=conn_body),

        req("03 Sample Records", "POST", "/test-connection/sample-records",
            ["pm.test('03 Sample 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));"],
            base=base, body=conn_body),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Transformation Service Connection",
        description="Validates Transformation Service: test-connection, metadata, sample-records.\n\nRequires DB config via `--env-var` (driverType, dbHost, dbPort, dbName, dbUser, dbPassword, dbSchema, driverClassName, aesRandomIV).",
        folder_name="Transformation Connection",
        items=items,
        extra_variables=[
            {"key": "driverType",      "value": "", "type": "string"},
            {"key": "dbHost",          "value": "", "type": "string"},
            {"key": "dbPort",          "value": "", "type": "string"},
            {"key": "dbName",          "value": "", "type": "string"},
            {"key": "dbUser",          "value": "", "type": "string"},
            {"key": "dbPassword",      "value": "", "type": "string"},
            {"key": "aesRandomIV",     "value": "", "type": "string"},
            {"key": "dbSchema",        "value": "", "type": "string"},
            {"key": "driverClassName", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Transformation-Connection.postman_collection.json", col)
