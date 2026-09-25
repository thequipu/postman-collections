#!/usr/bin/env python3
"""Create one Qase case per request in a Postman collection, and bind them.

    QASE_API_TOKEN=... python3 tools/bind-collection.py \
        --collection SMOKE-Platform-Health --suite "API Testing" --prefix QAPI

The Postman CLI reports one JUnit <testsuite> per request, named "<folder> / <request>",
so a request is the natural unit for a test case. This derives the cases from
the collection rather than having someone retype the request names into Qase,
where they would drift the first time a request is renamed.

Idempotent: a case whose title already exists is reused, not duplicated.
Re-run it after adding requests to a collection and only the new ones appear.
"""
import argparse, json, os, re, sys, urllib.error, urllib.request

BASE = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/") + "/v1"
CODE = os.environ.get("QASE_PROJECT_CODE", "QQA")
TOKEN = os.environ.get("QASE_API_TOKEN") or ""
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTOMATED = 2


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


def requests_of(collection):
    """Yield (junit_suite_name, request_name). Mirrors newman's JUnit naming."""
    path = os.path.join(ROOT, "flows", f"{collection}.postman_collection.json")
    if not os.path.exists(path):
        sys.exit(f"no such collection: {path}")
    doc = json.load(open(path))

    def walk(items, folder=None):
        for it in items:
            if "item" in it:
                yield from walk(it["item"], it["name"])
            elif folder:
                yield f"{folder} / {it['name']}", it["name"]
            else:
                # newman names a top-level request by itself, with no folder prefix
                yield it["name"], it["name"]
    return list(walk(doc["item"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True, help="basename under flows/")
    ap.add_argument("--suite", required=True, help="child suite title, e.g. 'API Testing'")
    ap.add_argument("--parent-suite", default="Platform Smoke")
    ap.add_argument("--prefix", default="QAPI", help="key prefix for the external id")
    ap.add_argument("--start", type=int, default=101, help="first number in the key sequence")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not TOKEN and not args.dry_run:
        sys.exit("QASE_API_TOKEN is not set.")

    reqs = requests_of(args.collection)
    print(f">> {args.collection}: {len(reqs)} requests")
    if args.dry_run:
        for i, (suite_name, req) in enumerate(reqs, args.start):
            print(f"   {args.prefix}-{i:03d}  {req}   <- {suite_name}")
        return

    suites = paged(f"/suite/{CODE}")
    parent = next((s for s in suites if s["title"] == args.parent_suite), None)
    if not parent:
        parent = {"id": call("POST", f"/suite/{CODE}", {"title": args.parent_suite})["result"]["id"]}
        print(f">> created parent suite {args.parent_suite}")
    child = next((s for s in suites if s["title"] == args.suite
                  and s.get("parent_id") == parent["id"]), None)
    if not child:
        child = {"id": call("POST", f"/suite/{CODE}",
                            {"title": args.suite, "parent_id": parent["id"]})["result"]["id"]}
        print(f">> created suite {args.parent_suite} / {args.suite}")

    by_title = {c["title"]: c["id"] for c in paged(f"/case/{CODE}")}
    amap_path = os.path.join(ROOT, "automation-map.json")
    amap = json.load(open(amap_path))
    # Reuse the key already bound to this junit_suite, so re-running never renumbers.
    by_suite = {v.get("junit_suite"): k for k, v in amap.items() if v.get("junit_suite")}
    used = {int(m.group(1)) for k in amap
            if (m := re.fullmatch(rf"{re.escape(args.prefix)}-(\d+)", k))}
    nxt = args.start

    created = reused = 0
    for suite_name, req in reqs:
        key = by_suite.get(suite_name)
        if not key:
            while nxt in used:
                nxt += 1
            key = f"{args.prefix}-{nxt:03d}"
            used.add(nxt)
        title = f"{key}: {req}"
        if title in by_title:
            cid = by_title[title]
            reused += 1
        else:
            cid = call("POST", f"/case/{CODE}", {
                "title": title, "suite_id": child["id"], "automation": AUTOMATED,
                "description": f"[{key}] Bound to newman: "
                               f'{{"collection": "{args.collection}", "junit_suite": "{suite_name}"}}',
            })["result"]["id"]
            created += 1
        amap[key] = {"automated": True, "qase_id": cid, "runner": "postman",
                     "test": key, "collection": args.collection,
                     "junit_suite": suite_name, "title": req}

    for v in amap.values():
        v.setdefault("runner", "none")
    json.dump(amap, open(amap_path, "w"), indent=1, sort_keys=True)
    json.dump({k: v["qase_id"] for k, v in amap.items()},
              open(os.path.join(ROOT, "qase-case-map.json"), "w"), indent=1, sort_keys=True)
    print(f">> {created} case(s) created, {reused} reused; automation-map now {len(amap)} entries")


if __name__ == "__main__":
    main()
