"""Reusable setup steps for creating DS → Schema → Schema-Graph (with entities) → Realm.

Correct flow (verified from onprem):
1. POST /datasource → create DS, capture dsId + dataCatalogName
2. GET /metadata/datasource/{dsName} → get real entities (dataSets with columns)
3. POST /schema {schemaName, prefix} → create schema with prefix
4. POST /schema-graph → creates version + schema graph with entities in ONE call
5. POST /realm → create realm with schemaName + versionId
"""

from .core import req


# KG /metadata/* endpoints require this Accept media type (MetadataController).
KG_ACCEPT = [{"key": "Accept",
              "value": "application/vnd.quipu.rdf.meta-data+json;version=1.0.0"}]


def graph_builder_js(version_name="v1"):
    """JS lines that build the FULL UI-shaped schema graph into _graphNodes/_graphLinks.

    Mirrors exactly what the schema-editor UI POSTs to /schema-graph (confirmed from a
    real browser capture). Reads accumulated raw fetch-data-source responses from
    _dsMetaList and, per datasource, emits:
      data_source -has_tables-> table -has_property-> property(column)
      Version     -Has_Node->  Node(entity) -has_node_property-> Node Property -maps_to_column-> property
    The critical rule: nodeId = schemaPrefix + uri, so every node's nodeId starts with the
    schema prefix — GET /schema-graph?versionUri= derives that prefix and returns only
    matching nodes. Also sets _versionUri = schemaPrefix + 'Version#<version_name>'.
    """
    return [
        "const P=pm.collectionVariables.get('schemaPrefix')||pm.collectionVariables.get('_dsPrefix')||'pmflow';",
        f"const VNAME='{version_name}'; const versionUri=P+'Version#'+VNAME;",
        "pm.collectionVariables.set('_versionUri', versionUri);",
        "// URL-encoded form for query params — versionUri contains '#' which must be %23",
        "pm.collectionVariables.set('_versionUriEnc', encodeURIComponent(versionUri));",
        "const DT={int8:'BIGINT',int4:'INTEGER',int2:'SMALLINT',serial:'INTEGER',bigserial:'BIGINT',varchar:'VARCHAR',bpchar:'VARCHAR',char:'VARCHAR',text:'VARCHAR',bool:'BOOLEAN',float8:'DOUBLE',float4:'FLOAT',numeric:'DECIMAL',decimal:'DECIMAL',timestamp:'TIMESTAMP',timestamptz:'TIMESTAMP',date:'DATE',time:'TIME',uuid:'VARCHAR',json:'VARCHAR',jsonb:'VARCHAR'};",
        "function nid(u){return P+u;}",
        "let metaList=[]; try{metaList=JSON.parse(pm.collectionVariables.get('_dsMetaList')||'[]');}catch(e){}",
        "const nodes=[{node_type:'Version',id:versionUri,uri:versionUri,nodeId:versionUri,label:VNAME,tags:[],description:''}];",
        "const links=[];",
        "metaList.forEach(meta=>{",
        "  const edges=(meta&&meta.hasTableEdges)||[];",
        "  if(edges.length===0) return;",
        "  const t0=edges[0].tableNode||{}; const tshort=t0.nodeId||''; const segs=tshort.split(':');",
        "  const dsName=segs[segs.length-2]||'ds'; const dsShort=segs.slice(0,-1).join(':');",
        "  const driver=(segs[segs.length-3]||'postgres').toUpperCase();",
        "  const dsIdVal=(meta&&meta._dsId!=null)?parseInt(meta._dsId):null;",
        "  const entPrefix='http://'+dsName+'.in/';",
        "  // dataSourceID is REQUIRED — without it the stream generator resolves the Trino catalog to",
        "  // 'unknown' and ingestion fails ('Schema unknown does not exist').",
        "  nodes.push({node_type:'data_source',id:dsShort,node_id:dsShort,uri:dsShort,nodeId:nid(dsShort),label:dsName,driverType:driver,driver_type:driver,dataSourceID:dsIdVal});",
        "  edges.forEach(te=>{",
        "    const tn=te.tableNode||{}; const tShort=tn.nodeId; const tLong=tn.uri; const tLabel=tn.label;",
        "    if(!tShort||!tLong) return;",
        "    nodes.push({node_type:'table',id:tShort,node_id:tShort,uri:tLong,nodeId:nid(tLong),label:tLabel});",
        "    links.push({source:dsShort,target:tShort,relationship:'has_tables',direction:'FORWARD'});",
        "    const entUri=entPrefix+'Node#'+tLabel;",
        "    nodes.push({node_type:'Node',id:entUri,uri:entUri,nodeId:nid(entUri),label:tLabel,entityLabel:tLabel,namedEntity:false,prefix:entPrefix,tags:[]});",
        "    links.push({source:versionUri,target:entUri,relationship:'Has_Node',direction:'FORWARD',node_uri:versionUri});",
        "    (tn.hasPropertyEdges||[]).forEach(pe=>{",
        "      const pn=pe.propertyNode||{}; const cShort=pn.nodeId; const cLong=pn.uri; const cLabel=pn.label;",
        "      if(!cShort||!cLong) return;",
        "      const rawdt=(pn.dataType||'').toLowerCase();",
        "      nodes.push({node_type:'property',id:cShort,node_id:cShort,uri:cLong,nodeId:nid(cLong),label:cLabel,dataType:pn.dataType,data_type:pn.dataType,primaryKey:!!pn.primaryKey,primary_key:!!pn.primaryKey,uniqueKey:!!pn.uniqueKey,foreignKey:!!pn.foreignKey,nullable:pn.nullable!==false});",
        "      links.push({source:tShort,target:cShort,relationship:'has_property',direction:'FORWARD'});",
        "      const npUri=entPrefix+'NodeProperty#'+tLabel+'#'+cLabel;",
        "      const ndt=DT[rawdt]||(pn.dataType||'VARCHAR').toUpperCase();",
        "      nodes.push({node_type:'Node Property',id:npUri,uri:npUri,nodeId:nid(npUri),label:cLabel,dataType:ndt,data_type:ndt,primaryKey:!!pn.primaryKey,primary_key:!!pn.primaryKey,uniqueKey:!!pn.uniqueKey,tags:[]});",
        "      links.push({source:entUri,target:npUri,relationship:'has_node_property',direction:'FORWARD',node_uri:entUri,prefix:entPrefix});",
        "      links.push({source:npUri,target:cShort,relationship:'maps_to_column',direction:'FORWARD',node_uri:entUri});",
        "    });",
        "    // MONGO: fetch-data-source returns 0 columns — synthesize property/NodeProperty nodes",
        "    // from the shapeCypher fields captured in _mongoShape by the Create Mongo DS step.",
        "    if(driver==='MONGO' && (tn.hasPropertyEdges||[]).length===0){",
        "      let mshape={}; try{mshape=JSON.parse(pm.collectionVariables.get('_mongoShape')||'{}');}catch(e){}",
        "      (mshape[tLabel]||[]).forEach(fld=>{",
        "        const cShort=tShort+':'+fld; const cLong=tLong+':'+fld; const ndt='VARCHAR';",
        "        nodes.push({node_type:'property',id:cShort,node_id:cShort,uri:cLong,nodeId:nid(cLong),label:fld,dataType:ndt,data_type:ndt,primaryKey:false,primary_key:false,uniqueKey:false,foreignKey:false,nullable:true});",
        "        links.push({source:tShort,target:cShort,relationship:'has_property',direction:'FORWARD'});",
        "        const npUri=entPrefix+'NodeProperty#'+tLabel+'#'+fld;",
        "        nodes.push({node_type:'Node Property',id:npUri,uri:npUri,nodeId:nid(npUri),label:fld,dataType:ndt,data_type:ndt,primaryKey:false,primary_key:false,uniqueKey:false,tags:[]});",
        "        links.push({source:entUri,target:npUri,relationship:'has_node_property',direction:'FORWARD',node_uri:entUri,prefix:entPrefix});",
        "        links.push({source:npUri,target:cShort,relationship:'maps_to_column',direction:'FORWARD',node_uri:entUri});",
        "      });",
        "    }",
        "  });",
        "});",
        "// FULL-FIDELITY stamping — make every node match the shape the UICore schema editor",
        "// persists (verified against a working DemoTest read-back). The UI's canvas nodes carry",
        "// these fields (from the server-side entity fetch) and round-trip them on POST /schema-graph;",
        "// our fabricated nodes must set them explicitly or they persist as null.",
        "const _sidRaw=pm.collectionVariables.get('schemaId');",
        "const _sid=(_sidRaw&&!isNaN(_sidRaw))?parseInt(_sidRaw):(_sidRaw||'');",
        "const _TEN=pm.environment.get('tenant_id')||'eksquipu';",
        "const _USER=pm.collectionVariables.get('test_username')||pm.environment.get('test_username')||_TEN;",
        "function _uuid(){return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,function(c){var r=Math.random()*16|0,v=c==='x'?r:(r&0x3|0x8);return v.toString(16);});}",
        "nodes.forEach(n=>{",
        "  n.schemaId=_sid;",
        "  if(n.node_type==='Version') return;",  # Version: only schemaId/description/tags (already set)
        "  n.identity=_uuid();",
        "  n.tenantId=_TEN; n.tenant_id=_TEN; n.createdBy=_USER; n.created_by=_USER;",
        "  if(n.description===undefined) n.description='';",
        "  if(n.node_type==='property'){ n.primary_key=!!n.primaryKey; n.foreign_key=!!n.foreignKey; n.unique_key=!!n.uniqueKey; }",
        "  if(n.node_type==='Node'){ n.entity_label=n.entityLabel; n.named_entity=!!n.namedEntity; n.updatedBy=_USER; n.updated_by=_USER; }",
        "  if(n.node_type==='Node Property'){ n.primary_key=!!n.primaryKey; n.unique_key=!!n.uniqueKey; n.alternateLabel=false; n.alternate_label=false; n.preferredLabel=false; n.preferred_label=false; n.freeText=false; n.timeLabel=false; n.time_label=false; n.timeFormat=''; n.time_format=''; }",
        "});",
        "pm.collectionVariables.set('_graphNodes', JSON.stringify(nodes));",
        "pm.collectionVariables.set('_graphLinks', JSON.stringify(links));",
        "console.log('Built UI schema graph: '+nodes.length+' nodes, '+links.length+' links (schemaId='+_sid+', full-fidelity)');",
    ]


