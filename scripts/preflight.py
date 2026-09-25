#!/usr/bin/env python3
"""Check this agent can actually run what the cases are bound to, before any test runs.

    ENVIRONMENT=onprem python3 scripts/preflight.py

Prints one line per check and exits non-zero if a required one failed. Required
means: a runner that automation-map.json actually binds cases to. If nothing is
bound to pytest, a missing Playwright is reported but does not fail the build.

This exists because a missing runner otherwise surfaces late, as every one of its
cases reporting `blocked` — which looks like a test problem rather than an agent
problem. Fail here instead, with the reason.
"""
import json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENVIRONMENT = os.environ.get("ENVIRONMENT", "onprem")
UI_REPO = Path(os.environ.get("UI_REPO", ROOT.parent / "automation_fast_api"))
UI_DOCKER_IMAGE = os.environ.get("UI_DOCKER_IMAGE", "")
MODE = os.environ.get("MODE", "real")

rows = []          # (ok: bool|None, required: bool, name, detail)


def check(name, required, fn):
    try:
        ok, detail = fn()
    except Exception as e:                      # a check must never crash the build
        ok, detail = False, f"check errored: {e}"
    rows.append((ok, required, name, detail))


def have(cmd, args=("--version",)):
    exe = shutil.which(cmd)
    if not exe:
        return False, "not on PATH"
    try:
        p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=60)
        return True, (p.stdout or p.stderr).strip().splitlines()[0][:60] if (p.stdout or p.stderr) else exe
    except Exception as e:
        return False, f"present but not runnable: {e}"


def main():
    amap_path = ROOT / "automation-map.json"
    if not amap_path.exists():
        print("!! automation-map.json not found — run from the repo root")
        return 2
    # Prefer the resolved scope: an API-only run must not be failed by a broken
    # Playwright image, and a UI-only run must not require newman.
    scope_path = ROOT / "reports" / "scope.json"
    if scope_path.exists():
        source = json.load(open(scope_path))
        where = "this run's scope"
    else:
        source = json.load(open(amap_path))
        where = "automation-map.json (no run scope resolved)"
    bound = {v.get("runner", "none") for v in source.values()
             if v.get("automated")} - {"none"}
    amap = source
    print(f">> environment : {ENVIRONMENT}")
    print(f">> mode        : {MODE}")
    print(f">> runners required by {where}: {', '.join(sorted(bound)) or 'none'}")
    print()

    check("python3", True, lambda: have("python3"))
    check("curl", True, lambda: have("curl"))

    def envfile():
        p = ROOT / "environments" / f"{ENVIRONMENT}.postman_environment.json"
        if not p.exists():
            return False, f"missing {p.relative_to(ROOT)}"
        json.load(open(p))
        return True, str(p.relative_to(ROOT))
    check(f"environment '{ENVIRONMENT}'", "postman" in bound, envfile)

    # --- newman ---
    check("node", "postman" in bound, lambda: have("node"))
    check("postman CLI", "postman" in bound, lambda: have("postman"))

    def bindings():
        """Every case in scope must resolve to something the runner can find."""
        import subprocess as _sp
        r = _sp.run([sys.executable, str(ROOT / "tools" / "verify-bindings.py")],
                    capture_output=True, text=True, timeout=120, cwd=str(ROOT),
                    env={**os.environ, "UI_REPO": str(UI_REPO)})
        if r.returncode != 0:
            bad = [l.strip() for l in r.stdout.splitlines() if l.startswith("   ")]
            return False, (bad[0][:90] if bad else "unresolved bindings")
        return True, "every binding resolves"
    check("bindings", bool(bound), bindings)

    # --- pytest / playwright ---
    def ui_repo():
        if not UI_REPO.exists():
            return False, f"not found at {UI_REPO} — the pipeline checks it out before this stage"
        if not (UI_REPO / "tests").is_dir():
            return False, f"{UI_REPO} has no tests/ directory"
        return True, str(UI_REPO)
    check("UI repo", "pytest" in bound, ui_repo)

    def ui_runner():
        """Docker image when one is named, else the local interpreter."""
        if UI_DOCKER_IMAGE:
            exe = shutil.which("docker")
            if not exe:
                return False, "docker not on PATH but UI_DOCKER_IMAGE is set"
            p = subprocess.run([exe, "image", "inspect", UI_DOCKER_IMAGE],
                               capture_output=True, text=True, timeout=120)
            if p.returncode != 0:
                return False, f"image {UI_DOCKER_IMAGE} not present — build docker/ui-tests.Dockerfile"
            return True, f"image {UI_DOCKER_IMAGE}"
        if not UI_REPO.exists():
            return False, "UI repo absent"
        py = UI_REPO / "venv" / "bin" / "python"
        py = str(py) if py.exists() else sys.executable
        p = subprocess.run([py, "-m", "pytest", "--version"],
                           capture_output=True, text=True, timeout=120, cwd=str(UI_REPO))
        return p.returncode == 0, (p.stdout or p.stderr).strip().splitlines()[0][:60]
    check("pytest runner", "pytest" in bound, ui_runner)

    def chromium():
        """Launch the browser. Nothing short of that proves it is really installed."""
        code = ("from playwright.sync_api import sync_playwright\n"
                "with sync_playwright() as p:\n"
                "    b = p.chromium.launch(); v = b.version; b.close(); print(v)\n")
        if UI_DOCKER_IMAGE:
            if not shutil.which("docker"):
                return False, "docker not on PATH"
            cmd = ["docker", "run", "--rm", "-u", f"{os.getuid()}:{os.getgid()}",
                   "-e", "HOME=/tmp", UI_DOCKER_IMAGE, "python", "-c", code]
            cwd = ROOT
        else:
            if not UI_REPO.exists():
                return False, "UI repo absent"
            py = UI_REPO / "venv" / "bin" / "python"
            cmd = [str(py) if py.exists() else sys.executable, "-c", code]
            cwd = UI_REPO
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(cwd))
        if p.returncode != 0:
            tail = (p.stderr or p.stdout).strip().splitlines()
            return False, (tail[-1][:80] if tail else "chromium did not launch")
        return True, f"chromium {p.stdout.strip()}"
    check("chromium launches", "pytest" in bound, chromium)

    # --- Qase, only when this run reports to it ---
    def qase():
        token = os.environ.get("QASE_API_TOKEN", "")
        code = os.environ.get("QASE_PROJECT_CODE", "")
        if not (token and code):
            return None, "no token/project in env — results will not be published"
        import urllib.request, urllib.error
        base = os.environ.get("QASE_API_BASE_URL", "https://api.qase.io").rstrip("/")
        req = urllib.request.Request(f"{base}/v1/project/{code}",
                                     headers={"Token": token, "accept": "application/json"})
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=30).read())
            return True, f"project {code}: {d['result']['title']}"
        except urllib.error.HTTPError as e:
            return False, f"HTTP {e.code} — token rejected or project not visible"
    check("Qase API", bool(os.environ.get("QASE_RUN_ID")), qase)

    width = max(len(r[2]) for r in rows)
    failed = []
    for ok, required, name, detail in rows:
        mark = "SKIP" if ok is None else (" OK " if ok else "FAIL")
        tag = "" if required else "  (not required)"
        print(f"  [{mark}] {name.ljust(width)}  {detail}{tag}")
        if ok is False and required:
            failed.append(name)

    print()
    if failed:
        print(f"!! preflight failed: {', '.join(failed)}")
        print("   These are agent problems, not test failures. Install the missing tooling,")
        print("   or unbind the affected runner in automation-map.json.")
        return 1
    print(">> preflight passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
