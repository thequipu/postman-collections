#!/usr/bin/env python3
"""Say which test cases a report covers, after running a script directly.

    python3 scripts/show_cases.py reports/junit/SMOKE-Platform-Health.xml
    python3 scripts/show_cases.py ../automation_fast_api/test_suite/results/<suite>_<ts>.json
    python3 scripts/show_cases.py --latest            # newest report under reports/junit

Running a collection or a suite by hand is the normal way to debug one, but its
output speaks in request and stage names — nothing on screen says which Qase
case just passed. This reads the report the script already wrote and answers
that, without re-running anything or needing a Qase run to exist.

Accepts either shape: JUnit XML from the Postman CLI or pytest, and the JSON
report run_suite.py writes. --json prints the same flat records the pipeline
publishes, so a direct run and a Qase-triggered run are comparable.
"""
import argparse, glob, json, os, sys, xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP", "blocked": "BLOCK"}


def load_map():
    amap = json.load(open(os.path.join(ROOT, "automation-map.json")))
    return {k: v for k, v in amap.items() if v.get("runner", "none") != "none"}


def from_junit(path, bound):
    """Postman CLI and pytest both write JUnit; they differ in what a case is."""
    root = ET.parse(path).getroot()
    out = []

    # Postman: one <testsuite> per request, named "<folder> / <request>".
    suites = {ts.get("name"): ts for ts in root.iter("testsuite")}
    for key, v in bound.items():
        want = v.get("junit_suite")
        if want and want in suites:
            ts = suites[want]
            bad = int(ts.get("failures") or 0) + int(ts.get("errors") or 0)
            out.append((key, v, "failed" if bad else "passed",
                        round(float(ts.get("time") or 0) * 1000)))

    # pytest: one <testcase>, matched through the node id.
    cases = {}
    for tc in root.iter("testcase"):
        cases.setdefault((tc.get("classname"), (tc.get("name") or "").split("[")[0]), []).append(tc)
    for key, v in bound.items():
        nodeid = v.get("nodeid")
        if not nodeid:
            continue
        bits = nodeid.split("::")
        cls = bits[0][:-3].replace("/", ".") if bits[0].endswith(".py") else bits[0]
        if len(bits) > 2:
            cls += "." + ".".join(bits[1:-1])
        got = cases.get((cls, bits[-1]))
        if got:
            failed = any(tc.find("failure") is not None or tc.find("error") is not None for tc in got)
            out.append((key, v, "failed" if failed else "passed",
                        round(sum(float(tc.get("time") or 0) for tc in got) * 1000)))
    return out


def from_suite_report(path, bound):
    """The JSON run_suite.py writes: services, each with its own cases."""
    doc = json.load(open(path))
    stages = {s.get("stage"): s for svc in doc.get("stages", []) for s in svc.get("stages", [])}
    status = {"SUCCESS": "passed", "FAILED": "failed", "SKIPPED": "skipped"}
    out = []
    for key, v in bound.items():
        st = stages.get(v.get("stage"))
        if st and v.get("suite") == doc.get("suite"):
            out.append((key, v, status.get(st.get("status"), "blocked"),
                        round(st.get("duration_ms") or 0)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report", nargs="?", help="a JUnit .xml or a run_suite .json report")
    ap.add_argument("--latest", action="store_true", help="newest report under reports/junit")
    ap.add_argument("--json", action="store_true", help="print the pipeline's flat records")
    args = ap.parse_args()

    path = args.report
    if args.latest or not path:
        found = sorted(glob.glob(os.path.join(ROOT, "reports", "junit", "*.xml")),
                       key=os.path.getmtime)
        if not found:
            sys.exit("no report given and nothing under reports/junit")
        path = found[-1]
    if not os.path.exists(path):
        sys.exit(f"no such report: {path}")

    bound = load_map()
    rows = (from_suite_report(path, bound) if path.endswith(".json")
            else from_junit(path, bound))
    if not rows:
        sys.exit(f"!! {os.path.basename(path)} covers no case in automation-map.json\n"
                 "   Either nothing here is bound yet, or a request or stage was renamed.")

    rows.sort(key=lambda r: r[0])
    if args.json:
        recs = []
        for key, v, status, ms in rows:
            e = {"id": key, "status": status, "ms": ms, "qase_id": v["qase_id"]}
            if v.get("linear"):
                e["linear"] = v["linear"]
            recs.append(e)
        print(json.dumps(recs, indent=1))
        return 0

    print(f">> {os.path.basename(path)} — {len(rows)} case(s)")
    for key, v, status, ms in rows:
        linear = f"  {v['linear']}" if v.get("linear") else ""
        print(f"   [{MARK.get(status, status):<5}] {key:<10} qase:{v['qase_id']:<5}"
              f"{linear:<12} {ms:>6}ms  {v.get('title','')[:38]}")
    n = sum(1 for r in rows if r[2] == "passed")
    print(f">> {n} passed, {len(rows)-n} not passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
