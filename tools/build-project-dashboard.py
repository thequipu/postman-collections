#!/usr/bin/env python3
"""Build the project-health page for one Qase project.

    QASE_API_TOKEN=... python3 tools/build-project-dashboard.py [-o reports/project.html]

Qase's own dashboards cannot show this: its result index returns nothing for
this workspace (354 verdicts, `entity = "result"` -> 0), so every result-based
widget there renders empty. This reads /v1/result directly instead.

It answers project-level questions rather than per-run ones — how much of the
suite is actually wired to a script, which cases fail persistently rather than
once, and how the pass rate moves build over build.
"""
import argparse, json, os, subprocess, sys, urllib.error, urllib.request
from datetime import date

BASE = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/") + "/v1"
CODE = os.environ.get("QASE_PROJECT_CODE", "QQA")
TOKEN = os.environ.get("QASE_API_TOKEN") or ""
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))


def get(path):
    req = urllib.request.Request(BASE + path, headers={"Token": TOKEN, "accept": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
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
    ap.add_argument("-o", "--out", default="reports/project.html")
    args = ap.parse_args()
    if not TOKEN:
        sys.exit("QASE_API_TOKEN is not set.")

    suites = {s["id"]: s for s in paged(f"/suite/{CODE}")}

    def crumbs(s):
        names, node = [s["title"]], s
        while node.get("parent_id") in suites:
            node = suites[node["parent_id"]]
            names.insert(0, node["title"])
        return " ▸ ".join(names)

    import re
    KEY = re.compile(r"\[([A-Z][A-Z0-9]+-\d+)\]")
    cases = {}
    for c in paged(f"/case/{CODE}"):
        m = KEY.search(c.get("description") or "")
        key = m[1] if m else f"case-{c['id']}"
        cases[key] = {"qase_id": c["id"], "title": c["title"],
                      "suite": crumbs(suites[c["suite_id"]]) if c.get("suite_id") in suites else "?",
                      "linear": None}

    # The automation map is what actually decides whether a case can run at all.
    amap = json.load(open(os.path.join(ROOT, "automation-map.json")))
    bound = {k: True for k, v in amap.items() if v.get("runner", "none") != "none"}
    for k, v in amap.items():
        if k in cases and v.get("linear"):
            cases[k]["linear"] = v["linear"]

    runs = []
    for r in paged(f"/run/{CODE}"):
        results = {}
        for e in paged(f"/result/{CODE}?run={r['id']}"):
            if not e.get("case_id"):
                continue
            key = next((k for k, c in cases.items() if c["qase_id"] == e["case_id"]), None)
            if key:
                results[key] = {"status": e.get("status"), "comment": e.get("comment") or ""}
        build = next((f.get("value") for f in (r.get("custom_fields") or []) if f.get("id") == 3), None)
        runs.append({"id": r["id"], "title": r["title"], "build": build,
                     "start": (r.get("start_time") or "")[:16].replace("T", " "),
                     "end": (r.get("end_time") or "")[:16].replace("T", " "),
                     "results": results})
    runs.sort(key=lambda r: r["id"])

    plans = [{"title": p["title"], "cases_count": p["cases_count"]} for p in paged(f"/plan/{CODE}")]

    payload = {"cases": cases, "runs": runs, "bound": bound, "plans": plans,
               "snapshot": date.today().isoformat()}
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")

    tpl = open(os.path.join(HERE, "project.tpl.html")).read()
    if "/*__DATA__*/" not in tpl:
        sys.exit("project.tpl.html has no /*__DATA__*/ placeholder")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        fh.write(tpl.replace("/*__DATA__*/", blob))

    verdicts = sum(1 for r in runs for v in r["results"].values()
                   if v["status"] in ("passed", "failed", "blocked"))
    print(f">> {args.out}: {len(cases)} cases, {len(bound)} wired, {len(runs)} runs, {verdicts} verdicts")


if __name__ == "__main__":
    main()
