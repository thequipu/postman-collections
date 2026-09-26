#!/usr/bin/env python3
"""Make the Qase suites mirror what actually runs the cases, and say so on each case.

    UI_REPO=../automation_fast_api QASE_API_TOKEN=... python3 tools/sync-qase-structure.py [--dry-run]

Two problems this fixes.

Suites did not say what runs them. "API Testing" held two unrelated collections,
so picking a suite to run told you nothing about what would execute. Each source
— a Postman collection, a run_suite.py suite, a pytest file — now gets its own
suite under the runner it belongs to:

    API Testing / SMOKE-Platform-Health
    API Testing / FLOW-Qase-Basic
    UI Testing  / Playwright
    UI Testing  / datacatalog_login_positive

And a case did not say which script runs it. Each description now carries the
binding in a readable form, including the command that runs that case alone, so
someone reading the case in Qase can reproduce the run without this repo's map.

It also maintains test plans. A plan is a saved selection of cases: a run is
created FROM a plan instead of listing case ids, so "run the API health checks"
stops being a list someone assembles by hand and becomes a name. Adding a case
to a collection and re-running this puts it in the plan, and every future run
made from that plan picks it up.

Idempotent: suites, descriptions and plans are reconciled, never duplicated.
"""
import argparse, json, os, sys, urllib.error, urllib.request

BASE = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/") + "/v1"
CODE = os.environ.get("QASE_PROJECT_CODE", "QQA")
TOKEN = os.environ.get("QASE_API_TOKEN") or ""
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = "— automation binding —"


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


def placement(key, v):
    """(parent suite, child suite) for a binding — the runner, then its source."""
    r = v.get("runner")
    if r == "postman":
        return "API Testing", v["collection"]
    if r == "suite":
        return "UI Testing", v["suite"]
    if r == "pytest":
        return "UI Testing", "Playwright"
    return None, None


def binding_text(key, v):
    """What runs this case, and how to run just it."""
    r = v.get("runner")
    # The [key] marker stays: tools/fetch-workspace.py and build-dashboard.py
    # parse it out of the description to recover a case's external id.
    lines = [f"[{key}]", "", MARKER, f"runner: {r}"]
    if r == "postman":
        lines += [f"collection: flows/{v['collection']}.postman_collection.json",
                  f"request: {v['junit_suite']}",
                  "",
                  "postman collection run "
                  f"flows/{v['collection']}.postman_collection.json \\",
                  "  -e environments/onprem.postman_environment.json --insecure"]
    elif r == "suite":
        lines += [f"suite: test_suite/suites/{v['suite']}.json",
                  f"step: {v['step']}", f"case: {v['stage']}",
                  "",
                  f"python test_suite/run_suite.py --suite {v['suite']} {v['step']}"]
    elif r == "pytest":
        lines += [f"test: {v['nodeid']}", "", f"pytest {v['nodeid']}"]
    if v.get("linear"):
        lines += ["", f"test case in Linear: {v['linear']}"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not TOKEN and not args.dry_run:
        sys.exit("QASE_API_TOKEN is not set")

    amap = json.load(open(os.path.join(ROOT, "automation-map.json")))
    bound = {k: v for k, v in amap.items() if v.get("runner", "none") != "none"}

    wanted = {}
    for k, v in bound.items():
        parent, child = placement(k, v)
        if child:
            wanted.setdefault((parent, child), []).append(k)

    print(f">> {len(bound)} bound case(s) across {len(wanted)} suite(s)")
    for (parent, child), keys in sorted(wanted.items()):
        print(f"   {parent} / {child}: {len(keys)}")
    if args.dry_run:
        k0 = sorted(bound)[0]
        print(f"\n   example description for {k0}:\n")
        print("   " + binding_text(k0, bound[k0]).replace("\n", "\n   "))
        return 0

    suites = paged(f"/suite/{CODE}")
    by_title = {}
    for s in suites:
        by_title.setdefault(s["title"], []).append(s)

    def ensure(title, parent_id=None):
        for s in by_title.get(title, []):
            if s.get("parent_id") == parent_id:
                return s["id"]
        payload = {"title": title}
        if parent_id:
            payload["parent_id"] = parent_id
        sid = call("POST", f"/suite/{CODE}", payload)["result"]["id"]
        by_title.setdefault(title, []).append({"id": sid, "title": title, "parent_id": parent_id})
        print(f"   created suite {title}")
        return sid

    suite_ids = {}
    for parent, child in sorted(wanted):
        pid = ensure(parent)
        suite_ids[(parent, child)] = ensure(child, pid)

    cases = {c["id"]: c for c in paged(f"/case/{CODE}")}
    moved = described = 0
    for (parent, child), keys in sorted(wanted.items()):
        target = suite_ids[(parent, child)]
        for k in keys:
            v = bound[k]
            case = cases.get(v["qase_id"])
            if not case:
                print(f"   !! {k}: qase case {v['qase_id']} not found")
                continue
            body = binding_text(k, v)
            # Keep anything a human wrote above the marker; replace only our block.
            existing = case.get("description") or ""
            human = existing.split(MARKER)[0].strip()
            # Earlier tools wrote their own generated line; it is not human text
            # and it names the runner we no longer use.
            human = "\n".join(l for l in human.splitlines()
                               if not l.startswith(f"[{k}] Bound to")).strip()
            desc = (human + "\n\n" + body).strip() if human else body

            payload = {}
            if case.get("suite_id") != target:
                payload["suite_id"] = target
            if existing.strip() != desc.strip():
                payload["description"] = desc
            if not payload:
                continue
            call("PATCH", f"/case/{CODE}/{v['qase_id']}", payload)
            moved += "suite_id" in payload
            described += "description" in payload

    print(f">> {moved} case(s) moved, {described} description(s) rewritten")

    # --- test plans: a named selection, so a run needs a name, not a case list ---
    plans = {
        "API health": [k for k, v in bound.items()
                       if v.get("collection") == "SMOKE-Platform-Health"],
        "UI validation": [k for k, v in bound.items()
                          if v.get("runner") in ("pytest", "suite")],
        "Release verification": [k for k, v in bound.items()
                                 if v.get("collection") == "SMOKE-Platform-Health"
                                 or v.get("runner") in ("pytest", "suite")],
    }
    existing = {p["title"]: p for p in paged(f"/plan/{CODE}")}
    for title, keys in plans.items():
        ids = sorted(bound[k]["qase_id"] for k in keys)
        if not ids:
            continue
        body = {"title": title,
                "description": f"{len(ids)} case(s), maintained by tools/sync-qase-structure.py.",
                "cases": ids}
        if title in existing:
            call("PATCH", f"/plan/{CODE}/{existing[title]['id']}", body)
            print(f"   plan '{title}': {len(ids)} case(s) (updated)")
        else:
            call("POST", f"/plan/{CODE}", body)
            print(f"   plan '{title}': {len(ids)} case(s) (created)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
