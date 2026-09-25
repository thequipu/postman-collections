#!/usr/bin/env python3
"""Publish reports/results.json to a Qase run, and verify it actually landed.

    QASE_RUN_ID=24 QASE_API_TOKEN=... python3 scripts/publish_results.py

Why this is not one bulk POST: on 2026-09-25 Qase's
`/v1/result/{code}/{run}/bulk` began returning HTTP 200 `{"status":true}` and
recording nothing. A Jenkins build reported "published 14 results: HTTP 200"
against a run that stayed empty — the worst kind of failure, because it looks
like success. The single-result endpoint worked for the identical payload.

So: try bulk once (cheap, and it will be the fast path again when Qase fixes
it), then read the run back and post anything still missing one at a time.
The run's own recorded state is the only thing trusted here, never a status
code. Exits non-zero if any result could not be confirmed.
"""
import json, os, sys, time, urllib.error, urllib.request

BASE = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/") + "/v1"
CODE = os.environ.get("QASE_PROJECT_CODE", "")
RUN = os.environ.get("QASE_RUN_ID", "")
TOKEN = os.environ.get("QASE_API_TOKEN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.environ.get("RESULTS", os.path.join(ROOT, "reports", "results.json"))
CASE_MAP = os.environ.get("CASE_MAP", os.path.join(ROOT, "qase-case-map.json"))

STATUS = {"passed": "passed", "pass": "passed", "failed": "failed", "fail": "failed",
          "skipped": "skipped", "skip": "skipped", "blocked": "blocked", "error": "failed"}


def call(method, path, payload=None):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode() if payload is not None else None,
        method=method, headers={"Token": TOKEN, "accept": "application/json",
                                "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"status": False, "errorMessage": f"HTTP {e.code}: "
                f"{e.read()[:200].decode('utf-8', 'replace')}"}


def recorded_cases():
    """case_ids that the run has actually recorded a result for."""
    seen, offset = set(), 0
    while True:
        d = call("GET", f"/result/{CODE}?run={RUN}&limit=100&offset={offset}")
        if not d.get("status"):
            return seen
        ents = d["result"]["entities"]
        seen |= {e["case_id"] for e in ents if e.get("case_id")}
        if len(ents) < 100:
            return seen
        offset += 100


def main():
    for name, val in (("QASE_PROJECT_CODE", CODE), ("QASE_RUN_ID", RUN), ("QASE_API_TOKEN", TOKEN)):
        if not val:
            sys.exit(f"{name} is not set")

    results = json.load(open(RESULTS))
    cmap = json.load(open(CASE_MAP))
    in_run = set(call("GET", f"/run/{CODE}/{RUN}?include=cases")["result"].get("cases") or [])

    payload, by_case = [], {}
    for r in results:
        cid = cmap.get(r["id"])
        if not cid or (in_run and cid not in in_run):
            continue                      # never publish outside the run's own scope
        entry = {"case_id": cid, "status": STATUS.get(r["status"], "skipped"),
                 "time_ms": int(r.get("ms") or 0)}
        comment = r.get("error") or r.get("reason")
        if comment:
            entry["comment"] = str(comment)[:5000]
        payload.append(entry)
        by_case[cid] = entry

    if not payload:
        print(">> nothing to publish for this run")
        return 0
    print(f">> publishing {len(payload)} result(s) to run {RUN}")

    before = recorded_cases()
    bulk = call("POST", f"/result/{CODE}/{RUN}/bulk", {"results": payload})
    landed = recorded_cases() - before
    if landed:
        print(f"   bulk recorded {len(landed)}")
    elif bulk.get("status"):
        # Accepted and discarded. Not an error we can see, only one we can measure.
        print("   bulk reported success but recorded nothing — posting individually")
    else:
        print(f"   bulk refused ({bulk.get('errorMessage')}) — posting individually")

    missing = [c for c in by_case if c not in recorded_cases()]
    for i, cid in enumerate(missing, 1):
        d = call("POST", f"/result/{CODE}/{RUN}", by_case[cid])
        if not d.get("status"):
            print(f"   !! case {cid}: {d.get('errorMessage')}")
        if i % 50 == 0:
            time.sleep(2)                 # stay under the 100-per-10s burst cap

    final = recorded_cases()
    ok = [c for c in by_case if c in final]
    lost = [c for c in by_case if c not in final]
    print(f">> run {RUN}: {len(ok)}/{len(by_case)} result(s) confirmed on the run")
    if lost:
        print(f"!! {len(lost)} result(s) never landed: {sorted(lost)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
