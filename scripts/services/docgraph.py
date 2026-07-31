"""FLOW-DocumentGraph-Parse: Document graph health + parse validation."""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "docgraph_base_url"

    items = [
        build_setup(base, "/actuator/health"),

        req("01 Health Check", "GET", "/actuator/health",
            ["pm.test('01 DocGraph healthy', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('DocGraph health: '+JSON.stringify(b).slice(0,200));"],
            base=base, noauth=True),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Document Graph Parse",
        description="Document Graph service health validation.\n\nUses `{{docgraph_base_url}}` (port 3048, direct — not behind gateway).",
        folder_name="DocumentGraph Parse",
        items=items,
    )
    return write_flow("FLOW-DocumentGraph-Parse.postman_collection.json", col)
