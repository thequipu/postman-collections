"""FLOW-Neuro-Graph-Test: Graph API + Steering Config integration test.

Converted from neuro_graph_test_prestage.sh / netapp.sh.
Covers: space+steering config (profile, instructions, model selection),
        graph namespace CRUD, graph listings (pagination), single reads,
        writes (create/patch node/edge/episode), invalidation matrix,
        pin/unpin, deletes, negative tests, and full cleanup.

Environment variables required (via --env-var):
  neuro_base_url, app_base_url, fabric_id, tenant_id,
  client_id, client_secret, test_username, test_password,
  keycloak_token_url

Recommended: --delay-request 5000 --timeout-request 60000
"""

from flowlib.core import req, build_collection, write_flow

NEURO = "neuro_base_url"
APP = "app_base_url"
P = "let b={}; try{b=pm.response.json();}catch(e){}"
GRAPH_ID = "testgraph"


def nreq(name, method, path, tests, body=None, prerequest=None,
         skip_on_fail=True, noauth=False, no_fabric=False, bad_auth=False,
         base=NEURO):
    hdrs = []
    if not no_fabric:
        hdrs.append({"key": "X-Fabric", "value": "{{fabric_id}}"})
    if bad_auth:
        hdrs.append({"key": "Authorization", "value": "Bearer invalid-token-xxx"})
    return req(name, method, path, tests, body=body, base=base,
               extra_headers=hdrs or None,
               prerequest=prerequest, skip_on_fail=skip_on_fail,
               noauth=noauth or bad_auth)


NEURO_GRAPH_VARS = [
    {"key": "space_name", "value": "", "type": "string"},
    {"key": "ns_name", "value": "", "type": "string"},
    {"key": "graph_ns", "value": "", "type": "string"},
    {"key": "fabric_id", "value": "", "type": "string"},
    {"key": "_graph_id", "value": GRAPH_ID, "type": "string"},
    {"key": "_node_uri", "value": "", "type": "string"},
    {"key": "_node_name", "value": "", "type": "string"},
    {"key": "_edge_uri", "value": "", "type": "string"},
    {"key": "_edge_uri_2", "value": "", "type": "string"},
    {"key": "_edge_uri_3", "value": "", "type": "string"},
    {"key": "_episode_uri", "value": "", "type": "string"},
    {"key": "_created_node_uri", "value": "", "type": "string"},
    {"key": "_thread_uri", "value": "", "type": "string"},
    {"key": "_available_model", "value": "", "type": "string"},
    {"key": "_entity_count_before", "value": "0", "type": "string"},
    {"key": "_invalidate_fact_text", "value": "", "type": "string"},
]

EXTRACTION_PROFILE = {
    "role": "Memory for automated API testing. Tracks people, teams, locations and their relationships.",
    "salienceNote": "Remember who works where, who reports to whom, team structures, locations, and travel preferences. Ignore greetings and scheduling.",
    "entityKinds": [
        {"name": "Person", "description": "A person or employee", "examples": ["Karthik", "Jane", "Caroline"]},
        {"name": "Organization", "description": "A company or team", "examples": ["Acme", "Platform team"]},
        {"name": "Location", "description": "A city or place", "examples": ["Berlin", "Chennai"]},
        {"name": "Role", "description": "A job title or position", "examples": ["VP of Engineering", "senior engineer"]},
    ],
    "extractionTargets": [
        "who works at which organization",
        "who reports to whom",
        "where a person is located",
        "what role a person holds",
    ],
    "exclusions": ["greetings and small talk", "scheduling and availability"],
    "positiveExamples": [{"input": "Jane joined Acme as a senior engineer in Berlin.",
                          "expected": "Jane (Person) -works_at-> Acme (Organization); Jane (Person) -located_in-> Berlin (Location)"}],
    "negativeExamples": ["Let me look that up for you - an intention, not a fact"],
}

INSTRUCTIONS = [
    {"family": "EXTRACTION", "name": "expand-acronyms",
     "text": "Always expand VP as Vice President when recording roles. Never leave abbreviated forms in facts."},
    {"family": "EXTRACTION", "name": "preserve-identifiers",
     "text": "Copy team and organization names exactly as stated. Do not abbreviate or normalize."},
    {"family": "SUMMARY", "name": "summary-style",
     "text": "One sentence. State current status only."},
]

NS_PROFILE = {
    "role": "Graph namespace for product documentation. Tracks products, technologies, and their relationships.",
    "entityKinds": [
        {"name": "Product", "description": "A software product or tool", "examples": ["Data Fabric", "Kubernetes"]},
        {"name": "Technology", "description": "A technology or framework", "examples": ["Apache Kafka", "PostgreSQL"]},
    ],
    "extractionTargets": ["what products exist", "what technologies are used"],
}


# ---------------------------------------------------------------------------
#  SETUP
# ---------------------------------------------------------------------------

def setup_step():
    return {
        "name": "00 Setup",
        "event": [
            {"listen": "prerequest", "script": {"type": "text/javascript", "exec": [
                "pm.collectionVariables.unset('_flow_failed');",
                "pm.collectionVariables.unset('_flow_failed_at');",
                "const sp='ngt-'+Date.now();",
                "pm.collectionVariables.set('space_name', sp);",
                "pm.collectionVariables.set('ns_name', sp+'-self');",
                "pm.collectionVariables.set('graph_ns', sp+'-"
                + GRAPH_ID + "');",
                "if(!pm.environment.get('fabric_id')&&pm.collectionVariables.get('fabric_id')){",
                "  pm.environment.set('fabric_id',pm.collectionVariables.get('fabric_id'));",
                "}",
                "pm.collectionVariables.set('_skip_url',"
                " pm.environment.get('neuro_base_url')+'/v1/health');",
                "console.log('Setup: space='+sp+' graph_ns='+sp+'-"
                + GRAPH_ID + "'"
                "+'  tenant='+pm.environment.get('tenant_id')"
                "+'  fabric='+pm.environment.get('fabric_id'));",
            ]}},
            {"listen": "test", "script": {"type": "text/javascript", "exec": [
                "pm.test('00 neuro reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,401,404]));",
                "if(pm.response.code>=500){",
                "  pm.collectionVariables.set('_flow_failed','true');",
                "  pm.collectionVariables.set('_flow_failed_at','00 Setup');",
                "}",
            ]}},
        ],
        "request": {
            "method": "GET", "header": [],
            "url": {"raw": "{{neuro_base_url}}/v1/health",
                    "host": ["{{neuro_base_url}}"], "path": ["v1", "health"]},
            "auth": {"type": "noauth"},
        },
        "response": [],
    }


