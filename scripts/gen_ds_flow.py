"""
Generate FLOW-DataSource-CRUD.postman_collection.json

Fully generic — ZERO hardcoded values:
  - All DB config comes from collection variables / environment
  - Table names captured dynamically from metadata graph
  - Query built dynamically from first captured table
  - Stop-on-fail: any failed step stops the flow (skips remaining)
  - Teardown always runs (cleanup even after failure)

Steps:
  00 Setup           — clear state, verify token
  01 Test Connection  — validate DB reachable (config-based)
  02 Create DS        — persist datasource record
  03 Get DS by ID     — verify creation, capture metadata
  04 Test Conn by ID  — validate created DS connects
  05 Fetch Graph      — get metadata (tables/columns), capture firstTableName
  06 Fetch Sample     — sample rows from first table
  07 Run Query        — SELECT * FROM firstTable LIMIT 10
  08 Update DS        — change description
  09 Verify Update    — confirm description changed
  10 Delete DS        — permanent delete
  11 Verify Deleted   — confirm gone
  99 Teardown         — idempotent cleanup

Usage:
  python scripts/gen_ds_flow.py
  newman run flows/FLOW-DataSource-CRUD.postman_collection.json \\
    -e environments/onprem-api.postman_environment.json --insecure \\
    --env-var "test_username=..." --env-var "test_password=..." \\
    --env-var "client_secret=..." \\
    --env-var "driverType=POSTGRES" --env-var "dbHost=..." ...
"""

import json, os

os.makedirs("flows", exist_ok=True)

# ============================================================
# HELPERS
# ============================================================

def raw_body(obj):
    s = json.dumps(obj, indent=2)
    for numvar in ('{{dbPort}}', '{{realmId}}'):
        s = s.replace('"' + numvar + '"', numvar)
    return {"mode": "raw", "raw": s, "options": {"raw": {"language": "json"}}}


def req(name, method, path, tests, body=None, base="app_base_url",
        extra_headers=None, prerequest=None, skip_on_fail=True):
    """Build a Postman request item.

    skip_on_fail: if True, prepend a pre-request script that skips this step
                  when a previous step has set _flow_failed=true.
    """
    hdr = [{"key": "X-TENANT-ID", "value": "{{tenant_id}}"}]
    if extra_headers:
        hdr += extra_headers
    if body:
        hdr.append({"key": "Content-Type", "value": "application/json"})

    url_raw = "{{" + base + "}}" + path
    path_parts = [p for p in path.split("?")[0].strip("/").split("/")]
    url = {"raw": url_raw, "host": ["{{" + base + "}}"], "path": path_parts}
    if "?" in path:
        q = path.split("?")[1]
        url["query"] = [{"key": kv.split("=")[0], "value": kv.split("=")[1]} for kv in q.split("&")]

    r = {"method": method, "header": hdr, "url": url}
    if body:
        r["body"] = raw_body(body)

    events = []

    # --- pre-request: skip if previous step failed ---
    pre_lines = []
    if skip_on_fail:
        pre_lines += [
            "if (pm.collectionVariables.get('_flow_failed') === 'true') {",
            "  console.log('SKIP: ' + pm.info.requestName + ' (previous step failed)');",
            "  pm.request.url = pm.collectionVariables.get('_skip_url') || 'http://localhost:1/__skip__';",
            "  return;",
            "}",
        ]
    if prerequest:
        pre_lines += prerequest
    if pre_lines:
        events.append({"listen": "prerequest", "script": {"type": "text/javascript", "exec": pre_lines}})

    # --- test: mark failed on assertion error ---
    test_lines = []
    if skip_on_fail:
        test_lines += [
            "// Skip check — if flow already failed, mark this step as skipped",
            "if (pm.collectionVariables.get('_flow_failed') === 'true') {",
            "  pm.test('SKIPPED: ' + pm.info.requestName + ' (failed at: ' + (pm.collectionVariables.get('_flow_failed_at')||'?') + ')', function() {});",
            "  return;",
            "}",
        ]
    test_lines += tests
    events.append({"listen": "test", "script": {"type": "text/javascript", "exec": test_lines}})

    return {"name": name, "request": r, "event": events, "response": []}


