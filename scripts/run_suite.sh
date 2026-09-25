#!/usr/bin/env bash
# run_suite.sh — the script the Qase-triggered Jenkins job runs.
#
# Its only contract is: leave reports/results.json behind, shaped like
#   [{"id":"QTC-441","status":"passed","ms":1240},
#    {"id":"QTC-445","status":"failed","ms":2200,"error":"..."}]
# where `id` is the Linear issue key. Jenkinsfile.qase maps those through
# qase-case-map.json and publishes them to the Qase run that launched it.
#
# Today it runs SMOKE checks only — reachability of the environment under test —
# and reports every other case as skipped, so the whole chain can be triggered
# and verified before the real UI automation is wired in. Replace `run_checks`
# with the real runner when it exists; nothing downstream changes.
#
#   SUITE=access-management ENVIRONMENT=onprem bash scripts/run_suite.sh
set -uo pipefail

ENVIRONMENT="${ENVIRONMENT:-onprem}"
SUITE="${SUITE:-all}"
MAP="${MAP:-qase-case-map.json}"
OUT="reports/results.json"
mkdir -p reports

# No endpoint is baked in. BASE_URL must be supplied deliberately, so a run can
# never reach a customer or production environment by default.
BASE="${BASE_URL:-}"
case "$ENVIRONMENT" in
  onprem|prestage|local) ;;
  *) echo "!! unknown ENVIRONMENT: $ENVIRONMENT" >&2; exit 2 ;;
esac

echo ">> environment : $ENVIRONMENT  (${BASE:-<no BASE_URL - no host will be contacted>})"
echo ">> suite       : $SUITE"
[ -f "$MAP" ] || { echo "!! $MAP not found — run from the repo root" >&2; exit 1; }

# ---- smoke checks -----------------------------------------------------------
# Each check prints: <linear-id> <passed|failed|skipped> <ms> [message]
# portable millisecond clock — BSD date has no %3N
now_ms() { python3 -c 'import time;print(int(time.time()*1000))'; }

run_checks() {
  local t0 code ms
  if [ -z "$BASE" ]; then
    echo "QTC-441 skipped 0 no BASE_URL supplied - nothing was contacted"
    while read -r id; do
      [ "$id" = "QTC-441" ] && continue
      echo "$id skipped 0 not covered by the smoke script"
    done < <(python3 -c "
import json
print('\n'.join(sorted(json.load(open('$MAP')))))")
    return
  fi
  t0=$(now_ms)
  # curl already prints 000 when it cannot connect; a second `|| echo 000`
  # would append a line and break the comparison below
  code=$(curl -sk -o /dev/null -w '%{http_code}' -m 20 "$BASE" 2>/dev/null)
  code="${code:-000}"
  ms=$(( $(now_ms) - t0 ))

  if [ "$code" = "000" ] || [ "${code:0:1}" = "5" ]; then
    echo "QTC-441 failed $ms environment unreachable at $BASE"
  else
    echo "QTC-441 passed $ms reachable, HTTP $code"
  fi

  # everything else is not executed by this script yet
  local first=1
  while read -r id; do
    [ "$id" = "QTC-441" ] && continue
    echo "$id skipped 0 not covered by the smoke script"
  done < <(python3 -c "
import json,sys
print('\n'.join(sorted(json.load(open('$MAP')))))" )
}

# ---- emit results.json ------------------------------------------------------
run_checks | python3 -c "
import json, sys
out = []
for line in sys.stdin:
    parts = line.rstrip('\n').split(' ', 3)
    if len(parts) < 3: continue
    cid, status, ms = parts[0], parts[1], parts[2]
    entry = {'id': cid, 'status': status, 'ms': int(ms or 0)}
    if len(parts) == 4 and parts[3]:
        entry['error' if status == 'failed' else 'reason'] = parts[3]
    out.append(entry)
json.dump(out, open('$OUT','w'), indent=1)
import collections
c = collections.Counter(o['status'] for o in out)
print(f\"   {len(out)} results  {dict(c)}\")
"
echo ">> wrote $OUT"
