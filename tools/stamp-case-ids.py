#!/usr/bin/env python3
"""Write each case's id into the script that runs it.

    UI_REPO=../automation_fast_api python3 tools/stamp-case-ids.py [--dry-run]

automation-map.json already says which script runs a case. This is the other
direction: open a collection or a suite file and see which case each step
serves, without going through the map.

  Postman   the request's `description` gains a "Qase case" line. Deliberately
            NOT the request name — that name is the JUnit testsuite, and every
            binding in the map matches on it, so renaming would unbind all 16.
  run_suite the case's `tags` gain `qase:<key>`. tags is the one per-case field
            the runner carries as a label and keeps out of the login payload;
            any other key would be passed to perform_login as a credential field.
  pytest    left alone — a node id is already the binding, and a test file has
            nowhere to put this that is not a comment.

Idempotent: an existing stamp is replaced, not appended.
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_REPO = os.environ.get("UI_REPO", os.path.join(os.path.dirname(ROOT), "automation_fast_api"))
STAMP = "Qase case:"


def stamp_line(key, v):
    bits = [f"{STAMP} {key} (id {v['qase_id']})"]
    if v.get("linear"):
        bits.append(f"Linear test case: {v['linear']}")
    return " · ".join(bits)


def stamp_postman(bound, dry):
    changed = 0
    by_collection = {}
    for k, v in bound.items():
        if v.get("runner") == "postman":
            by_collection.setdefault(v["collection"], {})[v["junit_suite"]] = (k, v)

    for coll, wanted in sorted(by_collection.items()):
        path = os.path.join(ROOT, "flows", f"{coll}.postman_collection.json")
        if not os.path.exists(path):
            print(f"   !! missing {path}")
            continue
        doc = json.load(open(path))
        touched = 0

        def walk(items, folder=None):
            nonlocal touched
            for it in items:
                if "item" in it:
                    walk(it["item"], it["name"])
                    continue
                name = f"{folder} / {it['name']}" if folder else it["name"]
                hit = wanted.get(name)
                if not hit:
                    continue
                key, v = hit
                req = it.setdefault("request", {})
                old = req.get("description") or ""
                kept = "\n".join(l for l in old.splitlines() if not l.startswith(STAMP)).strip()
                new = (kept + "\n" + stamp_line(key, v)).strip() if kept else stamp_line(key, v)
                if new != old:
                    req["description"] = new
                    touched += 1
        walk(doc["item"])

        if touched and not dry:
            with open(path, "w") as fh:
                json.dump(doc, fh, indent=2)
        if touched:
            print(f"   {coll}: {touched} request(s) stamped")
            changed += touched
    return changed


def stamp_suites(bound, dry):
    changed = 0
    by_suite = {}
    for k, v in bound.items():
        if v.get("runner") == "suite":
            by_suite.setdefault(v["suite"], {})[v["stage"]] = (k, v)

    for suite, wanted in sorted(by_suite.items()):
        path = os.path.join(UI_REPO, "test_suite", "suites", f"{suite}.json")
        if not os.path.exists(path):
            print(f"   !! missing {path}")
            continue
        doc = json.load(open(path))
        touched = 0
        for block in ("LOGIN_TESTS",):
            for case in doc.get(block, []):
                hit = wanted.get(case.get("name"))
                if not hit:
                    continue
                key, v = hit
                tags = [t for t in (case.get("tags") or []) if not t.startswith("qase:")]
                tags.append(f"qase:{key}")
                if tags != case.get("tags"):
                    case["tags"] = tags
                    touched += 1
        if touched and not dry:
            with open(path, "w") as fh:
                json.dump(doc, fh, indent=2)
        if touched:
            print(f"   {suite}: {touched} case(s) tagged")
            changed += touched
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    amap = json.load(open(os.path.join(ROOT, "automation-map.json")))
    bound = {k: v for k, v in amap.items() if v.get("runner", "none") != "none"}
    print(f">> {len(bound)} bound case(s)")
    n = stamp_postman(bound, args.dry_run) + stamp_suites(bound, args.dry_run)
    print(f">> {n} script location(s) {'would be' if args.dry_run else ''} stamped".replace("  ", " "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
