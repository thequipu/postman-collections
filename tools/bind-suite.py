#!/usr/bin/env python3
"""Create one Qase case per case in a run_suite.py suite, and bind them.

    UI_REPO=../automation_fast_api QASE_API_TOKEN=... python3 tools/bind-suite.py \
        --suite datacatalog_login_positive --step login_tests --prefix QUI

run_suite.py reports one stage per entry in the suite's case list, named by that
entry's "name". So a suite case is the natural unit for a Qase case, and the
stage name is the binding key — the same shape as tools/bind-collection.py uses
for Postman requests.

Derived from the suite file rather than retyped, so renaming a case in the suite
and re-running this keeps Qase in step instead of silently orphaning a binding.
Idempotent: a stage already bound keeps its key and its Qase case.
"""
import argparse, json, os, re, sys, urllib.error, urllib.request

BASE = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/") + "/v1"
CODE = os.environ.get("QASE_PROJECT_CODE", "QQA")
TOKEN = os.environ.get("QASE_API_TOKEN") or ""
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_REPO = os.environ.get("UI_REPO", os.path.join(os.path.dirname(ROOT), "automation_fast_api"))
AUTOMATED = 2

# Which suite key holds the case list for a given step.
STEP_CASES = {"login_tests": "LOGIN_TESTS"}


def call(method, path, payload=None):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode() if payload is not None else None,
        method=method, headers={"Token": TOKEN, "accept": "application/json",
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
    ap.add_argument("--suite", required=True)
    ap.add_argument("--step", required=True, choices=sorted(STEP_CASES))
    ap.add_argument("--qase-suite", default="UI Testing")
    ap.add_argument("--parent-suite", default="Platform Smoke")
    ap.add_argument("--prefix", default="QUI")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = os.path.join(UI_REPO, "test_suite", "suites", f"{args.suite}.json")
    if not os.path.exists(path):
        sys.exit(f"no such suite: {path}")
    cases = json.load(open(path)).get(STEP_CASES[args.step], [])
    if not cases:
        sys.exit(f"{args.suite}.json has no {STEP_CASES[args.step]} entries")
    stages = [c.get("name") for c in cases if c.get("name")]
    print(f">> {args.suite} / {args.step}: {len(stages)} case(s)")

    if args.dry_run:
        for s in stages:
            print(f"   {s}")
        return
    if not TOKEN:
        sys.exit("QASE_API_TOKEN is not set.")

    suites = paged(f"/suite/{CODE}")
    parent = next((s for s in suites if s["title"] == args.parent_suite), None)
    if not parent:
        parent = {"id": call("POST", f"/suite/{CODE}", {"title": args.parent_suite})["result"]["id"]}
    child = next((s for s in suites if s["title"] == args.qase_suite
                  and s.get("parent_id") == parent["id"]), None)
    if not child:
        child = {"id": call("POST", f"/suite/{CODE}",
                            {"title": args.qase_suite, "parent_id": parent["id"]})["result"]["id"]}

    by_title = {c["title"]: c["id"] for c in paged(f"/case/{CODE}")}
    amap_path = os.path.join(ROOT, "automation-map.json")
    amap = json.load(open(amap_path))
    # A stage already bound keeps its key, so renumbering never happens.
    by_stage = {v.get("stage"): k for k, v in amap.items()
                if v.get("runner") == "suite" and v.get("suite") == args.suite}
    used = {int(m.group(1)) for k in amap
            if (m := re.fullmatch(rf"{re.escape(args.prefix)}-(\d+)", k))}
    nxt = args.start
    created = reused = 0

    for stage in stages:
        key = by_stage.get(stage)
        if not key:
            while nxt in used:
                nxt += 1
            key = f"{args.prefix}-{nxt:03d}"
            used.add(nxt)
        title = f"{key}: {stage}"
        if title in by_title:
            cid = by_title[title]
            reused += 1
        else:
            cid = call("POST", f"/case/{CODE}", {
                "title": title, "suite_id": child["id"], "automation": AUTOMATED,
                "description": f"[{key}] Bound to run_suite: "
                               f'{{"suite": "{args.suite}", "step": "{args.step}", '
                               f'"stage": "{stage}"}}'})["result"]["id"]
            created += 1
        amap[key] = {"automated": True, "qase_id": cid, "runner": "suite", "test": key,
                     "suite": args.suite, "step": args.step, "stage": stage, "title": stage}

    for v in amap.values():
        v.setdefault("runner", "none")
    json.dump(amap, open(amap_path, "w"), indent=1, sort_keys=True)
    json.dump({k: v["qase_id"] for k, v in amap.items()},
              open(os.path.join(ROOT, "qase-case-map.json"), "w"), indent=1, sort_keys=True)
    print(f">> {created} created, {reused} reused; automation-map now {len(amap)} entries")


if __name__ == "__main__":
    main()
