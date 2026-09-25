#!/usr/bin/env python3
"""Create the Qase suites and cases for the basic flow, and bind them in automation-map.json.

    QASE_API_TOKEN=... python3 tools/create-basic-cases.py [--dry-run]

Idempotent: a suite or case that already exists by title is reused, not duplicated.
Re-running after a partial failure is safe.
"""
import argparse, json, os, sys, urllib.error, urllib.request

BASE = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/") + "/v1"
CODE = os.environ.get("QASE_PROJECT_CODE", "QQA")
TOKEN = os.environ.get("QASE_API_TOKEN") or ""
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AUTOMATED = 2          # Qase: 0 manual, 1 to-be-automated, 2 automated

# key -> (suite, title, runner, locator)
CASES = [
    ("QAPI-001", "API Testing", "Setup: security service reachable and healthy",
     "newman", {"collection": "FLOW-Qase-Basic", "junit_suite": "Qase Basic / 00 Setup"}),
    ("QAPI-002", "API Testing", "Admin login returns a valid token set",
     "newman", {"collection": "FLOW-Qase-Basic", "junit_suite": "Qase Basic / 01 Admin Login"}),
    ("QAPI-003", "API Testing", "Valid tenant is accepted",
     "newman", {"collection": "FLOW-Qase-Basic", "junit_suite": "Qase Basic / 02 Validate Tenant"}),
    ("QAPI-004", "API Testing", "Schema list is retrievable",
     "newman", {"collection": "FLOW-Qase-Basic", "junit_suite": "Qase Basic / 03 List Schemas"}),
    ("QUI-001", "UI Testing", "UI smoke: browser launches and a page loads",
     "pytest", {"nodeid": "tests/test_smoke.py::test_smoke"}),
]
PARENT_SUITE = "Platform Smoke"


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Token": TOKEN, "accept": "application/json",
                                          "content-type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Qase {e.code} on {method} {path}: {e.read()[:300].decode('utf-8','replace')}")


def paged(path):
    out, offset = [], 0
    while True:
        sep = "&" if "?" in path else "?"
        batch = call("GET", f"{path}{sep}limit=100&offset={offset}")["result"]["entities"]
        out += batch
        if len(batch) < 100:
            return out
        offset += 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not TOKEN:
        sys.exit("QASE_API_TOKEN is not set.")

    if args.dry_run:
        for key, suite, title, runner, loc in CASES:
            print(f"  would create {key:<9} [{PARENT_SUITE} / {suite}] {title}  <- {runner} {loc}")
        return

    suites = {s["title"]: s for s in paged(f"/suite/{CODE}")}
    parent = suites.get(PARENT_SUITE)
    if not parent:
        pid = call("POST", f"/suite/{CODE}", {"title": PARENT_SUITE,
                   "description": "Cases bound to real automation, one case per runner step."})["result"]["id"]
        print(f">> created suite {PARENT_SUITE} (id {pid})")
    else:
        pid = parent["id"]
        print(f">> suite {PARENT_SUITE} exists (id {pid})")

    child_ids = {}
    for child in sorted({c[1] for c in CASES}):
        existing = next((s for s in suites.values()
                         if s["title"] == child and s.get("parent_id") == pid), None)
        if existing:
            child_ids[child] = existing["id"]
            print(f">> suite {PARENT_SUITE} / {child} exists (id {existing['id']})")
        else:
            cid = call("POST", f"/suite/{CODE}", {"title": child, "parent_id": pid})["result"]["id"]
            child_ids[child] = cid
            print(f">> created suite {PARENT_SUITE} / {child} (id {cid})")

    by_title = {c["title"]: c for c in paged(f"/case/{CODE}")}
    created = {}
    for key, suite, title, runner, loc in CASES:
        full = f"{key}: {title}"
        if full in by_title:
            created[key] = by_title[full]["id"]
            print(f">> case {key} exists (qase id {created[key]})")
            continue
        payload = {
            "title": full,
            "suite_id": child_ids[suite],
            # The key in brackets is what tools/*.py parse back out as the external id.
            "description": f"[{key}] Bound to {runner}: {json.dumps(loc)}",
            "automation": AUTOMATED,
        }
        created[key] = call("POST", f"/case/{CODE}", payload)["result"]["id"]
        print(f">> created case {key} (qase id {created[key]})")

    # Bind into automation-map.json, and derive qase-case-map.json from it.
    amap_path = os.path.join(ROOT, "automation-map.json")
    amap = json.load(open(amap_path))
    for key, suite, title, runner, loc in CASES:
        amap[key] = {"automated": True, "qase_id": created[key], "runner": runner,
                     "test": key, "title": title, **loc}
    for k, v in amap.items():
        v.setdefault("runner", "none")          # existing 155 UI cases have no runner yet
    json.dump(amap, open(amap_path, "w"), indent=1, sort_keys=True)

    cmap_path = os.path.join(ROOT, "qase-case-map.json")
    json.dump({k: v["qase_id"] for k, v in amap.items()},
              open(cmap_path, "w"), indent=1, sort_keys=True)

    runners = {}
    for v in amap.values():
        runners[v.get("runner", "none")] = runners.get(v.get("runner", "none"), 0) + 1
    print(f">> automation-map.json: {len(amap)} entries, runners {runners}")
    print(f">> qase-case-map.json derived: {len(amap)} entries")


if __name__ == "__main__":
    main()
