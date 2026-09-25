#!/usr/bin/env python3
"""Build the QQA run dashboard from live Qase data.

    QASE_API_TOKEN=... python3 tools/build-dashboard.py [-o reports/dashboard.html]

Writes a self-contained HTML file: every run in the project, its suite-level
breakdown, its failures, and pass rate per feature across builds. Publish it
wherever you like -- it needs no network once written.
"""
import argparse, json, os, re, sys, urllib.error, urllib.request
from datetime import date

BASE = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/") + "/v1"
CODE = os.environ.get("QASE_PROJECT_CODE", "QQA")
TOKEN = os.environ.get("QASE_API_TOKEN") or ""
HERE = os.path.dirname(os.path.abspath(__file__))

# Qase stamps the build onto this run custom field; keep in sync with Jenkinsfile.qase.
BUILD_FIELD_ID = int(os.environ.get("QASE_BUILD_FIELD_ID", "3"))

# run_suite.sh embeds the Linear key as [QTC-123]; a bare bracket is not an id.
LINEAR_ID = re.compile(r"\[([A-Z][A-Z0-9]+-\d+)\]")


def get(path):
    req = urllib.request.Request(BASE + path, headers={"Token": TOKEN, "accept": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Qase {e.code} on {path}: {e.read()[:200].decode('utf-8', 'replace')}")


def paged(path, key="entities"):
    """Qase caps a page at 100; walk until short."""
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
    ap.add_argument("-o", "--out", default="reports/dashboard.html")
    args = ap.parse_args()
    if not TOKEN:
        sys.exit("QASE_API_TOKEN is not set.")

    suites = {s["id"]: s for s in paged(f"/suite/{CODE}")}

    def path_of(suite):
        names, node = [suite["title"]], suite
        while node.get("parent_id") in suites:
            node = suites[node["parent_id"]]
            names.insert(0, node["title"])
        return names

    cases = {}
    for c in paged(f"/case/{CODE}"):
        crumbs = path_of(suites[c["suite_id"]]) if c.get("suite_id") in suites else ["Unassigned"]
        desc = c.get("description") or ""
        cases[str(c["id"])] = {
            # run_suite.sh embeds the Linear id as [QTC-nnn] in the description
            "linear": (LINEAR_ID.search(desc) or [None, None])[1],
            "title": c["title"],
            "area": crumbs[0],
            "feature": crumbs[1] if len(crumbs) > 1 else "",
            "cat": crumbs[-1] if len(crumbs) > 2 else "",
        }

    runs = []
    for r in paged(f"/run/{CODE}"):
        detail = get(f"/run/{CODE}/{r['id']}?include=cases")["result"]
        results = {}
        for e in paged(f"/result/{CODE}?run={r['id']}"):
            if e.get("case_id"):
                results[str(e["case_id"])] = {"status": e.get("status"), "comment": e.get("comment")}
        build = next((f.get("value") for f in (r.get("custom_fields") or [])
                      if f.get("id") == BUILD_FIELD_ID), None)
        runs.append({
            "id": r["id"], "title": r["title"], "build": build, "status": r["status_text"],
            "start": (r.get("start_time") or "")[:16].replace("T", " "),
            "end": (r.get("end_time") or "")[:16].replace("T", " "),
            "cases": [str(c) for c in (detail.get("cases") or [])],
            "results": results,
        })
    runs.sort(key=lambda r: r["id"])

    payload = json.dumps({"cases": cases, "runs": runs, "snapshot": date.today().isoformat()},
                         separators=(",", ":"))
    # A literal </script> inside the JSON would close the script block and blank the page.
    payload = payload.replace("</", "<\\/")

    with open(os.path.join(HERE, "dashboard.tpl.html")) as fh:
        html = fh.read()
    if "/*__DATA__*/" not in html:
        sys.exit("dashboard.tpl.html has no /*__DATA__*/ placeholder.")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        fh.write(html.replace("/*__DATA__*/", payload))

    verdicts = sum(1 for r in runs for v in r["results"].values()
                   if v["status"] in ("passed", "failed", "blocked"))
    print(f">> {args.out}: {len(runs)} runs, {len(cases)} cases, {verdicts} verdicts")


if __name__ == "__main__":
    main()
