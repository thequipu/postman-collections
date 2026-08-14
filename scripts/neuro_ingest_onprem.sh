#!/usr/bin/env bash
set -euo pipefail

# ---- Config (ONPREM) --------------------------------------------------------
# Onprem Keycloak realm is "onpremquipu"; gateway is api-onprem.thequipu.in.
# TLS is self-signed -> every curl uses -k/--insecure.
TOKEN_URL="https://ui-login.thequipu.in/realms/onpremquipu/protocol/openid-connect/token"

# NOTE: quipuNeuro is the NetApp-branded API path. The onprem equivalent is
# assumed to be the same prefix behind the Java gateway. If ingest 404s, the
# real onprem base path is the one unknown to verify (see probe at bottom).
API_BASE="https://api-onprem.thequipu.in/quipuNeuro/v1"

SPACE="${SPACE:-karthik}"          # ingest target space; override: SPACE=xxx ./neuro_ingest_onprem.sh
FABRIC="${FABRIC:-}"               # required to auto-create a new space when tenant has >1 fabric; override: FABRIC=xxx ...

USERNAME="quipuadmin"
PASSWORD="karthik"
CLIENT_ID="onpremquipu-client"
CLIENT_SECRET="7twCqTl1Ur49tOwtLAbEy6kEXOVEIRwm"

# ---- Payload ----------------------------------------------------------------
CONTENT="Karthik prefers aisle seats and usually flies out of Chennai."
THREAD_ID="thread-$(date -u +%Y-%m-%d)-001"
SPEAKER="Karthik"
OCCURRED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---- 1. Get token -----------------------------------------------------------
echo ">> Requesting token (onprem realm onpremquipu)..." >&2
TOKEN_RESPONSE=$(curl -sSk --fail-with-body --location "$TOKEN_URL" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=password" \
  --data-urlencode "username=$USERNAME" \
  --data-urlencode "password=$PASSWORD" \
  --data-urlencode "client_id=$CLIENT_ID" \
  --data-urlencode "client_secret=$CLIENT_SECRET")

if command -v jq >/dev/null 2>&1; then
  JWT=$(printf '%s' "$TOKEN_RESPONSE" | jq -r '.access_token')
else
  JWT=$(printf '%s' "$TOKEN_RESPONSE" | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
fi

if [ -z "$JWT" ] || [ "$JWT" = "null" ]; then
  echo "!! Failed to get access_token. Response was:" >&2
  echo "$TOKEN_RESPONSE" >&2
  exit 1
fi
echo ">> Token acquired (${#JWT} chars)" >&2

# ---- 2. Ingest --------------------------------------------------------------
read -r -d '' PAYLOAD <<EOF || true
{
  "content": "$CONTENT",
  "threadId": "$THREAD_ID",
  "contentType": "text/plain",
  "role": "user",
  "speaker": "$SPEAKER",
  "occurredAt": "$OCCURRED_AT"
}
EOF

echo ">> Ingesting to space '$SPACE'${FABRIC:+ (fabric '$FABRIC')}..." >&2
FABRIC_HEADER=()
[ -n "$FABRIC" ] && FABRIC_HEADER=(-H "X-Fabric: $FABRIC")
curl -sSk --fail-with-body -X POST "$API_BASE/spaces/$SPACE/ingest" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  "${FABRIC_HEADER[@]}" \
  -d "$PAYLOAD"

echo
echo ">> Done." >&2
