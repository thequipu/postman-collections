#!/usr/bin/env python3
"""Check every binding in automation-map.json actually resolves.

    UI_REPO=../automation_fast_api python3 tools/verify-bindings.py

A binding that does not resolve only shows up at run time, as that case
reporting `blocked` — which reads as an infrastructure problem rather than a
typo in a request name. This catches it before a run.

Exits non-zero when anything is unresolved, so it can gate a build.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_REPO = os.environ.get("UI_REPO", os.path.join(os.path.dirname(ROOT), "automation_fast_api"))


def junit_names(collection):
    """The <testsuite> names newman will emit for this collection."""
    path = os.path.join(ROOT, "flows", f"{collection}.postman_collection.json")
    if not os.path.exists(path):
        return None
    names = []

    def walk(items, folder=None):
        for it in items:
            if "item" in it:
                walk(it["item"], it["name"])
            elif folder:
                names.append(f"{folder} / {it['name']}")
            else:
                names.append(it["name"])
    walk(json.load(open(path))["item"])
    return names


def main():
    amap = json.load(open(os.path.join(ROOT, "automation-map.json")))
    problems, counts = [], {}
    cache = {}

    for key, v in sorted(amap.items()):
        runner = v.get("runner", "none")
        counts[runner] = counts.get(runner, 0) + 1
        if runner == "newman":
            coll = v.get("collection")
            if coll not in cache:
                cache[coll] = junit_names(coll)
            if cache[coll] is None:
                problems.append(f"{key}: no collection flows/{coll}.postman_collection.json")
            elif v.get("junit_suite") not in cache[coll]:
                problems.append(f"{key}: {v.get('junit_suite')!r} is not a request in {coll}")
        elif runner == "suite":
            f = os.path.join(UI_REPO, "test_suite", "suites", f"{v.get('suite')}.json")
            if not v.get("suite") or not os.path.exists(f):
                problems.append(f"{key}: no suite {v.get('suite')!r} in {UI_REPO}/test_suite/suites")
            elif not v.get("stage"):
                problems.append(f"{key}: binding has no 'stage' to match in the report")
        elif runner == "pytest":
            f = (v.get("nodeid") or "").split("::")[0]
            if not f or not os.path.exists(os.path.join(UI_REPO, f)):
                problems.append(f"{key}: {f or '(no nodeid)'} missing from {UI_REPO}")

    for r, n in sorted(counts.items()):
        print(f"  {r:<8} {n}")
    if problems:
        print("\n!! unresolved bindings:")
        for p in problems:
            print(f"   {p}")
        return 1
    print("\n>> every binding resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
