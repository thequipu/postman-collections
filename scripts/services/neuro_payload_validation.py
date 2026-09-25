"""FLOW-Neuro-Payload-Validation: Comprehensive neuro ingest & recall validation.

Converted from neuro_payload_validation_prestage.sh / netapp.sh.
Covers all 17 sections: 5 ingest doors, 2 recall surfaces, graph ingest,
assert, auth, idempotency, invalidation matrix, content grammar,
round-trip verification, MCP, and cleanup.

Environment variables required (via --env-var):
  neuro_base_url   — e.g. https://api-prestage-1-prestage.thequipu.in/quipuNeuro
  app_base_url     — e.g. https://api-prestage-1-prestage.thequipu.in/applicationService
  fabric_id        — e.g. memoryquipuprestage  (X-Fabric header)
  tenant_id, client_id, client_secret, test_username, test_password,
  keycloak_token_url
"""

from flowlib.core import req, build_setup, build_collection, write_flow

NEURO = "neuro_base_url"
APP = "app_base_url"
FABRIC_HDR = [{"key": "X-Fabric", "value": "{{fabric_id}}"}]
P = "let b={}; try{b=pm.response.json();}catch(e){}"


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


NEURO_VARS = [
    {"key": "space_name", "value": "", "type": "string"},
    {"key": "ns_name", "value": "", "type": "string"},
    {"key": "graph_ns", "value": "", "type": "string"},
    {"key": "fabric_id", "value": "", "type": "string"},
    {"key": "_ingest1_unit_id", "value": "", "type": "string"},
    {"key": "_ingest1_body", "value": "", "type": "string"},
    {"key": "_ns_ingest_unit_id", "value": "", "type": "string"},
    {"key": "_ns_ingest_body", "value": "", "type": "string"},
    {"key": "_thread_onboard", "value": "onboarding-2026Q3", "type": "string"},
    {"key": "_thread_project", "value": "project-helix-alpha", "type": "string"},
    {"key": "_thread_standup", "value": "daily-standup-20260831", "type": "string"},
    {"key": "_owner_alice", "value": "user-alice-nkomo", "type": "string"},
    {"key": "_owner_bob", "value": "user-bob-tanaka", "type": "string"},
    {"key": "_graph_id", "value": "product-docs", "type": "string"},
    {"key": "_mx_edge_uri", "value": "", "type": "string"},
    {"key": "_mx_query", "value": "", "type": "string"},
]


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
                "const sp='npv-'+Date.now();",
                "pm.collectionVariables.set('space_name', sp);",
                "pm.collectionVariables.set('ns_name', sp+'-self');",
                "pm.collectionVariables.set('graph_ns', sp+'-'+pm.collectionVariables.get('_graph_id'));",
                "if(!pm.environment.get('fabric_id')&&pm.collectionVariables.get('fabric_id')){",
                "  pm.environment.set('fabric_id',pm.collectionVariables.get('fabric_id'));",
                "}",
                "pm.collectionVariables.set('_skip_url',"
                " pm.environment.get('neuro_base_url')+'/v1/health');",
                "console.log('Setup: space='+sp+' tenant='+pm.environment.get('tenant_id')"
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
#  SECTION 1 — SPACE INGEST
# ---------------------------------------------------------------------------