def create_ds_step(step, base="app_base_url"):
    """Create datasource and capture ID + catalog name."""
    return req(f"{step} Create DataSource", "POST", "/datasource",
        [f"const code=pm.response.code;",
         f"pm.test('{step} DS 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const d=b.dataSourceModel||b.data||b;",
         "if(d.id||d.sourceId) pm.collectionVariables.set('dsId', String(d.id||d.sourceId));",
         "if(d.dataCatalogName) pm.collectionVariables.set('dataCatalogName', d.dataCatalogName);",
         "// Extract dsName from dataCatalogName for metadata lookup",
         "const cat=d.dataCatalogName||'';",
         "// dataCatalogName format: 'tenant::urn:li:dataset:type:name_schema'",
         "// metadata API needs the last segment (name_schema part)",
         "const parts=cat.split(':');",
         "const dsName=parts.length>0?parts[parts.length-1]:'';",
         "if(dsName) pm.collectionVariables.set('dsMetaName', dsName);",
         "console.log('dsMetaName='+dsName);",
         f"console.log('DS id='+(d.id||d.sourceId)+', catalog='+cat);"],
        base=base, body={"name": "x"},
        prerequest=[
            "// Build the JDBC datasource body dynamically. dbPort is OMITTED when empty — snowflake",
            "// has no port, and sending dbPort:'' makes the server 400 'Failed to read request'",
            "// (Jackson can't deserialize '' into an Integer).",
            "const g=k=>pm.variables.get(k)||pm.environment.get(k)||'';",
            "const body={name:'pm_flow_ds_'+Date.now(),driverType:g('driverType'),dbHostName:g('dbHost'),"
            "databaseName:g('dbName'),dbUserName:g('dbUser'),dbPassword:g('dbPassword'),"
            "aesRandomIV:g('aesRandomIV'),dbSchema:g('dbSchema'),driverClassName:g('driverClassName'),deleted:false};",
            "const port=String(g('dbPort')).trim();",
            "if(port!=='' && !isNaN(port)){ body.dbPort=parseInt(port); }",
            "pm.request.body.raw=JSON.stringify(body);",
        ])


