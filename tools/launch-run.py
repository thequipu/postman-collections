#!/usr/bin/env python3
"""Create a Qase run from a plan and start the Jenkins job against it.

    QASE_API_TOKEN=... JENKINS_USER=... JENKINS_TOKEN=... \
      python3 tools/launch-run.py --plan "Release verification"

Stands in for Qase's own Launch button, which returns HTTP 500 without creating
a run: its UI posts a run with no `title`, which the Qase API itself rejects.
This does the same two things in the same order the button should - create the
run from a plan, then trigger the job carrying that run's id - so scope still
comes from the run (scripts/resolve_scope.py) and results land back on it.

Environment:
    QASE_API_TOKEN      required
    QASE_PROJECT_CODE   default QQA
    QASE_API_BASE_URL   default https://api.qase.io
    JENKINS_URL         default https://jenkins-prod.thequipu.in
    JENKINS_USER        required
    JENKINS_TOKEN       required - a Jenkins API token, not a password

Exits non-zero if the run cannot be created, comes back empty, or the job
refuses the trigger. An empty run would execute nothing, so it is refused here
rather than producing a green build that tested nothing.
"""
import argparse, base64, http.cookiejar, json, os, sys
import urllib.error, urllib.parse, urllib.request
from datetime import date

QASE = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/") + "/v1"
CODE = os.environ.get("QASE_PROJECT_CODE", "QQA")
TOKEN = os.environ.get("QASE_API_TOKEN") or ""
JENKINS = os.environ.get("JENKINS_URL", "https://jenkins-prod.thequipu.in").rstrip("/")
JUSER = os.environ.get("JENKINS_USER") or ""
JTOKEN = os.environ.get("JENKINS_TOKEN") or ""


def qase(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(QASE + path, data=data, method=method,
                                 headers={"Token": TOKEN, "accept": "application/json",
                                          "content-type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Qase {e.code} on {method} {path}: {e.read()[:300].decode('utf-8', 'replace')}")


# One opener for the process, so the crumb's session cookie survives to the POST.
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def jenkins(path, data=None, headers=None):
    """Returns (status, headers, body). Never raises on an HTTP error status.

    Authorization is sent preemptively: urllib's auth handler waits for a 401
    challenge, so the first POST would arrive anonymous and Jenkins rejects it
    for a missing crumb before it ever asks who we are.
    """
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    h = dict(headers or {})
    h["Authorization"] = "Basic " + base64.b64encode(f"{JUSER}:{JTOKEN}".encode()).decode()
    req = urllib.request.Request(JENKINS + path, data=body,
                                 method="POST" if data is not None else "GET", headers=h)
    try:
        r = _OPENER.open(req, timeout=60)
        return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def find_plan(want):
    plans = qase("GET", f"/plan/{CODE}?limit=100")["result"]["entities"]
    if want.isdigit():
        hit = next((p for p in plans if str(p["id"]) == want), None)
    else:
        hit = next((p for p in plans if p["title"].lower() == want.lower()), None)
    if not hit:
        names = ", ".join(f'{p["id"]}:{p["title"]}' for p in plans)
        sys.exit(f"no plan matching {want!r}. Available: {names}")
    return hit


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--plan", help="plan title or id, e.g. 'Release verification'")
    src.add_argument("--run", type=int, help="start an existing run instead of creating one")
    ap.add_argument("--title", help="run title (default: '<plan> — <today>')")
    ap.add_argument("--job", default="qase-release-verification")
    ap.add_argument("--environment", default="onprem")
    ap.add_argument("--mode", default="real", choices=["real", "smoke", "simulate"])
    ap.add_argument("--build-endpoint", default="",
                    help="URL returning the build; stamped on the run. A bare version string is not a URL.")
    ap.add_argument("--no-complete", action="store_true", help="leave the run open after the build")
    ap.add_argument("--dry-run", action="store_true", help="resolve the plan and print, create nothing")
    args = ap.parse_args()

    if not TOKEN:
        sys.exit("QASE_API_TOKEN is not set")

    if args.run:
        run = qase("GET", f"/run/{CODE}/{args.run}")["result"]
        run_id, total = run["id"], run["stats"]["total"]
        print(f">> run {run_id}: {run['title']} ({total} cases, {run.get('status_text')})")
        if args.dry_run:
            print(f">> would trigger {args.job} (env={args.environment} mode={args.mode})")
            return 0
    else:
        plan = find_plan(args.plan)
        title = args.title or f"{plan['title']} — {date.today().isoformat()}"
        print(f">> plan {plan['id']}: {plan['title']} ({plan.get('cases_count', '?')} cases)")
        if args.dry_run:
            print(f">> would create run {title!r} and trigger {args.job} "
                  f"(env={args.environment} mode={args.mode})")
            return 0
        run_id = qase("POST", f"/run/{CODE}", {"title": title, "plan_id": plan["id"]})["result"]["id"]
        total = qase("GET", f"/run/{CODE}/{run_id}")["result"]["stats"]["total"]
        print(f">> created run {run_id}: {title} ({total} cases)")

    if not total:
        sys.exit(f"!! run {run_id} holds no cases - it would execute nothing.")

    if not (JUSER and JTOKEN):
        sys.exit("JENKINS_USER and JENKINS_TOKEN are not set - run created but not started")

    # An API token needs no crumb; a password does. Send one when the issuer offers it.
    headers = {}
    status, _, body = jenkins("/crumbIssuer/api/json")
    if status == 200:
        c = json.loads(body)
        headers[c["crumbRequestField"]] = c["crumb"]

    params = {"QASE_PROJECT_CODE": CODE, "QASE_RUN_ID": str(run_id),
              "QASE_REPORT": "true", "QASE_RUN_COMPLETE": "false" if args.no_complete else "true",
              "MODE": args.mode, "ENVIRONMENT": args.environment}
    if args.build_endpoint:
        params["BUILD_ENDPOINT"] = args.build_endpoint

    status, hdrs, body = jenkins(f"/job/{args.job}/buildWithParameters", params, headers)
    if status != 201:
        sys.exit(f"!! Jenkins refused the trigger: HTTP {status} {body[:200]}\n"
                 f"   run {run_id} exists but was not started.")

    print(f">> queued: {hdrs.get('Location', '?')}")
    print(f">> run {run_id} will fill in as results are published")
    return 0


if __name__ == "__main__":
    sys.exit(main())