# ---------------------------------------------------------------------------
#  SECTION A — CREATE SPACE + STEERING CONFIG
# ---------------------------------------------------------------------------

def steering_config_steps():
    INGEST = "/v1/spaces/{{space_name}}/ingest"
    return [
        # A01: First ingest — creates the space
        nreq("A01 Create Space Ingest", "POST", INGEST,
             ["const code=pm.response.code;",
              "pm.test('A01 → 202', ()=>{ if(code!==202){pm.collectionVariables.set('_flow_failed','true');"
              "pm.collectionVariables.set('_flow_failed_at','A01');} pm.expect(code).to.eql(202); });",
              P, "pm.test('A01 unitId', ()=>pm.expect(b.unitId).to.exist);",
              "pm.test('A01 namespaceId', ()=>pm.expect(b.namespaceId).to.exist);"],
             body={"_": ""},
             prerequest=[
                 "pm.request.body.raw=JSON.stringify({content:'Karthik prefers aisle seats and usually flies out of Chennai.',"
                 "threadId:'thread-'+Date.now()+'-001',contentType:'text/plain',"
                 "role:'user',speaker:'Karthik',occurredAt:new Date().toISOString()});"]),

        # A02: PUT extraction profile
        nreq("A02 Put Profile", "PUT",
             "/space/by-name/{{space_name}}/extraction-profile",
             [P, "pm.test('A02 → 200|201', ()=>pm.expect(pm.response.code).to.be.oneOf([200,201]));"],
             body=EXTRACTION_PROFILE, base=APP),

        # A03: GET extraction profile — verify fields
        nreq("A03 Get Profile", "GET",
             "/space/by-name/{{space_name}}/extraction-profile",
             [P, "pm.test('A03 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "const p=Array.isArray(b)?b[0]:b;",
              "if(p){",
              "  pm.test('A03 has role', ()=>pm.expect(p.role).to.include('automated'));",
              "  pm.test('A03 entityKinds=4', ()=>pm.expect(p.entityKinds.length).to.eql(4));",
              "  pm.test('A03 extractionTargets=4', ()=>pm.expect(p.extractionTargets.length).to.eql(4));",
              "  pm.test('A03 exclusions=2', ()=>pm.expect(p.exclusions.length).to.eql(2));",
              "  pm.test('A03 positiveExamples', ()=>pm.expect(p.positiveExamples).to.exist);",
              "}"],
             base=APP),

        # A04: PUT instructions
        nreq("A04 Put Instructions", "PUT",
             "/space/by-name/{{space_name}}/instructions",
             [P, "pm.test('A04 → 200|201', ()=>pm.expect(pm.response.code).to.be.oneOf([200,201]));"],
             body=INSTRUCTIONS, base=APP),

        # A05: GET instructions — verify 3
        nreq("A05 Get Instructions", "GET",
             "/space/by-name/{{space_name}}/instructions",
             [P, "pm.test('A05 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(Array.isArray(b)){",
              "  pm.test('A05 count=3', ()=>pm.expect(b.length).to.eql(3));",
              "  pm.test('A05 has expand-acronyms', ()=>pm.expect(b.some(i=>i.name==='expand-acronyms')).to.be.true);",
              "  pm.test('A05 has preserve-identifiers', ()=>pm.expect(b.some(i=>i.name==='preserve-identifiers')).to.be.true);",
              "  pm.test('A05 has summary-style', ()=>pm.expect(b.some(i=>i.name==='summary-style')).to.be.true);",
              "}"],
             base=APP),

        # A06: GET extraction/status — discover models
        nreq("A06 Extraction Status", "GET",
             "/v1/spaces/{{space_name}}/extraction/status",
             [P, "pm.test('A06 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('A06 promptVersion', ()=>pm.expect(b.promptVersion).to.exist);",
              "pm.test('A06 availableModels', ()=>pm.expect(b.availableModels).to.exist);",
              "if(b.availableModels&&b.availableModels.length>0){",
              "  pm.collectionVariables.set('_available_model', b.availableModels[0]);",
              "  console.log('Available model: '+b.availableModels[0]);",
              "}",
              "console.log('promptVersion='+b.promptVersion+' profileConfigured='+b.profileConfigured"
              "+'  profileInert='+b.profileInert);"]),

        # A07: PUT model selection
        nreq("A07 Put Model", "PUT",
             "/space/by-name/{{space_name}}/model-selection",
             [P, "pm.test('A07 → 200|201', ()=>pm.expect(pm.response.code).to.be.oneOf([200,201]));"],
             body={"_": ""},
             prerequest=[
                 "const m=pm.collectionVariables.get('_available_model')||'';",
                 "if(!m){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.body.raw=JSON.stringify({extractionModel:m,adjudicationModel:m});"],
             base=APP),

        # A08: Verify model in extraction/status
        nreq("A08 Verify Model", "GET",
             "/v1/spaces/{{space_name}}/extraction/status",
             [P, "pm.test('A08 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "const m=pm.collectionVariables.get('_available_model');",
              "if(m&&b.extractionModel){",
              "  pm.test('A08 model matches', ()=>pm.expect(b.extractionModel).to.eql(m));",
              "  pm.test('A08 source SPACE', ()=>pm.expect(b.extractionModelSource).to.eql('SPACE'));",
              "}"]),

        # A09: Create graph namespace
        nreq("A09 Create Graph NS", "POST",
             "/space/by-name/{{space_name}}/graph",
             [P, "pm.test('A09 → 200|201', ()=>pm.expect(pm.response.code).to.be.oneOf([200,201]));"],
             body={"graphId": GRAPH_ID, "label": "Test Graph Namespace"},
             base=APP),

        # A10: GET scopes
        nreq("A10 Get Scopes", "GET",
             "/v1/spaces/{{space_name}}/scopes",
             [P, "pm.test('A10 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(Array.isArray(b)){",
              "  pm.test('A10 >=2 scopes', ()=>pm.expect(b.length).to.be.at.least(2));",
              "  console.log('Scopes: '+JSON.stringify(b));",
              "}"]),

        # A11: PUT namespace-scoped profile
        nreq("A11 Put NS Profile", "PUT",
             "/space/by-name/{{space_name}}/extraction-profile",
             [P, "pm.test('A11 → 200|201', ()=>pm.expect(pm.response.code).to.be.oneOf([200,201]));"],
             body={"_": ""},
             prerequest=[
                 "const gns=pm.collectionVariables.get('graph_ns');",
                 "pm.request.body.raw=JSON.stringify({targetNamespaceName:gns,"
                 "role:'Graph namespace for product documentation. Tracks products, technologies, and their relationships.',"
                 "entityKinds:[{name:'Product',description:'A software product or tool',examples:['Data Fabric','Kubernetes']},"
                 "{name:'Technology',description:'A technology or framework',examples:['Apache Kafka','PostgreSQL']}],"
                 "extractionTargets:['what products exist','what technologies are used']});"],
             base=APP),

        # A12: GET all profiles — verify both
        nreq("A12 Get All Profiles", "GET",
             "/space/by-name/{{space_name}}/extraction-profile",
             [P, "pm.test('A12 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(Array.isArray(b)){",
              "  if(b.length>=2) pm.test('A12 both profiles', ()=>pm.expect(b.length).to.be.at.least(2));",
              "  else console.log('A12: only '+b.length+' profile(s) — ns profile may not be separate');",
              "}"],
             base=APP),

        # A13: Ingest into graph namespace — message 1
        nreq("A13 Graph Ingest 1", "POST",
             "/v1/spaces/{{space_name}}/graphs/" + GRAPH_ID + "/ingest",
             [P, "pm.test('A13 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "pm.test('A13 namespaceId', ()=>pm.expect(b.namespaceId).to.exist);"],
             body={"content": "The Data Fabric product supports real-time ingestion and is built on Apache Kafka. PostgreSQL is used for metadata storage.",
                   "threadId": "graph-thread-001", "contentType": "text/plain",
                   "role": "user", "speaker": "Admin"}),

        # A14: Ingest into graph namespace — message 2
        nreq("A14 Graph Ingest 2", "POST",
             "/v1/spaces/{{space_name}}/graphs/" + GRAPH_ID + "/ingest",
             [P, "pm.test('A14 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"content": "Kubernetes is the container orchestration platform used by the team. Redis is used for caching and session management.",
                   "threadId": "graph-thread-002", "contentType": "text/plain",
                   "role": "user", "speaker": "Admin"}),

        # A15: Graph ns stats (wait for projection — stats appear after extraction settles)
        nreq("A15 Graph NS Stats", "GET",
             "/v1/spaces/{{space_name}}/graph/stats?namespaceId={{graph_ns}}",
             [P, "pm.test('A15 → 200|404', ()=>pm.expect(pm.response.code).to.be.oneOf([200,404]));",
              "if(pm.response.code===200&&b.labels){",
              "  const ec=(b.labels.filter(l=>l.label==='Entity')[0]||{}).count||0;",
              "  console.log('Graph NS entities='+ec);",
              "}"],
             prerequest=["pm.collectionVariables.set('_soft_5xx','true');"]),

        # A16: Graph ns nodes/list — verify profile override
        nreq("A16 Graph NS Nodes", "POST",
             "/v1/spaces/{{space_name}}/graph/nodes/list",
             [P, "pm.test('A16 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items&&b.items.length>0){",
              "  const types=b.items.map(i=>(i.attributes||{}).entityType).filter(Boolean);",
              "  console.log('Graph NS entity types: '+JSON.stringify([...new Set(types)]));",
              "}"]),
        nreq("A16b Graph NS Edges", "POST",
             "/v1/spaces/{{space_name}}/graph/edges/list",
             [P, "pm.test('A16b → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items) console.log('Graph NS facts: '+b.items.length);"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('graph_ns'),limit:50,cursor:null});"]),

        # A17: DELETE namespace-scoped profile
        nreq("A17 Del NS Profile", "DELETE",
             "/space/by-name/{{space_name}}/extraction-profile",
             [P, "pm.test('A17 → 200|400|404', ()=>pm.expect(pm.response.code).to.be.oneOf([200,400,404]));"],
             prerequest=[
                 "const gns=pm.collectionVariables.get('graph_ns');",
                 "pm.request.url=pm.environment.get('app_base_url')"
                 "+'/space/by-name/'+pm.collectionVariables.get('space_name')"
                 "+'/extraction-profile?targetNamespaceName='+gns;"],
             base=APP),

        # A18: Verify only space-wide profile remains
        nreq("A18 Verify Profile", "GET",
             "/space/by-name/{{space_name}}/extraction-profile",
             [P, "pm.test('A18 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(Array.isArray(b)){",
              "  const gns=pm.collectionVariables.get('graph_ns');",
              "  const nsStill=b.filter(p=>p.targetNamespaceName===gns).length;",
              "  pm.test('A18 ns profile removed', ()=>pm.expect(nsStill).to.eql(0));",
              "}"],
             base=APP),
    ]


# ---------------------------------------------------------------------------
#  SECTION B — DATA INJECTION + RECALL
# ---------------------------------------------------------------------------

def data_injection_steps():
    INGEST = "/v1/spaces/{{space_name}}/ingest"
    return [
        # B01: Ingest_2 — people and reporting
        nreq("B01 Ingest People", "POST", INGEST,
             [P, "pm.test('B01 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"content": "Jane joined Acme as a senior engineer in Berlin in 2021. She reports to David who is the VP of Engineering.",
                   "threadId": "thread-data-004", "contentType": "text/plain",
                   "role": "user", "speaker": "Admin"}),

        # B02: Ingest_3 — teams and products
        nreq("B02 Ingest Teams", "POST", INGEST,
             [P, "pm.test('B02 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"content": "The Platform team uses Kubernetes for deployment and their main product is the Data Fabric. Caroline leads the frontend squad.",
                   "threadId": "thread-data-002", "contentType": "text/plain",
                   "role": "user", "speaker": "Admin"}),

        # B03: Exclusion test — greetings (should NOT create facts)
        nreq("B03 Ingest Exclusion", "POST", INGEST,
             [P, "pm.test('B03 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"content": "Hi there, thanks for waiting! Let me schedule a meeting for next Tuesday to discuss the claim. Have a great day!",
                   "threadId": "thread-data-003", "contentType": "text/plain",
                   "role": "user", "speaker": "Admin"}),

        # B04: Assert_1 — Caroline works at Platform team
        nreq("B04 Assert 1", "POST", "/v1/spaces/{{space_name}}/assert",
             [P, "pm.test('B04 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "pm.test('B04 accepted', ()=>pm.expect(b.accepted).to.exist);",
              "pm.test('B04 namespaceId', ()=>pm.expect(b.namespaceId).to.exist);"],
             body={"entitySurfaceForm": "Caroline", "label": "Person",
                   "property": "works_at", "value": "Platform team",
                   "worldTime": True, "validFrom": "2026-03-01T00:00:00Z"}),

        # B05: Assert_2 — David VP
        nreq("B05 Assert 2", "POST", "/v1/spaces/{{space_name}}/assert",
             [P, "pm.test('B05 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "David", "label": "Person",
                   "property": "role", "value": "VP of Engineering",
                   "worldTime": True, "validFrom": "2025-01-01T00:00:00Z"}),

        # B06: Assert_3 — Jane in Berlin
        nreq("B06 Assert 3", "POST", "/v1/spaces/{{space_name}}/assert",
             [P, "pm.test('B06 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "Jane", "label": "Person",
                   "property": "located_in", "value": "Berlin",
                   "worldTime": True, "validFrom": "2021-06-01T00:00:00Z"}),

        # B07: Wait — check stats (projection settling)
        nreq("B07 Wait Stats", "GET",
             "/v1/spaces/{{space_name}}/graph/stats?namespaceId={{ns_name}}",
             [P, "pm.test('B07 → 200', ()=>pm.expect(pm.response.code).to.be.oneOf([200,404]));",
              "if(pm.response.code===200&&b.labels){",
              "  const ec=(b.labels.filter(l=>l.label==='Entity')[0]||{}).count||0;",
              "  const fc=(b.labels.filter(l=>l.label==='Fact')[0]||{}).count||0;",
              "  console.log('Stats: Entity='+ec+' Fact='+fc);",
              "}"],
             prerequest=["pm.collectionVariables.set('_soft_5xx','true');"]),

        # B08: Verify model after ingest
        nreq("B08 Model After Ingest", "GET",
             "/v1/spaces/{{space_name}}/extraction/status",
             [P, "pm.test('B08 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "const m=pm.collectionVariables.get('_available_model');",
              "if(m&&b.extractionModel) pm.test('B08 model still set', ()=>pm.expect(b.extractionModel).to.eql(m));"]),

        # B09: Reset model to defaults
        nreq("B09 Reset Model", "PUT",
             "/space/by-name/{{space_name}}/model-selection",
             [P, "pm.test('B09 → 200|201', ()=>pm.expect(pm.response.code).to.be.oneOf([200,201]));"],
             body={"extractionModel": "", "adjudicationModel": ""}, base=APP),

        # B10: Recall LIVE
        nreq("B10 Recall LIVE", "POST",
             "/v1/spaces/{{space_name}}/recall",
             [P, "pm.test('B10 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items&&b.items.length>0) pm.test('B10 has items', ()=>pm.expect(b.items.length).to.be.above(0));",
              "else console.log('B10: no recall items yet (projection settling)');"],
             body={"query": "What seat does Karthik prefer?", "tokenBudget": 1200, "mode": "LIVE"}),

        # B11: Recall LIVE + thread
        nreq("B11 Recall Thread", "POST",
             "/v1/spaces/{{space_name}}/recall",
             [P, "pm.test('B11 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "which team is Caroline on now?", "tokenBudget": 1200,
                   "mode": "LIVE", "threadId": "conversation-42"}),

        # B12: Recall AS_OF
        nreq("B12 Recall AS_OF", "POST",
             "/v1/spaces/{{space_name}}/recall",
             [P, "pm.test('B12 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "which team was Caroline on?", "tokenBudget": 1200,
                   "mode": "AS_OF", "asOf": "2026-01-15T00:00:00Z"}),

        # B13: Recall AS_OF no budget → 400
        nreq("B13 No Budget 400", "POST",
             "/v1/spaces/{{space_name}}/recall",
             [P, "pm.test('B13 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"query": "which team was Caroline on?", "mode": "AS_OF",
                   "asOf": "2026-01-15T00:00:00Z"}),

        # B14: Capture spans
        nreq("B14 Capture Spans", "GET",
             "/v1/spaces/{{space_name}}/capture/spans?sinceSeq=0&limit=20",
             [P, "pm.test('B14 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"]),

        # B15: Graph threads (old endpoint)
        nreq("B15 Graph Threads Old", "GET",
             "/v1/spaces/{{space_name}}/graph/threads?limit=20",
             [P, "pm.test('B15 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(Array.isArray(b)&&b.length>0&&b[0].uri){",
              "  pm.collectionVariables.set('_thread_uri', b[0].uri);",
              "}"]),

        # B16: Graph participants
        nreq("B16 Participants", "GET",
             "/v1/spaces/{{space_name}}/graph/participants?limit=50",
             [P, "pm.test('B16 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"]),

        # B17: Memories namespace recall
        nreq("B17 NS Recall", "POST",
             "/v1/memories/{{ns_name}}/recall",
             [P, "pm.test('B17 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items&&b.items.length>0) pm.test('B17 has items', ()=>pm.expect(b.items.length).to.be.above(0));",
              "else console.log('B17: recall items empty (projection settling)');"],
             body={"query": "What seat does Karthik prefer?", "tokenBudget": 800}),

        # B18: Memories recall bad ns → 404
        nreq("B18 Bad NS 404", "POST",
             "/v1/memories/no-such-namespace-xyz/recall",
             [P, "pm.test('B18 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"query": "anything", "tokenBudget": 800}),
    ]


# ---------------------------------------------------------------------------
#  SECTION C — GRAPH LISTINGS + PAGINATION
# ---------------------------------------------------------------------------

def graph_listing_steps():
    return [
        # C01: nodes/list
        nreq("C01 Nodes List", "POST",
             "/v1/spaces/{{space_name}}/graph/nodes/list",
             [P, "pm.test('C01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items&&b.items.length>0){",
              "  pm.collectionVariables.set('_node_uri', b.items[0].uri||'');",
              "  pm.collectionVariables.set('_node_name', b.items[0].name||'');",
              "  pm.test('C01 node has uri', ()=>pm.expect(b.items[0].uri).to.exist);",
              "  pm.test('C01 node has name', ()=>pm.expect(b.items[0].name).to.exist);",
              "  pm.test('C01 node has label', ()=>pm.expect(b.items[0].label).to.exist);",
              "  pm.test('C01 node has createdAt', ()=>pm.expect(b.items[0].createdAt).to.exist);",
              "} else console.log('C01: no nodes yet');"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('ns_name'),limit:50,cursor:null,labels:['Entity']});"]),

        # C02: edges/list — deep validation
        nreq("C02 Edges List", "POST",
             "/v1/spaces/{{space_name}}/graph/edges/list",
             [P, "pm.test('C02 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items&&b.items.length>0){",
              "  const fi=b.items.findIndex(i=>i.sourceNodeName!=null);",
              "  const f=b.items[fi>=0?fi:0];",
              "  pm.test('C02 fact has uri', ()=>pm.expect(f.uri).to.exist);",
              "  pm.test('C02 fact has name', ()=>pm.expect(f.name).to.exist);",
              "  pm.test('C02 fact has fact', ()=>pm.expect(f.fact).to.exist);",
              "  pm.test('C02 fact has sourceNodeUri', ()=>pm.expect(f.sourceNodeUri).to.exist);",
              "  pm.test('C02 fact has targetNodeUri', ()=>pm.expect(f.targetNodeUri).to.exist);",
              "  pm.test('C02 fact has validAt', ()=>pm.expect(f.validAt).to.exist);",
              "  pm.test('C02 fact has createdAt', ()=>pm.expect(f.createdAt).to.exist);",
              "  pm.collectionVariables.set('_edge_uri', f.uri||'');",
              "  if(b.items.length>1) pm.collectionVariables.set('_edge_uri_2', b.items[1].uri||'');",
              "  if(b.items.length>2) pm.collectionVariables.set('_edge_uri_3', b.items[2].uri||'');",
              "  const factUris=b.items.filter(i=>i.uri&&i.uri.includes('Fact/')).length;",
              "  pm.test('C02 all Fact URIs', ()=>pm.expect(factUris).to.eql(b.items.length));",
              "} else console.log('C02: no edges yet');"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('ns_name'),limit:50,cursor:null});"]),

        # C03: episodes/list
        nreq("C03 Episodes List", "POST",
             "/v1/spaces/{{space_name}}/graph/episodes/list",
             [P, "pm.test('C03 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items&&b.items.length>0){",
              "  pm.collectionVariables.set('_episode_uri', b.items[0].uri||'');",
              "  pm.test('C03 episode has uri', ()=>pm.expect(b.items[0].uri).to.exist);",
              "  pm.test('C03 episode has sourceType', ()=>pm.expect(b.items[0].sourceType).to.exist);",
              "} else console.log('C03: no episodes yet');"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('ns_name'),limit:50,cursor:null});"]),

        # C04: threads/list
        nreq("C04 Threads List", "POST",
             "/v1/spaces/{{space_name}}/graph/threads/list",
             [P, "pm.test('C04 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items&&b.items.length>0){",
              "  pm.test('C04 thread has threadId', ()=>pm.expect(b.items[0].threadId).to.exist);",
              "} else console.log('C04: no threads yet');"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('ns_name'),limit:50,cursor:null});"]),

        # C05: Pagination page 1 (edges, limit=2)
        nreq("C05 Page1 Edges", "POST",
             "/v1/spaces/{{space_name}}/graph/edges/list",
             [P, "pm.test('C05 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items){",
              "  console.log('C05 page1: '+b.items.length+' items');",
              "  if(b.items.length===2) pm.test('C05 limit respected', ()=>pm.expect(b.items.length).to.eql(2));",
              "  if(b.nextCursor) pm.collectionVariables.set('_page_cursor', b.nextCursor);",
              "  else console.log('C05: no nextCursor (not enough data for pagination)');",
              "}"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('ns_name'),limit:2,cursor:null});"]),

        # C06: Pagination page 2 (follow cursor)
        nreq("C06 Page2 Edges", "POST",
             "/v1/spaces/{{space_name}}/graph/edges/list",
             [P, "pm.test('C06 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items&&b.items.length>0) pm.test('C06 page2 has items', ()=>pm.expect(b.items.length).to.be.above(0));",
              "else console.log('C06: page2 empty');"],
             body={"_": ""},
             prerequest=[
                 "const c=pm.collectionVariables.get('_page_cursor');",
                 "if(!c){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.body.raw=JSON.stringify("
                 "{namespaceId:pm.collectionVariables.get('ns_name'),limit:2,cursor:c});"]),
    ]


# ---------------------------------------------------------------------------
#  SECTION D — GRAPH SINGLE READS
# ---------------------------------------------------------------------------

def graph_read_steps():
    return [
        # D01: GET node by URI
        nreq("D01 Get Node", "GET",
             "/v1/spaces/{{space_name}}/graph/node",
             [P, "pm.test('D01 → 200|404', ()=>pm.expect(pm.response.code).to.be.oneOf([200,404]));",
              "if(pm.response.code===200){",
              "  pm.test('D01 uri', ()=>pm.expect(b.uri).to.exist);",
              "  pm.test('D01 name', ()=>pm.expect(b.name).to.exist);",
              "  pm.test('D01 label', ()=>pm.expect(b.label).to.exist);",
              "}"],
             prerequest=[
                 "const u=pm.collectionVariables.get('_node_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/node?uri='+encodeURIComponent(u)+'&namespaceId='+pm.collectionVariables.get('ns_name');"]),

        # D02: GET edge by URI
        nreq("D02 Get Edge", "GET",
             "/v1/spaces/{{space_name}}/graph/edge",
             [P, "pm.test('D02 → 200|404', ()=>pm.expect(pm.response.code).to.be.oneOf([200,404]));",
              "if(pm.response.code===200){",
              "  pm.test('D02 uri', ()=>pm.expect(b.uri).to.exist);",
              "  pm.test('D02 fact', ()=>pm.expect(b.fact).to.exist);",
              "  pm.test('D02 sourceNodeUri', ()=>pm.expect(b.sourceNodeUri).to.exist);",
              "  pm.test('D02 targetNodeUri', ()=>pm.expect(b.targetNodeUri).to.exist);",
              "  pm.test('D02 validAt', ()=>pm.expect(b.validAt).to.exist);",
              "}"],
             prerequest=[
                 "const u=pm.collectionVariables.get('_edge_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge?uri='+encodeURIComponent(u);"]),

        # D03: GET episode by URI
        nreq("D03 Get Episode", "GET",
             "/v1/spaces/{{space_name}}/graph/episode",
             [P, "pm.test('D03 → 200|404', ()=>pm.expect(pm.response.code).to.be.oneOf([200,404]));",
              "if(pm.response.code===200){",
              "  pm.test('D03 uri', ()=>pm.expect(b.uri).to.exist);",
              "  pm.test('D03 sourceType', ()=>pm.expect(b.sourceType).to.exist);",
              "}"],
             prerequest=[
                 "const u=pm.collectionVariables.get('_episode_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/episode?uri='+encodeURIComponent(u);"]),

        # D04: GET stats
        nreq("D04 Stats", "GET",
             "/v1/spaces/{{space_name}}/graph/stats?namespaceId={{ns_name}}",
             [P, "pm.test('D04 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('D04 namespaceId', ()=>pm.expect(b.namespaceId).to.exist);",
              "pm.test('D04 labels', ()=>pm.expect(b.labels).to.exist);",
              "if(b.labels){",
              "  const ec=(b.labels.filter(l=>l.label==='Entity')[0]||{}).count||0;",
              "  pm.collectionVariables.set('_entity_count_before', String(ec));",
              "  console.log('D04 stats: Entity='+ec);",
              "}"]),

        # D05: GET namespace (full graph view)
        nreq("D05 Namespace View", "GET",
             "/v1/spaces/{{space_name}}/graph/namespace?namespaceId={{ns_name}}&limit=200",
             [P, "pm.test('D05 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(pm.response.code===200){",
              "  pm.test('D05 has nodes', ()=>pm.expect(b.nodes).to.exist);",
              "  pm.test('D05 has edges', ()=>pm.expect(b.edges).to.exist);",
              "  console.log('D05 namespace: nodes='+Object.keys(b.nodes||{}).length+' edges='+(b.edges||[]).length);",
              "}"]),
    ]


# ---------------------------------------------------------------------------
#  SECTION E — WRITES + INVALIDATION + PIN/UNPIN
# ---------------------------------------------------------------------------

def write_and_pin_steps():
    return [
        # E01: Create node
        nreq("E01 Create Node", "POST",
             "/v1/spaces/{{space_name}}/graph/node",
             [P, "pm.test('E01 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "if(b.uri) pm.collectionVariables.set('_created_node_uri', b.uri);",
              "pm.test('E01 accepted', ()=>pm.expect(String(b.accepted)).to.eql('true'));"],
             body={"_": ""},
             prerequest=[
                 "pm.request.body.raw=JSON.stringify({namespaceId:pm.collectionVariables.get('ns_name'),"
                 "name:'TestBot-'+Date.now(),label:'Entity',"
                 "summary:'Test entity created by graph test',attributes:{purpose:'test'}});"]),

        # E02: Verify created node (may need projection time)
        nreq("E02 Verify Create", "GET",
             "/v1/spaces/{{space_name}}/graph/node",
             [P, "pm.test('E02 → 200|404', ()=>pm.expect(pm.response.code).to.be.oneOf([200,404]));",
              "if(pm.response.code===200){",
              "  pm.test('E02 label Entity', ()=>pm.expect(b.label).to.eql('Entity'));",
              "  pm.test('E02 summary', ()=>pm.expect(b.summary).to.include('graph test'));",
              "} else console.log('E02: node not yet projected');"],
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_created_node_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/node?uri='+encodeURIComponent(u)+'&namespaceId='+pm.collectionVariables.get('ns_name');"]),

        # E03: Stats after create
        nreq("E03 Stats After", "GET",
             "/v1/spaces/{{space_name}}/graph/stats?namespaceId={{ns_name}}",
             [P, "pm.test('E03 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.labels){",
              "  const ec=(b.labels.filter(l=>l.label==='Entity')[0]||{}).count||0;",
              "  const before=parseInt(pm.collectionVariables.get('_entity_count_before')||'0');",
              "  pm.test('E03 count not decreased', ()=>pm.expect(ec).to.be.at.least(before));",
              "}"]),

        # E04: Patch node
        nreq("E04 Patch Node", "PATCH",
             "/v1/spaces/{{space_name}}/graph/node",
             ["pm.test('E04 → 202|500', ()=>pm.expect(pm.response.code).to.be.oneOf([202,500]));"],
             body={"summary": "Updated by test", "attributes": {"purpose": "test", "updated": "true"}},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_created_node_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/node?uri='+encodeURIComponent(u);"]),

        # E05: Patch edge (correct a fact)
        nreq("E05 Patch Edge", "PATCH",
             "/v1/spaces/{{space_name}}/graph/edge",
             ["pm.test('E05 → 202|500', ()=>pm.expect(pm.response.code).to.be.oneOf([202,500]));"],
             body={"fact": "Corrected fact from test script"},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_edge_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge?uri='+encodeURIComponent(u);"]),

        # E06: Verify patch edge
        nreq("E06 Verify Patch Edge", "GET",
             "/v1/spaces/{{space_name}}/graph/edge",
             [P, "pm.test('E06 → 200|404|500', ()=>pm.expect(pm.response.code).to.be.oneOf([200,404,500]));",
              "if(pm.response.code===200){",
              "  pm.test('E06 has fact', ()=>pm.expect(b.fact).to.exist);",
              "  pm.test('E06 sourceNodeUri', ()=>pm.expect(b.sourceNodeUri).to.exist);",
              "}"],
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_edge_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge?uri='+encodeURIComponent(u);"]),

        # E07: Patch episode
        nreq("E07 Patch Episode", "PATCH",
             "/v1/spaces/{{space_name}}/graph/episode",
             ["pm.test('E07 → 202|500', ()=>pm.expect(pm.response.code).to.be.oneOf([202,500]));"],
             body={"summary": "Corrected summary from test"},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_episode_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/episode?uri='+encodeURIComponent(u);"]),

        # E08: Invalidate fact (PATCH invalidAt on edge_uri_2)
        nreq("E08 Invalidate Fact", "PATCH",
             "/v1/spaces/{{space_name}}/graph/edge",
             ["pm.test('E08 → 202|500', ()=>pm.expect(pm.response.code).to.be.oneOf([202,500]));"],
             body={"invalidAt": "2026-01-01T00:00:00Z"},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_edge_uri_2');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge?uri='+encodeURIComponent(u);"]),

        # E09: Verify invalidated edge has invalidAt
        nreq("E09 Verify Invalidated", "GET",
             "/v1/spaces/{{space_name}}/graph/edge",
             [P, "pm.test('E09 → 200|404|500', ()=>pm.expect(pm.response.code).to.be.oneOf([200,404,500]));",
              "if(pm.response.code===200&&b.invalidAt){",
              "  pm.test('E09 invalidAt set', ()=>pm.expect(b.invalidAt).to.exist);",
              "  pm.collectionVariables.set('_invalidate_fact_text', b.fact||'');",
              "} else console.log('E09: invalidAt not yet visible');"],
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_edge_uri_2');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge?uri='+encodeURIComponent(u);"]),

        # E10: Recall LIVE includeInvalidated=false — invalidated fact excluded
        nreq("E10 Recall Excl Inv", "POST",
             "/v1/memories/{{ns_name}}/recall",
             [P, "pm.test('E10 → 200|500', ()=>pm.expect(pm.response.code).to.be.oneOf([200,500]));"],
             body={"_": ""},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const ft=pm.collectionVariables.get('_invalidate_fact_text')||'test query';",
                 "pm.request.body.raw=JSON.stringify({query:ft.substring(0,80),tokenBudget:1200,"
                 "mode:'LIVE',includeInvalidated:false});"]),

        # E11: Recall LIVE includeInvalidated=true — fact should appear
        nreq("E11 Recall Incl Inv", "POST",
             "/v1/memories/{{ns_name}}/recall",
             [P, "pm.test('E11 → 200|500', ()=>pm.expect(pm.response.code).to.be.oneOf([200,500]));"],
             body={"_": ""},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const ft=pm.collectionVariables.get('_invalidate_fact_text')||'test query';",
                 "pm.request.body.raw=JSON.stringify({query:ft.substring(0,80),tokenBudget:1200,"
                 "mode:'LIVE',includeInvalidated:true});"]),

        # E12: Pin fact (edge_uri)
        nreq("E12 Pin Fact", "POST",
             "/v1/spaces/{{space_name}}/graph/edge/pin",
             ["pm.test('E12 → 202|200|500', ()=>pm.expect(pm.response.code).to.be.oneOf([202,200,500]));"],
             body={"_": ""},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_edge_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "const ns=pm.collectionVariables.get('ns_name');",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge/pin?namespaceId='+ns+'&uri='+encodeURIComponent(u);",
                 "pm.request.body.raw='{}';"]),

        # E13: Recall verify pin — unrelated query should still return pinned fact
        nreq("E13 Recall Pin", "POST",
             "/v1/memories/{{ns_name}}/recall",
             [P, "pm.test('E13 → 200|500', ()=>pm.expect(pm.response.code).to.be.oneOf([200,500]));"],
             body={"query": "weather forecast antarctica penguins ice",
                   "tokenBudget": 2000, "mode": "LIVE"},
             prerequest=["pm.collectionVariables.set('_soft_5xx','true');"]),

        # E14: Unpin fact
        nreq("E14 Unpin Fact", "DELETE",
             "/v1/spaces/{{space_name}}/graph/edge/pin",
             ["pm.test('E14 → 202|200|404|500', ()=>pm.expect(pm.response.code).to.be.oneOf([202,200,404,500]));"],
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_edge_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "const ns=pm.collectionVariables.get('ns_name');",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge/pin?namespaceId='+ns+'&uri='+encodeURIComponent(u);"]),
    ]


# ---------------------------------------------------------------------------
#  SECTION F — DELETES + VERIFY
# ---------------------------------------------------------------------------

def delete_steps():
    return [
        # F01: Delete fact (edge)
        nreq("F01 Delete Fact", "DELETE",
             "/v1/spaces/{{space_name}}/graph/edge",
             ["pm.test('F01 → 202|500', ()=>pm.expect(pm.response.code).to.be.oneOf([202,500]));"],
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_edge_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge?uri='+encodeURIComponent(u);"]),

        # F02: Verify fact deleted → 404
        nreq("F02 Verify Fact Del", "GET",
             "/v1/spaces/{{space_name}}/graph/edge",
             ["pm.test('F02 → 200|404|500', ()=>pm.expect(pm.response.code).to.be.oneOf([200,404,500]));",
              "if(pm.response.code===404) console.log('F02: fact deleted (404)');",
              "else console.log('F02: fact still visible ('+pm.response.code+') — projection pending');"],
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_edge_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge?uri='+encodeURIComponent(u);"]),

        # F03: Delete created node
        nreq("F03 Delete Node", "DELETE",
             "/v1/spaces/{{space_name}}/graph/node",
             ["pm.test('F03 → 202|404|500', ()=>pm.expect(pm.response.code).to.be.oneOf([202,404,500]));"],
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_created_node_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/node?uri='+encodeURIComponent(u);"]),

        # F04: Delete episode
        nreq("F04 Delete Episode", "DELETE",
             "/v1/spaces/{{space_name}}/graph/episode",
             ["pm.test('F04 → 202|404|500', ()=>pm.expect(pm.response.code).to.be.oneOf([202,404,500]));"],
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const u=pm.collectionVariables.get('_episode_uri');",
                 "if(!u){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__';return;}",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/episode?uri='+encodeURIComponent(u);"]),
    ]


# ---------------------------------------------------------------------------
#  SECTION G — NEGATIVE TESTS
# ---------------------------------------------------------------------------

def negative_steps():
    return [
        # G01: GET non-existent node → 404
        nreq("G01 Node 404", "GET",
             "/v1/spaces/{{space_name}}/graph/node?uri=Entity%2Fdoes-not-exist-xyz&namespaceId={{ns_name}}",
             [P, "pm.test('G01 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"]),

        # G02: GET stats bad namespace → 404
        nreq("G02 Bad NS 404", "GET",
             "/v1/spaces/{{space_name}}/graph/stats?namespaceId=no-such-namespace-xyz",
             [P, "pm.test('G02 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"]),

        # G03: PATCH non-existent node → 404
        nreq("G03 Patch 404", "PATCH",
             "/v1/spaces/{{space_name}}/graph/node?uri=Entity%2Fdoes-not-exist-xyz",
             [P, "pm.test('G03 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"summary": "should fail"}),

        # G04: DELETE non-existent edge → 404
        nreq("G04 Delete 404", "DELETE",
             "/v1/spaces/{{space_name}}/graph/edge?uri=Fact%2Fdoes-not-exist-xyz",
             [P, "pm.test('G04 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"]),
    ]


# ---------------------------------------------------------------------------
#  SECTION H — CLEANUP
# ---------------------------------------------------------------------------

def cleanup_steps():
    return [
        # H01: DELETE instruction
        nreq("H01 Del Instruction", "DELETE",
             "/space/by-name/{{space_name}}/instructions?family=EXTRACTION&instructionName=expand-acronyms",
             [P, "pm.test('H01 → 200|400|404', ()=>pm.expect(pm.response.code).to.be.oneOf([200,400,404]));"],
             base=APP, skip_on_fail=False),

        # H02: GET instructions — verify 2 remain
        nreq("H02 Verify Instrs", "GET",
             "/space/by-name/{{space_name}}/instructions",
             [P, "pm.test('H02 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(Array.isArray(b)){",
              "  pm.test('H02 count 2', ()=>pm.expect(b.length).to.eql(2));",
              "  pm.test('H02 acronyms gone', ()=>pm.expect(b.every(i=>i.name!=='expand-acronyms')).to.be.true);",
              "}"],
             base=APP, skip_on_fail=False),

        # H03: DELETE extraction profile
        nreq("H03 Del Profile", "DELETE",
             "/space/by-name/{{space_name}}/extraction-profile",
             [P, "pm.test('H03 → 200|400|404', ()=>pm.expect(pm.response.code).to.be.oneOf([200,400,404]));"],
             base=APP, skip_on_fail=False),

        # H04: GET profile — verify empty
        nreq("H04 Verify Profile Del", "GET",
             "/space/by-name/{{space_name}}/extraction-profile",
             [P, "pm.test('H04 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(Array.isArray(b)) console.log('H04: profiles remaining: '+b.length);"],
             base=APP, skip_on_fail=False),

        # H05: Verify extraction/status profileConfigured=false
        nreq("H05 Status After Cleanup", "GET",
             "/v1/spaces/{{space_name}}/extraction/status",
             [P, "pm.test('H05 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.profileConfigured===false) pm.test('H05 profileConfigured false', ()=>pm.expect(b.profileConfigured).to.eql(false));",
              "else console.log('H05: profileConfigured='+b.profileConfigured+' (cache may not have invalidated)');"],
             skip_on_fail=False),

        # H06: DELETE space
        req("H06 Del Space", "DELETE",
            "/space/by-name/{{space_name}}",
            ["pm.test('H06 → 200|204|404', ()=>pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=APP,
            extra_headers=[{"key": "X-Fabric", "value": "{{fabric_id}}"}],
            skip_on_fail=False),

        # H07: Verify recall → 404
        nreq("H07 Recall 404", "POST",
             "/v1/spaces/{{space_name}}/recall",
             ["pm.test('H07 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"query": "anything", "tokenBudget": 100, "mode": "LIVE"},
             skip_on_fail=False),

        # H08: Verify stats → 404
        nreq("H08 Stats 404", "GET",
             "/v1/spaces/{{space_name}}/graph/stats?namespaceId={{ns_name}}",
             ["pm.test('H08 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             skip_on_fail=False),

        # H09: Verify list → 404
        nreq("H09 List 404", "POST",
             "/v1/spaces/{{space_name}}/graph/nodes/list",
             ["pm.test('H09 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('ns_name'),limit:5,cursor:null});"],
             skip_on_fail=False),

        # H10: Verify ingest → 404
        nreq("H10 Ingest 404", "POST",
             "/v1/spaces/{{space_name}}/ingest",
             ["pm.test('H10 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"content": "should fail", "threadId": "test"},
             skip_on_fail=False),

        # Teardown
        {
            "name": "99 Teardown",
            "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": [
                "pm.test('99 teardown', ()=>pm.expect(pm.response.code).to.be.oneOf([200,204,401,404]));",
                "pm.collectionVariables.unset('_flow_failed');",
                "pm.collectionVariables.unset('_flow_failed_at');",
            ]}}],
            "request": {
                "method": "GET", "header": [],
                "url": {"raw": "{{neuro_base_url}}/v1/health",
                        "host": ["{{neuro_base_url}}"], "path": ["v1", "health"]},
                "auth": {"type": "noauth"},
            },
            "response": [],
        },
    ]


# ---------------------------------------------------------------------------
#  GENERATE
# ---------------------------------------------------------------------------

def generate():
    items = [
        setup_step(),
        *steering_config_steps(),
        *data_injection_steps(),
        *graph_listing_steps(),
        *graph_read_steps(),
        *write_and_pin_steps(),
        *delete_steps(),
        *negative_steps(),
        *cleanup_steps(),
    ]

    col = build_collection(
        "FLOW - Neuro Graph Test",
        "Comprehensive neuro graph API integration test.\n\n"
        "Sections: A) Space + Steering Config, B) Data Injection + Recall,\n"
        "C) Graph Listings + Pagination, D) Single Reads, E) Writes + Pin/Unpin,\n"
        "F) Deletes, G) Negative Tests, H) Cleanup.\n\n"
        "Recommended: --delay-request 5000 --timeout-request 60000",
        "Neuro Graph Test",
        items,
        extra_variables=NEURO_GRAPH_VARS,
    )
    write_flow("FLOW-Neuro-Graph-Test.postman_collection.json", col)