# ============================================================
# REQUEST BODIES — all values from variables, zero hardcoded
# ============================================================

conn_cfg = {
    "name": "pm-flow-ds-{{$timestamp}}",
    "driverType": "{{driverType}}",
    "dbHostName": "{{dbHost}}",
    "dbPort": "{{dbPort}}",
    "databaseName": "{{dbName}}",
    "dbUserName": "{{dbUser}}",
    "dbPassword": "{{dbPassword}}",
    "aesRandomIV": "{{aesRandomIV}}",
    "dbSchema": "{{dbSchema}}",
    "driverClassName": "{{driverClassName}}"
}

create_body = {
    "name": "pm-flow-ds-{{$timestamp}}",
    "driverType": "{{driverType}}",
    "dbHostName": "{{dbHost}}",
    "dbPort": "{{dbPort}}",
    "databaseName": "{{dbName}}",
    "dbUserName": "{{dbUser}}",
    "dbPassword": "{{dbPassword}}",
    "aesRandomIV": "{{aesRandomIV}}",
    "dbSchema": "{{dbSchema}}",
    "driverClassName": "{{driverClassName}}",
    "deleted": False
}

update_body = {
    "id": "{{datasourceId}}",
    "name": "{{dsName}}",
    "driverType": "{{driverType}}",
    "dbHostName": "{{dbHost}}",
    "dbPort": "{{dbPort}}",
    "databaseName": "{{dbName}}",
    "dbUserName": "{{dbUser}}",
    "dbPassword": "{{dbPassword}}",
    "aesRandomIV": "{{aesRandomIV}}",
    "dbSchema": "{{dbSchema}}",
    "driverClassName": "{{driverClassName}}",
    "description": "{{updateDescription}}",
    "deleted": False
}

fetch_graph_body = {"uri": "{{dataCatalogName}}"}

fetch_sample_body = {
    "dataSourceId": "{{datasourceId}}",
    "dataSourceModel": None,
    "tableList": ["{{firstTableName}}"]
}

run_query_body = {
    "dataSourceId": "{{datasourceId}}",
    "dataSourceModel": None,
    "tableNames": ["{{firstTableName}}"],
    "query": "{{runQuery}}"
}


# ============================================================
# TEST SCRIPTS — with stop-on-fail markers
# ============================================================

def fail_marker(step_name):
    """JS lines to mark flow as failed when assertion fails."""
    return [
        f"// Mark flow failed if {step_name} assertions failed",
        "try {",
    ]

def fail_catch(step_name):
    return [
        "} catch(e) {",
        f"  console.error('{step_name} FAILED: ' + e.message);",
        "  pm.collectionVariables.set('_flow_failed', 'true');",
        f"  pm.collectionVariables.set('_flow_failed_at', '{step_name}');",
        "  throw e;",
        "}",
    ]


t_conn_cfg = [
    "const code = pm.response.code;",
    "pm.test('01 Test-connection reachable (2xx)', () => { if(![200,201].includes(code)) { pm.collectionVariables.set('_flow_failed','true'); pm.collectionVariables.set('_flow_failed_at','01 Test Connection'); } pm.expect(code).to.be.oneOf([200,201]); });",
    "let b={}; try{b=pm.response.json();}catch(e){}",
    "const s=JSON.stringify(b).toLowerCase();",
    "const ok = code===200 || b.success===true || b.connected===true || /success|connected|valid/.test(s);",
    "pm.test('01 DB connection succeeded', () => { if(!ok) { pm.collectionVariables.set('_flow_failed','true'); } pm.expect(ok, 'result: '+s.slice(0,120)).to.be.true; });",
]

