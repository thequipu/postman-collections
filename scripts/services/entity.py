"""FLOW-Entity-CRUD: Entity + Property + Relationship lifecycle."""

from flowlib.core import req, build_setup, build_collection, write_flow


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=["entityUri", "propertyUri", "relationshipUri"]),

        req("01 List Entities", "GET", "/entity-graph/entities?page=0&size=20",
            ["pm.test('01 List entities 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Entities response keys: '+Object.keys(b||{}).join(', '));"],
            base=base),

        req("02 Create Entity", "POST", "/entity",
            ["const code = pm.response.code;",
             "pm.test('02 Create entity 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','02 Create Entity');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const uri = b.uri || b.entityUri || b.id;",
             "if(uri) pm.collectionVariables.set('entityUri', uri);",
             "console.log('Entity created: '+uri);"],
            base=base,
            body={"label": "pm-flow-entity-{{$timestamp}}", "prefix": "pm-flow:",
                  "description": "Auto-created by FLOW test"}),

        req("03 Search Entity", "GET", "/entity/search?q=pm-flow",
            ["pm.test('03 Search 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("04 Get Subgraph", "GET", "/entity-graph/entity-subgraph?uri={{entityUri}}",
            ["pm.test('04 Get subgraph 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('04 has data', () => pm.expect(JSON.stringify(b).length).to.be.above(2));"],
            base=base),

        req("05 Add Property", "POST", "/entity/property?entityUri={{entityUri}}",
            ["pm.test('05 Add property 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const uri = b.uri || b.propertyUri || b.id;",
             "if(uri) pm.collectionVariables.set('propertyUri', uri);",
             "console.log('Property added: '+uri);"],
            base=base,
            body={"label": "pm_flow_prop", "dataType": "string", "primaryKey": False}),

        req("06 Delete Property", "DELETE", "/entity/property?uri={{propertyUri}}",
            ["pm.test('06 Delete property 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("07 Delete Entity", "DELETE", "/entity?uri={{entityUri}}",
            ["pm.test('07 Delete entity 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        # Teardown
        req("99 Teardown", "DELETE", "/entity?uri={{entityUri}}",
            ["pm.test('99 teardown tolerant', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed');",
             "pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Entity CRUD",
        description="Entity lifecycle: create -> search -> subgraph -> add property -> delete.",
        folder_name="Entity CRUD",
        items=items,
        extra_variables=[
            {"key": "entityUri",       "value": "", "type": "string"},
            {"key": "propertyUri",     "value": "", "type": "string"},
            {"key": "relationshipUri", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Entity-CRUD.postman_collection.json", col)
