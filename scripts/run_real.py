#!/usr/bin/env python3
"""Execute the automation bound to the cases in scope and report one line per case.

Called by run_suite.sh for MODE=real. Reads reports/scope.json (already filtered
to the Qase run's cases) and writes, on stdout, the line format run_suite.sh
serialises:

    <case-key> <passed|failed|skipped|blocked> <ms> [message]

Each case names its runner and where to find itself in that runner's JUnit
report, so selecting cases in Qase decides what actually executes:

    "runner": "postman", "collection": "FLOW-Qase-Basic",
                        "junit_suite": "Qase Basic / 01 Admin Login"
    "runner": "pytest", "nodeid": "tests/test_smoke.py::test_smoke"

A bound case that the runner never reported comes back `blocked`, never passed —
a silent gap must not read as success.
"""
import json, os, shutil, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JUNIT_DIR = ROOT / "reports" / "junit"
ENVIRONMENT = os.environ.get("ENVIRONMENT", "onprem")
UI_REPO = Path(os.environ.get("UI_REPO", ROOT.parent / "automation_fast_api"))
UI_DOCKER_IMAGE = os.environ.get("UI_DOCKER_IMAGE", "")   # empty = use the local interpreter
TIMEOUT = int(os.environ.get("RUNNER_TIMEOUT", "900"))

# Postman variable name <- environment variable. Secrets never live in the collection.
ENV_VAR_MAP = {
    "client_secret": "CLIENT_SECRET",
    "test_username": "TEST_USERNAME",
    "test_password": "TEST_PASSWORD",
    "adminUsername": "ADMIN_USERNAME",
    "adminPassword": "ADMIN_PASSWORD",
}


def emit(key, status, ms=0, msg=""):
    print(f"{key} {status} {int(ms)}{(' ' + msg) if msg else ''}", flush=True)


def run(cmd, cwd):
    """Run a command, never raise. Returns (exit_code, combined_output)."""
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=TIMEOUT)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"runner exceeded {TIMEOUT}s"
    except FileNotFoundError as e:
        return 127, str(e)


# --------------------------------------------------------------- postman -----
def postman(cases):
    """cases: {key: entry} for runner == postman.

    The Postman CLI, not newman. Its JUnit output is byte-for-byte compatible in
    the part that matters — <testsuite name="<folder> / <request>"> — verified
    against newman on SMOKE-Platform-Health: same 12 names, same verdicts.
    """
    exe = shutil.which("postman")
    if not exe:
        for k in cases:
            emit(k, "blocked", 0, "the postman CLI is not installed on this agent")
        return

    envfile = ROOT / "environments" / f"{ENVIRONMENT}.postman_environment.json"
    if not envfile.exists():
        for k in cases:
            emit(k, "blocked", 0, f"no environment file for '{ENVIRONMENT}'")
        return

    by_collection = {}
    for k, v in cases.items():
        by_collection.setdefault(v["collection"], {})[k] = v

    for collection, members in sorted(by_collection.items()):
        path = ROOT / "flows" / f"{collection}.postman_collection.json"
        if not path.exists():
            for k in members:
                emit(k, "blocked", 0, f"collection {collection} not found")
            continue

        report = JUNIT_DIR / f"{collection}.xml"
        report.unlink(missing_ok=True)          # never read a previous build's report
        cmd = [exe, "collection", "run", str(path), "-e", str(envfile), "--insecure",
               "-r", "cli,junit", "--reporter-junit-export", str(report),
               "--timeout-request", "120000"]
        for pm_var, env_var in ENV_VAR_MAP.items():
            if os.environ.get(env_var):
                cmd += ["--env-var", f"{pm_var}={os.environ[env_var]}"]

        print(f">> postman {collection} against {ENVIRONMENT}", file=sys.stderr)
        code, out = run(cmd, ROOT)
        if not report.exists():
            tail = " | ".join(out.strip().splitlines()[-3:])[:300] or f"exit {code}"
            for k in members:
                emit(k, "blocked", 0, f"postman produced no report: {tail}")
            continue
        report_suites(report, members, "junit_suite")