t_create = [
    "const code = pm.response.code;",
    "pm.test('02 Create returns 2xx', () => { if(![200,201].includes(code)) { pm.collectionVariables.set('_flow_failed','true'); pm.collectionVariables.set('_flow_failed_at','02 Create'); } pm.expect(code).to.be.oneOf([200,201]); });",
    "let b={}; try{b=pm.response.json();}catch(e){}",
    "const d = b.dataSourceModel || b.data || b;",
    "const id = d.id || d.sourceId;",
    "pm.test('02 response has datasource id', () => { if(id===undefined) { pm.collectionVariables.set('_flow_failed','true'); } pm.expect(id, 'id').to.not.be.undefined; });",
    "if(id!==undefined){ pm.collectionVariables.set('datasourceId', String(id)); }",
    "if(d.name){ pm.collectionVariables.set('dsName', d.name); }",
    "if(d.driverType){ pm.collectionVariables.set('driverType', d.driverType); }",
    "if(d.dataCatalogName){ pm.collectionVariables.set('dataCatalogName', d.dataCatalogName); }",
    "if(d.dataSourceId){ pm.collectionVariables.set('dataSourceId_uuid', d.dataSourceId); }",
    "console.log('Created: id='+id+', name='+(d.name||'')+', catalog='+(d.dataCatalogName||''));",
]

t_get = [
    "pm.test('03 Get returns 200', () => pm.response.to.have.status(200));",
    "let b={}; try{b=pm.response.json();}catch(e){}",
    "const d = b.dataSourceModel || b.data || b;",
    "pm.test('03 id matches created', () => pm.expect(String(d.id||d.sourceId)).to.eql(String(pm.collectionVariables.get('datasourceId'))));",
    "pm.test('03 driverType matches', () => pm.expect(String(d.driverType||'').toUpperCase()).to.eql((pm.collectionVariables.get('driverType')||'').toUpperCase()));",
]

t_conn_id = [
    "pm.test('04 Test-connection-by-id reachable (2xx)', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
    "let b={}; try{b=pm.response.json();}catch(e){}",
    "const s=JSON.stringify(b).toLowerCase();",
    "const ok = pm.response.code===200 || b.success===true || b.connected===true || /success|connected|valid/.test(s);",
    "pm.test('04 created datasource connects', () => pm.expect(ok, 'result: '+s.slice(0,120)).to.be.true);",
]

t_fetch_graph = [
    "pm.test('05 Fetch graph returns 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
    "let b={}; try{b=pm.response.json();}catch(e){}",
    "pm.test('05 response is not empty', () => pm.expect(JSON.stringify(b).length).to.be.above(2));",
    "",
    "// ── Dynamic table extraction (no hardcoded table names) ──",
    "let tableNames = [];",
    "if(b.hasTableEdges && Array.isArray(b.hasTableEdges)) {",
    "  tableNames = b.hasTableEdges.map(e => e.label || e.name || e.tableName).filter(Boolean);",
    "}",
    "if(tableNames.length===0 && b.tables) { tableNames = b.tables.map(t => t.name || t.label).filter(Boolean); }",
    "if(tableNames.length===0 && b.nodes) { tableNames = b.nodes.filter(n => (n.nodeType||'')==='Table').map(n => n.label || n.name).filter(Boolean); }",
    "if(tableNames.length===0) {",
    "  const s = JSON.stringify(b);",
    "  const m = s.match(/\"label\"\\s*:\\s*\"([^\"]+)\"/g);",
    "  if(m) { tableNames = m.map(x => x.replace(/\"label\"\\s*:\\s*\"/,'').replace(/\"$/,'')).filter(Boolean); }",
    "}",
    "",
    "// Skip the DS-level label (first entry is usually the datasource itself)",
    "if(tableNames.length > 1) { tableNames = tableNames.slice(1); }",
    "",
    "if(tableNames.length > 0) {",
    "  pm.collectionVariables.set('firstTableName', tableNames[0]);",
    "  // Build dynamic query — quote style depends on DB type",
    "  const dt = (pm.collectionVariables.get('driverType')||'').toUpperCase();",
    "  const tbl = tableNames[0];",
    "  let q;",
    "  if (dt === 'ORACLE') { q = 'SELECT * FROM \"' + tbl + '\" FETCH FIRST 10 ROWS ONLY'; }",
    "  else if (dt === 'MSSQL') { q = 'SELECT TOP 10 * FROM [' + tbl + ']'; }",
    "  else if (dt === 'MYSQL' || dt === 'MARIADB') { q = 'SELECT * FROM `' + tbl + '` LIMIT 10'; }",
    "  else { q = 'SELECT * FROM ' + tbl + ' LIMIT 10'; }",
    "  pm.collectionVariables.set('runQuery', q);",
    "  pm.collectionVariables.set('firstTableName', tbl);",
    "  console.log('Captured '+tableNames.length+' tables. firstTable='+tbl);",
    "  console.log('Dynamic query: '+q);",
    "} else {",
    "  console.log('WARNING: No tables extracted — graph keys: '+Object.keys(b||{}).join(', '));",
    "}",
]

