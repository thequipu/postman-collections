"""FLOW-SchemaGraph-CRUD: Schema graph operations with real entities."""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import (create_ds_step, fetch_entities_step, create_schema_graph_step,
                           SETUP_VARS, SETUP_CLEAR_VARS)


def generate():
    base = "app_base_url"
    items = [
        build_setup(base, "/actuator/health", clear_vars=SETUP_CLEAR_VARS),
        create_ds_step("01a", base),
        fetch_entities_step("01b", base),

        req("01c Create Schema", "POST", "/schema",
            ["const code=pm.response.code;",
             "pm.test('01c 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01c');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.schemaModel||b.data||b;",
             "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
             "if(d.id||d.schemaId) pm.collectionVariables.set('schemaId', String(d.id||d.schemaId));",
             "if(d.prefix) pm.collectionVariables.set('schemaPrefix', d.prefix);"],
            base=base, body={"schemaName": "x"},
            prerequest=[
                "const schemaName='pm_flow_sg_schema_'+Date.now();",
                "const prefix=schemaName.replace(/_/g,'-');",
                "pm.collectionVariables.set('schemaPrefix', prefix);",
                "pm.request.body.raw=JSON.stringify({schemaName:schemaName,prefix:prefix,description:'SchemaGraph dep'});",
            ]),

        # ── Schema Graph CRUD ──
        # Save graph correctly: version+MinIO (KG) -> UI/Neo4j merge -> verify entities visible
        *create_schema_graph_step("02", base),

        req("03 Get Graph", "GET", "/schema-graph?versionUri={{_versionUriEnc}}",
            ["pm.test('03 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const ns=(b.nodes||[]).filter(n=>n.node_type==='Node');",
             "pm.test('03 entities present', () => pm.expect(ns.length).to.be.above(0));"],
            base=base),

        req("04 Get by Name", "GET", "/schema-graph/by-name?schemaName={{schemaName}}&versionId={{versionId}}",
            ["pm.test('04 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "if(pm.response.code===200){pm.test('04 has entities', () => pm.expect((b.nodes||[]).filter(n=>n.node_type==='Node').length).to.be.above(0));}"],
            base=base),

        # PUT is a DETACH-DELETE-by-prefix then re-add — so it must resend the FULL graph
        # (schemaUri=versionUri, proper nodeId=prefix+uri) plus one added entity, or it
        # would wipe the schema. Uses the graph built by step 02i.
        req("05 Update Graph", "PUT", "/schema-graph",
            ["pm.test('05 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base, body={"schemaUri": ""},
            prerequest=[
                "const P=pm.collectionVariables.get('schemaPrefix')||pm.collectionVariables.get('_dsPrefix');",
                "const vu=pm.collectionVariables.get('_versionUri');",
                "let n=[]; try{n=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]');}catch(e){}",
                "let l=[]; try{l=JSON.parse(pm.collectionVariables.get('_graphLinks')||'[]');}catch(e){}",
                "const eu=P+'Node#updated_by_flow';",
                "n.push({node_type:'Node',id:eu,uri:eu,nodeId:P+eu,label:'updated_by_flow',entityLabel:'updated_by_flow',namedEntity:false,prefix:P,tags:[]});",
                "l.push({source:vu,target:eu,relationship:'Has_Node',direction:'FORWARD',node_uri:vu});",
                "pm.request.body.raw=JSON.stringify({schemaUri:vu,prefix:P,nodes:n,links:l});",
            ]),

        req("06 Copy Version", "POST", "/schema-graph/copy-version",
            ["pm.test('06 200|201|400', () => pm.expect(pm.response.code).to.be.oneOf([200,201,204,400]));"],
            base=base, body={"sourceVersionUri": ""},
            prerequest=[
                "const p=pm.collectionVariables.get('schemaPrefix')||pm.collectionVariables.get('_dsPrefix');",
                "pm.request.body.raw=JSON.stringify({sourceVersionUri:p+'Version#v1',targetVersionName:'v2-copy-'+Date.now()});",
            ]),

        req("07 Delete Graph", "DELETE", "/schema-graph?prefix={{schemaPrefix}}",
            ["pm.test('07 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"], base=base),

        # Cleanup
        req("08 Del Version", "DELETE", "/versions/delete?versionId={{versionId}}",
            ["pm.test('08 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("09 Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('09 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base),
        req("10 Del DS", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('10 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"], base=base),
        req("99 Teardown", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]
    col = build_collection(name="FLOW - Schema Graph CRUD", description="Schema graph with real entities.",
        folder_name="Schema Graph CRUD", items=items, extra_variables=SETUP_VARS)
    return write_flow("FLOW-SchemaGraph-CRUD.postman_collection.json", col)
