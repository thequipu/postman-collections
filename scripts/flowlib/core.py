"""Core utilities for generating Postman Flow collections.

Extracted from gen_ds_flow.py — provides req(), build_setup(), build_teardown(),
build_collection(), and write_flow().
"""

import json
import os

from .auth import keycloak_prerequest


def raw_body(obj):
    """Serialize a dict to Postman raw JSON body, unquoting numeric template vars."""
    s = json.dumps(obj, indent=2)
    for numvar in ('{{dbPort}}', '{{realmId}}'):
        s = s.replace('"' + numvar + '"', numvar)
    return {"mode": "raw", "raw": s, "options": {"raw": {"language": "json"}}}


def req(name, method, path, tests, body=None, base="app_base_url",
        extra_headers=None, prerequest=None, skip_on_fail=True, noauth=False):
    """Build a Postman request item with skip-on-fail support.

    Args:
        name:           Step name (e.g. '01 Get All Tenants')
        method:         HTTP method
        path:           URL path after base (e.g. '/realm?page=0&size=20')
        tests:          List of JS test script lines
        body:           Request body dict (optional)
        base:           Environment variable for base URL (default: app_base_url)
        extra_headers:  Additional headers list (optional)
        prerequest:     Additional pre-request JS lines (optional)
        skip_on_fail:   If True, skip this step when a previous step failed
        noauth:         If True, disable bearer auth for this request
    """
    hdr = [{"key": "X-TENANT-ID", "value": "{{tenant_id}}"}]
    if extra_headers:
        hdr += extra_headers
    if body:
        hdr.append({"key": "Content-Type", "value": "application/json"})

    url_raw = "{{" + base + "}}" + path
    path_parts = [p for p in path.split("?")[0].strip("/").split("/") if p]
    url = {"raw": url_raw, "host": ["{{" + base + "}}"], "path": path_parts}
    if "?" in path:
        q = path.split("?")[1]
        url["query"] = [{"key": kv.split("=")[0], "value": kv.split("=")[1]}
                        for kv in q.split("&")]

    r = {"method": method, "header": hdr, "url": url}
    if body:
        r["body"] = raw_body(body)
    if noauth:
        r["auth"] = {"type": "noauth"}

    events = []

    # Pre-request: skip if previous step failed
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

    # Test: skip check + actual tests
    test_lines = []
    if skip_on_fail:
        test_lines += [
            "if (pm.collectionVariables.get('_flow_failed') === 'true') {",
            "  pm.test('SKIPPED: ' + pm.info.requestName + ' (failed at: ' + (pm.collectionVariables.get('_flow_failed_at')||'?') + ')', function() {});",
            "  return;",
            "}",
        ]
    test_lines += tests
    events.append({"listen": "test", "script": {"type": "text/javascript", "exec": test_lines}})

    return {"name": name, "request": r, "event": events, "response": []}


def fail_on_error(step_name, status_check="pm.response.code"):
    """JS lines to mark flow as failed when HTTP status is not 2xx."""
    return [
        f"if ({status_check} >= 400) {{",
        f"  pm.collectionVariables.set('_flow_failed', 'true');",
        f"  pm.collectionVariables.set('_flow_failed_at', '{step_name}');",
        "}",
    ]


def build_setup(base_var, health_path="/actuator/health", clear_vars=None):
    """Build the 00 Setup step.

    Args:
        base_var:     Base URL variable name (e.g. 'app_base_url')
        health_path:  Health endpoint path
        clear_vars:   List of collection variable names to clear
    """
    clear_lines = [
        "pm.collectionVariables.unset('_flow_failed');",
        "pm.collectionVariables.unset('_flow_failed_at');",
    ]
    for v in (clear_vars or []):
        clear_lines.append(f"pm.collectionVariables.unset('{v}');")

    clear_lines += [
        f"pm.collectionVariables.set('_skip_url', pm.environment.get('{base_var}') + '{health_path}');",
        "console.log('Setup: state cleared for env=' + pm.environment.get('env_name'));",
    ]

    return {
        "name": "00 Setup",
        "event": [
            {"listen": "prerequest", "script": {"type": "text/javascript", "exec": clear_lines}},
            {"listen": "test", "script": {"type": "text/javascript", "exec": [
                "pm.test('00 token acquired', () => pm.expect(pm.collectionVariables.get('access_token')||pm.environment.get('access_token')||'').to.not.eql(''));",
                "pm.test('00 service reachable', () => pm.expect(pm.response.code).to.eql(200));",
                "if (pm.response.code !== 200) {",
                "  pm.collectionVariables.set('_flow_failed', 'true');",
                "  pm.collectionVariables.set('_flow_failed_at', '00 Setup');",
                "}",
            ]}}
        ],
        "request": {
            "method": "GET", "header": [],
            "url": {"raw": "{{" + base_var + "}}" + health_path,
                    "host": ["{{" + base_var + "}}"],
                    "path": [p for p in health_path.strip("/").split("/") if p]},
            "auth": {"type": "noauth"},
        },
        "response": []
    }


