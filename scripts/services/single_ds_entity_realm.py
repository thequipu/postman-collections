"""FLOW-SingleDS-EntityLayer-Realm: build the schema the PRODUCT way — create each business
entity one-by-one via POST /entity (entity layer), then assemble the schema graph from the
server-stamped entity-graph (datasource-subgraph) instead of fabricating nodes client-side.

Contrast with FLOW-SingleDS-Realm (which fabricates the /schema-graph payload in graph_builder_js
and lands 0 rows). Here:
  DS -> entities metadata -> schema -> POST /entity per table (loop, server stamps identity/tenant)
  -> GET entity-graph/datasource-subgraph (fully-stamped nodes) -> POST /schema-graph (+versionsModel)
  -> realm -> namespace (wait UP) -> generate streams -> SAVE + event/ingest -> strict verify.

Point it at a specific DB via env-vars (same as FLOW-SingleDS-Realm). Any stream that does not land
rows fails the flow.
"""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import (create_ds_step, fetch_entities_step, SETUP_VARS, SETUP_CLEAR_VARS)


_SKIP = ["if(pm.environment.get('skip_cleanup')==='true'||pm.collectionVariables.get('skip_cleanup')==='true'){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }"]

# Postgres raw type -> canonical Node-Property dataType (matches the server's suggested-schema output,
# where every integer family collapses to BIGINT).
_DT = ("const DT={int8:'BIGINT',int4:'BIGINT',int2:'BIGINT',serial:'BIGINT',bigserial:'BIGINT',"
       "smallserial:'BIGINT',numeric:'DECIMAL',decimal:'DECIMAL',float8:'DOUBLE',float4:'DOUBLE',"
       "bool:'BOOLEAN',timestamp:'TIMESTAMP',timestamptz:'TIMESTAMP',date:'DATE',time:'TIME',"
       "json:'JSON',jsonb:'JSON',uuid:'VARCHAR',bytea:'VARBINARY'};"
       "function cdt(t){t=(t||'').toLowerCase();return DT[t]||(t?t.toUpperCase():'VARCHAR');}")


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=SETUP_CLEAR_VARS + [
            "realmId", "realmName", "realmReferenceName", "_streamCount", "_streamNames",
            "_nsAttempt", "_ingAttempt", "_entIdx", "_entCount"]),

        # ── DS → entities metadata → schema ──
        create_ds_step("01a", base),
        fetch_entities_step("01b", base),

        req("02 Create Schema", "POST", "/schema",
            ["const code=pm.response.code;",
             "pm.test('02 Schema 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','02');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.schemaModel||b.data||b;",
             "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
             "if(d.id||d.schemaId) pm.collectionVariables.set('schemaId', String(d.id||d.schemaId));",
             "if(d.prefix) pm.collectionVariables.set('schemaPrefix', d.prefix);"],
            base=base, body={"schemaName": "x"},
            prerequest=[
                "const sn='pm_flow_entity_'+Date.now();",
                "const prefix=sn.replace(/_/g,'-');",
                "pm.collectionVariables.set('schemaPrefix', prefix);",
                "pm.request.body.raw=JSON.stringify({schemaName:sn,prefix:prefix,description:'Entity-layer realm flow'});",
            ]),

        # ── Create each business entity ONE BY ONE via POST /entity (server stamps identity/tenant/FK-ready) ──
        # Self-looping step: creates entity for table[_entIdx], then setNextRequest itself until all tables done.
        req("03 Create Entity", "POST", "/entity",
            ["const code=pm.response.code;",
             "pm.test('03 entity 2xx (idx '+(pm.collectionVariables.get('_entIdx')||'0')+')', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','03');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const i=parseInt(pm.collectionVariables.get('_entIdx')||'0');",
             "console.log('entity['+i+'] created: '+(b.entityUri||'?')+' props='+((b.properties||[]).length));",
             "let meta=[]; try{meta=JSON.parse(pm.collectionVariables.get('_dsMetaList')||'[]');}catch(e){}",
             "const n=((meta[0]&&meta[0].hasTableEdges)||[]).length;",
             "const next=i+1;",
             "if(next<n){ pm.collectionVariables.set('_entIdx', String(next)); postman.setNextRequest('03 Create Entity'); }",
             "else { pm.collectionVariables.set('_entCount', String(n)); pm.collectionVariables.unset('_entIdx'); console.log('ALL '+n+' entities created'); }"],
            base=base, body={"label": "x"},
            prerequest=[
                _DT,
                "let meta=[]; try{meta=JSON.parse(pm.collectionVariables.get('_dsMetaList')||'[]');}catch(e){}",
                "const edges=(meta[0]&&meta[0].hasTableEdges)||[];",
                "const i=parseInt(pm.collectionVariables.get('_entIdx')||'0');",
                "const P=pm.collectionVariables.get('_dsPrefix')||'http://pmflow.in/';",
                "const dsCat=pm.collectionVariables.get('dataCatalogName');",
                "const te=edges[i]||{}; const tn=te.tableNode||{};",
                "const cols=(tn.hasPropertyEdges||[]).map(pe=>pe.propertyNode||{});",
                "const props=cols.map(c=>({label:c.label,dataType:cdt(c.dataType),primaryKey:!!c.primaryKey,uniqueKey:!!c.uniqueKey,foreignKey:!!c.foreignKey,nullable:c.nullable!==false,mappedColumnUri:(c.nodeId||c.node_id||c.uri),mappedColumnUris:[(c.nodeId||c.node_id||c.uri)]}));",
                "const body={label:tn.label,prefix:P,dataSourceUri:dsCat,namedEntity:false,description:'',tags:[],properties:props};",
                "pm.request.body.raw=JSON.stringify(body);",
            ]),

        # ── Read the fully-stamped entity graph for the DS, assemble it as the schema graph, and SAVE
        #    (+versionsModel). Done in-memory (sendRequest) to avoid collection-var body corruption. ──
        req("04 Save Schema Graph from Entities", "GET",
            "/entity-graph/datasource-subgraph?uri={{dataCatalogName}}",
            ["pm.test('04 subgraph 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let g={}; try{g=pm.response.json();}catch(e){}",
             "let nodes=g.nodes||[]; let links=g.links||[];",
             "const ent=nodes.filter(n=>n.node_type==='Node').length;",
             "pm.test('04 entities in subgraph (>0)', () => pm.expect(ent).to.be.above(0));",
             "const P=pm.collectionVariables.get('schemaPrefix');",
             "const sn=pm.collectionVariables.get('schemaName');",
             "const sidRaw=pm.collectionVariables.get('schemaId'); const sid=(sidRaw&&!isNaN(sidRaw))?parseInt(sidRaw):sidRaw;",
             "const VN=P+'Version#v1';",
             "// stamp schema prefix nodeId + schemaId (exactly what UICore stampNodeIds does)",
             "nodes.forEach(n=>{ n.nodeId=P+(n.uri||n.id||''); n.schemaId=sid; });",
             "nodes.push({node_type:'Version',id:VN,uri:VN,nodeId:VN,label:'v1',schemaId:sid,tags:[],description:''});",
             "nodes.filter(n=>n.node_type==='Node').forEach(en=>{ links.push({source:VN,target:(en.id||en.uri),relationship:'Has_Node',direction:'FORWARD',node_uri:VN}); });",
             "pm.collectionVariables.set('_versionUri', VN);",
             "pm.collectionVariables.set('_versionUriEnc', encodeURIComponent(VN));",
             "const ids=[]; (function(){const v=parseInt(pm.collectionVariables.get('dsId'));if(v&&!isNaN(v))ids.push(v);})();",
             "const body={prefix:P,schemaName:sn,schemaUri:P+'Schema#'+sn,nodes:nodes,links:links,versionsModel:{versionName:'v1',description:'',defaultVersion:false,latest:true,deleted:false,versionLocked:false,dataSourceIds:ids,entity360Flows:[]}};",
             "const app=pm.environment.get('app_base_url');",
             "const hdr={'Authorization':'Bearer '+(pm.collectionVariables.get('access_token')||pm.environment.get('access_token')),'X-TENANT-ID':pm.environment.get('tenant_id'),'Content-Type':'application/json'};",
             "pm.sendRequest({url:app+'/schema-graph', method:'POST', header:hdr, body:{mode:'raw', raw:JSON.stringify(body)}}, (e,r)=>{",
             "  const ok=r&&[200,201].includes(r.code);",
             "  pm.test('04 schema-graph saved 2xx', () => { if(!ok){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','04');} pm.expect(ok).to.be.true; });",
             "  let rb={}; try{rb=r.json();}catch(x){}",
             "  const vid=rb.versionId||rb.id;",
             "  if(vid) pm.collectionVariables.set('versionId', String(vid));",
             "  console.log('schema-graph saved from '+ent+' entities ('+nodes.length+' nodes) versionId='+vid);",
             "});"],
            base=base),

        req("05 Verify Schema Graph", "GET", "/schema-graph?versionUri={{_versionUriEnc}}",
            ["pm.test('05 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const ns=b.nodes||[]; const ent=ns.filter(n=>n.node_type==='Node');",
             "const stamped=ns.filter(n=>n.identity).length;",
             "pm.test('05 entities present', () => pm.expect(ent.length).to.be.above(0));",
             "console.log('schema-graph read back: '+ns.length+' nodes, '+ent.length+' entities, '+stamped+' with identity');"],
            base=base),

        # ── Realm ──
        req("06 Create Realm", "POST", "/realm",
            ["const code=pm.response.code;",
             "pm.test('06 Realm 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','06');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.realmModel||b.data||b;",
             "if(d.id||d.realmId) pm.collectionVariables.set('realmId', String(d.id||d.realmId));",
             "if(d.name||d.realmName) pm.collectionVariables.set('realmName', d.name||d.realmName);",
             "if(d.referenceName) pm.collectionVariables.set('realmReferenceName', d.referenceName);",
             "console.log('Realm id='+(d.id||d.realmId)+' ref='+d.referenceName);"],
            base=base, body={"name": "x"},
            prerequest=[
                "pm.request.body.raw=JSON.stringify({name:'pm_flow_entity_realm_'+Date.now(),description:'Entity-layer fabric',schemaName:pm.collectionVariables.get('schemaName'),versionId:parseInt(pm.collectionVariables.get('versionId'))});",
            ]),

        # ── Namespace ──
        req("07 Create Namespace (Synapse)", "POST", "/synapse/namespace/create",
            ["const code=pm.response.code;",
             "pm.test('07 namespace 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','07');} pm.expect(code).to.be.oneOf([200,201]); });"],
            base="kg_base_url", body={"name": "x"},
            prerequest=[
                "const historic=String(pm.environment.get('requiresHistoricIngest')||'true')!=='false';",
                "const vector=String(pm.environment.get('vectorIngestionRequired')||'true')!=='false';",
                "pm.request.body.raw=JSON.stringify({name:pm.collectionVariables.get('realmReferenceName'),schemaName:pm.collectionVariables.get('schemaName'),schemaVersion:'v1',requiresHistoricIngest:historic,type:null,vectorIngestionRequired:vector});",
            ]),

        # ── Generate streams ──
        req("08 Generate Ingest Streams", "POST", "/streams/generate",
            ["pm.test('08 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let arr=[]; try{arr=pm.response.json();}catch(e){} if(!Array.isArray(arr)) arr=[];",
             "pm.collectionVariables.set('_streamCount', String(arr.length));",
             "pm.collectionVariables.set('_streamNames', JSON.stringify(arr.map(s=>s.name).filter(Boolean)));",
             "console.log('streams generated: '+arr.length+(arr.length?(' e.g. '+arr[0].name):''));"],
            base="transform_base_url", body={"realmId": 0},
            prerequest=["pm.request.body.raw=JSON.stringify({realmId:parseInt(pm.collectionVariables.get('realmId'))});"]),
        req("09 Verify Streams Generated", "GET", "/actuator/health",
            ["pm.test('09 health', () => pm.response.to.have.status(200));",
             "const n=parseInt(pm.collectionVariables.get('_streamCount')||'0');",
             "pm.test('09 streams generated (>0)', () => pm.expect(n).to.be.above(0));"],
            base=base),

        # ── Wait namespace UP ──
        req("10 Wait Namespace UP", "GET", "/synapse/namespace/status?name={{realmReferenceName}}",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "let st=''; try{st=(pm.response.json().status||'').toUpperCase();}catch(e){}",
             "const a=parseInt(pm.collectionVariables.get('_nsAttempt')||'0');",
             "console.log('namespace status attempt '+a+': '+st);",
             "if(st==='UP'){ pm.collectionVariables.unset('_nsAttempt'); }",
             "else if(a<18){ pm.collectionVariables.set('_nsAttempt', String(a+1)); postman.setNextRequest('10 Wait Namespace UP'); }",
             "else { pm.collectionVariables.unset('_nsAttempt'); }",
             "pm.test('10 namespace reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base="kg_base_url",
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "if(parseInt(pm.collectionVariables.get('_nsAttempt')||'0')>0){ const t=Date.now(); while(Date.now()-t<4000){} }",
            ]),

        # ── SAVE + RUN ingestion in-memory ──
        req("11 Save + Run Ingestion", "POST", "/streams/generate",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "pm.test('11 regen 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let arr=[]; try{arr=pm.response.json();}catch(e){} if(!Array.isArray(arr)) arr=[];",
             "const rid=parseInt(pm.collectionVariables.get('realmId'));",
             "arr.forEach(s=>{ s.realmId=rid; });",
             "const app=pm.environment.get('app_base_url'); const txn=pm.environment.get('transform_base_url');",
             "const hdr={'Authorization':'Bearer '+(pm.collectionVariables.get('access_token')||pm.environment.get('access_token')),'X-TENANT-ID':pm.environment.get('tenant_id'),'Content-Type':'application/json'};",
             "const raw=JSON.stringify(arr);",
             "pm.sendRequest({url:app+'/atomicIngestStream/create-streams', method:'POST', header:hdr, body:{mode:'raw', raw:raw}}, (e1,r1)=>{",
             "  pm.test('11 create-streams 2xx', () => pm.expect(r1 && r1.code).to.be.oneOf([200,201]));",
             "  console.log('create-streams: '+(r1?r1.code:e1));",
             "  pm.sendRequest({url:txn+'/event/ingest?truncate=false&seedSequenceFromJournal=false&forceIngest=true', method:'POST', header:hdr, body:{mode:'raw', raw:raw}}, (e2,r2)=>{",
             "    pm.test('11 event/ingest 2xx', () => pm.expect(r2 && r2.code).to.be.oneOf([200,201,204]));",
             "    console.log('event/ingest: '+(r2?r2.code:e2));",
             "  });",
             "});"],
            base="transform_base_url", body={"realmId": 0},
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "pm.request.body.raw=JSON.stringify({realmId:parseInt(pm.collectionVariables.get('realmId'))});",
            ]),

        # ── STRICT verify ──
        req("12 Verify Tables Landed", "GET", "/synapse/namespace/stats?namespace={{realmReferenceName}}",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "let expected=[]; try{expected=JSON.parse(pm.collectionVariables.get('_streamNames')||'[]');}catch(e){}",
             "let landed={}; try{(pm.response.json().labels||[]).forEach(l=>{ if((l.count||0)>0) landed[l.label]=l.count; });}catch(e){}",
             "const missing=expected.filter(n=>!(n in landed));",
             "const a=parseInt(pm.collectionVariables.get('_ingAttempt')||'0');",
             "console.log('ingest verify attempt '+a+' landed='+JSON.stringify(landed)+' missing='+JSON.stringify(missing));",
             "const done=(expected.length>0 && missing.length===0) || a>=18;",
             "if(!done){ pm.collectionVariables.set('_ingAttempt', String(a+1)); postman.setNextRequest('12 Verify Tables Landed'); return; }",
             "pm.collectionVariables.unset('_ingAttempt');",
             "if(missing.length===0 && expected.length>0){ console.log('INGESTION VALIDATED: '+expected.length+' tables, rows='+JSON.stringify(landed)); }",
             "else { console.log('DATAFLOW FAILED: '+missing.length+'/'+expected.length+' stream(s) did not land: '+JSON.stringify(missing)); }",
             "pm.test('12 all '+expected.length+' table(s) ingested rows (missing: '+JSON.stringify(missing)+')', () => { pm.expect(expected.length).to.be.above(0); pm.expect(missing, 'tables with 0 rows').to.eql([]); });"],
            base="kg_base_url",
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "if(parseInt(pm.collectionVariables.get('_ingAttempt')||'0')>0){ const t=Date.now(); while(Date.now()-t<4000){} }",
            ]),

        # ── Cleanup (honors skip_cleanup=true) ──
        req("20 Del Realm", "DELETE", "/realm/{{realmId}}?permanent=false",
            ["pm.test('20 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, skip_on_fail=False, prerequest=_SKIP),
        req("21 Remove Namespace", "DELETE", "/synapse/namespace/remove?name={{realmReferenceName}}&permanent=true",
            ["pm.test('21 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base="kg_base_url", skip_on_fail=False, prerequest=_SKIP),
        req("22 Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('22 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, skip_on_fail=False, prerequest=_SKIP),
        req("99 Teardown (Del DS)", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False, prerequest=_SKIP),
    ]

    col = build_collection(
        name="FLOW - Single-DS Entity-Layer Realm + Ingestion",
        description="Product-faithful schema build: create each entity one-by-one via POST /entity "
                    "(server stamps identity/tenant), assemble the schema graph from the entity-graph "
                    "(datasource-subgraph), then realm + real ingestion. Creds via env-vars. "
                    "Any stream that does not land rows fails the flow.",
        folder_name="Single-DS Entity Realm", items=items, extra_variables=SETUP_VARS + [
            {"key": k, "value": "", "type": "string"} for k in
            ["realmId", "realmName", "realmReferenceName", "_streamCount", "_streamNames",
             "_nsAttempt", "_ingAttempt", "_entIdx", "_entCount"]])
    return write_flow("FLOW-SingleDS-EntityLayer-Realm.postman_collection.json", col)