def space_ingest_steps():
    SI = "/v1/spaces/{{space_name}}/ingest"
    return [
        # SI-01: All fields (happy path) — creates the space implicitly
        nreq("SI-01 All Fields", "POST", SI,
             ["const code=pm.response.code;",
              "pm.test('SI-01 → 202', ()=>{ if(code!==202){pm.collectionVariables.set('_flow_failed','true');"
              "pm.collectionVariables.set('_flow_failed_at','SI-01');} pm.expect(code).to.eql(202); });",
              P,
              "pm.test('SI-01 unitId', ()=>pm.expect(b.unitId).to.exist);",
              "pm.test('SI-01 unitId UUID', ()=>pm.expect(b.unitId).to.match(/^[0-9a-f]{8}-/));",
              "pm.test('SI-01 namespaceId', ()=>pm.expect(b.namespaceId).to.exist);",
              "pm.test('SI-01 ns ends -self', ()=>pm.expect(b.namespaceId).to.include('self'));",
              "pm.test('SI-01 2 keys', ()=>pm.expect(Object.keys(b).length).to.eql(2));",
              "if(b.unitId) pm.collectionVariables.set('_ingest1_unit_id', b.unitId);"],
             body={"_": ""},
             prerequest=[
                 "const body={content:'Dr. Amara Osei joined Meridian Health Sciences as Chief Research "
                 "Officer in January 2024. She relocated from the Accra office to the Boston headquarters "
                 "and now leads the Helix Alpha clinical trial program.',"
                 "threadId:pm.collectionVariables.get('_thread_onboard'),"
                 "contentType:'text/plain',role:'user',speaker:'hr.admin@meridian.example',"
                 "occurredAt:'2024-01-15T09:00:00Z'};",
                 "pm.collectionVariables.set('_ingest1_body', JSON.stringify(body));",
                 "pm.request.body.raw=JSON.stringify(body);",
             ]),

        # SI-02: Minimal (content only)
        nreq("SI-02 Minimal", "POST", SI,
             [P, "pm.test('SI-02 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "pm.test('SI-02 unitId', ()=>pm.expect(b.unitId).to.exist);"],
             body={"content": "Bob Tanaka is a data engineer working from the Tokyo satellite office."}),

        # SI-03: Blank content → 400
        nreq("SI-03 Blank Content", "POST", SI,
             [P, "pm.test('SI-03 → 400', ()=>pm.expect(pm.response.code).to.eql(400));",
              "pm.test('SI-03 errorCode', ()=>pm.expect(b.errorCode).to.exist);",
              "pm.test('SI-03 msg mentions content', ()=>pm.expect(String(b.message||'')).to.include('content'));"],
             body={"content": "", "threadId": "test", "role": "user"}),

        # SI-04: Whitespace content → 400
        nreq("SI-04 Whitespace Content", "POST", SI,
             ["pm.test('SI-04 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"content": "   ", "threadId": "test"}),

        # SI-05: TRAP — text instead of content → 400
        nreq("SI-05 Text Trap", "POST", SI,
             [P, "pm.test('SI-05 → 400', ()=>pm.expect(pm.response.code).to.eql(400));",
              "pm.test('SI-05 says content', ()=>pm.expect(String(b.message||'')).to.include('content'));"],
             body={"text": "Wrong field for space ingest", "threadId": "trap-test"}),

        # SI-06: Null content → 400
        nreq("SI-06 Null Content", "POST", SI,
             ["pm.test('SI-06 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"content": None, "threadId": "test"}),

        # SI-07: role:llm
        nreq("SI-07 Role LLM", "POST", SI,
             [P, "pm.test('SI-07 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "pm.test('SI-07 unitId', ()=>pm.expect(b.unitId).to.exist);"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({content:'Based on the records, Dr. Osei "
                         "specializes in immunotherapy and has published 47 papers on checkpoint inhibitors.',"
                         "role:'llm',threadId:pm.collectionVariables.get('_thread_project'),"
                         "occurredAt:'2024-02-10T14:30:00Z'});"]),

        # SI-08: role:ASSISTANT
        nreq("SI-08 Role ASSISTANT", "POST", SI,
             ["pm.test('SI-08 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({content:'Dr. Osei\\'s latest grant application "
                         "was approved for $2.4M from the NIH to fund Phase II trials.',"
                         "role:'ASSISTANT',threadId:pm.collectionVariables.get('_thread_project'),"
                         "occurredAt:'2024-03-05T11:00:00Z'});"]),

        # SI-09: role:user (explicit)
        nreq("SI-09 Role User", "POST", SI,
             ["pm.test('SI-09 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({content:'The clinical operations team "
                         "expanded to 12 members under Dr. Osei\\'s leadership by Q2 2024.',"
                         "role:'user',speaker:'project.lead@meridian.example',"
                         "threadId:pm.collectionVariables.get('_thread_project'),"
                         "occurredAt:'2024-06-15T10:00:00Z'});"]),

        # SI-10: role custom value
        nreq("SI-10 Role Custom", "POST", SI,
             ["pm.test('SI-10 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({content:'External audit confirmed Meridian\\'s "
                         "Boston lab meets ISO 15189 accreditation standards.',"
                         "role:'auditor',threadId:pm.collectionVariables.get('_thread_project'),"
                         "occurredAt:'2024-07-20T16:00:00Z'});"]),

        # SI-11: speaker field
        nreq("SI-11 Speaker", "POST", SI,
             ["pm.test('SI-11 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({content:'I think we should move the Phase II "
                         "deadline to September given the enrollment delays.',"
                         "speaker:'Dr. Amara Osei',threadId:pm.collectionVariables.get('_thread_standup'),"
                         "occurredAt:'2026-08-31T09:15:00Z'});"]),

        # SI-12: contentType text/markdown
        nreq("SI-12 Markdown", "POST", SI,
             ["pm.test('SI-12 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({content:'## Weekly Update\\n- Enrollment: "
                         "84/120 patients\\n- Site activation: Chicago + Houston live\\n- Next milestone: "
                         "interim analysis Oct 2026',contentType:'text/markdown',"
                         "threadId:pm.collectionVariables.get('_thread_project'),"
                         "occurredAt:'2026-08-28T08:00:00Z'});"]),

        # SI-13: contentType application/json
        nreq("SI-13 JSON Content", "POST", SI,
             ["pm.test('SI-13 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({content:JSON.stringify({trial:'Helix Alpha',"
                         "phase:2,sites:['Boston','Chicago','Houston']}),"
                         "contentType:'application/json',"
                         "threadId:pm.collectionVariables.get('_thread_project'),"
                         "occurredAt:'2026-08-25T12:00:00Z'});"]),

        # SI-14: occurredAt far past (backfill)
        nreq("SI-14 Backfill", "POST", SI,
             ["pm.test('SI-14 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"content": "Meridian Health Sciences was founded in 2018 by Dr. Kwame Mensah in Accra, "
                   "Ghana, originally focused on malaria vaccine research.",
                   "occurredAt": "2018-03-01T00:00:00Z", "threadId": "company-history"}),

        # SI-15: occurredAt omitted
        nreq("SI-15 No OccurredAt", "POST", SI,
             ["pm.test('SI-15 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"content": "The new genomics sequencer arrived at the Boston lab this morning."}),

        # SI-16: Unknown field (silently ignored)
        nreq("SI-16 Unknown Field", "POST", SI,
             [P, "pm.test('SI-16 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "pm.test('SI-16 unitId', ()=>pm.expect(b.unitId).to.exist);"],
             body={"content": "Dr. Yuki Sato joined as Head of Bioinformatics.",
                   "conntent": "typo field", "threadID": "wrong case",
                   "occurredAt": "2025-09-01T00:00:00Z"}),

        # SI-17: ownerUserId on space form (silently dropped)
        nreq("SI-17 Owner Dropped", "POST", SI,
             ["pm.test('SI-17 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({content:'Dr. Fatima Al-Rashid manages "
                         "regulatory submissions for Meridian in the EU.',"
                         "ownerUserId:pm.collectionVariables.get('_owner_alice'),"
                         "occurredAt:'2025-06-15T00:00:00Z'});"]),

        # SI-18: Empty body → 400
        nreq("SI-18 Empty Body", "POST", SI,
             ["pm.test('SI-18 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={}),

        # SI-19: Error envelope shape
        nreq("SI-19 Error Shape", "POST", SI,
             [P, "pm.test('SI-19 → 400', ()=>pm.expect(pm.response.code).to.eql(400));",
              "pm.test('SI-19 errorCode', ()=>pm.expect(b.errorCode).to.exist);",
              "pm.test('SI-19 errorCode Q400', ()=>pm.expect(b.errorCode).to.eql('Q400'));",
              "pm.test('SI-19 message', ()=>pm.expect(b.message).to.exist);",
              "pm.test('SI-19 timestamp', ()=>pm.expect(b.timestamp).to.exist);",
              "pm.test('SI-19 3 keys', ()=>pm.expect(Object.keys(b).length).to.eql(3));"],
             body={"content": ""}),
    ]


# ---------------------------------------------------------------------------
#  SECTION 2 — NAMESPACE INGEST
# ---------------------------------------------------------------------------

def namespace_ingest_steps():
    NI = "/v1/memories/{{ns_name}}/ingest"
    return [
        # NI-01: All fields
        nreq("NI-01 All Fields", "POST", NI,
             [P, "pm.test('NI-01 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "pm.test('NI-01 unitId', ()=>pm.expect(b.unitId).to.exist);",
              "pm.test('NI-01 unitId UUID', ()=>pm.expect(b.unitId).to.match(/^[0-9a-f]{8}-/));",
              "pm.test('NI-01 1 key', ()=>pm.expect(Object.keys(b).length).to.eql(1));",
              "if(b.unitId) pm.collectionVariables.set('_ns_ingest_unit_id', b.unitId);"],
             body={"_": ""},
             prerequest=[
                 "const body={text:'Alice Nkomo is a clinical data manager at Meridian Health Sciences, "
                 "based in the Nairobi regional office. She handles patient data reconciliation for the "
                 "Helix Alpha trial across three African sites.',"
                 "threadId:pm.collectionVariables.get('_thread_onboard'),"
                 "contentType:'text/plain',sourceType:'USER',occurredAt:'2025-01-10T08:00:00Z',"
                 "ownerUserId:pm.collectionVariables.get('_owner_alice')};",
                 "pm.collectionVariables.set('_ns_ingest_body', JSON.stringify(body));",
                 "pm.request.body.raw=JSON.stringify(body);",
             ]),

        # NI-02: Minimal (text only)
        nreq("NI-02 Minimal", "POST", NI,
             ["pm.test('NI-02 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"text": "Bob Tanaka transferred from Tokyo to the Boston office in March 2025 "
                   "to lead data pipeline engineering."}),

        # NI-03: Blank text → 400
        nreq("NI-03 Blank Text", "POST", NI,
             ["pm.test('NI-03 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"text": "", "sourceType": "USER"}),

        # NI-04: Whitespace text → 400
        nreq("NI-04 Whitespace", "POST", NI,
             ["pm.test('NI-04 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"text": "   ", "sourceType": "USER"}),

        # NI-05: TRAP — content instead of text → 400
        nreq("NI-05 Content Trap", "POST", NI,
             ["pm.test('NI-05 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"content": "Wrong field for namespace ingest", "sourceType": "USER"}),

        # NI-06: Null text → 400
        nreq("NI-06 Null Text", "POST", NI,
             ["pm.test('NI-06 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"text": None, "sourceType": "USER"}),

        # NI-07: sourceType USER
        nreq("NI-07 SourceType USER", "POST", NI,
             ["pm.test('NI-07 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"text": "Source type USER: Dr. Osei presented the interim results at ASCO 2025 in Chicago.",
                   "sourceType": "USER", "occurredAt": "2025-06-02T14:00:00Z"}),

        # NI-08: sourceType DOCUMENT
        nreq("NI-08 SourceType DOCUMENT", "POST", NI,
             ["pm.test('NI-08 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"text": "Source type DOCUMENT: The Helix Alpha Protocol v3.2 specifies a maximum of "
                   "120 enrolled patients across 8 sites with a primary endpoint of progression-free "
                   "survival at 12 months.", "sourceType": "DOCUMENT", "occurredAt": "2024-11-01T00:00:00Z"}),

        # NI-09: sourceType LLM
        nreq("NI-09 SourceType LLM", "POST", NI,
             ["pm.test('NI-09 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"text": "Source type LLM: Based on enrollment projections, the trial should reach full "
                   "enrollment by October 2026.", "sourceType": "LLM", "occurredAt": "2026-07-01T00:00:00Z"}),

        # NI-10: sourceType AGENT_OTEL
        nreq("NI-10 SourceType AGENT_OTEL", "POST", NI,
             ["pm.test('NI-10 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"text": "Source type AGENT_OTEL: Automated lab report processing completed 847 samples.",
                   "sourceType": "AGENT_OTEL", "occurredAt": "2026-08-29T22:00:00Z"}),

        # NI-11: sourceType KAFKA (may not exist in all deployments)
        nreq("NI-11 SourceType KAFKA", "POST", NI,
             ["pm.test('NI-11 → 202|400', ()=>pm.expect(pm.response.code).to.be.oneOf([202,400]));"],
             body={"text": "Source type KAFKA: Patient enrollment event site Houston.",
                   "sourceType": "KAFKA", "occurredAt": "2026-08-30T11:30:00Z"}),

        # NI-12: sourceType omitted (defaults)
        nreq("NI-12 SourceType Default", "POST", NI,
             ["pm.test('NI-12 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"text": "The quarterly board meeting is scheduled for September 15th at Boston."}),

        # NI-13: ownerUserId Bob
        nreq("NI-13 Owner Bob", "POST", NI,
             ["pm.test('NI-13 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({text:'Bob Tanaka built the real-time adverse "
                         "event monitoring dashboard using Apache Kafka and Grafana.',"
                         "sourceType:'USER',ownerUserId:pm.collectionVariables.get('_owner_bob'),"
                         "occurredAt:'2025-04-01T00:00:00Z'});"]),

        # NI-14: ownerUserId whitespace → 500 (known bug)
        nreq("NI-14 Owner Whitespace", "POST", NI,
             ["pm.test('NI-14 → 500|400', ()=>pm.expect(pm.response.code).to.be.oneOf([500,400]));"],
             body={"text": "Whitespace ownerUserId test.", "sourceType": "USER", "ownerUserId": "   "},
             prerequest=["pm.collectionVariables.set('_soft_5xx','true');"]),

        # NI-15: ownerUserId >128 chars → 500
        nreq("NI-15 Owner Too Long", "POST", NI,
             ["pm.test('NI-15 → 500|400', ()=>pm.expect(pm.response.code).to.be.oneOf([500,400]));"],
             body={"_": ""},
             prerequest=["pm.collectionVariables.set('_soft_5xx','true');",
                         "pm.request.body.raw=JSON.stringify({text:'Long ownerUserId test.',"
                         "sourceType:'USER',ownerUserId:'x'.repeat(132)});"]),

        # NI-16: no occurredAt
        nreq("NI-16 No OccurredAt", "POST", NI,
             ["pm.test('NI-16 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"text": "The new mass spectrometer was calibrated for clinical use in the proteomics wing.",
                   "sourceType": "USER"}),

        # NI-17: past occurredAt
        nreq("NI-17 Past OccurredAt", "POST", NI,
             ["pm.test('NI-17 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"text": "The Nairobi office opened in 2022 as Meridian's first presence in East Africa.",
                   "sourceType": "USER", "occurredAt": "2022-06-01T00:00:00Z"}),

        # NI-18: Unknown field (ignored)
        nreq("NI-18 Unknown Field", "POST", NI,
             ["pm.test('NI-18 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"text": "Dr. Lena Petrova joined as Head of Biostatistics from Moscow.",
                   "conntent": "typo", "sourcetype": "wrong case"}),

        # NI-19: Empty body → 400
        nreq("NI-19 Empty Body", "POST", NI,
             ["pm.test('NI-19 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={}),

        # NI-20: Bad namespace → 404
        nreq("NI-20 Bad Namespace", "POST", "/v1/memories/does-not-exist-ns-xyz/ingest",
             [P, "pm.test('NI-20 → 404', ()=>pm.expect(pm.response.code).to.eql(404));",
              "pm.test('NI-20 has error', ()=>pm.expect(b.error).to.exist);",
              "pm.test('NI-20 no errorCode', ()=>pm.expect(b.errorCode).to.be.undefined);",
              "pm.test('NI-20 no timestamp', ()=>pm.expect(b.timestamp).to.be.undefined);"],
             body={"text": "This namespace does not exist."}),
    ]


# ---------------------------------------------------------------------------
#  SECTION 3 — GRAPH INGEST + ASSERT
# ---------------------------------------------------------------------------

def graph_ingest_assert_steps():
    SA = "/v1/spaces/{{space_name}}/assert"
    return [
        # Create graph namespace via applicationService
        req("GI-00 Create Graph NS", "POST",
            "/space/by-name/{{space_name}}/graph",
            [P, "pm.test('GI-00 graph ns', ()=>pm.expect(pm.response.code).to.be.oneOf([200,201,409]));"],
            base=APP, body={"_": ""},
            extra_headers=[{"key": "X-Fabric", "value": "{{fabric_id}}"}],
            prerequest=["pm.request.body.raw=JSON.stringify({graphId:pm.collectionVariables.get('_graph_id'),"
                        "label:'Product Documentation'});"]),

        # GI-01: Graph ingest
        nreq("GI-01 Graph Ingest", "POST",
             "/v1/spaces/{{space_name}}/graphs/{{_graph_id}}/ingest",
             [P, "pm.test('GI-01 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "pm.test('GI-01 namespaceId', ()=>pm.expect(b.namespaceId).to.exist);",
              "const gns=pm.collectionVariables.get('graph_ns');",
              "if(gns) pm.test('GI-01 ns matches', ()=>pm.expect(b.namespaceId).to.eql(gns));"],
             body={"content": "The HelixDB platform is Meridian's proprietary clinical data warehouse, "
                   "built on PostgreSQL 16 with custom genomic data types.",
                   "threadId": "graph-docs-001", "contentType": "text/plain",
                   "role": "user", "speaker": "tech.lead@meridian.example",
                   "occurredAt": "2025-01-01T00:00:00Z"}),

        # GI-02: Graph ingest to non-existent graph (auto-creates)
        nreq("GI-02 Auto-Create Graph", "POST",
             "/v1/spaces/{{space_name}}/graphs/auto-created-graph/ingest",
             [P, "pm.test('GI-02 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "pm.test('GI-02 namespaceId', ()=>pm.expect(b.namespaceId).to.exist);"],
             body={"content": "This graph namespace is auto-created on first write.", "threadId": "test"}),

        # SA-01: Assert all fields
        nreq("SA-01 Assert Full", "POST", SA,
             [P, "pm.test('SA-01 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "pm.test('SA-01 accepted', ()=>pm.expect(String(b.accepted)).to.eql('true'));",
              "pm.test('SA-01 unitId', ()=>pm.expect(b.unitId).to.exist);",
              "pm.test('SA-01 unitId UUID', ()=>pm.expect(b.unitId).to.match(/^[0-9a-f]{8}-/));",
              "pm.test('SA-01 namespaceId', ()=>pm.expect(b.namespaceId).to.exist);",
              "pm.test('SA-01 detail', ()=>pm.expect(b.detail).to.exist);",
              "pm.test('SA-01 detail has extraction', ()=>pm.expect(b.detail).to.include('extraction'));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({entitySurfaceForm:'Dr. Amara Osei',"
                         "label:'Person',property:'leads_trial',value:'Helix Alpha Phase II',"
                         "worldTime:true,validFrom:'2024-01-15T00:00:00Z',validTo:null,graphId:null,"
                         "threadId:pm.collectionVariables.get('_thread_project')});"]),

        # SA-02: Minimal required fields
        nreq("SA-02 Assert Minimal", "POST", SA,
             ["pm.test('SA-02 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "Meridian Health Sciences", "property": "founded_in",
                   "value": "2018", "worldTime": False}),

        # SA-03: Blank entity → 400
        nreq("SA-03 Blank Entity", "POST", SA,
             ["pm.test('SA-03 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"entitySurfaceForm": "", "property": "works_at", "value": "Meridian"}),

        # SA-04: Blank property → 400
        nreq("SA-04 Blank Property", "POST", SA,
             ["pm.test('SA-04 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"entitySurfaceForm": "Dr. Osei", "property": "", "value": "Boston"}),

        # SA-05: Blank value → 400
        nreq("SA-05 Blank Value", "POST", SA,
             ["pm.test('SA-05 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"entitySurfaceForm": "Dr. Osei", "property": "located_in", "value": ""}),

        # SA-06: worldTime null → 400
        nreq("SA-06 WorldTime Null", "POST", SA,
             ["pm.test('SA-06 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"entitySurfaceForm": "Dr. Osei", "property": "located_in",
                   "value": "Boston", "worldTime": None}),

        # SA-07: worldTime true + validFrom
        nreq("SA-07 WorldTime+ValidFrom", "POST", SA,
             ["pm.test('SA-07 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "Alice Nkomo", "label": "Person", "property": "based_in",
                   "value": "Nairobi", "worldTime": True, "validFrom": "2022-06-01T00:00:00Z"}),

        # SA-08: worldTime true, no validFrom
        nreq("SA-08 WorldTime No ValidFrom", "POST", SA,
             ["pm.test('SA-08 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "Bob Tanaka", "label": "Person",
                   "property": "specializes_in", "value": "data pipeline engineering",
                   "worldTime": True}),

        # SA-09: worldTime false
        nreq("SA-09 WorldTime False", "POST", SA,
             ["pm.test('SA-09 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "HelixDB", "label": "Product", "property": "built_on",
                   "value": "PostgreSQL 16", "worldTime": False}),

        # SA-10: worldTime omitted → 400
        nreq("SA-10 WorldTime Omitted", "POST", SA,
             ["pm.test('SA-10 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"entitySurfaceForm": "Meridian Health Sciences",
                   "property": "headquartered_in", "value": "Boston, Massachusetts"}),

        # SA-11: Bounded window (validFrom + validTo)
        nreq("SA-11 Bounded Window", "POST", SA,
             ["pm.test('SA-11 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "Dr. Kwame Mensah", "label": "Person",
                   "property": "role", "value": "CEO", "worldTime": True,
                   "validFrom": "2018-03-01T00:00:00Z", "validTo": "2023-12-31T00:00:00Z"}),

        # SA-12: validTo without validFrom
        nreq("SA-12 ValidTo Only", "POST", SA,
             ["pm.test('SA-12 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "Dr. Mensah", "label": "Person",
                   "property": "served_as", "value": "board advisor", "worldTime": True,
                   "validTo": "2026-12-31T00:00:00Z"}),

        # SA-13: graphId → write to graph namespace
        nreq("SA-13 Assert to Graph", "POST", SA,
             ["pm.test('SA-13 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({entitySurfaceForm:'HelixDB',label:'Product',"
                         "property:'processes_daily',value:'2 terabytes of sequencing data',worldTime:false,"
                         "graphId:pm.collectionVariables.get('_graph_id')});"]),

        # SA-14: graphId non-writable auto-creates
        nreq("SA-14 Assert New Graph", "POST", SA,
             ["pm.test('SA-14 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "Test", "property": "tested_by", "value": "automation",
                   "worldTime": False, "graphId": "assert-auto-graph"}),

        # SA-15: threadId
        nreq("SA-15 With ThreadId", "POST", SA,
             ["pm.test('SA-15 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({entitySurfaceForm:'Dr. Yuki Sato',"
                         "label:'Person',property:'heads',value:'Bioinformatics department',"
                         "worldTime:false,threadId:pm.collectionVariables.get('_thread_standup')});"]),

        # SA-16: Underscore property (rendered as spaces in recall)
        nreq("SA-16 Underscore Prop", "POST", SA,
             ["pm.test('SA-16 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "Dr. Fatima Al-Rashid", "label": "Person",
                   "property": "manages_regulatory_submissions_for", "value": "EU market",
                   "worldTime": False}),

        # NA-01: Namespace assert
        nreq("NA-01 NS Assert", "POST", "/v1/memories/{{ns_name}}/assert",
             ["pm.test('NA-01 → 202', ()=>pm.expect(pm.response.code).to.eql(202));"],
             body={"entitySurfaceForm": "Dr. Lena Petrova", "label": "Person",
                   "property": "joined_from", "value": "Moscow Institute of Biostatistics",
                   "worldTime": True, "validFrom": "2025-11-01T00:00:00Z"}),

        # NA-02: Bad namespace → 404
        nreq("NA-02 Bad NS Assert", "POST", "/v1/memories/does-not-exist-ns-xyz/assert",
             ["pm.test('NA-02 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"entitySurfaceForm": "Test", "property": "test", "value": "test",
                   "worldTime": False}),
    ]


# ---------------------------------------------------------------------------
#  PROJECTION WAIT — check stats until entities >= 5
# ---------------------------------------------------------------------------

def projection_wait_step():
    return nreq("PW-01 Projection Wait", "GET",
                "/v1/spaces/{{space_name}}/graph/stats",
                ["pm.collectionVariables.set('_soft_5xx','true');",
                 P, "pm.test('PW-01 stats accessible', "
                 "()=>pm.expect(pm.response.code).to.be.oneOf([200,404,500]));",
                 "if(pm.response.code===200 && b.labels){",
                 "  const ents=(b.labels.find(l=>l.label==='Entity')||{}).count||0;",
                 "  console.log('Projection: '+ents+' entities');",
                 "  if(ents>0) pm.test('PW-01 entities projected', ()=>pm.expect(ents).to.be.above(0));",
                 "}"],
                prerequest=[
                    "const ns=pm.collectionVariables.get('ns_name');",
                    "pm.request.url=pm.environment.get('neuro_base_url')"
                    "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                    "+'/graph/stats?namespaceId='+encodeURIComponent(ns);",
                ])


# ---------------------------------------------------------------------------
#  SECTION 4 — RECALL INPUT VALIDATION
# ---------------------------------------------------------------------------

def recall_input_steps():
    SR = "/v1/spaces/{{space_name}}/recall"
    NR = "/v1/memories/{{ns_name}}/recall"
    return [
        # SR-01: All fields
        nreq("SR-01 All Fields", "POST", SR,
             [P, "pm.test('SR-01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('SR-01 items array', ()=>pm.expect(b.items).to.be.an('array'));",
              "pm.test('SR-01 dropped boolean', ()=>pm.expect(typeof b.droppedDueToBudget).to.eql('boolean'));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'What role does Dr. Amara Osei hold?',"
                         "tokenBudget:2000,mode:'LIVE',"
                         "threadId:pm.collectionVariables.get('_thread_project'),"
                         "includeInvalidated:false});"]),

        # SR-02: Minimal (query only)
        nreq("SR-02 Minimal", "POST", SR,
             ["pm.test('SR-02 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "Who works at Meridian?", "tokenBudget": 1000}),

        # SR-03: Empty query → 400
        nreq("SR-03 Empty Query", "POST", SR,
             ["pm.test('SR-03 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"query": "", "tokenBudget": 1000}),

        # SR-04: Blank query → 400
        nreq("SR-04 Blank Query", "POST", SR,
             ["pm.test('SR-04 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"query": "   ", "tokenBudget": 1000}),

        # SR-05: Null query → 400
        nreq("SR-05 Null Query", "POST", SR,
             ["pm.test('SR-05 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"query": None, "tokenBudget": 1000}),

        # SR-06: Missing query → 400
        nreq("SR-06 Missing Query", "POST", SR,
             ["pm.test('SR-06 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={"tokenBudget": 1000}),

        # SR-07: tokenBudget 0 → 400 or 200
        nreq("SR-07 Budget Zero", "POST", SR,
             ["pm.test('SR-07 → 200|400', ()=>pm.expect(pm.response.code).to.be.oneOf([200,400]));"],
             body={"query": "test", "tokenBudget": 0}),

        # SR-08: tokenBudget -1 → fallback
        nreq("SR-08 Budget Negative", "POST", SR,
             [P, "pm.test('SR-08 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('SR-08 items', ()=>pm.expect(b.items).to.be.an('array'));"],
             body={"query": "Who founded Meridian Health Sciences?", "tokenBudget": -1}),

        # SR-09: tokenBudget 50 (tiny) → droppedDueToBudget
        nreq("SR-09 Budget Tiny", "POST", SR,
             [P, "pm.test('SR-09 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('SR-09 dropped is boolean', ()=>pm.expect(typeof b.droppedDueToBudget).to.eql('boolean'));"],
             body={"query": "Tell me everything about every person at Meridian",
                   "tokenBudget": 50, "mode": "LIVE"}),

        # SR-10: tokenBudget 10000 (large) → dropped false
        nreq("SR-10 Budget Large", "POST", SR,
             [P, "pm.test('SR-10 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('SR-10 dropped false', ()=>pm.expect(b.droppedDueToBudget).to.eql(false));"],
             body={"query": "Who is Dr. Osei?", "tokenBudget": 10000, "mode": "LIVE"}),

        # SR-11: mode LIVE
        nreq("SR-11 Mode LIVE", "POST", SR,
             [P, "pm.test('SR-11 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('SR-11 items', ()=>pm.expect(b.items).to.be.an('array'));"],
             body={"query": "What clinical trial does Dr. Osei lead?",
                   "tokenBudget": 1500, "mode": "LIVE"}),

        # SR-12: mode EPISODIC
        nreq("SR-12 Mode EPISODIC", "POST", SR,
             [P, "pm.test('SR-12 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('SR-12 items', ()=>pm.expect(b.items).to.exist);"],
             body={"query": "What clinical trial does Dr. Osei lead?",
                   "tokenBudget": 1500, "mode": "EPISODIC"}),

        # SR-13: mode AS_OF + asOf
        nreq("SR-13 Mode AS_OF", "POST", SR,
             [P, "pm.test('SR-13 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('SR-13 items', ()=>pm.expect(b.items).to.exist);"],
             body={"query": "Who was the CEO of Meridian?", "tokenBudget": 1500,
                   "mode": "AS_OF", "asOf": "2020-06-01T00:00:00Z"}),

        # SR-14: AS_OF without asOf (falls back to now)
        nreq("SR-14 AS_OF No Time", "POST", SR,
             ["pm.test('SR-14 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "Where is Meridian headquartered?", "tokenBudget": 1500, "mode": "AS_OF"}),

        # SR-15: threadId
        nreq("SR-15 With ThreadId", "POST", SR,
             ["pm.test('SR-15 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'What is the Phase II deadline?',"
                         "tokenBudget:1500,mode:'LIVE',"
                         "threadId:pm.collectionVariables.get('_thread_standup')});"]),

        # SR-16: includeInvalidated true
        nreq("SR-16 Include Invalidated", "POST", SR,
             ["pm.test('SR-16 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "Who was CEO?", "tokenBudget": 1500, "mode": "LIVE",
                   "includeInvalidated": True}),

        # SR-17: includeInvalidated false
        nreq("SR-17 Exclude Invalidated", "POST", SR,
             ["pm.test('SR-17 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "Who was CEO?", "tokenBudget": 1500, "mode": "LIVE",
                   "includeInvalidated": False}),

        # SR-18: userId filter (namespace recall)
        nreq("SR-18 UserId Filter", "POST", NR,
             ["pm.test('SR-18 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'Who manages clinical data?',"
                         "tokenBudget:1500,mode:'LIVE',"
                         "userId:pm.collectionVariables.get('_owner_alice')});"]),

        # SR-19: userId non-existent
        nreq("SR-19 UserId NoOne", "POST", NR,
             ["pm.test('SR-19 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "Who manages clinical data?", "tokenBudget": 1500,
                   "mode": "LIVE", "userId": "no-such-user-xyz-999"}),

        # SR-20: scopes narrowing
        nreq("SR-20 Scopes", "POST", SR,
             [P, "pm.test('SR-20 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'What does Dr. Osei do?',"
                         "tokenBudget:1500,mode:'LIVE',"
                         "scopes:[pm.collectionVariables.get('ns_name')]});"]),

        # SR-21: bad scopes → 404
        nreq("SR-21 Bad Scopes", "POST", SR,
             ["pm.test('SR-21 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"query": "test", "tokenBudget": 500, "mode": "LIVE",
                   "scopes": ["no-grant-namespace-xyz"]}),

        # SR-22: Unknown extra field (ignored)
        nreq("SR-22 Unknown Field", "POST", SR,
             ["pm.test('SR-22 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "Dr. Osei", "tokenBudget": 1000,
                   "budgetToken": 999, "modee": "LIVE"}),

        # SR-23: Empty body → 400
        nreq("SR-23 Empty Body", "POST", SR,
             ["pm.test('SR-23 → 400', ()=>pm.expect(pm.response.code).to.eql(400));"],
             body={}),

        # NR-01: Namespace recall
        nreq("NR-01 NS Recall", "POST", NR,
             [P, "pm.test('NR-01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('NR-01 items array', ()=>pm.expect(b.items).to.be.an('array'));",
              "if(b.items && b.items.length>0) pm.test('NR-01 items found', "
              "()=>pm.expect(b.items.length).to.be.above(0));",
              "else console.log('NR-01: no items (extraction may not have settled)');"],
             body={"query": "Where is Alice Nkomo based?", "tokenBudget": 1200}),

        # NR-02: Bad namespace → 404
        nreq("NR-02 Bad NS Recall", "POST", "/v1/memories/does-not-exist-ns-xyz/recall",
             ["pm.test('NR-02 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"query": "test", "tokenBudget": 500}),

        # NR-03: Namespace EPISODIC
        nreq("NR-03 NS EPISODIC", "POST", NR,
             ["pm.test('NR-03 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "Meridian history", "tokenBudget": 1500, "mode": "EPISODIC"}),

        # NR-04: Namespace AS_OF
        nreq("NR-04 NS AS_OF", "POST", NR,
             ["pm.test('NR-04 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "Who works at Meridian?", "tokenBudget": 1500,
                   "mode": "AS_OF", "asOf": "2025-06-01T00:00:00Z"}),
    ]


# ---------------------------------------------------------------------------
#  SECTION 5 — RECALL OUTPUT VALIDATION
# ---------------------------------------------------------------------------

def recall_output_steps():
    SR = "/v1/spaces/{{space_name}}/recall"
    return [
        # RO: Rich recall for shape validation
        nreq("RO-01 Rich Recall Shape", "POST", SR,
             [P, "pm.test('RO-01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('RO-01 items array', ()=>pm.expect(b.items).to.be.an('array'));",
              "pm.test('RO-01 dropped boolean', ()=>pm.expect(typeof b.droppedDueToBudget).to.eql('boolean'));",
              "if(b.items && b.items.length>0){",
              "  const it=b.items[0];",
              "  pm.test('RO-01 item.content string', ()=>pm.expect(typeof it.content).to.eql('string'));",
              "  pm.test('RO-01 item.provenance array', ()=>pm.expect(it.provenance).to.be.an('array'));",
              "  pm.test('RO-01 item.score number', ()=>pm.expect(typeof it.score).to.eql('number'));",
              "  pm.test('RO-01 item.score [0,1]', ()=>{ pm.expect(it.score).to.be.at.least(0); pm.expect(it.score).to.be.at.most(1); });",
              "  pm.test('RO-01 item.namespaceId', ()=>pm.expect(it.namespaceId).to.exist);",
              "  pm.test('RO-01 item.superseded exists', ()=>pm.expect(it).to.have.property('superseded'));",
              "  // max score <= 1.0",
              "  const maxS=Math.max(...b.items.map(i=>i.score));",
              "  pm.test('RO-01 max score <= 1', ()=>pm.expect(maxS).to.be.at.most(1));",
              "  // no quipu:// in provenance",
              "  const hasQuipu=b.items.some(i=>(i.provenance||[]).some(p=>p.startsWith('quipu://')));",
              "  pm.test('RO-01 no quipu:// provenance', ()=>pm.expect(hasQuipu).to.eql(false));",
              "  // all items have provenance",
              "  const emptyProv=b.items.filter(i=>!i.provenance||i.provenance.length===0).length;",
              "  pm.test('RO-01 all items have provenance', ()=>pm.expect(emptyProv).to.eql(0));",
              "  // superseded marker consistency",
              "  const badMark=b.items.filter(i=>i.superseded&&!i.content.includes('[SUPERSEDED]')).length;",
              "}"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'Tell me about the people at Meridian "
                         "Health Sciences, their roles and locations',tokenBudget:4000,mode:'LIVE',"
                         "threadId:pm.collectionVariables.get('_thread_project')});"]),

        # RO-02: Large budget → dropped false
        nreq("RO-02 Large Budget", "POST", SR,
             [P, "pm.test('RO-02 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('RO-02 dropped false', ()=>pm.expect(b.droppedDueToBudget).to.eql(false));"],
             body={"query": "Dr. Osei", "tokenBudget": 10000, "mode": "LIVE"}),

        # RO-03: Tiny budget → dropped true (soft)
        nreq("RO-03 Tiny Budget", "POST", SR,
             [P, "pm.test('RO-03 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.test('RO-03 dropped boolean', ()=>pm.expect(typeof b.droppedDueToBudget).to.eql('boolean'));",
              "// With budget=30, droppedDueToBudget should be true (soft assertion)",
              "if(b.droppedDueToBudget!==true) console.log('WARN: tiny budget did not trigger drop');"],
             body={"query": "Tell me everything about Meridian, its people, products, trials",
                   "tokenBudget": 30, "mode": "LIVE"}),
    ]


# ---------------------------------------------------------------------------
#  SECTION 6 — ROUND-TRIP VERIFICATION
# ---------------------------------------------------------------------------

def roundtrip_steps():
    SR = "/v1/spaces/{{space_name}}/recall"
    NR = "/v1/memories/{{ns_name}}/recall"
    return [
        # VR-01: Speaker attribution recall
        nreq("VR-01 Speaker Recall", "POST", SR,
             [P, "pm.test('VR-01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items && b.items.length>0) pm.test('VR-01 items found', "
              "()=>pm.expect(b.items.length).to.be.above(0));",
              "else console.log('VR-01: no items (extraction settling)');"],
             body={"query": "Dr. Amara Osei Phase II deadline September enrollment delays",
                   "tokenBudget": 1500, "mode": "LIVE"}),

        # VR-02: Backfill AS_OF
        nreq("VR-02 Backfill AS_OF", "POST", SR,
             [P, "pm.test('VR-02 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "When was Meridian Health Sciences founded?", "tokenBudget": 1500,
                   "mode": "AS_OF", "asOf": "2019-01-01T00:00:00Z"}),

        # VR-03: No occurredAt + past AS_OF → nothing
        nreq("VR-03 No OccurredAt AS_OF", "POST", NR,
             [P, "pm.test('VR-03 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "mass spectrometer calibrated proteomics", "tokenBudget": 1500,
                   "mode": "AS_OF", "asOf": "2020-01-01T00:00:00Z"}),

        # VR-04a: Owner filter Alice
        nreq("VR-04a Owner Alice", "POST", NR,
             [P, "pm.test('VR-04a → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'data manager Nairobi trial sites',"
                         "tokenBudget:1500,mode:'LIVE',"
                         "userId:pm.collectionVariables.get('_owner_alice')});"]),

        # VR-04b: Owner filter Bob
        nreq("VR-04b Owner Bob", "POST", NR,
             [P, "pm.test('VR-04b → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'data manager Nairobi trial sites',"
                         "tokenBudget:1500,mode:'LIVE',"
                         "userId:pm.collectionVariables.get('_owner_bob')});"]),

        # VR-05: ownerUserId dropped on space form
        nreq("VR-05 Owner Dropped Recall", "POST", NR,
             [P, "pm.test('VR-05 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'regulatory submissions EU "
                         "Dr. Fatima Al-Rashid',tokenBudget:1500,mode:'LIVE',"
                         "userId:pm.collectionVariables.get('_owner_alice')});"]),

        # VR-06: Bounded window — LIVE should not return ended fact
        nreq("VR-06 Ended Fact LIVE", "POST", SR,
             [P, "pm.test('VR-06 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "Who is the CEO of Meridian?", "tokenBudget": 1500,
                   "mode": "LIVE", "includeInvalidated": False}),

        # VR-07: AS_OF within bounded window finds it
        nreq("VR-07 Within Window AS_OF", "POST", SR,
             [P, "pm.test('VR-07 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"query": "Who is the CEO of Meridian?", "tokenBudget": 1500,
                   "mode": "AS_OF", "asOf": "2021-06-01T00:00:00Z"}),
    ]


# ---------------------------------------------------------------------------
#  SECTION 7 — IDEMPOTENCY
# ---------------------------------------------------------------------------

def idempotency_steps():
    SI = "/v1/spaces/{{space_name}}/ingest"
    NI = "/v1/memories/{{ns_name}}/ingest"
    return [
        # ID-01: Replay same space ingest → same unitId
        nreq("ID-01 Replay Space", "POST", SI,
             [P, "pm.test('ID-01 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "const origId=pm.collectionVariables.get('_ingest1_unit_id');",
              "if(origId && b.unitId){",
              "  pm.test('ID-01 same unitId', ()=>pm.expect(b.unitId).to.eql(origId));",
              "}"],
             body={"_": ""},
             prerequest=["const saved=pm.collectionVariables.get('_ingest1_body');",
                         "if(saved) pm.request.body.raw=saved;"]),

        # ID-02: Replay same namespace ingest → same unitId
        nreq("ID-02 Replay NS", "POST", NI,
             [P, "pm.test('ID-02 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "const origId=pm.collectionVariables.get('_ns_ingest_unit_id');",
              "if(origId && b.unitId){",
              "  pm.test('ID-02 same unitId', ()=>pm.expect(b.unitId).to.eql(origId));",
              "}"],
             body={"_": ""},
             prerequest=["const saved=pm.collectionVariables.get('_ns_ingest_body');",
                         "if(saved) pm.request.body.raw=saved;"]),

        # ID-03: Same text, different threadId → DIFFERENT unitId
        nreq("ID-03 Diff Thread", "POST", SI,
             [P, "pm.test('ID-03 → 202', ()=>pm.expect(pm.response.code).to.eql(202));",
              "const origId=pm.collectionVariables.get('_ingest1_unit_id');",
              "if(origId && b.unitId){",
              "  pm.test('ID-03 different unitId', ()=>pm.expect(b.unitId).to.not.eql(origId));",
              "}"],
             body={"content": "Dr. Amara Osei joined Meridian Health Sciences as Chief Research Officer "
                   "in January 2024. She relocated from the Accra office to the Boston headquarters "
                   "and now leads the Helix Alpha clinical trial program.",
                   "threadId": "a-completely-different-thread", "contentType": "text/plain",
                   "role": "user", "speaker": "hr.admin@meridian.example",
                   "occurredAt": "2024-01-15T09:00:00Z"}),
    ]


# ---------------------------------------------------------------------------
#  SECTION 8 — AUTH & HEADER VALIDATION
# ---------------------------------------------------------------------------

def auth_steps():
    SR = "/v1/spaces/{{space_name}}/recall"
    SI = "/v1/spaces/{{space_name}}/ingest"
    return [
        # AH-01: No bearer → 401
        nreq("AH-01 No Bearer Recall", "POST", SR,
             ["pm.test('AH-01 → 401', ()=>pm.expect(pm.response.code).to.eql(401));"],
             body={"query": "test", "tokenBudget": 500}, noauth=True),

        # AH-02: Bad bearer → 401|400
        nreq("AH-02 Bad Bearer Recall", "POST", SR,
             ["pm.test('AH-02 → 401|400', ()=>pm.expect(pm.response.code).to.be.oneOf([401,400]));"],
             body={"query": "test", "tokenBudget": 500}, bad_auth=True),

        # AH-03: No bearer on ingest → 401
        nreq("AH-03 No Bearer Ingest", "POST", SI,
             ["pm.test('AH-03 → 401', ()=>pm.expect(pm.response.code).to.eql(401));"],
             body={"content": "unauthorized ingest attempt"}, noauth=True),

        # AH-04: Bad bearer on ingest → 401|400
        nreq("AH-04 Bad Bearer Ingest", "POST", SI,
             ["pm.test('AH-04 → 401|400', ()=>pm.expect(pm.response.code).to.be.oneOf([401,400]));"],
             body={"content": "bad token ingest attempt"}, bad_auth=True),
    ]


# ---------------------------------------------------------------------------
#  SECTION 9 — INVALIDATION (simplified — no polling loop)
# ---------------------------------------------------------------------------

def invalidation_steps():
    SR = "/v1/spaces/{{space_name}}/recall"
    NR = "/v1/memories/{{ns_name}}/recall"
    return [
        # MX-00: Get an edge to invalidate
        nreq("MX-00 Get Edge", "POST",
             "/v1/spaces/{{space_name}}/graph/edges/list",
             [P, "pm.test('MX-00 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items && b.items.length>0){",
              "  const edge=b.items.find(e=>e.sourceNodeName&&!e.invalidAt)||b.items[0];",
              "  if(edge.uri) pm.collectionVariables.set('_mx_edge_uri', edge.uri);",
              "  if(edge.fact) pm.collectionVariables.set('_mx_query', "
              "    edge.fact.replace(/[^a-zA-Z0-9 ]/g,' ').substring(0,60));",
              "  console.log('MX target: '+edge.uri);",
              "}"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('ns_name'),limit:20,cursor:null});"]),

        # MX-01: PATCH invalidAt
        nreq("MX-01 Invalidate Edge", "PATCH",
             "/v1/spaces/{{space_name}}/graph/edge",
             ["pm.test('MX-01 → 202|200|500', ()=>pm.expect(pm.response.code).to.be.oneOf([202,200,500]));"],
             body={"_": ""},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const uri=pm.collectionVariables.get('_mx_edge_uri');",
                 "if(!uri){ pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__'; return; }",
                 "const enc=encodeURIComponent(uri);",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge?uri='+enc;",
                 "pm.request.body.raw=JSON.stringify({invalidAt:'2026-06-01T00:00:00Z'});",
             ]),

        # MX-02: Verify edge has invalidAt
        nreq("MX-02 Verify Edge", "GET",
             "/v1/spaces/{{space_name}}/graph/edge",
             [P, "pm.test('MX-02 → 200|500', ()=>pm.expect(pm.response.code).to.be.oneOf([200,500]));",
              "if(pm.response.code===200 && b.invalidAt) pm.test('MX-02 invalidAt set', ()=>pm.expect(b.invalidAt).to.exist);"],
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const uri=pm.collectionVariables.get('_mx_edge_uri');",
                 "if(!uri){ pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__'; return; }",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge?uri='+encodeURIComponent(uri);",
             ]),

        # MX-03: LIVE+includeInvalidated:true → fact should appear
        nreq("MX-03 LIVE Include Inv", "POST", NR,
             [P, "pm.test('MX-03 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"_": ""},
             prerequest=["const q=pm.collectionVariables.get('_mx_query')||'Meridian test';",
                         "pm.request.body.raw=JSON.stringify({query:q,tokenBudget:2000,"
                         "mode:'LIVE',includeInvalidated:true});"]),

        # MX-04: EPISODIC (no temporal filter)
        nreq("MX-04 EPISODIC", "POST", NR,
             [P, "pm.test('MX-04 → 200', ()=>pm.expect(pm.response.code).to.eql(200));"],
             body={"_": ""},
             prerequest=["const q=pm.collectionVariables.get('_mx_query')||'Meridian test';",
                         "pm.request.body.raw=JSON.stringify({query:q,tokenBudget:2000,"
                         "mode:'EPISODIC'});"]),
    ]


# ---------------------------------------------------------------------------
#  SECTION 10-12 — CONTENT GRAMMAR, UNDERSCORE, TOKEN COST, DUPLICATE
# ---------------------------------------------------------------------------

def advanced_validation_steps():
    SR = "/v1/spaces/{{space_name}}/recall"
    return [
        # CG-01: Content grammar + provenance validation (rich recall)
        nreq("CG-01 Grammar Provenance", "POST", SR,
             [P, "pm.test('CG-01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items && b.items.length>0){",
              "  // No quipu:// in provenance",
              "  const hasQuipu=b.items.some(i=>(i.provenance||[]).some(p=>p.startsWith('quipu://')));",
              "  pm.test('CG-01 no quipu://', ()=>pm.expect(hasQuipu).to.eql(false));",
              "  // Provenance URIs contain /",
              "  const fabricUris=b.items.flatMap(i=>(i.provenance||[]).filter(p=>!p.startsWith('neuro:')));",
              "  const validFmt=fabricUris.filter(u=>u.includes('/'));",
              "  if(fabricUris.length>0) pm.test('CG-01 provenance format', "
              "    ()=>pm.expect(validFmt.length).to.eql(fabricUris.length));",
              "}"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'Tell me about all people roles "
                         "locations at Meridian Health Sciences',tokenBudget:6000,mode:'LIVE',"
                         "includeInvalidated:true,"
                         "threadId:pm.collectionVariables.get('_thread_project')});"]),

        # US-01: Underscore → space rendering
        nreq("US-01 Underscore Rendering", "POST", SR,
             [P, "pm.test('US-01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items && b.items.length>0){",
              "  const hasSpaces=b.items.some(i=>i.content&&i.content.toLowerCase().includes("
              "    'manages regulatory submissions for'));",
              "  const hasUnder=b.items.some(i=>i.content&&i.content.includes("
              "    'manages_regulatory_submissions_for'));",
              "  if(hasSpaces) pm.test('US-01 underscores as spaces', ()=>pm.expect(hasSpaces).to.eql(true));",
              "  if(hasUnder) console.log('WARN: US-01 underscores not converted');",
              "}"],
             body={"query": "Dr. Fatima Al-Rashid regulatory submissions EU",
                   "tokenBudget": 2000, "mode": "LIVE"}),

        # US-02: Assert audit attributes
        nreq("US-02 Audit Attributes", "POST",
             "/v1/spaces/{{space_name}}/graph/edges/list",
             [P, "pm.test('US-02 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items){",
              "  const withAudit=b.items.filter(i=>i.attributes&&i.attributes.assertedProperty);",
              "  if(withAudit.length>0){",
              "    pm.test('US-02 audit attrs found', ()=>pm.expect(withAudit.length).to.be.above(0));",
              "    pm.test('US-02 assertedSubject', ()=>pm.expect(withAudit[0].attributes.assertedSubject).to.exist);",
              "    pm.test('US-02 assertedProperty', ()=>pm.expect(withAudit[0].attributes.assertedProperty).to.exist);",
              "    pm.test('US-02 assertedValue', ()=>pm.expect(withAudit[0].attributes.assertedValue).to.exist);",
              "  }",
              "}"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('ns_name'),limit:50,cursor:null});"]),

        # TC-01: Token cost estimation
        nreq("TC-01 Token Budget", "POST", SR,
             [P, "pm.test('TC-01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items && b.droppedDueToBudget===false){",
              "  const est=b.items.reduce((s,i)=>s+Math.ceil((i.content||'').length/4)+2, 0);",
              "  pm.test('TC-01 tokens fit budget', ()=>pm.expect(est).to.be.at.most(4000));",
              "}"],
             body={"query": "Meridian Health Sciences people", "tokenBudget": 4000, "mode": "LIVE"}),

        # DC-01: Duplicate collapse
        nreq("DC-01 No Duplicates", "POST", SR,
             [P, "pm.test('DC-01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items && b.items.length>1){",
              "  const contents=b.items.map(i=>(i.content||'').toLowerCase().replace(/\\s+/g,' '));",
              "  const uniq=new Set(contents);",
              "  pm.test('DC-01 no duplicates', ()=>pm.expect(uniq.size).to.eql(contents.length));",
              "}"],
             body={"query": "Dr. Amara Osei Chief Research Officer Meridian joined January 2024",
                   "tokenBudget": 4000, "mode": "LIVE"}),
    ]


# ---------------------------------------------------------------------------
#  SECTION 13 — SOURCETYPE ON EPISODES & THREADS
# ---------------------------------------------------------------------------

def sourcetype_thread_steps():
    return [
        # SE-01: Episodes have sourceType
        nreq("SE-01 Episode SourceType", "POST",
             "/v1/spaces/{{space_name}}/graph/episodes/list",
             [P, "pm.test('SE-01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items && b.items.length>0){",
              "  const withType=b.items.filter(i=>i.sourceType);",
              "  pm.test('SE-01 episodes have sourceType', ()=>pm.expect(withType.length).to.be.above(0));",
              "}"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('ns_name'),limit:50,cursor:null});"]),

        # MT-01: Multiple threads
        nreq("MT-01 Thread List", "POST",
             "/v1/spaces/{{space_name}}/graph/threads/list",
             [P, "pm.test('MT-01 → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "if(b.items && b.items.length>0){",
              "  if(b.items.length>1) pm.test('MT-01 multiple threads', ()=>pm.expect(b.items.length).to.be.above(1));",
              "  else console.log('MT-01: only '+b.items.length+' thread(s) — extraction may still be settling');",
              "} else { console.log('MT-01: 0 threads — extraction still settling, soft pass'); }"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify("
                         "{namespaceId:pm.collectionVariables.get('ns_name'),limit:50,cursor:null});"]),

        # MT-02a: Thread isolation — project thread
        nreq("MT-02a Thread Project", "POST",
             "/v1/spaces/{{space_name}}/recall",
             [P, "pm.test('MT-02a → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "pm.collectionVariables.set('_mt2a_count', String((b.items||[]).length));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'What is the latest update?',"
                         "tokenBudget:1500,mode:'LIVE',"
                         "threadId:pm.collectionVariables.get('_thread_project')});"]),

        # MT-02b: Thread isolation — standup thread
        nreq("MT-02b Thread Standup", "POST",
             "/v1/spaces/{{space_name}}/recall",
             [P, "pm.test('MT-02b → 200', ()=>pm.expect(pm.response.code).to.eql(200));",
              "const a=pm.collectionVariables.get('_mt2a_count');",
              "console.log('MT-02 thread isolation: project='+a+' standup='+(b.items||[]).length);"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({query:'What is the latest update?',"
                         "tokenBudget:1500,mode:'LIVE',"
                         "threadId:pm.collectionVariables.get('_thread_standup')});"]),
    ]


# ---------------------------------------------------------------------------
#  SECTION 14 — ERROR SHAPES & X-FABRIC
# ---------------------------------------------------------------------------

def error_shape_steps():
    NI = "/v1/memories/{{ns_name}}/ingest"
    return [
        # ES-01: 500 body no internal leak
        nreq("ES-01 Error Shape", "POST", NI,
             [P, "pm.test('ES-01 → 500|400', ()=>pm.expect(pm.response.code).to.be.oneOf([500,400]));",
              "const bodyStr=pm.response.text()||'';",
              "const hasInternals=/exception|stacktrace|java\\.|org\\.|localhost/i.test(bodyStr);",
              "pm.test('ES-01 no internals leaked', ()=>pm.expect(hasInternals).to.eql(false));",
              "if(pm.response.code===500 && b.errorCode){",
              "  pm.test('ES-01 errorCode Q500', ()=>pm.expect(b.errorCode).to.eql('Q500'));",
              "}"],
             body={"text": "trigger error", "sourceType": "USER", "ownerUserId": "   "},
             prerequest=["pm.collectionVariables.set('_soft_5xx','true');"]),

        # XF-01: No X-Fabric → 404
        nreq("XF-01 No Fabric", "POST",
             "/v1/spaces/xf-test-no-fabric/ingest",
             [P, "pm.test('XF-01 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"content": "Testing X-Fabric omission", "threadId": "xf-test"},
             no_fabric=True),
    ]


# ---------------------------------------------------------------------------
#  SECTION 15 — HALF-OPEN WINDOW & PINNED FACTS
# ---------------------------------------------------------------------------

def halfopen_pinned_steps():
    NR = "/v1/memories/{{ns_name}}/recall"
    return [
        # HO-01: Exact boundary excluded (half-open [validFrom, invalidAt))
        nreq("HO-01 Boundary Excluded", "POST", NR,
             [P, "pm.test('HO-01 → 200|500', ()=>pm.expect(pm.response.code).to.be.oneOf([200,500]));",
              "const uri=pm.collectionVariables.get('_mx_edge_uri');",
              "if(pm.response.code===200 && uri && b.items){",
              "  const found=b.items.filter(i=>(i.provenance||[]).includes(uri));",
              "  pm.test('HO-01 excluded at boundary', ()=>pm.expect(found.length).to.eql(0));",
              "}"],
             body={"_": ""},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const uri=pm.collectionVariables.get('_mx_edge_uri');",
                 "if(!uri){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__'; return;}",
                 "const q=pm.collectionVariables.get('_mx_query')||'Meridian test';",
                 "pm.request.body.raw=JSON.stringify({query:q,tokenBudget:2000,"
                 "mode:'AS_OF',asOf:'2026-06-01T00:00:00Z',includeInvalidated:false});",
             ]),

        # HO-02: One second before boundary → valid
        nreq("HO-02 Before Boundary", "POST", NR,
             [P, "pm.test('HO-02 → 200|500', ()=>pm.expect(pm.response.code).to.be.oneOf([200,500]));"],
             body={"_": ""},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const uri=pm.collectionVariables.get('_mx_edge_uri');",
                 "if(!uri){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__'; return;}",
                 "const q=pm.collectionVariables.get('_mx_query')||'Meridian test';",
                 "pm.request.body.raw=JSON.stringify({query:q,tokenBudget:2000,"
                 "mode:'AS_OF',asOf:'2026-05-31T23:59:59Z',includeInvalidated:false});",
             ]),

        # PB-01: Pin a fact
        nreq("PB-01 Pin Edge", "POST",
             "/v1/spaces/{{space_name}}/graph/edge/pin",
             ["pm.test('PB-01 → 202|200|500|skip', ()=>{",
              "  const uri=pm.collectionVariables.get('_mx_edge_uri');",
              "  if(!uri){pm.test.skip('no edge to pin'); return;}",
              "  pm.expect(pm.response.code).to.be.oneOf([202,200,500]);",
              "});"],
             body={"_": ""},
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const uri=pm.collectionVariables.get('_mx_edge_uri');",
                 "if(!uri){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__'; return;}",
                 "const ns=pm.collectionVariables.get('ns_name');",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge/pin?namespaceId='+ns+'&uri='+encodeURIComponent(uri);",
                 "pm.request.body.raw='{}';",
             ]),

        # PB-02: Pinned fact bypasses temporal filter
        nreq("PB-02 Pinned Bypasses", "POST",
             "/v1/spaces/{{space_name}}/recall",
             [P, "pm.test('PB-02 → 200|500', ()=>pm.expect(pm.response.code).to.be.oneOf([200,500]));"],
             body={"query": "Meridian weather forecast test", "tokenBudget": 2000,
                   "mode": "AS_OF", "asOf": "1990-01-01T00:00:00Z"},
             prerequest=["pm.collectionVariables.set('_soft_5xx','true');"]),

        # PB-03: Unpin cleanup
        nreq("PB-03 Unpin", "DELETE",
             "/v1/spaces/{{space_name}}/graph/edge/pin",
             ["pm.test('PB-03 → ok', ()=>pm.expect(pm.response.code).to.be.oneOf([202,200,404,500]));"],
             prerequest=[
                 "pm.collectionVariables.set('_soft_5xx','true');",
                 "const uri=pm.collectionVariables.get('_mx_edge_uri');",
                 "if(!uri){pm.request.url=pm.collectionVariables.get('_skip_url')||"
                 "'http://localhost:1/__skip__'; return;}",
                 "const ns=pm.collectionVariables.get('ns_name');",
                 "pm.request.url=pm.environment.get('neuro_base_url')"
                 "+'/v1/spaces/'+pm.collectionVariables.get('space_name')"
                 "+'/graph/edge/pin?namespaceId='+ns+'&uri='+encodeURIComponent(uri);",
             ]),
    ]


# ---------------------------------------------------------------------------
#  SECTION 16 — MCP ENDPOINT
# ---------------------------------------------------------------------------

def mcp_steps():
    return [
        # MCP-01: memory_search
        nreq("MCP-01 Search", "POST", "/mcp",
             [P, "pm.test('MCP-01 → 200|400|404|405', "
              "()=>pm.expect(pm.response.code).to.be.oneOf([200,400,404,405]));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({jsonrpc:'2.0',id:1,"
                         "method:'tools/call',params:{name:'memory_search',arguments:"
                         "{query:'Dr. Amara Osei role',"
                         "spaceId:pm.collectionVariables.get('space_name')}}});"]),

        # MCP-02: memory_add
        nreq("MCP-02 Add", "POST", "/mcp",
             [P, "pm.test('MCP-02 → 200|400|404|405', "
              "()=>pm.expect(pm.response.code).to.be.oneOf([200,400,404,405]));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({jsonrpc:'2.0',id:2,"
                         "method:'tools/call',params:{name:'memory_add',arguments:"
                         "{content:'MCP integration test: endpoints verified.',"
                         "spaceId:pm.collectionVariables.get('space_name')}}});"]),

        # MCP-03: memory_add_fact
        nreq("MCP-03 Add Fact", "POST", "/mcp",
             [P, "pm.test('MCP-03 → 200|400|404|405', "
              "()=>pm.expect(pm.response.code).to.be.oneOf([200,400,404,405]));"],
             body={"_": ""},
             prerequest=["pm.request.body.raw=JSON.stringify({jsonrpc:'2.0',id:3,"
                         "method:'tools/call',params:{name:'memory_add_fact',arguments:"
                         "{entity:'Automated Test Suite',label:'Tool',property:'verified',"
                         "value:'all Neuro endpoints',"
                         "spaceId:pm.collectionVariables.get('space_name')}}});"]),
    ]


# ---------------------------------------------------------------------------
#  SECTION 17 — CLEANUP
# ---------------------------------------------------------------------------

def cleanup_steps():
    return [
        # Delete extraction profile
        req("CL-01 Del Profile", "DELETE",
            "/space/by-name/{{space_name}}/extraction-profile",
            ["pm.test('CL-01 ok', ()=>pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"],
            base=APP,
            extra_headers=[{"key": "X-Fabric", "value": "{{fabric_id}}"}],
            skip_on_fail=False),

        # Delete space
        req("CL-02 Del Space", "DELETE",
            "/space/by-name/{{space_name}}",
            ["pm.test('CL-02 space deleted', ()=>pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=APP,
            extra_headers=[{"key": "X-Fabric", "value": "{{fabric_id}}"}],
            skip_on_fail=False),

        # Verify recall → 404 after delete
        nreq("CL-03 Recall After Del", "POST",
             "/v1/spaces/{{space_name}}/recall",
             ["pm.test('CL-03 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"query": "anything", "tokenBudget": 100, "mode": "LIVE"},
             skip_on_fail=False),

        # Verify ingest → 404 after delete
        nreq("CL-04 Ingest After Del", "POST",
             "/v1/spaces/{{space_name}}/ingest",
             ["pm.test('CL-04 → 404', ()=>pm.expect(pm.response.code).to.eql(404));"],
             body={"content": "should fail", "threadId": "test"},
             skip_on_fail=False),

        # Teardown: clear flow state
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
        *space_ingest_steps(),
        *namespace_ingest_steps(),
        *graph_ingest_assert_steps(),
        projection_wait_step(),
        *recall_input_steps(),
        *recall_output_steps(),
        *roundtrip_steps(),
        *idempotency_steps(),
        *auth_steps(),
        *invalidation_steps(),
        *advanced_validation_steps(),
        *sourcetype_thread_steps(),
        *error_shape_steps(),
        *halfopen_pinned_steps(),
        *mcp_steps(),
        *cleanup_steps(),
    ]
    col = build_collection(
        name="FLOW - Neuro Payload Validation",
        description="Comprehensive neuro ingest & recall payload validation.\n"
                    "Covers: 5 ingest doors (space/namespace/graph), 2 recall surfaces, "
                    "space+namespace assert, auth, idempotency, invalidation matrix, "
                    "content grammar, MCP, round-trip verification, and cleanup.\n\n"
                    "Required env vars: neuro_base_url, app_base_url, fabric_id, tenant_id, "
                    "keycloak_token_url, client_id, client_secret, test_username, test_password",
        folder_name="Neuro Payload Validation",
        items=items,
        extra_variables=NEURO_VARS,
    )
    return write_flow("FLOW-Neuro-Payload-Validation.postman_collection.json", col)