def fetch_entities_step(step, base="app_base_url"):
    """Fetch real entities via POST /metadata-graph/fetch-data-source, then extract datasets.
    Falls back to GET /metadata/datasource if available.
    """
    return req(f"{step} Fetch DS Entities", "POST", "/metadata-graph/fetch-data-source",
        [f"pm.test('{step} Graph 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "// Build dsPrefix from datasource name (DS-side entity namespace — unchanged).",
         "const dsName=pm.collectionVariables.get('dsMetaName')||'pmflow';",
         "const dsPrefix='http://'+dsName.toLowerCase().replace(/[^a-z0-9_]/g,'_')+'.in/';",
         "pm.collectionVariables.set('_dsPrefix', dsPrefix);",
         "// Accumulate raw DS metadata for the UI schema-graph builder (supports multi-DS).",
         "// Tag with _dsId so the builder can set dataSourceID (needed for Trino catalog resolution).",
         "b._dsId = pm.collectionVariables.get('dsId');",
         "let metaList=[]; try{metaList=JSON.parse(pm.collectionVariables.get('_dsMetaList')||'[]');}catch(e){}",
         "metaList.push(b);",
         "pm.collectionVariables.set('_dsMetaList', JSON.stringify(metaList));",
         "// Extract entities from graph response (hasTableEdges → tableNode)",
         "let nodes=[];",
         "// Primary: hasTableEdges[].tableNode — from metadata-graph/fetch-data-source",
         "const tableEdges=b.hasTableEdges||[];",
         "if(tableEdges.length>0){",
         "  nodes=tableEdges.map((te,i)=>{",
         "    const tn=te.tableNode||{};",
         "    const label=tn.label||'table_'+i;",
         "    const props=(tn.hasPropertyEdges||[]).map(pe=>{const pn=pe.propertyNode||pe.columnNode||{}; return {name:pn.label||'',type:pn.dataType||'STRING'};});",
         "    return {id:dsPrefix+'Node#'+label,label:label,node_type:'Node',prefix:dsPrefix,properties:props};",
         "  });",
         "}",
         "// Secondary: hasEntityEdges[].entityNode",
         "if(nodes.length===0){",
         "  const entityEdges=b.hasEntityEdges||[];",
         "  nodes=entityEdges.map((ee,i)=>{const en=ee.entityNode||{}; return {id:dsPrefix+'Node#'+(en.label||'entity_'+i),label:en.label||'entity_'+i,node_type:'Node',prefix:dsPrefix,properties:[]};});",
         "}",
         "// Tertiary: dataSets format",
         "if(nodes.length===0){",
         "  const datasets=b.dataSets||b.datasets||[];",
         "  nodes=datasets.map((ds,i)=>{const label=(ds.name&&ds.name.name)||ds.name||'entity_'+i; return {id:dsPrefix+'Node#'+label,label:label,node_type:'Node',prefix:dsPrefix,properties:[]};});",
         "}",
         "const links=(nodes.length>1)?[{source:nodes[0].id,target:nodes[1].id,label:'related_to'}]:[];",
         "pm.collectionVariables.set('_graphNodes', JSON.stringify(nodes));",
         "pm.collectionVariables.set('_graphLinks', JSON.stringify(links));",
         f"console.log('Entities: '+nodes.length+' from DS graph');"],
        base=base, body={"uri": "{{dataCatalogName}}"})


