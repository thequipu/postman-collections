#!/usr/bin/env python3
"""Snapshot the whole Qase workspace: every project, case, run and result.

    QASE_API_TOKEN=... python3 tools/fetch-workspace.py -o reports/workspace.json

Kept separate from build-dashboard.py so the slow part (hundreds of API calls)
runs once and the page can be rebuilt from the JSON without re-fetching.
"""
import argparse, json, os, re, sys, time, urllib.error, urllib.request
from datetime import date

BASE = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/") + "/v1"
TOKEN = os.environ.get("QASE_API_TOKEN") or ""
BUILD_FIELD_ID = int(os.environ.get("QASE_BUILD_FIELD_ID", "3"))

# run_suite.sh embeds the Linear key as [QTC-123]; a bare bracket is not an id.
LINEAR_ID = re.compile(r"\[([A-Z][A-Z0-9]+-\d+)\]")

_policy = {}


def get(path):
    req = urllib.request.Request(BASE + path, headers={"Token": TOKEN, "accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                # Plan tier is readable from the rate-limit policy: 150 rpm free, 600 teams, 1000 enterprise.
                if not _policy and r.headers.get("ratelimit-policy"):
                    _policy["raw"] = r.headers["ratelimit-policy"]
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:      # burst cap is 100 per 10s
                time.sleep(2 * (attempt + 1))
                continue
            sys.exit(f"Qase {e.code} on {path}: {e.read()[:200].decode('utf-8','replace')}")


def paged(path, key="entities"):
    out, offset = [], 0
    while True:
        sep = "&" if "?" in path else "?"
        batch = get(f"{path}{sep}limit=100&offset={offset}")["result"][key]
        out += batch
        if len(batch) < 100:
            return out
        offset += 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="reports/workspace.json")
    args = ap.parse_args()
    if not TOKEN:
        sys.exit("QASE_API_TOKEN is not set.")

    projects = paged("/project")
    users = paged("/user")
    snap = {"snapshot": date.today().isoformat(), "users": [], "projects": [],
            "cases": {}, "runs": [], "defects": []}

    for u in users:
        snap["users"].append({"title": u.get("title"), "email": u.get("email"),
                              "status": u.get("status")})

    for p in projects:
        code = p["code"]
        counts = p.get("counts") or {}
        snap["projects"].append({
            "code": code, "title": p["title"],
            "cases": counts.get("cases", 0), "suites": counts.get("suites", 0),
            "runs": (counts.get("runs") or {}).get("total", 0),
            "runs_active": (counts.get("runs") or {}).get("active", 0),
            "defects": (counts.get("defects") or {}).get("total", 0),
            "milestones": counts.get("milestones", 0),
        })

        suites = {s["id"]: s for s in paged(f"/suite/{code}")}

        def crumbs(suite):
            names, node = [suite["title"]], suite
            while node.get("parent_id") in suites:
                node = suites[node["parent_id"]]
                names.insert(0, node["title"])
            return names

        # Qase sends automation as an int; the query language reads better with words.
        AUTOMATION = {0: "manual", 1: "to-be-automated", 2: "automated"}

        for c in paged(f"/case/{code}"):
            path = crumbs(suites[c["suite_id"]]) if c.get("suite_id") in suites else ["Unassigned"]
            desc = c.get("description") or ""
            snap["cases"][f"{code}:{c['id']}"] = {
                "project": code,
                "linear": (LINEAR_ID.search(desc) or [None, None])[1],
                "title": c["title"],
                "area": path[0],
                "feature": path[1] if len(path) > 1 else "",
                "cat": path[-1] if len(path) > 2 else "",
                "automation": AUTOMATION.get(c.get("automation"), "manual"),
                "priority": c.get("priority"),
                "suite": " ▸ ".join(path),
            }

        for r in paged(f"/run/{code}"):
            detail = get(f"/run/{code}/{r['id']}?include=cases")["result"]
            results = {}
            for e in paged(f"/result/{code}?run={r['id']}"):
                if e.get("case_id"):
                    results[f"{code}:{e['case_id']}"] = {"status": e.get("status"),
                                                         "comment": e.get("comment")}
            build = next((f.get("value") for f in (r.get("custom_fields") or [])
                          if f.get("id") == BUILD_FIELD_ID), None)
            snap["runs"].append({
                "project": code, "id": r["id"], "title": r["title"], "build": build,
                "status": r["status_text"],
                "start": (r.get("start_time") or "")[:16].replace("T", " "),
                "end": (r.get("end_time") or "")[:16].replace("T", " "),
                "cases": [f"{code}:{c}" for c in (detail.get("cases") or [])],
                "results": results,
            })

        for d in paged(f"/defect/{code}"):
            snap["defects"].append({"project": code, "id": d["id"], "title": d.get("title"),
                                    "status": d.get("status")})

    snap["runs"].sort(key=lambda r: (r["project"], r["id"]))
    snap["ratelimit_policy"] = _policy.get("raw", "")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(snap, fh, separators=(",", ":"))
    print(f">> {args.out}: {len(snap['projects'])} projects, {len(snap['cases'])} cases, "
          f"{len(snap['runs'])} runs, {len(snap['defects'])} defects")
    print(f"   rate-limit policy: {snap['ratelimit_policy']}")


if __name__ == "__main__":
    main()
