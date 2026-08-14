#!/usr/bin/env bash
set -uo pipefail   # no -e: run every call, capture whatever comes back

# =============================================================================
# Neuro — full namespace surface for the space we created (onprem).
# Runs every namespace-scoped API and SAVES each response to its own file under
#   reports/neuro/<UTC-timestamp>/
# Self-signed TLS -> -k. Tenant comes from the token; X-Tenant-ID sent anyway.
# =============================================================================

# ---- Config -----------------------------------------------------------------
TOKEN_URL="https://ui-login.thequipu.in/realms/onpremquipu/protocol/openid-connect/token"
NEURO="https://api-onprem.thequipu.in/quipuNeuro"
SPACE="${SPACE:-karthik}"
TENANT="${TENANT:-onpremquipu}"
NS="${NS:-karthik-self}"          # memories namespace = the real namespaceId (<space>-self); product-docs does NOT exist onprem

USERNAME="quipuadmin"; PASSWORD="karthik"
CLIENT_ID="onpremquipu-client"; CLIENT_SECRET="7twCqTl1Ur49tOwtLAbEy6kEXOVEIRwm"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUTDIR="reports/neuro/$TS"
mkdir -p "$OUTDIR"
SUMMARY="$OUTDIR/_summary.tsv"
printf "http\tname\tfile\n" > "$SUMMARY"

CURL="curl -sSk"
JQ(){ command -v jq >/dev/null 2>&1 && jq "$@" || cat; }

# call <name> <method> <url> [json-body]   -> saves body to $OUTDIR/<name>.json
call(){
  local name="$1" method="$2" url="$3" body="${4:-}"
  local f="$OUTDIR/$name.json" code
  if [ "$method" = "GET" ]; then
    code=$($CURL -o "$f" -w "%{http_code}" "$url" \
      -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT")
  else
    code=$($CURL -o "$f" -w "%{http_code}" -X "$method" "$url" \
      -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
      -H "Content-Type: application/json" -d "$body")
  fi
  printf "%s\t%s\t%s\n" "$code" "$name" "$f" >> "$SUMMARY"
  printf '\n\033[1;36m=== [%s] %s  %s ===\033[0m\n' "$code" "$name" "$url" >&2
  JQ . < "$f" 2>/dev/null || cat "$f"
  echo
}

# ---- Token ------------------------------------------------------------------
TOKEN=$($CURL --location "$TOKEN_URL" \
  --data-urlencode "grant_type=password" --data-urlencode "username=$USERNAME" \
  --data-urlencode "password=$PASSWORD" --data-urlencode "client_id=$CLIENT_ID" \
  --data-urlencode "client_secret=$CLIENT_SECRET" \
  | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -z "$TOKEN" ] && { echo "!! no token" >&2; exit 1; }
echo ">> token len ${#TOKEN} | space=$SPACE tenant=$TENANT | out=$OUTDIR" >&2

# ---- WRITES (populate the namespace) ---------------------------------------
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

# ---- READS (recall) --------------------------------------------------------
call recall_live POST "$NEURO/v1/spaces/$SPACE/recall" '{
  "query":"What seat does Karthik prefer?","tokenBudget":1200,"mode":"LIVE"}'

call recall_live_thread POST "$NEURO/v1/spaces/$SPACE/recall" '{
  "query":"which team is Caroline on now?","tokenBudget":1200,"mode":"LIVE","threadId":"conversation-42"}'

# AS_OF variants (probing correct body — 4 shapes; keep whichever returns 200)
call recall_asof_a POST "$NEURO/v1/spaces/$SPACE/recall" '{
  "query":"which team was Caroline on?","tokenBudget":1200,"mode":"AS_OF","asOf":"2026-01-15T00:00:00Z"}'
call recall_asof_b POST "$NEURO/v1/spaces/$SPACE/recall" '{
  "query":"which team was Caroline on?","tokenBudget":1200,"mode":"AS_OF","asOfTime":"2026-01-15T00:00:00Z"}'
call recall_asof_c POST "$NEURO/v1/spaces/$SPACE/recall" '{
  "query":"which team was Caroline on?","tokenBudget":1200,"mode":"AS_OF","validAt":"2026-01-15T00:00:00Z"}'

# ---- CAPTURE (raw span stream for the namespace) ---------------------------
call capture_spans GET "$NEURO/v1/spaces/$SPACE/capture/spans?sinceSeq=0&limit=20"

# ---- GRAPH -----------------------------------------------------------------
call graph_threads      GET "$NEURO/v1/spaces/$SPACE/graph/threads?limit=20"
call graph_participants GET "$NEURO/v1/spaces/$SPACE/graph/participants?limit=50"

# graph/thread needs a real threadUri — pull the first one from graph_threads
THREAD_URI=$(JQ -r '.[0].uri // empty' < "$OUTDIR/graph_threads.json" 2>/dev/null)
if [ -n "$THREAD_URI" ]; then
  ENC=$(printf '%s' "$THREAD_URI" | sed 's/ /%20/g')
  call graph_thread GET "$NEURO/v1/spaces/$SPACE/graph/thread?threadUri=$ENC"
else
  echo ">> no threadUri found; skipping graph_thread" >&2
fi

# ---- MEMORIES namespace (single-memory, no fan-out) ------------------------
call memories_recall POST "$NEURO/v1/memories/$NS/recall" '{
  "query":"What seat does Karthik prefer?","tokenBudget":800}'

# ---- Summary ---------------------------------------------------------------
echo >&2
printf '\033[1;33m===== SUMMARY (%s) =====\033[0m\n' "$OUTDIR" >&2
column -t -s$'\t' "$SUMMARY" >&2 2>/dev/null || cat "$SUMMARY" >&2
echo ">> All responses saved under $OUTDIR/" >&2
