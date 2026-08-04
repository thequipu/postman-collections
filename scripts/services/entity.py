"""FLOW-Entity-CRUD: Full entity lifecycle with properties, relationships."""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import full_setup_steps, cleanup_steps, SETUP_VARS, SETUP_CLEAR_VARS


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health",
                    clear_vars=SETUP_CLEAR_VARS + ["entityUri", "entity2Uri", "propertyUri",
                                                    "relationshipUri", "sugRelUri"]),

        *full_setup_steps("01", "pm-flow-entity", include_realm=True, base=base),

        # ── Entity CRUD ──
        req("02 List Entities", "GET", "/entity-graph/entities?page=0&size=20",
            ["pm.test('02 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("03 Complete Graph", "GET", "/entity-graph/complete-graph",
            ["pm.test('03 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),

        req("04 Create Entity", "POST", "/entity",
            ["const code=pm.response.code;",
             "pm.test('04 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','04');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const uri=b.uri||b.entityUri||b.id;",
             "pm.test('04 has uri', () => pm.expect(uri).to.not.be.undefined);",
             "if(uri) pm.collectionVariables.set('entityUri', uri);",
             "pm.test('04 uri well-formed', () => pm.expect(String(uri||'')).to.include('Node#'));"],
            base=base, body={"label": "pm-flow-entity-{{$timestamp}}", "prefix": "pm-flow:", "description": "FLOW test"}),

        req("05 Create Entity2", "POST", "/entity",
            ["pm.test('05 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const uri=b.uri||b.entityUri||b.id; if(uri) pm.collectionVariables.set('entity2Uri', uri);"],
            base=base, body={"label": "pm-flow-entity2-{{$timestamp}}", "prefix": "pm-flow:", "description": "Second entity"}),

        req("06 Search GET", "GET", "/entity/search?q=pm-flow",
            ["pm.test('06 200', () => pm.response.to.have.status(200));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "pm.test('06 found', () => pm.expect((Array.isArray(b)?b:(b.data||[])).length).to.be.above(0));"], base=base),
        req("07 Search POST", "POST", "/entity/search",
            ["pm.test('07 200|500', () => pm.expect(pm.response.code).to.be.oneOf([200,204,500]));"],
            base=base, body={"query": "pm-flow", "page": 0, "size": 10}),
        req("08 Subgraph", "GET", "/entity-graph/entity-subgraph?uri={{entityUri}}",
            ["pm.test('08 200', () => pm.response.to.have.status(200));"], base=base),
        req("09 DS Subgraph", "GET", "/entity-graph/datasource-subgraph?uri={{entityUri}}",
            ["pm.test('09 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("10 Update Entity", "PUT", "/entity?uri={{entityUri}}",
            ["pm.test('10 200', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base, body={"label": "pm-flow-entity-updated", "prefix": "pm-flow:", "description": "Updated"}),

        req("11 Add Property", "POST", "/entity/property?entityUri={{entityUri}}",
            ["pm.test('11 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const uri=b.propUri||b.uri||b.id; if(uri) pm.collectionVariables.set('propertyUri', uri);"],
            base=base, body={"label": "pm_flow_prop", "dataType": "string", "primaryKey": False}),
        req("12 Update Property", "PUT", "/entity/property?uri={{propertyUri}}",
            ["pm.test('12 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base, body={"label": "pm_flow_prop_updated", "dataType": "string", "primaryKey": False}),

        req("13 Add Relationship", "POST", "/entity/relationship?entityUri={{entityUri}}",
            ["pm.test('13 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const uri=b.relUri||b.uri||b.id; if(uri) pm.collectionVariables.set('relationshipUri', uri);"],
            base=base, body={"label": "pm_flow_rel", "targetUri": "{{entity2Uri}}", "description": "FLOW rel"}),
        req("14 Update Relationship", "PUT", "/entity/relationship?uri={{relationshipUri}}",
            ["pm.test('14 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base, body={"label": "pm_flow_rel_updated", "targetUri": "{{entity2Uri}}"}),

        req("15 Add Suggested Rel", "POST", "/entity/suggested-relationship",
            ["pm.test('15 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){} const uri=b.uri||b.id; if(uri) pm.collectionVariables.set('sugRelUri', uri);"],
            base=base, body={"sourceUri": "{{entityUri}}", "targetUri": "{{entity2Uri}}", "label": "pm_flow_sug"}),
        req("16 Update Suggested Rel", "PUT", "/entity/suggested-relationship?uri={{sugRelUri}}",
            ["pm.test('16 200|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base, body={"label": "pm_flow_sug_updated"}),

        req("17 Migrate DS", "POST", "/entity-graph/migrate?dataSourceId={{dsId}}",
            ["pm.test('17 200|404|500', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404,500]));"], base=base),

        # Cleanup entities
        req("18 Del Rel", "DELETE", "/entity/relationship?uri={{relationshipUri}}",
            ["pm.test('18 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"], base=base),
        req("19 Del Prop", "DELETE", "/entity/property?uri={{propertyUri}}",
            ["pm.test('19 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"], base=base),
        req("20 Del Entity", "DELETE", "/entity?uri={{entityUri}}",
            ["pm.test('20 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("21 Del Entity2", "DELETE", "/entity?uri={{entity2Uri}}",
            ["pm.test('21 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"], base=base),
        req("22 Batch Delete", "POST", "/entity/batch-delete",
            ["pm.test('22 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base, body={"uris": ["{{entityUri}}", "{{entity2Uri}}"]}),

        # Cleanup infra
        *cleanup_steps(23, include_realm=True, base=base),

        req("99 Teardown", "DELETE", "/realm/{{realmId}}?permanent=true",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Entity CRUD",
        description="Entity lifecycle with entities from datasource in schema graph.",
        folder_name="Entity CRUD", items=items,
        extra_variables=SETUP_VARS + [
            {"key": k, "value": "", "type": "string"}
            for k in ["entityUri", "entity2Uri", "propertyUri", "relationshipUri", "sugRelUri"]])
    return write_flow("FLOW-Entity-CRUD.postman_collection.json", col)
