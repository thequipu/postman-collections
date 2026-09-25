#!/usr/bin/env bash
# run_suite.sh — the script the Qase-triggered Jenkins job runs.
#
# It works out WHAT TO RUN from the Qase run itself:
#
#   1. asks Qase which cases the run contains          (QASE_RUN_ID + QASE_API_TOKEN)
#   2. resolves each to its automation id              (automation-map.json)
#   3. runs only the automated ones, reports the rest as skipped
#   4. writes reports/results.json keyed by Linear id
#
# So selecting a handful of cases in Qase is enough — nothing here needs editing,
# and a run scoped to one suite executes only that suite.
#
# Without QASE_RUN_ID it falls back to the whole map, which is what a local
# smoke check wants.
#
#   MODE=simulate SEED=7 bash scripts/run_suite.sh
#   QASE_RUN_ID=10 QASE_API_TOKEN=… bash scripts/run_suite.sh
set -uo pipefail

MODE="${MODE:-smoke}"
SEED="${SEED:-1}"
MAP="${MAP:-automation-map.json}"
OUT="reports/results.json"
QASE_API_BASE_URL="${QASE_API_BASE_URL:-https://api.qase.io}"
QASE_PROJECT_CODE="${QASE_PROJECT_CODE:-}"
QASE_RUN_ID="${QASE_RUN_ID:-}"
QASE_API_TOKEN="${QASE_API_TOKEN:-}"
BUILD_ENDPOINT="${BUILD_ENDPOINT:-}"
BUILD="${BUILD:-}"
BASE="${BASE_URL:-}"
ENVIRONMENT="${ENVIRONMENT:-onprem}"
UI_REPO="${UI_REPO:-$(cd .. 2>/dev/null && pwd)/automation_fast_api}"
mkdir -p reports
[ -f "$MAP" ] || { echo "!! $MAP not found — run from the repo root" >&2; exit 1; }

# ---- build number, from the service under test ------------------------------
# The build is whatever the service reports at the moment the run starts, not a
# number typed into a form. BUILD overrides it for a replay.
if [ -z "$BUILD" ] && [ -n "$BUILD_ENDPOINT" ]; then
  BUILD=$(curl -sk -m 20 "$BUILD_ENDPOINT" 2>/dev/null | python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    sys.exit()
for k in ("build","buildNumber","build_number","version","appVersion","gitCommit","commit"):
    if isinstance(d,dict) and d.get(k): print(d[k]); break
' 2>/dev/null)
  [ -n "$BUILD" ] && echo ">> build from service: $BUILD" || echo ">> build endpoint gave nothing usable"
fi
printf '%s' "${BUILD:-unknown}" > reports/build.txt

echo ">> mode        : $MODE"
echo ">> environment : $ENVIRONMENT"
echo ">> build       : ${BUILD:-unknown}"

# ---- which cases is this run asking for? ------------------------------------
SCOPE=reports/scope.json
# Resolved by one owner, so preflight and the pipeline see exactly the same scope.
# Already resolved by an earlier pipeline stage? Reuse it rather than asking twice.
if [ -s "$SCOPE" ] && [ "${SCOPE_RESOLVED:-}" = "1" ]; then
  echo ">> reusing the scope resolved earlier in this build"
else
  MAP="$MAP" python3 scripts/resolve_scope.py >/dev/null || {
    echo "!! could not resolve which cases this run covers" >&2; exit 1; }
fi

# ---- execute ----------------------------------------------------------------
# Each line: <linear-id> <passed|failed|skipped|blocked> <ms> [message]
run_checks() {
  if [ "$MODE" = "real" ]; then
    # Runs the automation each case is bound to — Postman CLI for flows, pytest and
    # the UI repo's own suite runner for UI.
    ENVIRONMENT="$ENVIRONMENT" UI_REPO="$UI_REPO" python3 scripts/run_real.py "$SCOPE"
    return
  fi

  if [ "$MODE" = "simulate" ]; then
    python3 - "$SCOPE" "$SEED" <<'PY'
import hashlib, json, sys
sel  = json.load(open(sys.argv[1])); seed = sys.argv[2]
FAIL = ["expected HTTP 200, got 500",
        "element not found: submit button did not render within 30s",
        "validation message missing for empty required field",
        "expected error banner, got dashboard redirect",
        "stale value shown after save; list not refreshed"]
for cid, v in sorted(sel.items()):
    if not (v["automated"] and v["test"]):
        print(f"{cid} skipped 0 manual case - no automation bound"); continue
    h = int(hashlib.sha256(f"{seed}:{cid}".encode()).hexdigest(), 16)
    r, ms = h % 100, 200 + (h >> 8) % 4000
    if   r < 82: print(f"{cid} passed {ms}")
    elif r < 92: print(f"{cid} failed {ms} {FAIL[h % len(FAIL)]} [{v['test']}]")
    elif r < 97: print(f"{cid} skipped 0 not enabled in this environment")
    else:        print(f"{cid} blocked 0 blocked by an open defect")
PY
    return
  fi

  # smoke: one real reachability check, the rest reported honestly as not run
  local t0 code ms first=1
  python3 - "$SCOPE" "$BASE" <<'PY'
import json, sys, time, urllib.request, ssl
sel, base = json.load(open(sys.argv[1])), sys.argv[2]
runnable = [c for c, v in sorted(sel.items()) if v["automated"] and v["test"]]
if not base:
    for c in sorted(sel): print(f"{c} skipped 0 no BASE_URL supplied - nothing was contacted")
    sys.exit()
probe = runnable[0] if runnable else None
if probe:
    t0 = time.time()
    try:
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(base, timeout=20, context=ctx) as r: code = r.status
    except Exception as e:
        code = 0
    ms = int((time.time() - t0) * 1000)
    if code == 0 or 500 <= code < 600:
        print(f"{probe} failed {ms} environment unreachable or erroring at {base} (HTTP {code})")
    else:
        print(f"{probe} passed {ms} reachable, HTTP {code}")
for c in sorted(sel):
    if c != probe: print(f"{c} skipped 0 not covered by the smoke script")
PY
}

run_checks | python3 -c "
import json, sys, collections
out=[]
for line in sys.stdin:
    p=line.rstrip('\n').split(' ',3)
    if len(p)<3: continue
    e={'id':p[0],'status':p[1],'ms':int(p[2] or 0)}
    if len(p)==4 and p[3]: e['error' if p[1]=='failed' else 'reason']=p[3]
    out.append(e)
json.dump(out, open('$OUT','w'), indent=1)
print('   %d results  %s' % (len(out), dict(collections.Counter(o['status'] for o in out))))
"
echo ">> wrote $OUT"
