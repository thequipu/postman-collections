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
_base = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/")
# Qase sends its own base as https://app.qase.io/api/v1, and every caller here
# appends /v1 itself - without this the URL ends up .../api/v1/v1/...
if _base.endswith("/v1"):
    _base = _base[:-3].rstrip("/")
BASE = _base
CODE = os.environ.get("QASE_PROJECT_CODE", "")
RUN = os.environ.get("QASE_RUN_ID", "")
TOKEN = os.environ.get("QASE_API_TOKEN", "")


def _get(path):
    req = urllib.request.Request(f"{BASE}/v1{path}",
                                 headers={"Token": TOKEN, "accept": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["result"]


def _paged(path):
    out, offset = [], 0
    while True:
        sep = "&" if "?" in path else "?"
        batch = _get(f"{path}{sep}limit=100&offset={offset}")["entities"]
        out += batch
        if len(batch) < 100:
            return out
        offset += 100


def _suite_cases(name):
    """Qase ids of every case under the suite titled `name`, descendants included."""
    suites = _paged(f"/suite/{CODE}")
    roots = [s["id"] for s in suites if (s.get("title") or "").lower() == name.lower()]
    if not roots:
        return None
    wanted, frontier = set(roots), list(roots)
    while frontier:                       # a parent selects everything beneath it
        parent = frontier.pop()
        for s in suites:
            if s.get("parent_id") == parent and s["id"] not in wanted:
                wanted.add(s["id"])
                frontier.append(s["id"])
    return {c["id"] for c in _paged(f"/case/{CODE}") if c.get("suite_id") in wanted}


def _plan_cases(name):
    plans = _paged(f"/plan/{CODE}")
    hit = next((p for p in plans if (p.get("title") or "").lower() == name.lower()), None)
    if not hit:
        return None
    return {c["case_id"] for c in _get(f"/plan/{CODE}/{hit['id']}")["cases"]}


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

    if in_run is not None and not in_run:
        # Qase's automated run type creates the run with no cases at all: it expects the
        # automation to decide what ran and report back. Left alone that resolves to an
        # empty scope and the build runs nothing, so take the selection from CASES when
        # the job was given one, and otherwise run everything that is bound.
        picked = [t.strip() for t in os.environ.get("CASES", "").split(",") if t.strip()]
        if picked:
            by_key = {k: v["qase_id"] for k, v in amap.items()}
            ids, unknown = set(), []
            for t in picked:
                low = t.lower()
                if low.startswith("suite:") or low.startswith("plan:"):
                    kind, _, name = t.partition(":")
                    name = name.strip()
                    try:
                        found = (_suite_cases(name) if kind.lower() == "suite"
                                 else _plan_cases(name))
                    except Exception as e:
                        print(f"!! could not read {kind.lower()} {name!r}: {e}", file=sys.stderr)
                        return 1
                    if found is None:
                        unknown.append(t)
                    else:
                        print(f">>   {kind.lower()} {name!r}: {len(found)} case(s)", file=sys.stderr)
                        ids |= found
                elif t.isdigit():
                    ids.add(int(t))
                elif t in by_key:
                    ids.add(by_key[t])
                else:
                    unknown.append(t)
            if unknown:
                print(f"!! CASES: no such case, suite or plan: {', '.join(unknown)}",
                      file=sys.stderr)
                return 1
            in_run = ids
            print(f">> run {RUN} holds no cases; CASES selects {len(ids)}", file=sys.stderr)
        else:
            in_run = None
            print(f">> run {RUN} holds no cases and CASES is empty; running everything bound",
                  file=sys.stderr)

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