def create_schema_step(step, name_prefix="pm_flow", base="app_base_url"):
    """Create schema with prefix."""
    return req(f"{step} Create Schema", "POST", "/schema",
        [f"const code=pm.response.code;",
         f"pm.test('{step} Schema 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const d=b.schemaModel||b.data||b;",
         "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
         "if(d.id||d.schemaId) pm.collectionVariables.set('schemaId', String(d.id||d.schemaId));",
         "if(d.prefix) pm.collectionVariables.set('schemaPrefix', d.prefix);",
         "console.log('Schema: '+(d.name||d.schemaName)+', prefix='+(d.prefix||''));"],
        base=base, body={"schemaName": "x", "prefix": "x"},
        prerequest=[
            f"const schemaName='{name_prefix}_schema_'+Date.now();",
            "// prefix = schema name, hyphenated (letters/digits/hyphen) — the schema's ingest-namespace URI.",
            "const prefix=schemaName.replace(/_/g,'-');",
            "pm.collectionVariables.set('schemaPrefix', prefix);",
            "pm.request.body.raw=JSON.stringify({schemaName:schemaName,prefix:prefix,description:'Auto-created by FLOW'});",
        ])


def save_schema_version_step(step, kg_base="kg_base_url", ds_id_vars=("dsId",)):
    """STEP 1/2 — KG save-schema-version: creates the version + stores the graph blob in
    MinIO (drives versioning/ingestion). Builds the full UI-shaped graph first and reuses
    it as the schemaGraph string. Captures versionId + _versionUri.
    """
    ids_js = "const ids=[]; " + " ".join(
        f"(function(){{const v=parseInt(pm.collectionVariables.get('{v}'));if(v&&!isNaN(v))ids.push(v);}})();"
        for v in ds_id_vars)
    return req(f"{step} Save Schema Version (version+MinIO)", "POST", "/metadata/save-schema-version",
        [f"const code=pm.response.code;",
         f"pm.test('{step} 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const vid=b.versionId||b.id;",
         "if(vid) pm.collectionVariables.set('versionId', String(vid));",
         "if(b.awsVersionId) pm.collectionVariables.set('awsVersionId', b.awsVersionId);",
         f"pm.test('{step} version created', () => pm.expect(vid).to.not.be.undefined);",
         "let nc=0; try{nc=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]').length;}catch(e){}",
         "console.log('Schema version saved: versionId='+vid+', '+nc+' graph nodes');"],
        base=kg_base, extra_headers=KG_ACCEPT, body={"schemaName": ""},
        prerequest=graph_builder_js() + [
            "const sn=pm.collectionVariables.get('schemaName');",
            "// P is already declared by graph_builder_js above",
            ids_js,
            "let n=[]; try{n=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]');}catch(e){}",
            "let l=[]; try{l=JSON.parse(pm.collectionVariables.get('_graphLinks')||'[]');}catch(e){}",
            "const gs=JSON.stringify({directed:true,multigraph:true,graph:{},prefix:P,nodes:n,links:l});",
            "const body={schemaGraph:gs,schemaName:sn,newSchemaName:null,awsVersionId:null,versionsModel:{versionName:'v1',description:'FLOW version',latest:true,deleted:false,defaultVersion:true,versionLocked:false,dataSourceIds:ids,entity360Flows:[]}};",
            "pm.request.body.raw=JSON.stringify(body);",
        ])


def save_schema_graph_ui_step(step, base="app_base_url"):
    """STEP 2/2 — applicationService /schema-graph: MERGE the UI-shaped nodes/links into the
    Neo4j :SchemaEntity graph the schema-editor canvas reads. schemaUri = versionUri.
    """
    return req(f"{step} Save Schema Graph (UI/Neo4j)", "POST", "/schema-graph",
        [f"const code=pm.response.code;",
         f"pm.test('{step} 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201,204]); }});",
         "console.log('UI schema-graph merged for '+pm.collectionVariables.get('_versionUri'));"],
        base=base, body={"schemaUri": ""},
        prerequest=[
            "const vu=pm.collectionVariables.get('_versionUri');",
            "let n=[]; try{n=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]');}catch(e){}",
            "let l=[]; try{l=JSON.parse(pm.collectionVariables.get('_graphLinks')||'[]');}catch(e){}",
            "pm.request.body.raw=JSON.stringify({schemaUri:vu,nodes:n,links:l});",
        ])