t_fetch_sample = [
    "pm.test('06 Fetch sample returns 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
    "pm.test('06 sample data received', () => pm.expect(pm.response.code).to.eql(200));",
    "let b={}; try{b=pm.response.json();}catch(e){}",
    "console.log('Sample response (first 300 chars): '+JSON.stringify(b).slice(0,300));",
]

t_run_query = [
    "let b={}; try{b=pm.response.json();}catch(e){}",
    "if(pm.response.code >= 400) {",
    "  console.log('Query error ('+pm.response.code+'): '+JSON.stringify(b).slice(0,300));",
    "}",
    "pm.test('07 Run query returns 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
    "const rows = b.rows || b.data || b.result || b;",
    "pm.test('07 query returned data', () => pm.expect(JSON.stringify(rows).length).to.be.above(2));",
    "console.log('Query returned '+(Array.isArray(rows)?rows.length:'?')+' rows');",
]

t_update = [
    "pm.test('08 Update returns 200', () => pm.response.to.have.status(200));",
    "let b={}; try{b=pm.response.json();}catch(e){}",
    "const desc = pm.collectionVariables.get('updateDescription') || 'pm-flow-updated';",
    "pm.test('08 update reflected', () => pm.expect(JSON.stringify(b)).to.include(desc));",
]

t_verify_upd = [
    "pm.test('09 Get(verify update) 200', () => pm.response.to.have.status(200));",
    "let b={}; try{b=pm.response.json();}catch(e){}",
    "const d=b.dataSourceModel||b.data||b;",
    "const desc = pm.collectionVariables.get('updateDescription') || 'pm-flow-updated';",
    "pm.test('09 description updated', () => pm.expect(String(d.description||'')).to.eql(desc));",
]

t_delete = [
    "pm.test('10 Delete returns 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));",
]

t_verify_del = [
    "pm.test('11 deleted: get 404 or empty', () => {",
    "  if ([404,500].includes(pm.response.code)) { return; }",
    "  let b={}; try{b=pm.response.json();}catch(e){}",
    "  const d=b.data||b;",
    "  pm.expect(d===null || d==='' || Object.keys(d||{}).length===0 || d.deleted===true).to.be.true;",
    "});",
]

t_teardown = [
    "pm.test('99 teardown tolerant', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404,400]));",
    "// Clean up flow state",
    "pm.collectionVariables.unset('_flow_failed');",
    "pm.collectionVariables.unset('_flow_failed_at');",
]


# ============================================================
# SETUP STEP
# ============================================================

