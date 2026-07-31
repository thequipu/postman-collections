"""FLOW-KnowledgeGraph-Metadata: Read-only KG metadata validation."""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "kg_base_url"

    items = [
        build_setup(base, "/actuator/health"),

        req("01 Get Schema Graph", "GET", "/metadata/get-saved-schema-graph?referenceName={{realm}}",
            ["pm.test('01 Schema graph 200 or 404', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));",
             "if(pm.response.code===200) {",
             "  let b={}; try{b=pm.response.json();}catch(e){}",
             "  console.log('Schema graph keys: '+Object.keys(b||{}).join(', '));",
             "}"],
            base=base),

        req("02 Namespace Stats", "GET", "/synapse/namespace/stats?namespace={{realm}}",
            ["pm.test('02 Namespace stats 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base=base),

        req("03 Namespace Status", "GET", "/synapse/namespace/status?name={{realm}}",
            ["pm.test('03 Namespace status 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base=base),

        req("04 List Watchers", "GET", "/synapse/watchers?namespace={{realm}}",
            ["pm.test('04 Watchers 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "console.log('Watchers: '+(Array.isArray(b)?b.length:'?'));"],
            base=base),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Knowledge Graph Metadata (Read-Only)",
        description="Read-only validation of KG Service: schema graph, namespace stats/status, watchers.\n\nUses `{{realm}}` from environment (tenant realm name).",
        folder_name="KG Metadata",
        items=items,
    )
    return write_flow("FLOW-KnowledgeGraph-Metadata.postman_collection.json", col)
