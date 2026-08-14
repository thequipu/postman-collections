"""FLOW-Entity-CRUD: Entity page operations on real DS entities.

NO schema/version/realm needed — entities come directly from datasource.
Creates DS → entities auto-available → entity CRUD operations → ingestion.
"""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import (create_ds_step, fetch_entities_step,
                           create_schema_graph_step,
                           cleanup_steps, teardown_step,
                           SKIP_CLEANUP_PRE, SKIP_CLEANUP_TEST)


def generate():
    base = "app_base_url"

    extra_vars = ["dsId", "dataCatalogName", "dsMetaName", "_dsPrefix",
                  "_graphNodes", "_graphLinks",
                  "entityUri", "newEntityUri", "copyEntityUri",
                  "propUri", "propUri2", "mergedPropUri", "relationshipUri",
                  "firstColumnUri", "secondColumnUri",
                  "_entityProps", "streamId", "_ingestion_status",
                  "schemaName", "schemaPrefix", "versionId", "awsVersionId",
                  "_dsMetaList", "_versionUri", "_versionUriEnc"]

    items = [
        build_setup(base, "/actuator/health",
                    clear_vars=extra_vars),

        # ═══ PHASE 1: Create DataSource (entities auto-available) ═══

        create_ds_step("01a", base),
        fetch_entities_step("01b", base),

        # ═══ PHASE 2: Get existing entity from DS graph ═══

        req("02 Get Entity from DS", "GET", "/actuator/health",
            ["pm.test('02 health', () => pm.response.to.have.status(200));"],
            base=base,
            prerequest=[
                "// Get first entity from DS graph (created by fetch_entities_step)",
                "let nodes=[]; try{nodes=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]');}catch(e){}",
                "if(nodes.length>0){",
                "  pm.collectionVariables.set('entityUri', nodes[0].id||nodes[0].uri);",
                "  console.log('DS entity: '+(nodes[0].id)+', label='+nodes[0].label);",
                "} else { console.log('No entities from DS graph'); }",
            ]),

        req("02b Get Entity Subgraph", "GET", "/entity-graph/entity-subgraph?uri={{entityUri}}",
            ["pm.test('02b 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const nodes=b.nodes||[];",
             "const columns=nodes.filter(n=>n.node_type==='property');",
             "// Capture column URIs for entity operations",
             "if(columns.length>0) pm.collectionVariables.set('firstColumnUri', columns[0].node_id||columns[0].nodeId||columns[0].id);",
             "if(columns.length>1) pm.collectionVariables.set('secondColumnUri', columns[1].node_id||columns[1].nodeId||columns[1].id);",
             "// Build properties from columns",
             "const props=columns.slice(0,3).map(c=>({label:c.label,dataType:c.data_type||c.dataType||'STRING',primaryKey:!!c.primary_key,uniqueKey:!!c.unique_key,foreignKey:!!c.foreign_key,nullable:true,mappedColumnUri:c.node_id||c.nodeId||c.id,mappedColumnUris:[c.node_id||c.nodeId||c.id]}));",
             "pm.collectionVariables.set('_entityProps', JSON.stringify(props));",
             "console.log('Subgraph: '+nodes.length+' nodes, '+columns.length+' columns, '+props.length+' props captured');"],
            base=base),

        # ═══ PHASE 3: Entity Operations ═══

        # Create NEW entity with real DS properties
        req("03 Create New Entity", "POST", "/entity",
            ["const code=pm.response.code;",
             "pm.test('03 Create 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','03');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const uri=b.entityUri||b.uri;",
             "pm.test('03 has entityUri', () => pm.expect(uri).to.not.be.undefined);",
             "if(uri) pm.collectionVariables.set('newEntityUri', uri);",
             "const props=b.properties||[];",
             "if(props.length>0) pm.collectionVariables.set('propUri', props[0].uri||props[0].propUri);",
             "if(props.length>1) pm.collectionVariables.set('propUri2', props[1].uri||props[1].propUri);",
             "console.log('New entity: '+uri+', '+props.length+' props');"],
            base=base, body={"label": "x"},
            prerequest=[
                "const prefix=pm.collectionVariables.get('_dsPrefix')||'http://pmflow.in/';",
                "const dsCat=pm.collectionVariables.get('dataCatalogName');",
                "let props=[]; try{props=JSON.parse(pm.collectionVariables.get('_entityProps')||'[]');}catch(e){}",
                "const body={label:'pm_flow_new_entity_'+Date.now(),prefix:prefix,dataSourceUri:dsCat,namedEntity:false,description:'Created by FLOW',tags:[],properties:props};",
                "console.log('Creating entity: prefix='+prefix+', '+props.length+' props');",
                "pm.request.body.raw=JSON.stringify(body);",
            ]),

        req("03b Verify New Entity", "GET", "/entity-graph/entity-subgraph?uri={{newEntityUri}}",
            ["pm.test('03b 200', () => pm.response.to.have.status(200));",
             "pm.test('03b entity accessible', () => pm.expect(pm.response.code).to.eql(200));"],
            base=base),

        # Add property with mappedColumnUri
        req("04 Add Property", "POST", "/entity/property?entityUri={{newEntityUri}}",
            ["pm.test('04 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const uri=b.propUri||b.uri;",
             "pm.test('04 has propUri', () => pm.expect(uri).to.not.be.undefined);",
             "if(uri) pm.collectionVariables.set('mergedPropUri', uri);",
             "console.log('Added prop: '+uri);"],
            base=base, body={"label": "x"},
            prerequest=[
                "const colUri=pm.collectionVariables.get('firstColumnUri')||'';",
                "const body={label:'pm_flow_added_prop',dataType:'VARCHAR',primaryKey:false,uniqueKey:false,foreignKey:false,alternateLabel:false,preferredLabel:false,timeLabel:false,timeFormat:'',nullable:true,mappedColumnUri:colUri,mappedColumnUris:colUri?[colUri]:[]};",
                "pm.request.body.raw=JSON.stringify(body);",
            ]),

        # Merge two properties (multiple mappedColumnUris)
        req("05 Merge Properties", "POST", "/entity/property?entityUri={{newEntityUri}}",
            ["pm.test('05 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Merged prop: '+(b.propUri||b.uri));"],
            base=base, body={"label": "x"},
            prerequest=[
                "const col1=pm.collectionVariables.get('firstColumnUri')||'';",
                "const col2=pm.collectionVariables.get('secondColumnUri')||col1;",
                "const uris=[col1,col2].filter(u=>u);",
                "const body={label:'pm_flow_merged_prop',dataType:'VARCHAR',primaryKey:false,uniqueKey:false,foreignKey:false,nullable:true,mappedColumnUri:col1,mappedColumnUris:uris};",
                "console.log('Merging '+uris.length+' columns');",
                "pm.request.body.raw=JSON.stringify(body);",
            ]),

        # Create new node FROM existing entity
        req("06 Create From Existing", "POST", "/entity",
            ["pm.test('06 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const uri=b.entityUri||b.uri;",
             "pm.test('06 has uri', () => pm.expect(uri).to.not.be.undefined);",
             "if(uri) pm.collectionVariables.set('copyEntityUri', uri);",
             "console.log('Copy entity: '+uri);"],
            base=base, body={"label": "x"},
            prerequest=[
                "const prefix=pm.collectionVariables.get('_dsPrefix')||'http://pmflow.in/';",
                "const dsCat=pm.collectionVariables.get('dataCatalogName');",
                "let props=[]; try{props=JSON.parse(pm.collectionVariables.get('_entityProps')||'[]');}catch(e){}",
                "const body={label:'pm_flow_copy_entity_'+Date.now(),prefix:prefix,dataSourceUri:dsCat,namedEntity:false,description:'Copied by FLOW',tags:[],properties:props};",
                "pm.request.body.raw=JSON.stringify(body);",
            ]),

        req("06b Verify Copy", "GET", "/entity-graph/entity-subgraph?uri={{copyEntityUri}}",
            ["pm.test('06b 200', () => pm.response.to.have.status(200));"],
            base=base),

        # Add relationship between entities
        req("07 Add Relationship", "POST", "/entity/relationship?entityUri={{newEntityUri}}",
            ["pm.test('07 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const uri=b.relUri||b.uri;",
             "if(uri) pm.collectionVariables.set('relationshipUri', uri);",
             "pm.test('07 has relUri', () => pm.expect(uri).to.not.be.undefined);"],
            base=base,
            body={"label": "pm_flow_rel", "targetUri": "{{copyEntityUri}}", "description": "FLOW rel"}),

        # Delete relationship
        req("08 Delete Relationship", "DELETE", "/entity/relationship?uri={{relationshipUri}}",
            ["pm.test('08 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base),

        # Delete property + verify
        req("09 Delete Property", "DELETE", "/entity/property?uri={{mergedPropUri}}",
            ["pm.test('09 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base),

        req("09b Verify Property Gone", "GET", "/entity-graph/entity-subgraph?uri={{newEntityUri}}",
            ["pm.test('09b 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const props=(b.nodes||[]).filter(n=>n.node_type==='Node Property');",
             "const deleted=props.find(p=>(p.uri||p.id)==pm.collectionVariables.get('mergedPropUri'));",
             "pm.test('09b prop removed', () => pm.expect(deleted).to.be.undefined);"],
            base=base),

        # Delete entity + verify
        req("10 Delete Entity", "DELETE", "/entity?uri={{newEntityUri}}",
            ["pm.test('10 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("10b Verify Entity Gone", "GET", "/entity-graph/entity-subgraph?uri={{newEntityUri}}",
            ["pm.test('10b 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const entity=(b.nodes||[]).find(n=>n.node_type==='Node'&&(n.uri||n.id)==pm.collectionVariables.get('newEntityUri'));",
             "pm.test('10b entity gone', () => pm.expect(entity).to.be.undefined);"],
            base=base),

        # Delete copied entity
        req("11 Delete Copy", "DELETE", "/entity?uri={{copyEntityUri}}",
            ["pm.test('11 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        # ═══ PHASE 4: Create Schema with remaining entities and save ═══

        req("12 Create Schema", "POST", "/schema",
            ["pm.test('12 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.schemaModel||b.data||b;",
             "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
             "if(d.prefix) pm.collectionVariables.set('schemaPrefix', d.prefix);",
             "console.log('Schema: '+(d.name||d.schemaName));"],
            base=base, body={"schemaName": "x"},
            prerequest=[
                "const prefix=pm.collectionVariables.get('_dsPrefix')||'http://pmflow.in/';",
                "pm.request.body.raw=JSON.stringify({schemaName:'pm_flow_entity_schema_'+Date.now(),prefix:prefix,description:'Entity flow schema'});",
            ]),

        # Re-fetch DS metadata so the schema-graph builder has fresh tables+columns.
        req("12b Fetch Current Entities", "POST", "/metadata-graph/fetch-data-source",
            ["pm.test('12b 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.collectionVariables.set('_dsMetaList', JSON.stringify([b]));",
             "const n=(b.hasTableEdges||[]).length;",
             "console.log('Current DS tables: '+n+' for schema-graph');"],
            base=base, body={"uri": "{{dataCatalogName}}"}),

        # Save the schema graph the way the UI does:
        #   13i  KG save-schema-version  -> creates version + MinIO blob (versioning/ingestion)
        #   13ii app POST /schema-graph  -> MERGE :SchemaEntity nodes for the editor canvas
        #   13iii GET /schema-graph?versionUri -> verify entities visible (same read as the UI)
        *create_schema_graph_step("13", base),

        # ═══ PHASE 5: Cleanup (skip_cleanup=true to keep DS+Schema) ═══

        req("90 Del DS", "DELETE", "/datasource/{{dsId}}",
            [SKIP_CLEANUP_TEST, "pm.test('90 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE),

        req("99 Teardown", "GET", "/actuator/health",
            ["pm.test('99 healthy', () => pm.response.to.have.status(200));",
             "console.log('=== ENTITY FLOW COMPLETE ===');",
             "console.log('DS: '+pm.collectionVariables.get('dsId'));",
             "console.log('skip_cleanup: '+(pm.environment.get('skip_cleanup')||'false'));"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Entity CRUD",
        description="Entity page operations on real DS entities.\n\n"
                    "NO schema needed — entities come from datasource directly.\n"
                    "Creates DS → entity subgraph → create entity (dataSourceUri+properties),\n"
                    "add property (mappedColumnUri), merge properties, create from existing,\n"
                    "relationship CRUD, delete + verify.\n"
                    "Pass --env-var 'skip_cleanup=true' to keep DS for inspection.",
        folder_name="Entity CRUD",
        items=items,
        extra_variables=[{"key": k, "value": "", "type": "string"} for k in extra_vars])
    return write_flow("FLOW-Entity-CRUD.postman_collection.json", col)