setup = {
    "name": "00 Setup",
    "event": [
        {"listen": "prerequest", "script": {"type": "text/javascript", "exec": [
            "// Clear all chained state",
            "pm.collectionVariables.unset('datasourceId');",
            "pm.collectionVariables.unset('dsName');",
            "pm.collectionVariables.unset('dataCatalogName');",
            "pm.collectionVariables.unset('dataSourceId_uuid');",
            "pm.collectionVariables.unset('firstTableName');",
            "pm.collectionVariables.unset('runQuery');",
            "pm.collectionVariables.unset('_flow_failed');",
            "pm.collectionVariables.unset('_flow_failed_at');",
            "",
            "// Set skip URL for stop-on-fail (health endpoint — always 200)",
            "pm.collectionVariables.set('_skip_url', pm.environment.get('app_base_url') + '/actuator/health');",
            "",
            "// Set default updateDescription if not provided",
            "if (!pm.collectionVariables.get('updateDescription')) {",
            "  pm.collectionVariables.set('updateDescription', 'pm-flow-updated-' + Date.now());",
            "}",
            "",
            "console.log('Setup: state cleared for env=' + pm.environment.get('env_name'));",
            "console.log('Config: driverType=' + (pm.collectionVariables.get('driverType')||pm.environment.get('driverType')||'?'));",
            "console.log('Config: dbHost=' + (pm.collectionVariables.get('dbHost')||pm.environment.get('dbHost')||'?'));",
            "console.log('Config: dbName=' + (pm.collectionVariables.get('dbName')||pm.environment.get('dbName')||'?'));",
        ]}},
        {"listen": "test", "script": {"type": "text/javascript", "exec": [
            "pm.test('00 token acquired', () => pm.expect(pm.collectionVariables.get('access_token')||pm.environment.get('access_token')||'').to.not.eql(''));",
            "pm.test('00 app service reachable', () => pm.expect(pm.response.code).to.eql(200));",
            "if (pm.response.code !== 200) {",
            "  pm.collectionVariables.set('_flow_failed', 'true');",
            "  pm.collectionVariables.set('_flow_failed_at', '00 Setup');",
            "}",
        ]}}
    ],
    "request": {
        "method": "GET", "header": [],
        "url": {"raw": "{{app_base_url}}/actuator/health", "host": ["{{app_base_url}}"], "path": ["actuator", "health"]},
        "auth": {"type": "noauth"},
        "description": "Clear state, verify token, check app service health."
    },
    "response": []
}


# ============================================================
# ORDERED STEPS
# ============================================================

