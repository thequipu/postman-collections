"""FLOW-SingleDS-Realm: full realm + REAL ingestion for ONE datasource.

Same pipeline as the 8-DS realm flow but for a single database (creds via env-vars), so it can be
pointed at a specific DB (e.g. user_management). Steps:
  DS -> entities -> schema -> /schema-graph (+versionsModel => versionId, no MinIO) -> realm
  -> namespace (wait UP) -> generate streams -> SAVE + event/ingest (in-memory) -> strict verify.
Any stream that does not land rows fails the flow (non-zero newman exit).
"""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import (create_ds_step, fetch_entities_step, create_schema_graph_step,
                           SETUP_VARS, SETUP_CLEAR_VARS)


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=SETUP_CLEAR_VARS + [
            "realmId", "realmName", "realmReferenceName", "_streamCount", "_streamNames",
            "_nsAttempt", "_ingAttempt"]),

        # ── DS → entities → schema → schema-graph (+version) ──
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
                "const sn='pm_flow_singleds_'+Date.now();",
                "const dsPrefix=pm.collectionVariables.get('_dsPrefix')||sn;",
                "pm.request.body.raw=JSON.stringify({schemaName:sn,prefix:dsPrefix,description:'Single-DS realm flow'});",
            ]),

        *create_schema_graph_step("03", base),   # mints versionId via /schema-graph + versionsModel

        # ── Realm ──
        req("04 Create Realm", "POST", "/realm",
            ["const code=pm.response.code;",
             "pm.test('04 Realm 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','04');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){} const d=b.realmModel||b.data||b;",
             "if(d.id||d.realmId) pm.collectionVariables.set('realmId', String(d.id||d.realmId));",
             "if(d.name||d.realmName) pm.collectionVariables.set('realmName', d.name||d.realmName);",
             "if(d.referenceName) pm.collectionVariables.set('realmReferenceName', d.referenceName);",
             "console.log('Realm id='+(d.id||d.realmId)+' ref='+d.referenceName);"],
            base=base, body={"name": "x"},
            prerequest=[
                "pm.request.body.raw=JSON.stringify({name:'pm_flow_singleds_realm_'+Date.now(),description:'Single-DS fabric',schemaName:pm.collectionVariables.get('schemaName'),versionId:parseInt(pm.collectionVariables.get('versionId'))});",
            ]),

        # ── Namespace (historic ingest) ──
        req("05 Create Namespace (Synapse)", "POST", "/synapse/namespace/create",
            ["const code=pm.response.code;",
             "pm.test('05 namespace 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','05');} pm.expect(code).to.be.oneOf([200,201]); });"],
            base="kg_base_url", body={"name": "x"},
            prerequest=[
                "const historic=String(pm.environment.get('requiresHistoricIngest')||'true')!=='false';",
                "const vector=String(pm.environment.get('vectorIngestionRequired')||'true')!=='false';",
                "pm.request.body.raw=JSON.stringify({name:pm.collectionVariables.get('realmReferenceName'),schemaName:pm.collectionVariables.get('schemaName'),schemaVersion:'v1',requiresHistoricIngest:historic,type:null,vectorIngestionRequired:vector});",
            ]),

        # ── Generate streams (gate: >0) ──
        req("06 Generate Ingest Streams", "POST", "/streams/generate",
            ["pm.test('06 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let arr=[]; try{arr=pm.response.json();}catch(e){} if(!Array.isArray(arr)) arr=[];",
             "pm.collectionVariables.set('_streamCount', String(arr.length));",
             "pm.collectionVariables.set('_streamNames', JSON.stringify(arr.map(s=>s.name).filter(Boolean)));",
             "console.log('streams generated: '+arr.length+(arr.length?(' e.g. '+arr[0].name):''));"],
            base="transform_base_url", body={"realmId": 0},
            prerequest=["pm.request.body.raw=JSON.stringify({realmId:parseInt(pm.collectionVariables.get('realmId'))});"]),
        req("07 Verify Streams Generated", "GET", "/actuator/health",
            ["pm.test('07 health', () => pm.response.to.have.status(200));",
             "const n=parseInt(pm.collectionVariables.get('_streamCount')||'0');",
             "pm.test('07 streams generated (>0)', () => pm.expect(n).to.be.above(0));"],
            base=base),

        # ── Wait namespace UP ──
        req("08 Wait Namespace UP", "GET", "/synapse/namespace/status?name={{realmReferenceName}}",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "let st=''; try{st=(pm.response.json().status||'').toUpperCase();}catch(e){}",
             "const a=parseInt(pm.collectionVariables.get('_nsAttempt')||'0');",
             "console.log('namespace status attempt '+a+': '+st);",
             "if(st==='UP'){ pm.collectionVariables.unset('_nsAttempt'); }",
             "else if(a<18){ pm.collectionVariables.set('_nsAttempt', String(a+1)); postman.setNextRequest('08 Wait Namespace UP'); }",
             "else { pm.collectionVariables.unset('_nsAttempt'); }",
             "pm.test('08 namespace reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,404]));"],
            base="kg_base_url",
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "if(parseInt(pm.collectionVariables.get('_nsAttempt')||'0')>0){ const t=Date.now(); while(Date.now()-t<4000){} }",
            ]),

        # ── SAVE + RUN ingestion in-memory (avoids the collection-var body corruption) ──
        req("09 Save + Run Ingestion", "POST", "/streams/generate",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "pm.test('09 regen 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let arr=[]; try{arr=pm.response.json();}catch(e){} if(!Array.isArray(arr)) arr=[];",
             "const rid=parseInt(pm.collectionVariables.get('realmId'));",
             "arr.forEach(s=>{ s.realmId=rid; });",
             "const app=pm.environment.get('app_base_url'); const txn=pm.environment.get('transform_base_url');",
             "const hdr={'Authorization':'Bearer '+(pm.collectionVariables.get('access_token')||pm.environment.get('access_token')),'X-TENANT-ID':pm.environment.get('tenant_id'),'Content-Type':'application/json'};",
             "const raw=JSON.stringify(arr);",
             "pm.sendRequest({url:app+'/atomicIngestStream/create-streams', method:'POST', header:hdr, body:{mode:'raw', raw:raw}}, (e1,r1)=>{",
             "  pm.test('09 create-streams 2xx', () => pm.expect(r1 && r1.code).to.be.oneOf([200,201]));",
             "  console.log('create-streams: '+(r1?r1.code:e1));",
             "  pm.sendRequest({url:txn+'/event/ingest?truncate=false&seedSequenceFromJournal=false&forceIngest=false', method:'POST', header:hdr, body:{mode:'raw', raw:raw}}, (e2,r2)=>{",
             "    pm.test('09 event/ingest 2xx', () => pm.expect(r2 && r2.code).to.be.oneOf([200,201,204]));",
             "    console.log('event/ingest: '+(r2?r2.code:e2));",
             "  });",
             "});"],
            base="transform_base_url", body={"realmId": 0},
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "pm.request.body.raw=JSON.stringify({realmId:parseInt(pm.collectionVariables.get('realmId'))});",
            ]),

        # ── STRICT verify: every table must land rows or the flow FAILS ──
        req("10 Verify Tables Landed", "GET", "/synapse/namespace/stats?namespace={{realmReferenceName}}",
            ["if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ return; }",
             "let expected=[]; try{expected=JSON.parse(pm.collectionVariables.get('_streamNames')||'[]');}catch(e){}",
             "let landed={}; try{(pm.response.json().labels||[]).forEach(l=>{ if((l.count||0)>0) landed[l.label]=l.count; });}catch(e){}",
             "const missing=expected.filter(n=>!(n in landed));",
             "const a=parseInt(pm.collectionVariables.get('_ingAttempt')||'0');",
             "console.log('ingest verify attempt '+a+' landed='+JSON.stringify(landed)+' missing='+JSON.stringify(missing));",
             "const done=(expected.length>0 && missing.length===0) || a>=18;",
             "if(!done){ pm.collectionVariables.set('_ingAttempt', String(a+1)); postman.setNextRequest('10 Verify Tables Landed'); return; }",
             "pm.collectionVariables.unset('_ingAttempt');",
             "if(missing.length===0 && expected.length>0){ console.log('INGESTION VALIDATED: '+expected.length+' tables, rows='+JSON.stringify(landed)); }",
             "else { console.log('DATAFLOW FAILED: '+missing.length+'/'+expected.length+' stream(s) did not land: '+JSON.stringify(missing)); }",
             "pm.test('10 all '+expected.length+' table(s) ingested rows (missing: '+JSON.stringify(missing)+')', () => { pm.expect(expected.length).to.be.above(0); pm.expect(missing, 'tables with 0 rows').to.eql([]); });"],
            base="kg_base_url",
            prerequest=[
                "if((parseInt(pm.collectionVariables.get('_streamCount')||'0'))<1){ pm.request.url=pm.collectionVariables.get('_skip_url'); return; }",
                "if(parseInt(pm.collectionVariables.get('_ingAttempt')||'0')>0){ const t=Date.now(); while(Date.now()-t<4000){} }",
            ]),

        # ── Cleanup ──
        req("20 Del Realm", "DELETE", "/realm/{{realmId}}?permanent=false",
            ["pm.test('20 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, skip_on_fail=False),
        req("21 Remove Namespace", "DELETE", "/synapse/namespace/remove?name={{realmReferenceName}}&permanent=true",
            ["pm.test('21 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base="kg_base_url", skip_on_fail=False),
        req("22 Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('22 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=base, skip_on_fail=False),
        req("99 Teardown (Del DS)", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('99 ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed'); pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False),
    ]

    col = build_collection(
        name="FLOW - Single-DS Realm + Ingestion",
        description="Full realm + real ingestion for ONE datasource (creds via env-vars). "
                    "Point it at a specific DB (e.g. user_management). Any stream that does not land "
                    "rows fails the flow.",
        folder_name="Single-DS Realm", items=items, extra_variables=SETUP_VARS + [
            {"key": k, "value": "", "type": "string"} for k in
            ["realmId", "realmName", "realmReferenceName", "_streamCount", "_streamNames",
             "_nsAttempt", "_ingAttempt"]])
    return write_flow("FLOW-SingleDS-Realm.postman_collection.json", col)