def verify_schema_graph_step(step, base="app_base_url"):
    """Read the graph back through the same endpoint the UI canvas uses — real proof
    that entities are visible in the schema."""
    return req(f"{step} Verify Schema Graph (UI read)", "GET",
        "/schema-graph?versionUri={{_versionUriEnc}}&includeEmbeddings=false",
        [f"pm.test('{step} 200', () => pm.response.to.have.status(200));",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const ns=b.nodes||[];",
         "const entities=ns.filter(n=>n.node_type==='Node');",
         f"pm.test('{step} has entities', () => pm.expect(entities.length).to.be.above(0));",
         "console.log('UI schema-graph read back: '+ns.length+' nodes, '+entities.length+' entities');"],
        base=base)


# ── Entity-layer schema build (product-faithful) ─────────────────────────────
# Instead of fabricating the schema graph client-side (graph_builder_js), create each business
# entity one-by-one via POST /entity so the SERVER stamps identity/tenant/createdBy and links each
# Node Property to its physical column. Then assemble the schema graph from the fully-stamped
# entity-graph (datasource-subgraph per DS) and save it (+versionsModel). Mirrors the UI.

# Postgres/generic raw type -> canonical Node-Property dataType (matches the server's output, where
# every integer family collapses to BIGINT).
ENTITY_DT_JS = (
    "const _DT={int8:'BIGINT',int4:'BIGINT',int2:'BIGINT',serial:'BIGINT',bigserial:'BIGINT',"
    "smallserial:'BIGINT',numeric:'DECIMAL',decimal:'DECIMAL',float8:'DOUBLE',float4:'DOUBLE',"
    "bool:'BOOLEAN',timestamp:'TIMESTAMP',timestamptz:'TIMESTAMP',date:'DATE',time:'TIME',"
    "json:'JSON',jsonb:'JSON',uuid:'VARCHAR',bytea:'VARBINARY'};"
    "function cdt(t){t=(t||'').toLowerCase();return _DT[t]||(t?t.toUpperCase():'VARCHAR');}")


def create_entities_loop_step(step, base="app_base_url"):
    """Self-looping step: create ONE business entity per table across ALL datasources in
    _dsMetaList via POST /entity. Advances _entIdx and setNextRequest's itself until every table
    (flattened across datasources) has an entity. Mongo columns are synthesized from _mongoShape."""
    name = f"{step} Create Entity"
    return req(name, "POST", "/entity",
        ["const code=pm.response.code;",
         f"pm.test('{step} entity 2xx (idx '+(pm.collectionVariables.get('_entIdx')||'0')+')', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const i=parseInt(pm.collectionVariables.get('_entIdx')||'0');",
         "let meta=[]; try{meta=JSON.parse(pm.collectionVariables.get('_dsMetaList')||'[]');}catch(e){}",
         "let flat=[]; meta.forEach(m=>{(m.hasTableEdges||[]).forEach(te=>flat.push(te));});",
         "console.log('entity['+i+'/'+flat.length+'] created: '+(b.entityUri||'?')+' props='+((b.properties||[]).length));",
         "const next=i+1;",
         f"if(next<flat.length){{ pm.collectionVariables.set('_entIdx', String(next)); postman.setNextRequest('{name}'); }}",
         "else { pm.collectionVariables.set('_entCount', String(flat.length)); pm.collectionVariables.unset('_entIdx'); console.log('ALL '+flat.length+' entities created'); }"],
        base=base, body={"label": "x"},
        prerequest=[
            ENTITY_DT_JS,
            "let meta=[]; try{meta=JSON.parse(pm.collectionVariables.get('_dsMetaList')||'[]');}catch(e){}",
            "let flat=[]; meta.forEach(m=>{(m.hasTableEdges||[]).forEach(te=>flat.push(te));});",
            "const i=parseInt(pm.collectionVariables.get('_entIdx')||'0');",
            "const te=flat[i]||{}; const tn=te.tableNode||{};",
            "const tShort=tn.nodeId||''; const segs=tShort.split(':');",
            "const dsName=segs[segs.length-2]||'ds'; const dsUrn=segs.slice(0,-1).join(':');",
            "const driver=(segs[segs.length-3]||'postgres').toUpperCase();",
            "const entPrefix='http://'+dsName+'.in/';",
            "let cols=(tn.hasPropertyEdges||[]).map(pe=>pe.propertyNode||{});",
            "let props=cols.map(c=>({label:c.label,dataType:cdt(c.dataType),primaryKey:!!c.primaryKey,uniqueKey:!!c.uniqueKey,foreignKey:!!c.foreignKey,nullable:c.nullable!==false,mappedColumnUri:(c.nodeId||c.node_id||c.uri),mappedColumnUris:[(c.nodeId||c.node_id||c.uri)]}));",
            "// MONGO: fetch-data-source returns 0 columns — synthesize from the captured shapeCypher fields.",
            "if(driver==='MONGO' && props.length===0){ let ms={}; try{ms=JSON.parse(pm.collectionVariables.get('_mongoShape')||'{}');}catch(e){} (ms[tn.label]||[]).forEach(f=>{ const cu=tShort+':'+f; props.push({label:f,dataType:'VARCHAR',primaryKey:false,uniqueKey:false,foreignKey:false,nullable:true,mappedColumnUri:cu,mappedColumnUris:[cu]}); }); }",
            "const body={label:tn.label,prefix:entPrefix,dataSourceUri:dsUrn,namedEntity:false,description:'',tags:[],properties:props};",
            "pm.request.body.raw=JSON.stringify(body);",
        ])


