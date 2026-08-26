#!/usr/bin/env python
"""Run FLOW-Realm-CRUD with all 8 datasources wired from config/db-configs/.

Assembles:
  - DB creds (postgres/mysql/mariadb/oracle/snowflake/mongo) -> Postman globals (template vars).
  - S3 creds/config for CSV + Excel (csv-datatype.json / excel-datatype.json) -> --env-var
    (the flow reads these with pm.environment.get(), so they MUST be environment scope).

Auth (Keycloak) is read from env vars CLIENT_SECRET / TEST_USERNAME / TEST_PASSWORD
(falling back to the eksquipu dev values). Usage:

  python scripts/run_realm_full.py [--env environments/minikube.postman_environment.json] [--keep]
"""
import argparse, json, os, shutil, ssl, subprocess, sys, tempfile, time
import urllib.request, urllib.parse, urllib.error


def wait_for_health(env_file, max_seconds=300, interval=10):
    """Poll applicationService /actuator/health until it returns 200, up to max_seconds.
    The backend can flap (service-discovery components drop -> aggregate health 500), which
    otherwise aborts the whole run at 00 Setup. Returns True once healthy, False on timeout."""
    ssl._create_default_https_context = ssl._create_unverified_context
    app = env_values(env_file).get("app_base_url")
    if not app:
        return True
    url = app + "/actuator/health"
    start = time.time()
    last = None
    while time.time() - start < max_seconds:
        try:
            code = urllib.request.urlopen(url, timeout=5).status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:
            code = "unreachable"
        if code == 200:
            print(f"[health] applicationService UP (waited {int(time.time()-start)}s)")
            return True
        if code != last:
            print(f"[health] applicationService {code} — waiting up to {max_seconds}s...")
            last = code
        time.sleep(interval)
    return False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config", "db-configs")

DB_PREFIX = {"postgres": "", "mysql": "mysql_", "mariadb": "maria_",
             "oracle": "oracle_", "snowflake": "snow_", "mongo": "mongo_"}
DB_FIELDS = ["driverType", "dbHost", "dbPort", "dbName", "dbUser", "dbPassword",
             "dbSchema", "driverClassName", "aesRandomIV"]