def report_suites(report, members, locator_key):
    """Map JUnit <testsuite name=...> back onto the cases that named it."""
    try:
        root = ET.parse(report).getroot()
    except ET.ParseError as e:
        for k in members:
            emit(k, "blocked", 0, f"unreadable JUnit report: {e}")
        return

    found = {}
    for ts in root.iter("testsuite"):
        failures = int(ts.get("failures") or 0) + int(ts.get("errors") or 0)
        names = [tc.get("name") or "" for tc in ts.iter("testcase")]
        # The flows' skip guard emits a PASSING assertion named "SKIPPED: ..." when an
        # earlier step failed. Zero failures there means "never ran", not "passed".
        skipped = bool(names) and all(n.startswith("SKIPPED:") for n in names)
        msg = ""
        if failures:
            node = ts.find(".//failure")
            if node is None:
                node = ts.find(".//error")
            if node is not None:
                msg = (node.get("message") or node.text or "").strip().replace("\n", " ")[:300]
        elif skipped:
            msg = names[0][:300]
        found[ts.get("name")] = (failures, skipped, len(names),
                                 float(ts.get("time") or 0) * 1000, msg)

    for key, entry in sorted(members.items()):
        want = entry.get(locator_key)
        if want not in found:
            emit(key, "blocked", 0, f"the runner reported no result for '{want}'")
            continue
        failures, skipped, n_assertions, ms, msg = found[want]
        if failures:
            emit(key, "failed", ms, msg or f"{failures} assertion(s) failed")
        elif skipped:
            emit(key, "skipped", ms, msg or "an earlier step in the flow failed")
        elif n_assertions == 0:
            # A request with no assertions proves nothing; don't let it read as green.
            emit(key, "blocked", ms, "the step ran but asserted nothing")
        else:
            emit(key, "passed", ms)


# ---------------------------------------------------------------- pytest -----
def nodeid_parts(nodeid):
    """tests/a.py::Cls::test_x -> ('tests.a.Cls', 'test_x') — pytest's JUnit shape."""
    bits = nodeid.split("::")
    classname = bits[0][:-3].replace("/", ".") if bits[0].endswith(".py") else bits[0]
    if len(bits) > 2:
        classname += "." + ".".join(bits[1:-1])
    return classname, bits[-1]