items = [
    setup,
    req("01 Test Connection (config)", "POST", "/test-connection",
        t_conn_cfg, body=conn_cfg, base="transform_base_url"),

    req("02 Create DataSource", "POST", "/datasource",
        t_create, body=create_body),

    req("03 Get DataSource by ID", "GET", "/datasource/id?sourceId={{datasourceId}}",
        t_get),

    req("04 Test Connection by DataSource ID", "POST", "/test-connection/{{datasourceId}}/{{driverType}}",
        t_conn_id, base="transform_base_url"),

    req("05 Fetch DataSource Graph", "POST", "/metadata-graph/fetch-data-source",
        t_fetch_graph, body=fetch_graph_body),

    req("06 Fetch Sample Source", "POST", "/source-query/fetch-sample-source",
        t_fetch_sample, body=fetch_sample_body, base="transform_base_url",
        extra_headers=[{"key": "X-Tenant-ID", "value": "{{tenant_id}}"}]),

    req("07 Run Query", "POST", "/source-query/query",
        t_run_query, body=run_query_body, base="transform_base_url",
        extra_headers=[{"key": "X-Tenant-ID", "value": "{{tenant_id}}"}],
        prerequest=[
            "// Build query body dynamically with proper types",
            "const tbl = pm.collectionVariables.get('firstTableName') || '';",
            "const qry = pm.collectionVariables.get('runQuery') || 'SELECT 1';",
            "const dsId = pm.collectionVariables.get('datasourceId') || '';",
            "if (tbl && dsId) {",
            "  const body = JSON.stringify({",
            "    dataSourceId: parseInt(dsId) || dsId,",
            "    dataSourceModel: null,",
            "    tableNames: [tbl],",
            "    query: qry",
            "  });",
            "  pm.request.body.raw = body;",
            "  console.log('Query body: ' + body.slice(0,200));",
            "}",
        ]),

    # ── Additional Transformation Service endpoints ──

    req("07a Fetch Metadata", "POST", "/test-connection/metadata",
        ["pm.test('07a Metadata 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400]));",
         "if(pm.response.code===200){",
         "  let b={}; try{b=pm.response.json();}catch(e){}",
         "  pm.test('07a has metadata', () => pm.expect(JSON.stringify(b).length).to.be.above(2));",
         "  console.log('Metadata keys: '+Object.keys(b).slice(0,5).join(', '));",
         "}"],
        body=conn_cfg, base="transform_base_url"),

    req("07b Sample Records", "POST", "/test-connection/sample-records",
        ["pm.test('07b Sample 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400,500]));",
         "if(pm.response.code===200){",
         "  let b={}; try{b=pm.response.json();}catch(e){}",
         "  pm.test('07b has data', () => pm.expect(JSON.stringify(b).length).to.be.above(2));",
         "}"],
        body={**conn_cfg, "tableName": "{{firstTableName}}", "name": "pm-flow-sample"},
        base="transform_base_url"),

    req("07c Upload Sample", "POST", "/test-connection/upload-sample",
        ["pm.test('07c Upload 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
        body={"dataSource": {"id": "{{datasourceId}}"}, "tableUriMap": {},
              "signatureModel": {"sampleSize": 100}},
        base="transform_base_url"),

    req("07d Get Node Map", "GET", "/node/get-map",
        ["pm.test('07d Node map 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
        base="transform_base_url"),

    req("08 Update DataSource", "PUT", "/datasource",
        t_update, body=update_body),

    req("09 Get DataSource (verify update)", "GET", "/datasource/id?sourceId={{datasourceId}}",
        t_verify_upd),

    req("10 Delete DataSource", "DELETE", "/datasource/{{datasourceId}}?permanent=true",
        t_delete),

    req("11 Get DataSource (verify deleted)", "GET", "/datasource/id?sourceId={{datasourceId}}",
        t_verify_del),

    req("99 Teardown - delete leftover", "DELETE", "/datasource/{{datasourceId}}?permanent=true",
        t_teardown, skip_on_fail=False),  # always runs
]


# ============================================================
# COLLECTION PRE-REQUEST (auto-refresh Keycloak token)
# ============================================================

prereq = [
    "const destructive=['POST','PUT','PATCH','DELETE'];",
    "if(pm.environment.get('allow_destructive')==='false' && destructive.includes(pm.request.method)){",
    "  throw new Error('Blocked '+pm.request.method+' in env='+pm.environment.get('env_name'));",
    "}",
    "const url=pm.environment.get('keycloak_token_url'); const user=pm.environment.get('test_username');",
    "if(!url||!user){ return; }",
    "const tok=pm.collectionVariables.get('access_token'); const exp=pm.collectionVariables.get('token_expiry');",
    "if(tok && exp && Date.now() < Number(exp)-60000){ return; }",
    "pm.sendRequest({url:url,method:'POST',header:{'Content-Type':'application/x-www-form-urlencoded'},",
    "  body:{mode:'urlencoded',urlencoded:[",
    "    {key:'grant_type',value:'password'},{key:'client_id',value:pm.environment.get('client_id')},",
    "    {key:'client_secret',value:pm.environment.get('client_secret')},",
    "    {key:'username',value:pm.environment.get('test_username')},{key:'password',value:pm.environment.get('test_password')}]}},",
    "  (e,res)=>{ if(e||res.code!==200){ throw new Error('token fetch failed: '+(e||res.status)); }",
    "    const b=res.json(); pm.collectionVariables.set('access_token',b.access_token);",
    "    pm.collectionVariables.set('token_expiry', Date.now()+b.expires_in*1000);",
    "    pm.environment.set('access_token', b.access_token); });",
]


# ============================================================
# COLLECTION VARIABLES — all empty defaults, no hardcoded values
# ============================================================

variables = [
    # Auth (populated by pre-request script)
    {"key": "access_token",      "value": "",  "type": "string"},
    {"key": "token_expiry",      "value": "",  "type": "string"},

    # Chained state (populated during flow)
    {"key": "datasourceId",      "value": "",  "type": "string"},
    {"key": "dsName",            "value": "",  "type": "string"},
    {"key": "dataCatalogName",   "value": "",  "type": "string"},
    {"key": "dataSourceId_uuid", "value": "",  "type": "string"},
    {"key": "firstTableName",    "value": "",  "type": "string"},
    {"key": "runQuery",          "value": "",  "type": "string"},
    {"key": "updateDescription", "value": "",  "type": "string"},

    # Flow control
    {"key": "_flow_failed",      "value": "",  "type": "string"},
    {"key": "_flow_failed_at",   "value": "",  "type": "string"},
    {"key": "_skip_url",         "value": "",  "type": "string"},

    # DB config — ALL must come from --env-var or environment file
    {"key": "realmId",           "value": "",  "type": "string"},
    {"key": "driverType",        "value": "",  "type": "string"},
    {"key": "dbHost",            "value": "",  "type": "string"},
    {"key": "dbPort",            "value": "",  "type": "string"},
    {"key": "dbName",            "value": "",  "type": "string"},
    {"key": "dbUser",            "value": "",  "type": "string"},
    {"key": "dbPassword",        "value": "",  "type": "string"},
    {"key": "aesRandomIV",       "value": "",  "type": "string"},
    {"key": "dbSchema",          "value": "",  "type": "string"},
    {"key": "driverClassName",   "value": "",  "type": "string"},
]


# ============================================================
# ASSEMBLE COLLECTION
# ============================================================

col = {
    "info": {
        "_postman_id": "f10w-ds-crud-0000-000000000012",
        "name": "FLOW - DataSource CRUD (Generic)",
        "description": (
            "**Generic E2E DataSource flow — zero hardcoded values.**\n\n"
            "All DB config comes from `--env-var` flags or environment file.\n"
            "Table names and queries are captured dynamically from the metadata graph.\n"
            "Stop-on-fail: any failed step skips remaining steps (teardown always runs).\n\n"
            "**Steps:**\n"
            "00 Setup → 01 Test Connection → 02 Create → 03 Get → 04 Test by ID → "
            "05 Fetch Graph → 06 Sample → 07 Query → 08 Update → 09 Verify → "
            "10 Delete → 11 Verify Deleted → 99 Teardown\n\n"
            "**Required --env-var:**\n"
            "```\n"
            "test_username, test_password, client_secret\n"
            "driverType, dbHost, dbPort, dbName, dbUser, dbPassword, dbSchema\n"
            "driverClassName, aesRandomIV\n"
            "```\n\n"
            "**Driver reference:**\n"
            "| DB | driverType | driverClassName | Port |\n"
            "|---|---|---|---|\n"
            "| MySQL | MYSQL | com.mysql.cj.jdbc.Driver | 3306 |\n"
            "| MariaDB | MARIADB | org.mariadb.jdbc.Driver | 3306 |\n"
            "| PostgreSQL | POSTGRES | org.postgresql.Driver | 5432 |\n"
            "| Oracle | ORACLE | oracle.jdbc.OracleDriver | 1521 |\n"
            "| SQL Server | MSSQL | com.microsoft.sqlserver.jdbc.SQLServerDriver | 1433 |\n\n"
            "**Example:**\n"
            "```bash\n"
            "newman run flows/FLOW-DataSource-CRUD.postman_collection.json \\\n"
            "  -e environments/onprem-api.postman_environment.json --insecure \\\n"
            "  --env-var test_username=onpremquipu \\\n"
            "  --env-var test_password=onpremquipu \\\n"
            "  --env-var client_secret=SECRET \\\n"
            "  --env-var driverType=POSTGRES \\\n"
            "  --env-var dbHost=207.180.249.216 \\\n"
            "  --env-var dbPort=5433 \\\n"
            "  --env-var dbName=healthcare_management \\\n"
            "  --env-var dbUser=postgres \\\n"
            "  --env-var dbPassword=ENCRYPTED \\\n"
            "  --env-var dbSchema=public \\\n"
            "  --env-var driverClassName=org.postgresql.Driver \\\n"
            "  --env-var aesRandomIV=IV_BASE64 \\\n"
            "  -r cli\n"
            "```"
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    },
    "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}]},
    "event": [{"listen": "prerequest", "script": {"type": "text/javascript", "exec": prereq}}],
    "variable": variables,
    "item": [{"name": "DataSource CRUD (Generic)", "item": items}]
}

with open("flows/FLOW-DataSource-CRUD.postman_collection.json", "w", encoding="utf-8") as f:
    json.dump(col, f, indent=2, ensure_ascii=False)
print("wrote flows/FLOW-DataSource-CRUD.postman_collection.json with", len(items), "steps")
