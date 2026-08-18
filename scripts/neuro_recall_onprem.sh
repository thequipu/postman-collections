#!/usr/bin/env bash
set -euo pipefail

# ---- Config (ONPREM) --------------------------------------------------------
# Onprem Keycloak realm "onpremquipu"; gateway api-onprem.thequipu.in; self-signed TLS -> -k.
TOKEN_URL="https://ui-login.thequipu.in/realms/onpremquipu/protocol/openid-connect/token"
API_BASE="https://api-onprem.thequipu.in/quipuNeuro/v1"

SPACE="${SPACE:-karthik}"                 # space to recall from; override: SPACE=xxx ...
TENANT="${TENANT:-onpremquipu}"           # X-Tenant-ID header (onprem derives tenant from token, so optional)

USERNAME="quipuadmin"
PASSWORD="karthik"
CLIENT_ID="onpremquipu-client"
CLIENT_SECRET="7twCqTl1Ur49tOwtLAbEy6kEXOVEIRwm"

# ---- Recall params (override via env or $1 for the query) -------------------
QUERY="${1:-${QUERY:-What seat does Karthik prefer?}}"
TOKEN_BUDGET="${TOKEN_BUDGET:-1200}"
MODE="${MODE:-LIVE}"

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

# ---- 2. Recall --------------------------------------------------------------
read -r -d '' PAYLOAD <<EOF || true
{
  "query": "$QUERY",
  "tokenBudget": $TOKEN_BUDGET,
  "mode": "$MODE"
}
EOF

echo ">> Recall from space '$SPACE': \"$QUERY\"" >&2
RESP=$(curl -sSk --fail-with-body -X POST "$API_BASE/spaces/$SPACE/recall" \
  -H "Authorization: Bearer $JWT" \
  -H "X-Tenant-ID: $TENANT" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

if command -v jq >/dev/null 2>&1; then
  printf '%s' "$RESP" | jq '{droppedDueToBudget, items: [.items[] | {score, content, namespaceId}]}'
else
  printf '%s\n' "$RESP"
fi

echo ">> Done." >&2