def save_schema_graph_from_entities_step(step, base="app_base_url", ds_id_vars=("dsId",)):
    """Assemble the schema graph from the server-stamped entity-graph: GET
    entity-graph/datasource-subgraph for each datasource, merge, stamp schema nodeId+schemaId, add
    the Version node + Has_Node links, then POST /schema-graph (+versionsModel) to mint versionId.
    All fetch+save happens in one closure (sendRequest) to avoid collection-var body corruption."""
    ids_js = "const ids=[]; " + " ".join(
        f"(function(){{const v=parseInt(pm.collectionVariables.get('{v}'));if(v&&!isNaN(v))ids.push(v);}})();"
        for v in ds_id_vars)
    return req(f"{step} Save Schema Graph from Entities", "GET", "/actuator/health",
        [f"pm.test('{step} health', () => pm.response.to.have.status(200));",
         "const P=pm.collectionVariables.get('schemaPrefix'); const sn=pm.collectionVariables.get('schemaName');",
         "const sidRaw=pm.collectionVariables.get('schemaId'); const sid=(sidRaw&&!isNaN(sidRaw))?parseInt(sidRaw):sidRaw;",
         "let meta=[]; try{meta=JSON.parse(pm.collectionVariables.get('_dsMetaList')||'[]');}catch(e){}",
         "const dsUrns=[]; meta.forEach(m=>{const te=(m.hasTableEdges||[])[0]; if(te&&te.tableNode){const segs=(te.tableNode.nodeId||'').split(':'); const uu=segs.slice(0,-1).join(':'); if(uu&&dsUrns.indexOf(uu)<0)dsUrns.push(uu);}});",
         ids_js,
         "const app=pm.environment.get('app_base_url');",
         "const hdr={'Authorization':'Bearer '+(pm.collectionVariables.get('access_token')||pm.environment.get('access_token')),'X-TENANT-ID':pm.environment.get('tenant_id'),'Content-Type':'application/json'};",
         "let nodes=[]; let links=[];",
         "function finalize(){",
         "  const VN=P+'Version#v1';",
         "  nodes.forEach(n=>{ n.nodeId=P+(n.uri||n.id||''); n.schemaId=sid; });",
         "  nodes.push({node_type:'Version',id:VN,uri:VN,nodeId:VN,label:'v1',schemaId:sid,tags:[],description:''});",
         "  nodes.filter(n=>n.node_type==='Node').forEach(en=>{ links.push({source:VN,target:(en.id||en.uri),relationship:'Has_Node',direction:'FORWARD',node_uri:VN}); });",
         "  pm.collectionVariables.set('_versionUri', VN); pm.collectionVariables.set('_versionUriEnc', encodeURIComponent(VN));",
         "  const body={prefix:P,schemaName:sn,schemaUri:P+'Schema#'+sn,nodes:nodes,links:links,versionsModel:{versionName:'v1',description:'',defaultVersion:false,latest:true,deleted:false,versionLocked:false,dataSourceIds:ids,entity360Flows:[]}};",
         "  pm.sendRequest({url:app+'/schema-graph', method:'POST', header:hdr, body:{mode:'raw', raw:JSON.stringify(body)}}, (e,r)=>{",
         "    const ok=r&&[200,201].includes(r.code);",
         f"    pm.test('{step} schema-graph saved 2xx', () => {{ if(!ok){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(ok).to.be.true; }});",
         "    let rb={}; try{rb=r.json();}catch(x){}",
         "    const vid=rb.versionId||rb.id; if(vid) pm.collectionVariables.set('versionId', String(vid));",
         "    const ent=nodes.filter(n=>n.node_type==='Node').length;",
         "    console.log('schema-graph saved from '+ent+' entities ('+nodes.length+' nodes, '+dsUrns.length+' DS) versionId='+vid);",
         "  });",
         "}",
         "function fetchNext(k){",
         "  if(k>=dsUrns.length){ finalize(); return; }",
         "  pm.sendRequest({url:app+'/entity-graph/datasource-subgraph?uri='+encodeURIComponent(dsUrns[k]), method:'GET', header:hdr}, (e,r)=>{",
         "    let g={}; try{g=r.json();}catch(x){}",
         "    (g.nodes||[]).forEach(n=>nodes.push(n)); (g.links||[]).forEach(l=>links.push(l));",
         "    fetchNext(k+1);",
         "  });",
         "}",
         "if(!P){ pm.test('"+step+" prefix present', () => pm.expect(P,'schemaPrefix').to.be.ok); } else { fetchNext(0); }"],
        base=base)


