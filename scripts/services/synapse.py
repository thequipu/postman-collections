"""FLOW-Synapse-Namespace: Full namespace lifecycle on Synapse (port 8888)."""

from flowlib.core import req, build_setup, build_collection, write_flow


def generate():
    base = "synapse_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=["nsName"]),

        req("01 List Namespaces", "GET", "/namespaces",
            ["pm.test('01 List namespaces 200', () => pm.response.to.have.status(200));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "console.log('Namespaces: '+(Array.isArray(b)?b.length:'?'));"],
            base=base),

        req("02 Create Namespace", "POST", "/namespaces/create?name=pm_flow_ns_{{$timestamp}}&isHistoricIngestRequired=false",
            ["const code = pm.response.code;",
             "pm.test('02 Create namespace 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','02 Create Namespace');} pm.expect(code).to.be.oneOf([200,201]); });",
             "// Extract namespace name from request URL",
             "const urlStr = pm.request.url.toString();",
             "const nameMatch = urlStr.match(/name=([^&]+)/);",
             "if(nameMatch) { pm.collectionVariables.set('nsName', nameMatch[1]); console.log('Namespace: '+nameMatch[1]); }"],
            base=base),

        req("03 Get Status", "GET", "/namespaces/{{nsName}}/status",
            ["pm.test('03 Status 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("04 Get Stats", "GET", "/namespaces/{{nsName}}/stats",
            ["pm.test('04 Stats 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("05 Enable Namespace", "POST", "/namespaces/{{nsName}}/enable",
            ["pm.test('05 Enable 200', () => pm.expect(pm.response.code).to.be.oneOf([200,202]));"],
            base=base),

        req("06 Run Cypher Query", "POST", "/query/cypher",
            ["pm.test('06 Cypher 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Cypher result: '+JSON.stringify(b).slice(0,200));"],
            base=base,
            body={"query": "RETURN 1 AS n", "namespace": "{{nsName}}"}),

        req("07 Disable Namespace", "POST", "/namespaces/{{nsName}}/disable",
            ["pm.test('07 Disable 200', () => pm.expect(pm.response.code).to.be.oneOf([200,202]));"],
            base=base),

        req("08 Delete Namespace", "DELETE", "/namespaces/{{nsName}}?permanent=true",
            ["pm.test('08 Delete 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        # Teardown (always runs)
        req("99 Teardown", "DELETE", "/namespaces/{{nsName}}?permanent=true",
            ["pm.test('99 teardown tolerant', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed');",
             "pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Synapse Namespace",
        description="Full Synapse namespace lifecycle: create -> status -> enable -> cypher -> disable -> delete.\n\nUses `{{synapse_base_url}}` (port 8888, direct — not behind gateway).",
        folder_name="Synapse Namespace",
        items=items,
        extra_variables=[
            {"key": "nsName", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Synapse-Namespace.postman_collection.json", col)
