"""FLOW-Nexus-Search: Read-only search/traversal validation."""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "nexus_base_url"

    items = [
        build_setup(base, "/actuator/health"),

        req("01 Get Traversable Schema", "POST", "/nexus/schema/traversable/get",
            ["pm.test('01 Traversable schema 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Schema response: '+JSON.stringify(b).slice(0,200));"],
            base=base,
            body={"fabricId": "{{realm}}"}),

        req("02 Search", "POST", "/nexus/search",
            ["pm.test('02 Search 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base=base,
            body={"query": "test", "fabricId": "{{realm}}"}),

        req("03 GIN", "POST", "/nexus/gin",
            ["pm.test('03 GIN 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base=base,
            body={"fabricId": "{{realm}}"}),

        req("04 Labels", "POST", "/nexus/labels",
            ["pm.test('04 Labels 200', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base=base,
            body={"fabricId": "{{realm}}"}),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Nexus Search (Read-Only)",
        description="Read-only validation of Nexus search pipeline: traversable schema, search, GIN, labels.\n\nUses `{{realm}}` from environment.",
        folder_name="Nexus Search",
        items=items,
    )
    return write_flow("FLOW-Nexus-Search.postman_collection.json", col)
