#!/usr/bin/env bash
set -uo pipefail   # NOTE: no -e; we want every call to run even if one 4xx/5xx's

# ---- Config (ONPREM) --------------------------------------------------------
TOKEN_URL="https://ui-login.thequipu.in/realms/onpremquipu/protocol/openid-connect/token"
NEURO="https://api-onprem.thequipu.in/quipuNeuro"
SPACE="${SPACE:-karthik}"
TENANT="${TENANT:-onpremquipu}"
NS="${NS:-product-docs}"          # memories namespace

USERNAME="quipuadmin"; PASSWORD="karthik"
CLIENT_ID="onpremquipu-client"; CLIENT_SECRET="7twCqTl1Ur49tOwtLAbEy6kEXOVEIRwm"

CURL="curl -sSk"
hdr=(-H "Authorization: Bearer __JWT__" -H "X-Tenant-ID: $TENANT" -H "Content-Type: application/json")

pp(){ if command -v jq >/dev/null 2>&1; then jq . 2>/dev/null || cat; else cat; fi; }
section(){ printf '\n\033[1;36m=== %s ===\033[0m\n' "$1" >&2; }

# ---- Token ------------------------------------------------------------------
section "TOKEN"
TOKEN=$($CURL --location "$TOKEN_URL" \
  --data-urlencode "grant_type=password" --data-urlencode "username=$USERNAME" \
  --data-urlencode "password=$PASSWORD" --data-urlencode "client_id=$CLIENT_ID" \
  --data-urlencode "client_secret=$CLIENT_SECRET" \
  | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -z "$TOKEN" ] && { echo "!! no token" >&2; exit 1; }
echo "token len: ${#TOKEN}" >&2
AUTH=(-H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" -H "Content-Type: application/json")

# ---- 1. assert a fact (bitemporal) -----------------------------------------
section "ASSERT  Caroline works_at Platform team (validFrom 2026-03-01)"
$CURL -w "\n[HTTP %{http_code}]\n" -X POST "$NEURO/v1/spaces/$SPACE/assert" "${AUTH[@]}" -d '{
  "entitySurfaceForm":"Caroline","label":"Person","property":"works_at",
  "value":"Platform team","worldTime":true,
  "validFrom":"2026-03-01T00:00:00Z","validTo":null,"graphId":null,"threadId":"conversation-42"
}' | pp

# ---- 2. ingest text into memories namespace --------------------------------
section "MEMORIES INGEST (text)  $NS"
$CURL -w "\n[HTTP %{http_code}]\n" -X POST "$NEURO/v1/memories/$NS/ingest" "${AUTH[@]}" -d '{
  "text":"Jane joined Acme as an engineer in 2021.","threadId":"conversation-42",
  "contentType":"text/plain","sourceType":"USER"
}' | pp

# ---- 3. ingest a document (pdf url) ----------------------------------------
section "MEMORIES INGEST (document/pdf)  $NS"
$CURL -w "\n[HTTP %{http_code}]\n" -X POST "$NEURO/v1/memories/$NS/ingest" "${AUTH[@]}" -d '{
  "text":"https://docs.netapp.com/ontap-914-release-notes.pdf",
  "contentType":"application/pdf","sourceType":"DOCUMENT"
}' | pp

# ---- 4. recall LIVE (with thread) ------------------------------------------
section "RECALL  LIVE  'which team is Caroline on now?'"
$CURL -w "\n[HTTP %{http_code}]\n" -X POST "$NEURO/v1/spaces/$SPACE/recall" "${AUTH[@]}" -d '{
  "query":"which team is Caroline on now?","tokenBudget":1200,"mode":"LIVE","threadId":"conversation-42"
}' | pp

# ---- 5. recall AS_OF (time travel) -----------------------------------------
section "RECALL  AS_OF 2026-01-15  'which team was Caroline on?'"
$CURL -w "\n[HTTP %{http_code}]\n" -X POST "$NEURO/v1/spaces/$SPACE/recall" "${AUTH[@]}" -d '{
  "query":"which team was Caroline on?","mode":"AS_OF","asOf":"2026-01-15T00:00:00Z"
}' | pp

# ---- 6. recall from memories namespace -------------------------------------
section "MEMORIES RECALL  $NS  'FlexGroup volume limits'"
$CURL -w "\n[HTTP %{http_code}]\n" -X POST "$NEURO/v1/memories/$NS/recall" "${AUTH[@]}" -d '{
  "query":"FlexGroup volume limits","tokenBudget":800
}' | pp

# ---- 7. graph: list threads ------------------------------------------------
section "GRAPH  threads (limit 20)"
$CURL -w "\n[HTTP %{http_code}]\n" "$NEURO/v1/spaces/$SPACE/graph/threads?limit=20" \
  -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" | pp

# ---- 8. graph: participants ------------------------------------------------
section "GRAPH  participants (limit 50)"
$CURL -w "\n[HTTP %{http_code}]\n" "$NEURO/v1/spaces/$SPACE/graph/participants?limit=50" \
  -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" | pp

# ---- 9. graph: single thread (needs a real threadUri) ----------------------
# Uncomment and set THREAD_URI to a value from step 7's output:
# section "GRAPH  thread by uri"
# $CURL -w "\n[HTTP %{http_code}]\n" -G "$NEURO/v1/spaces/$SPACE/graph/thread" \
#   --data-urlencode "threadUri=$THREAD_URI" \
#   -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" | pp

echo >&2; echo ">> Done." >&2