def load(name):
    with open(os.path.join(CFG, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def env_values(env_file):
    """Read the postman environment file into a {key: value} dict."""
    with open(os.path.join(ROOT, env_file), encoding="utf-8") as f:
        return {v["key"]: v.get("value", "") for v in json.load(f).get("values", [])}


def preflight(env_file, client_secret, username, password):
    """Fire a minimal save-schema-version to detect the KG/MinIO version-save degradation
    (returns empty 200 / no versionId) before spending ~7 min on a full run.
    Returns (ok: bool, message: str)."""
    ssl._create_default_https_context = ssl._create_unverified_context
    ev = env_values(env_file)
    kc = ev.get("keycloak_token_url"); app = ev.get("app_base_url"); kg = ev.get("kg_base_url")
    cid = ev.get("client_id") or "eksquipu-client"; tenant = ev.get("tenant_id") or "eksquipu"
    if not (kc and app and kg):
        return True, "preflight skipped (env file missing keycloak/app/kg URLs)"

    def call(url, data=None, method="POST", H=None, form=False, accept=None):
        h = dict(H or {}); body = None
        if data is not None:
            body = (urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode())
            h["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        if accept:
            h["Accept"] = accept
        r = urllib.request.Request(url, data=body, method=method)
        for k, v in h.items():
            r.add_header(k, v)
        try:
            x = urllib.request.urlopen(r); return x.status, x.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
    try:
        tok = json.loads(call(kc, {"grant_type": "password", "client_id": cid,
            "client_secret": client_secret, "username": username, "password": password},
            form=True)[1])["access_token"]
    except Exception as e:
        return False, f"preflight: could not get token ({e})"
    H = {"Authorization": "Bearer " + tok, "X-TENANT-ID": tenant}
    MT = "application/vnd.quipu.rdf.meta-data+json;version=1.0.0"
    ts = int(time.time()); sn = f"pm_preflight_{ts}"; P = f"http://pm_preflight_{ts}.in/"; vuri = P + "Version#v1"
    call(app + "/schema", {"schemaName": sn, "prefix": P, "description": "preflight"}, "POST", H)
    gs = json.dumps({"directed": True, "multigraph": True, "graph": {}, "prefix": P,
                     "nodes": [{"node_type": "Version", "id": vuri, "uri": vuri, "nodeId": vuri,
                                "label": "v1", "tags": [], "description": ""}], "links": []})
    st, sb = call(kg + "/metadata/save-schema-version",
                  {"schemaGraph": gs, "schemaName": sn, "newSchemaName": None, "awsVersionId": None,
                   "versionsModel": {"versionName": "v1", "description": "pf", "latest": True,
                                     "deleted": False, "defaultVersion": True, "versionLocked": False,
                                     "dataSourceIds": [], "entity360Flows": []}}, "POST", H, accept=MT)
    vid = None
    try:
        vid = json.loads(sb).get("versionId") if sb else None
    except Exception:
        vid = None
    call(app + f"/schema?schemaName={urllib.parse.quote(sn)}", method="DELETE", H=H)
    if vid:
        return True, f"preflight OK — save-schema-version healthy (versionId={vid})"
    return False, (f"save-schema-version DEGRADED: returned {st} with no versionId (bodylen={len(sb)}). "
                   "The KG/MinIO version-save is down — a full run would fail at 04i. "
                   "Fix the backend, or pass --skip-preflight to run anyway.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="environments/minikube.postman_environment.json")
    ap.add_argument("--collection", default="flows/FLOW-Realm-CRUD.postman_collection.json")
    ap.add_argument("--keep", action="store_true", help="keep DS after run (skip_cleanup)")
    ap.add_argument("--memory", action="store_true",
                    help="create a MEMORY fabric (namespace type=MEMORY, skip vectorize)")
    ap.add_argument("--hard", action="store_true",
                    help="permanent realm delete (needs memory_space migration V42-V44 applied)")
    ap.add_argument("--skip-preflight", action="store_true",
                    help="skip the save-schema-version health check and run anyway")
    ap.add_argument("--health-wait", type=int, default=300,
                    help="seconds to wait for applicationService health before running (default 300 = 5 min; 0 to skip)")
    args = ap.parse_args()

    # Wait for the (flaky) applicationService to be healthy before starting — otherwise the run
    # aborts at 00 Setup when the backend is momentarily 500.
    if args.health_wait > 0 and not wait_for_health(args.env, args.health_wait):
        sys.exit(f"[health] applicationService not healthy after {args.health_wait}s — aborting.")

    # DB creds -> globals (resolved by {{prefix_dbHost}} templates)
    gvals = []
    for name, pfx in DB_PREFIX.items():
        d = load(f"{name}-datatype")
        for k in DB_FIELDS:
            if d.get(k) is not None:
                gvals.append({"key": f"{pfx}{k}", "value": str(d[k]), "enabled": True})
    gfd, gpath = tempfile.mkstemp(suffix=".json", prefix="realm_globals_", dir=ROOT)
    with os.fdopen(gfd, "w") as f:
        json.dump({"id": "realm-full", "name": "realm-full", "values": gvals,
                   "_postman_variable_scope": "globals"}, f)

    # S3 config for CSV + Excel -> environment-scope env vars
    csv, xls = load("csv-datatype"), load("excel-datatype")
    env_vars = {
        "client_secret": os.environ.get("CLIENT_SECRET", "h7rKFLYmYX407iWrgcDJPx9N2L04V4So"),
        "test_username": os.environ.get("TEST_USERNAME", "eksquipu"),
        "test_password": os.environ.get("TEST_PASSWORD", "eksquipu"),
        "s3_access_key": csv["accessKey"], "s3_secret_key": csv["secret"],
        "s3_region": csv.get("region", "ap-south-1"),
        "s3_csv_bucket": csv["bucket"], "s3_csv_key": csv["key"], "s3_csv_file": csv["file"],
        "s3_excel_bucket": xls["bucket"], "s3_excel_key": xls["key"], "s3_excel_file": xls["file"],
        # NOTE: mongo shapeCypher is embedded directly in the flow (realm.py MONGO_SHAPE_CYPHER),
        # NOT passed here — --env-var truncates multi-line values at the first newline.
    }
    if args.keep:
        env_vars["skip_cleanup"] = "true"
    if args.memory:
        env_vars["memoryNamespace"] = "true"
    if args.hard:
        env_vars["hardDelete"] = "true"

    # Pre-flight: fail fast if the KG version-save is degraded (would fail at step 04i after ~7 min).
    if not args.skip_preflight:
        ok, msg = preflight(args.env, env_vars["client_secret"],
                            env_vars["test_username"], env_vars["test_password"])
        print(f"[preflight] {msg}")
        if not ok:
            os.remove(gpath)
            sys.exit("[preflight] Aborting before the newman run. Use --skip-preflight to override.")

    newman = shutil.which("newman") or shutil.which("newman.cmd")
    if not newman:
        sys.exit("newman not found on PATH")
    cmd = [newman, "run", args.collection, "-e", args.env,
           "--globals", os.path.basename(gpath), "--insecure",
           "--timeout-request", "120000", "-r", "cli"]
    for k, v in env_vars.items():
        cmd += ["--env-var", f"{k}={v}"]

    try:
        result = subprocess.run(cmd, cwd=ROOT, check=False)
    finally:
        os.remove(gpath)
    # Propagate newman's exit code so a failed assertion (e.g. a stream that did not ingest)
    # marks the whole dataflow as FAILED instead of silently exiting 0.
    if result.returncode != 0:
        print(f"\n[run] DATAFLOW FAILED — newman exited {result.returncode} (>=1 assertion failed).")
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