def build_teardown(base_var, health_path="/actuator/health"):
    """Build the 99 Teardown step (always runs, clears flow state)."""
    return {
        "name": "99 Teardown",
        "event": [
            {"listen": "test", "script": {"type": "text/javascript", "exec": [
                "pm.test('99 teardown', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
                "pm.collectionVariables.unset('_flow_failed');",
                "pm.collectionVariables.unset('_flow_failed_at');",
            ]}}
        ],
        "request": {
            "method": "GET", "header": [],
            "url": {"raw": "{{" + base_var + "}}" + health_path,
                    "host": ["{{" + base_var + "}}"],
                    "path": [p for p in health_path.strip("/").split("/") if p]},
            "auth": {"type": "noauth"},
        },
        "response": []
    }


def global_capture_test():
    """Collection-level test that runs after EVERY request: surface any API error's status +
    message (so tolerant per-step assertions can't hide it), record it for review, and FAIL on
    server errors (5xx) — a 5xx is never a legitimate outcome, so it must not pass silently.
    Health/skip URLs are excluded (they are intentional redirects)."""
    return [
        "(function(){",
        "  const code=pm.response.code;",
        "  let u=''; try{u=pm.request.url.toString();}catch(e){}",
        "  if(code<400 || u.indexOf('__skip__')>=0 || u.indexOf('/actuator/health')>=0) return;",
        "  let msg='';",
        "  try{const b=pm.response.json(); msg=b.message||b.error||b.errorCode||JSON.stringify(b);}catch(e){try{msg=pm.response.text();}catch(x){}}",
        "  if(msg && msg.length>300) msg=msg.slice(0,300);",
        "  console.log('API FAIL ['+pm.info.requestName+'] '+code+' '+pm.request.method+' '+u+' :: '+msg);",
        "  let fails=[]; try{fails=JSON.parse(pm.collectionVariables.get('_api_failures')||'[]');}catch(e){}",
        "  fails.push({step:pm.info.requestName, code:code, message:msg});",
        "  pm.collectionVariables.set('_api_failures', JSON.stringify(fails));",
        "  // 5xx is a real server failure — register a failing assertion so it can't pass silently.",
        "  // EXCEPT endpoints whose 5xx is a known tenant/infra-config gap (surfaced by the step's own",
        "  // assertion instead), so one backend gap doesn't cascade into dozens of identical failures:",
        "  //   synapse namespace status/stats -> 500 when the tenant has no QuipuSynapse URL configured",
        "  //   test-connection/sample-records  -> 500 when called without a persisted datasource id",
        "  const soft5xx = u.indexOf('/synapse/namespace/status')>=0 || u.indexOf('/synapse/namespace/stats')>=0 || u.indexOf('/test-connection/sample-records')>=0;",
        "  if(code>=500 && !soft5xx){ pm.test('[api] server '+code+' @ '+pm.info.requestName+' :: '+msg, () => { throw new Error(code+' '+msg); }); }",
        "})();",
    ]


def build_collection(name, description, folder_name, items, extra_variables=None):
    """Assemble a complete Postman collection JSON.

    Args:
        name:             Collection display name
        description:      Collection description (markdown)
        folder_name:      Top-level folder name
        items:            List of request items
        extra_variables:  Additional collection variables (list of dicts)
    """
    variables = [
        {"key": "access_token",      "value": "", "type": "string"},
        {"key": "token_expiry",      "value": "", "type": "string"},
        {"key": "_flow_failed",      "value": "", "type": "string"},
        {"key": "_flow_failed_at",   "value": "", "type": "string"},
        {"key": "_skip_url",         "value": "", "type": "string"},
        {"key": "_api_failures",     "value": "", "type": "string"},
    ]
    if extra_variables:
        variables += extra_variables

    return {
        "info": {
            "_postman_id": f"flow-{folder_name.lower().replace(' ', '-')}-auto",
            "name": name,
            "description": description,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}]},
        "event": [
            {"listen": "prerequest", "script": {"type": "text/javascript", "exec": keycloak_prerequest()}},
            {"listen": "test", "script": {"type": "text/javascript", "exec": global_capture_test()}},
        ],
        "variable": variables,
        "item": [{"name": folder_name, "item": items}]
    }


def write_flow(filename, collection):
    """Write collection JSON to flows/ directory."""
    os.makedirs("flows", exist_ok=True)
    filepath = f"flows/{filename}"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)
    print(f"  wrote {filepath} ({len(collection['item'][0]['item'])} steps)")
    return filepath
