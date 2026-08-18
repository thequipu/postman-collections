#!/usr/bin/env bash
set -uo pipefail   # no -e: run every call, print whatever comes back

# =============================================================================
# Neuro — SINGLE script, ALL conditions, NETAPP (team) env.
#   Usage:  bash scripts/neuro_test_all.sh
#   Prints every response to the console. Writes NOTHING to disk.
# Overridable: SPACE, TENANT, NS, INSECURE(=1 to skip TLS verify)
# =============================================================================

# ---- Config (NETAPP) --------------------------------------------------------
TOKEN_URL="https://ui-login-prod-netapp.quipu.netapp.com/realms/netapp/protocol/openid-connect/token"
NEURO="https://api-prod-netapp.quipu.netapp.com/quipuNeuro"
SPACE="${SPACE:-karthik_ak}"
TENANT="${TENANT:-netapp}"
NS="${NS:-${SPACE}-self}"                     # memories namespace = real namespaceId (<space>-self)
INSECURE="${INSECURE:-1}"                     # use -k (skip TLS verify)

USERNAME="vinodrajadmin"; PASSWORD="qGWg9MCPYg7"
CLIENT_ID="netapp-client"; CLIENT_SECRET="6EZ0WchEk7fw8Xf4YqA1HfJh6SXklv1N"

CURL="curl -sS"; [ "$INSECURE" = "1" ] && CURL="curl -sSk"
JQ(){ command -v jq >/dev/null 2>&1 && jq "$@" || cat; }

LAST_BODY=""   # holds the most recent response body (for chaining graph_thread)

# call <name> <method> <url> [json-body]   -> prints [code] name + body, sets LAST_BODY
call(){
  local name="$1" method="$2" url="$3" body="${4:-}" out code
  if [ "$method" = "GET" ]; then
    out=$($CURL -w $'\n%{http_code}' "$url" \
      -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT")
  else
    out=$($CURL -w $'\n%{http_code}' -X "$method" "$url" \
      -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
      -H "Content-Type: application/json" -d "$body")
  fi
  code=${out##*$'\n'}; LAST_BODY=${out%$'\n'*}
  printf '\n\033[1;36m=== [%s] %s ===\033[0m\n' "$code" "$name"
  printf '%s' "$LAST_BODY" | JQ -c . 2>/dev/null || printf '%s\n' "$LAST_BODY"
}

# ---- Token ------------------------------------------------------------------
echo ">> ENV=netapp  space=$SPACE  tenant=$TENANT  ns=$NS  insecure=$INSECURE" >&2
TOKEN=$($CURL --location "$TOKEN_URL" \
  --data-urlencode "grant_type=password" --data-urlencode "username=$USERNAME" \
  --data-urlencode "password=$PASSWORD" --data-urlencode "client_id=$CLIENT_ID" \
  --data-urlencode "client_secret=$CLIENT_SECRET" \
  | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -z "$TOKEN" ] && { echo "!! no token (reachability / creds / VPN?)" >&2; exit 1; }
echo ">> token len ${#TOKEN}" >&2

# =====================  ALL CONDITIONS  ======================================
# --- writes ---
call ingest POST "$NEURO/v1/spaces/$SPACE/ingest" "$(cat <<JSON
{"content":"Karthik prefers aisle seats and usually flies out of Chennai.",
 "threadId":"thread-$(date -u +%Y-%m-%d)-001","contentType":"text/plain",
 "role":"user","speaker":"Karthik","occurredAt":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
JSON
)"
call assert POST "$NEURO/v1/spaces/$SPACE/assert" '{
  "entitySurfaceForm":"Caroline","label":"Person","property":"works_at",
  "value":"Platform team","worldTime":true,
  "validFrom":"2026-03-01T00:00:00Z","validTo":null,"graphId":null,"threadId":"conversation-42"}'

# --- recall: LIVE, LIVE+thread, AS_OF ---
call recall_live        POST "$NEURO/v1/spaces/$SPACE/recall" '{"query":"What seat does Karthik prefer?","tokenBudget":1200,"mode":"LIVE"}'
call recall_live_thread POST "$NEURO/v1/spaces/$SPACE/recall" '{"query":"which team is Caroline on now?","tokenBudget":1200,"mode":"LIVE","threadId":"conversation-42"}'
call recall_asof        POST "$NEURO/v1/spaces/$SPACE/recall" '{"query":"which team was Caroline on?","tokenBudget":1200,"mode":"AS_OF","asOf":"2026-01-15T00:00:00Z"}'

# --- negative condition: AS_OF without tokenBudget must 400 ---
call recall_asof_no_budget POST "$NEURO/v1/spaces/$SPACE/recall" '{"query":"which team was Caroline on?","mode":"AS_OF","asOf":"2026-01-15T00:00:00Z"}'

# --- capture ---
call capture_spans GET "$NEURO/v1/spaces/$SPACE/capture/spans?sinceSeq=0&limit=20"

# --- graph ---
call graph_threads GET "$NEURO/v1/spaces/$SPACE/graph/threads?limit=20"
THREAD_URI=$(printf '%s' "$LAST_BODY" | JQ -r '.[0].uri // empty' 2>/dev/null)
call graph_participants GET "$NEURO/v1/spaces/$SPACE/graph/participants?limit=50"
if [ -n "$THREAD_URI" ]; then
  ENC=$(printf '%s' "$THREAD_URI" | sed 's/ /%20/g')
  call graph_thread GET "$NEURO/v1/spaces/$SPACE/graph/thread?threadUri=$ENC"
else
  echo ">> no threadUri; skipping graph_thread" >&2
fi

# --- memories namespace (single, no fan-out) ---
call memories_recall POST "$NEURO/v1/memories/$NS/recall" '{"query":"What seat does Karthik prefer?","tokenBudget":800}'
# negative condition: unprovisioned memory must 404
call memories_recall_missing POST "$NEURO/v1/memories/product-docs/recall" '{"query":"anything","tokenBudget":800}'

echo; echo ">> Done." >&2
