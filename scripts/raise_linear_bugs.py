#!/usr/bin/env python3
"""Raise a Linear issue for every case that failed, and link it to the case.

    LINEAR_API_KEY=... QASE_RUN_ID=31 python3 scripts/raise_linear_bugs.py [--dry-run]

Reads reports/results.json. For each failed or blocked case it finds the issue
already tracking that failure and comments on it, or opens a new one. It never
opens a second issue for a failure already being tracked — four services have
been down all day, and a build every hour would otherwise file four issues an
hour.

Identity is a marker in the issue description, `[qase-case:<id>]`, searched for
rather than stored anywhere: nothing here needs a database, and an issue someone
moves or renames is still found.

Where the bug is filed:
  - a case mirrored from Linear (its key is a real issue, e.g. QTC-441) gets the
    bug as a SUB-ISSUE of that test case, so the case and its defect stay linked
  - a case that exists only in Qase (QAPI-*, QUI-*) gets a top-level issue in the
    same team, since there is no parent to hang it from

Team, state and labels are resolved by name at run time, so no ids are baked in.
"""
import argparse, json, os, sys, urllib.error, urllib.request

API = "https://api.linear.app/graphql"
KEY = os.environ.get("LINEAR_API_KEY", "")
TEAM_KEY = os.environ.get("LINEAR_TEAM_KEY", "QTC")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.environ.get("RESULTS", os.path.join(ROOT, "reports", "results.json"))
BUILD = os.environ.get("BUILD", "")
RUN_ID = os.environ.get("QASE_RUN_ID", "")
PROJECT_CODE = os.environ.get("QASE_PROJECT_CODE", "QQA")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "")
BUILD_URL = os.environ.get("BUILD_URL", "")          # Jenkins sets this
MARKER = "qase-case"