def pytest(cases):
    if not UI_REPO.exists():
        for k in cases:
            emit(k, "blocked", 0, f"UI repo not present at {UI_REPO}")
        return

    report = JUNIT_DIR / "pytest.xml"
    report.unlink(missing_ok=True)
    nodeids = sorted({v["nodeid"] for v in cases.values()})
    # Named node ids only. A bare `pytest` here would pull in tests that hit shared
    # preprod with committed credentials, and one that truncates a checked-in fixture.
    args = ["-m", "pytest", *nodeids, "-p", "no:cacheprovider", "-q"]

    if UI_DOCKER_IMAGE:
        # Ubuntu 20.04 ships python3.8 and Playwright needs >=3.10, so the UI tests
        # run in the Playwright image instead of on the agent's interpreter.
        inner = UI_REPO / ".junit-pytest.xml"
        inner.unlink(missing_ok=True)
        cmd = ["docker", "run", "--rm",
               "-u", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp"]
        for var in ("APP_URL",):          # which app the UI tests point at
            if os.environ.get(var):
                cmd += ["-e", f"{var}={os.environ[var]}"]
        cmd += ["-v", f"{UI_REPO}:/work", "-w", "/work", UI_DOCKER_IMAGE,
                "python", *args, "--junitxml=/work/.junit-pytest.xml"]
        print(f">> pytest in {UI_DOCKER_IMAGE}: {' '.join(nodeids)}", file=sys.stderr)
        code, out = run(cmd, ROOT)
        if inner.exists():
            shutil.copyfile(inner, report)
    else:
        python = UI_REPO / "venv" / "bin" / "python"
        python = str(python) if python.exists() else sys.executable
        cmd = [python, *args, f"--junitxml={report}"]
        print(f">> pytest {' '.join(nodeids)}", file=sys.stderr)
        code, out = run(cmd, UI_REPO)

    if not report.exists():
        tail = " | ".join(out.strip().splitlines()[-3:])[:300] or f"exit {code}"
        for k in cases:
            emit(k, "blocked", 0, f"pytest produced no report: {tail}")
        return

    try:
        root = ET.parse(report).getroot()
    except ET.ParseError as e:
        for k in cases:
            emit(k, "blocked", 0, f"unreadable JUnit report: {e}")
        return

    # pytest-playwright parametrises by browser, so one node id can yield several
    # testcases (test_smoke[chromium], [firefox], ...). Collect them all and fold.
    found = {}
    for tc in root.iter("testcase"):
        bad = tc.find("failure")
        if bad is None:
            bad = tc.find("error")
        skip = tc.find("skipped")
        ms = float(tc.get("time") or 0) * 1000
        if bad is not None:
            state = ("failed", (bad.get("message") or bad.text or "").strip().replace("\n", " ")[:300])
        elif skip is not None:
            state = ("skipped", (skip.get("message") or "skipped by pytest")[:300])
        else:
            state = ("passed", "")
        base = (tc.get("name") or "").split("[")[0]
        found.setdefault((tc.get("classname"), base), []).append((state, ms))

    for key, entry in sorted(cases.items()):
        got = found.get(nodeid_parts(entry["nodeid"]))
        if not got:
            emit(key, "blocked", 0, f"pytest reported no result for '{entry['nodeid']}'")
            continue
        total_ms = sum(ms for _, ms in got)
        statuses = [s for (s, _), _ in got]
        msgs = [m for (_, m), _ in got if m]
        if "failed" in statuses:
            emit(key, "failed", total_ms, msgs[0] if msgs else "assertion failed")
        elif all(s == "skipped" for s in statuses):
            emit(key, "skipped", total_ms, msgs[0] if msgs else "skipped by pytest")
        else:
            emit(key, "passed", total_ms)


# ----------------------------------------------------------------- suite -----
def suite(cases):
    """test_suite/run_suite.py — the UI repo's own runner.

    It drives full journeys (login, schema, data catalog) that pytest does not
    cover, and writes its own JSON report rather than JUnit, so it is read here
    instead of through the JUnit path.
    """
    if not UI_REPO.exists():
        for k in cases:
            emit(k, "blocked", 0, f"UI repo not present at {UI_REPO}")
        return

    results_dir = UI_REPO / "test_suite" / "results"
    by_invocation = {}
    for k, v in cases.items():
        by_invocation.setdefault((v["suite"], v.get("step", "")), {})[k] = v

    for (suite_name, step), members in sorted(by_invocation.items()):
        # Clear this suite's old reports so the newest file is unambiguously ours.
        for stale in results_dir.glob(f"{suite_name}_*.json"):
            stale.unlink(missing_ok=True)

        args = ["test_suite/run_suite.py", "--suite", suite_name] + ([step] if step else [])
        if UI_DOCKER_IMAGE:
            cmd = ["docker", "run", "--rm", "-u", f"{os.getuid()}:{os.getgid()}",
                   "-e", "HOME=/tmp"]
            for var in ("APP_URL",):
                if os.environ.get(var):
                    cmd += ["-e", f"{var}={os.environ[var]}"]
            cmd += ["-v", f"{UI_REPO}:/work", "-w", "/work", UI_DOCKER_IMAGE, "python", *args]
            cwd = ROOT
        else:
            python = UI_REPO / "venv" / "bin" / "python"
            cmd = [str(python) if python.exists() else sys.executable, *args]
            cwd = UI_REPO
        print(f">> run_suite {suite_name} {step}".rstrip(), file=sys.stderr)
        code, out = run(cmd, cwd)

        reports = sorted(results_dir.glob(f"{suite_name}_*.json"),
                         key=lambda p: p.stat().st_mtime) if results_dir.exists() else []
        if not reports:
            tail = " | ".join(out.strip().splitlines()[-3:])[:300] or f"exit {code}"
            for k in members:
                emit(k, "blocked", 0, f"run_suite produced no report: {tail}")
            continue

        # stages[] holds one entry per service, each with its own stages[] of cases.
        found = {}
        for service in json.load(open(reports[-1])).get("stages", []):
            for st in service.get("stages", []):
                found[st.get("stage")] = st

        for key, entry in sorted(members.items()):
            want = entry.get("stage")
            st = found.get(want)
            if st is None:
                emit(key, "blocked", 0, f"run_suite reported no stage named '{want}'")
                continue
            status = {"SUCCESS": "passed", "FAILED": "failed",
                      "SKIPPED": "skipped"}.get(st.get("status"), "blocked")
            msg = "" if status == "passed" else (st.get("message") or "")[:300]
            emit(key, status, st.get("duration_ms") or 0, msg)


def main():
    scope = json.load(open(sys.argv[1] if len(sys.argv) > 1 else ROOT / "reports" / "scope.json"))
    JUNIT_DIR.mkdir(parents=True, exist_ok=True)

    groups = {}
    for key, entry in scope.items():
        if not entry.get("automated"):
            emit(key, "skipped", 0, "manual case - no automation bound")
            continue
        runner = entry.get("runner", "none")
        if runner == "none":
            emit(key, "skipped", 0, "automated, but not yet bound to a runner")
            continue
        groups.setdefault(runner, {})[key] = entry

    for runner, cases in sorted(groups.items()):
        if runner == "postman":
            postman(cases)
        elif runner == "pytest":
            pytest(cases)
        elif runner == "suite":
            suite(cases)
        else:
            for k in cases:
                emit(k, "blocked", 0, f"unknown runner '{runner}'")


if __name__ == "__main__":
    main()