def create_entity_schema_graph_step(step, base="app_base_url", ds_id_vars=("dsId",)):
    """Product-faithful replacement for create_schema_graph_step: create entities one-by-one via
    POST /entity (server stamps identity/tenant/FK-ready), assemble the schema graph from the
    entity-graph, save (+versionsModel), verify. Returns a LIST of steps — splice with * ."""
    return [
        create_entities_loop_step(f"{step}a", base),
        save_schema_graph_from_entities_step(f"{step}b", base, ds_id_vars),
        verify_schema_graph_step(f"{step}c", base),
    ]


def save_schema_graph_version_step(step, base="app_base_url", ds_id_vars=("dsId",)):
    """Build the graph and create the schema VERSION in ONE call: applicationService
    /schema-graph with a versionsModel. This is what the UI does — it saves to Neo4j and MINTS
    the versionId in the response. Replaces the KG save-schema-version (MinIO), which the UI does
    NOT use (and which returns an empty 200 when MinIO is unavailable)."""
    ids_js = "const ids=[]; " + " ".join(
        f"(function(){{const v=parseInt(pm.collectionVariables.get('{v}'));if(v&&!isNaN(v))ids.push(v);}})();"
        for v in ds_id_vars)
    return req(f"{step} Save Schema Graph + Version (Neo4j)", "POST", "/schema-graph",
        [f"const code=pm.response.code;",
         f"pm.test('{step} 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const vid=b.versionId||b.id;",
         "if(vid) pm.collectionVariables.set('versionId', String(vid));",
         f"pm.test('{step} version created', () => pm.expect(vid, 'versionId from /schema-graph').to.not.be.undefined);",
         "let nc=0; try{nc=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]').length;}catch(e){}",
         "console.log('Schema graph saved + version minted: versionId='+vid+', '+nc+' nodes');"],
        base=base, body={"schemaName": ""},
        prerequest=graph_builder_js() + [
            "const sn=pm.collectionVariables.get('schemaName');",
            "// P is already declared by graph_builder_js above",
            "const schemaUri=P+'Schema#'+sn;",
            ids_js,
            "let n=[]; try{n=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]');}catch(e){}",
            "let l=[]; try{l=JSON.parse(pm.collectionVariables.get('_graphLinks')||'[]');}catch(e){}",
            "const body={prefix:P,schemaName:sn,schemaUri:schemaUri,nodes:n,links:l,versionsModel:{versionName:'v1',description:'',defaultVersion:false,latest:true,deleted:false,versionLocked:false,dataSourceIds:ids,entity360Flows:[]}};",
            "pm.request.body.raw=JSON.stringify(body);",
        ])


def create_schema_graph_step(step, base="app_base_url", kg_base="kg_base_url",
                             ds_id_vars=("dsId",)):
    """Correct schema-graph persistence. Returns a LIST of steps:
    /schema-graph + versionsModel (Neo4j, mints versionId) -> verify. Splice with * .
    ds_id_vars: collection-variable names holding datasource ids to attach to the version.
    (kg_base kept for signature compatibility; the KG/MinIO save-schema-version is no longer used.)
    """
    return [
        save_schema_graph_version_step(f"{step}i", base, ds_id_vars),
        verify_schema_graph_step(f"{step}iii", base),
    ]


def create_realm_step(step, name_prefix="pm_flow", base="app_base_url"):
    """Create realm with schemaName + versionId."""
    return req(f"{step} Create Realm", "POST", "/realm",
        [f"const code=pm.response.code;",
         f"pm.test('{step} Realm 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const d=b.realmModel||b.data||b;",
         "if(d.id||d.realmId) pm.collectionVariables.set('realmId', String(d.id||d.realmId));",
         "if(d.name||d.realmName) pm.collectionVariables.set('realmName', d.name||d.realmName);",
         "console.log('Realm id='+(d.id||d.realmId));"],
        base=base, body={"name": "x"},
        prerequest=[
            f"pm.request.body.raw=JSON.stringify({{name:'{name_prefix}_realm_'+Date.now(),description:'FLOW realm',schemaName:pm.collectionVariables.get('schemaName'),versionId:parseInt(pm.collectionVariables.get('versionId'))}});",
        ])