def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=body, method="POST",
                                 headers={"Authorization": KEY,
                                          "Content-Type": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Linear HTTP {e.code}: {e.read()[:300].decode('utf-8','replace')}")
    if d.get("errors"):
        sys.exit(f"Linear error: {json.dumps(d['errors'])[:400]}")
    return d["data"]


def team():
    d = gql("""query($key:String!){ teams(filter:{key:{eq:$key}}, first:1){ nodes{
                 id key name
                 labels(first:100){ nodes{ id name } }
                 states(first:50){ nodes{ id name type } } } } }""", {"key": TEAM_KEY})
    nodes = d["teams"]["nodes"]
    if not nodes:
        sys.exit(f"no Linear team with key {TEAM_KEY!r}")
    return nodes[0]


def find_issue(case_id):
    """The issue already tracking this case's failure, open or closed."""
    d = gql("""query($q:String!){ searchIssues(term:$q, first:10){ nodes{
                 id identifier title url description
                 state{ name type } } } }""", {"q": f"[{MARKER}:{case_id}]"})
    for n in d["searchIssues"]["nodes"]:
        if f"[{MARKER}:{case_id}]" in (n.get("description") or ""):
            return n
    return None


def issue_by_identifier(ident):
    """Resolve e.g. QTC-441 to an issue id, so a bug can be its sub-issue."""
    try:
        num = int(ident.split("-")[1])
    except (IndexError, ValueError):
        return None
    d = gql("""query($key:String!,$n:Float!){ issues(filter:{
                 team:{key:{eq:$key}}, number:{eq:$n}}, first:1){ nodes{ id identifier } } }""",
            {"key": ident.split("-")[0], "n": num})
    nodes = d["issues"]["nodes"]
    return nodes[0]["id"] if nodes else None


def context_lines(key, entry, result):
    run_url = f"https://app.qase.io/run/{PROJECT_CODE}/dashboard/{RUN_ID}" if RUN_ID else ""
    lines = [f"**Case** `{key}` — {entry.get('title', '')}",
             f"**Runner** `{entry.get('runner', '?')}`"]
    if ENVIRONMENT:
        lines.append(f"**Environment** `{ENVIRONMENT}`")
    if BUILD:
        lines.append(f"**Build** `{BUILD}`")
    if run_url:
        lines.append(f"**Qase run** {run_url}")
    if BUILD_URL:
        lines.append(f"**Jenkins** {BUILD_URL}")
    err = result.get("error") or result.get("reason") or ""
    if err:
        lines += ["", "```", err[:2000], "```"]
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be filed, touch nothing")
    args = ap.parse_args()
    if not KEY and not args.dry_run:
        sys.exit("LINEAR_API_KEY is not set")

    results = json.load(open(RESULTS))
    amap = json.load(open(os.path.join(ROOT, "automation-map.json")))
    failures = [r for r in results if r["status"] in ("failed", "blocked")]
    if not failures:
        print(">> no failures — nothing to file")
        return 0
    print(f">> {len(failures)} failing case(s)")

    if args.dry_run:
        for r in failures:
            e = amap.get(r["id"], {})
            parent = r["id"] if r["id"].startswith("QTC-") else "(no parent — Qase-only case)"
            print(f"   {r['id']:<10} {e.get('title','')[:40]:<42} parent: {parent}")
            print(f"      {(r.get('error') or r.get('reason') or '')[:90]}")
        return 0

    t = team()
    labels = {n["name"].lower(): n["id"] for n in t["labels"]["nodes"]}
    bug_label = next((labels[n] for n in ("bug", "🐛 bug", "defect") if n in labels), None)
    states = {n["name"].lower(): n for n in t["states"]["nodes"]}
    todo = next((states[n]["id"] for n in ("todo", "test todo", "backlog") if n in states), None)

    filed = {}          # case key -> {identifier, url}, written for the publisher
    opened = commented = 0
    for r in failures:
        key = r["id"]
        entry = amap.get(key, {})
        case_id = entry.get("qase_id", key)
        body = "\n".join(context_lines(key, entry, r))
        existing = find_issue(case_id)

        if existing:
            gql("""mutation($id:String!,$body:String!){
                     commentCreate(input:{issueId:$id, body:$body}){ success } }""",
                {"id": existing["id"], "body": f"Still failing.\n\n{body}"})
            # A bug that was closed and is failing again belongs back on the board.
            if existing["state"]["type"] in ("completed", "canceled") and todo:
                gql("""mutation($id:String!,$s:String!){
                         issueUpdate(id:$id, input:{stateId:$s}){ success } }""",
                    {"id": existing["id"], "s": todo})
                print(f"   {key}: reopened {existing['identifier']}")
            else:
                print(f"   {key}: commented on {existing['identifier']}")
            filed[key] = {"identifier": existing["identifier"], "url": existing["url"]}
            commented += 1
            continue

        payload = {
            "teamId": t["id"],
            "title": f"{entry.get('title', key)} is failing"[:250],
            "description": f"[{MARKER}:{case_id}] Filed automatically from a test run.\n\n" + body,
        }
        if bug_label:
            payload["labelIds"] = [bug_label]
        if key.startswith("QTC-"):
            pid = issue_by_identifier(key)
            if pid:
                payload["parentId"] = pid          # the bug hangs off its test case
        d = gql("""mutation($i:IssueCreateInput!){ issueCreate(input:$i){
                     success issue{ identifier url } } }""", {"i": payload})
        iss = d["issueCreate"]["issue"]
        filed[key] = {"identifier": iss["identifier"], "url": iss["url"]}
        print(f"   {key}: opened {iss['identifier']} {iss['url']}")
        opened += 1

    # publish_results.py reads this and names the defect on the failing result,
    # so the link is visible from the Qase side too, not only from Linear.
    out = os.path.join(ROOT, "reports", "linear-bugs.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(filed, open(out, "w"), indent=1, sort_keys=True)
    print(f">> {opened} opened, {commented} updated — wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
