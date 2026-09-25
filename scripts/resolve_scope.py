#!/usr/bin/env python3
"""Work out which cases this run covers, and write reports/scope.json.

    QASE_RUN_ID=17 QASE_API_TOKEN=... python3 scripts/resolve_scope.py

The Qase run is the single source of truth for what executes. Three consumers
need that answer before anything runs — preflight (which runners must work),
the pipeline (whether to fetch the UI repo at all), and run_suite.sh (what to
run) — so it is resolved once, here, rather than separately in each.

Without a run id it falls back to the whole map, which is what a local check
wants. Prints the runners in scope, one per line, on stdout.
"""
import json, os, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = Path(os.environ.get("MAP", ROOT / "automation-map.json"))
SCOPE = ROOT / "reports" / "scope.json"
BASE = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/")
CODE = os.environ.get("QASE_PROJECT_CODE", "")
RUN = os.environ.get("QASE_RUN_ID", "")
TOKEN = os.environ.get("QASE_API_TOKEN", "")


def main():
    if not MAP.exists():
        print(f"!! {MAP.name} not found — run from the repo root", file=sys.stderr)
        return 1
    amap = json.load(open(MAP))
    SCOPE.parent.mkdir(parents=True, exist_ok=True)

    in_run = None
    if RUN and TOKEN and CODE:
        req = urllib.request.Request(
            f"{BASE}/v1/run/{CODE}/{RUN}?include=cases",
            headers={"Token": TOKEN, "accept": "application/json"})
        try:
            in_run = set(json.loads(urllib.request.urlopen(req, timeout=30).read())["result"]["cases"])
        except Exception as e:
            # Falling back to the whole map would silently widen the run, so refuse.
            print(f"!! could not read the cases of run {RUN}: {e}", file=sys.stderr)
            return 1

    sel = {k: v for k, v in amap.items() if in_run is None or v["qase_id"] in in_run}
    json.dump(sel, open(SCOPE, "w"), indent=1, sort_keys=True)

    runners = sorted({v.get("runner", "none") for v in sel.values()
                      if v.get("automated") and v.get("runner", "none") != "none"})
    automated = sum(1 for v in sel.values() if v.get("automated"))
    where = f"run {RUN}" if in_run is not None else "the whole map (no run scope given)"
    print(f">> {where}: {len(sel)} cases — {automated} automated, "
          f"{len(sel) - automated} manual", file=sys.stderr)
    print(f">> runners in scope: {', '.join(runners) or 'none'}", file=sys.stderr)

    for r in runners:                      # stdout is the machine-readable answer
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