def full_setup_steps(step_prefix="01", name_prefix="pm_flow", include_realm=True, base="app_base_url"):
    """Full setup: DS → Fetch Entities → Schema (with prefix) → Schema-Graph (version+entities) → Realm.

    Returns list of steps.
    """
    p = step_prefix
    steps = [
        create_ds_step(f"{p}a", base),
        fetch_entities_step(f"{p}b", base),
        create_schema_step(f"{p}c", name_prefix, base),
        *create_schema_graph_step(f"{p}d", base),
    ]
    if include_realm:
        steps.append(create_realm_step(f"{p}e", name_prefix, base))
    return steps


SKIP_CLEANUP_PRE = [
    "// Check skip_cleanup flag — if true, skip this cleanup step",
    "if(pm.environment.get('skip_cleanup')==='true'||pm.collectionVariables.get('skip_cleanup')==='true'){",
    "  console.log('SKIP CLEANUP: '+pm.info.requestName);",
    "  pm.request.url=pm.collectionVariables.get('_skip_url')||pm.environment.get('app_base_url')+'/actuator/health';",
    "  return;",
    "}",
]


SKIP_CLEANUP_TEST = "if(pm.environment.get('skip_cleanup')==='true'||pm.collectionVariables.get('skip_cleanup')==='true'){pm.test('SKIPPED (skip_cleanup=true)',()=>{}); return;}"


def realm_delete_prereq(realm_var="realmId"):
    """JS to set the realm-delete URL honoring the hardDelete env flag.
    Default permanent=false (soft) — permanent=true needs the memory_space migration V42-V44
    on the tenant DB, else the server 500s on `relation "memory_space" does not exist`."""
    return [
        "const hard=String(pm.environment.get('hardDelete')||'false')==='true';",
        f"if(pm.collectionVariables.get('{realm_var}')) pm.request.url=pm.environment.get('app_base_url')+'/realm/'+pm.collectionVariables.get('{realm_var}')+'?permanent='+hard;",
    ]


def cleanup_steps(start_num=90, include_realm=True, base="app_base_url"):
    """Cleanup steps in reverse order. Skipped when skip_cleanup=true."""
    steps = []
    n = start_num
    if include_realm:
        steps.append(req(f"{n} Del Realm", "DELETE", "/realm/{{realmId}}",
            [SKIP_CLEANUP_TEST, f"pm.test('{n} ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, prerequest=SKIP_CLEANUP_PRE + realm_delete_prereq()))
        n += 1
    steps.append(req(f"{n} Del Graph", "DELETE", "/schema-graph?prefix={{schemaPrefix}}",
        [SKIP_CLEANUP_TEST, f"pm.test('{n} ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
        base=base, prerequest=SKIP_CLEANUP_PRE))
    n += 1
    steps.append(req(f"{n} Del Version", "DELETE", "/versions/delete?versionId={{versionId}}",
        [SKIP_CLEANUP_TEST, f"pm.test('{n} ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
        base=base, prerequest=SKIP_CLEANUP_PRE))
    n += 1
    steps.append(req(f"{n} Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
        [SKIP_CLEANUP_TEST, f"pm.test('{n} ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
        base=base, prerequest=SKIP_CLEANUP_PRE))
    n += 1
    steps.append(req(f"{n} Del DS", "DELETE", "/datasource/{{dsId}}",
        [SKIP_CLEANUP_TEST, f"pm.test('{n} ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
        base=base, prerequest=SKIP_CLEANUP_PRE))
    return steps


def teardown_step(base="app_base_url"):
    """Final teardown — always runs, respects skip_cleanup."""
    return req("99 Teardown", "DELETE", "/realm/{{realmId}}",
        [SKIP_CLEANUP_TEST,
         "pm.test('99 teardown', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
         "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
        base=base, skip_on_fail=False,
        prerequest=SKIP_CLEANUP_PRE + realm_delete_prereq())


SETUP_VARS = [
    {"key": "dsId", "value": "", "type": "string"},
    {"key": "dataCatalogName", "value": "", "type": "string"},
    {"key": "dsMetaName", "value": "", "type": "string"},
    {"key": "schemaName", "value": "", "type": "string"},
    {"key": "schemaId", "value": "", "type": "string"},
    {"key": "schemaPrefix", "value": "", "type": "string"},
    {"key": "versionId", "value": "", "type": "string"},
    {"key": "realmId", "value": "", "type": "string"},
    {"key": "realmName", "value": "", "type": "string"},
    {"key": "_dsPrefix", "value": "", "type": "string"},
    {"key": "_graphNodes", "value": "", "type": "string"},
    {"key": "_graphLinks", "value": "", "type": "string"},
    {"key": "_dsMetaList", "value": "", "type": "string"},
    {"key": "_versionUri", "value": "", "type": "string"},
    {"key": "_versionUriEnc", "value": "", "type": "string"},
    {"key": "awsVersionId", "value": "", "type": "string"},
]

SETUP_CLEAR_VARS = ["dsId", "dataCatalogName", "dsMetaName", "schemaName", "schemaId",
                    "schemaPrefix", "versionId", "realmId", "realmName",
                    "_dsPrefix", "_graphNodes", "_graphLinks",
                    "_dsMetaList", "_versionUri", "_versionUriEnc", "awsVersionId"]
