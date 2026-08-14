#!/usr/bin/env python
"""Batch-run a list of newman flows against the eksquipu cloud (env file: minikube) as a
given user, and print a pass/fail table. Passes a broad env-var set (postgres DS creds +
S3 CSV/Excel + Keycloak admin) so each flow's own setup can create what it needs.

Usage: python scripts/run_all_flows.py [--user karthik] [--env environments/minikube.postman_environment.json]
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FLOWS = [
    "FLOW-DataSource-CRUD", "FLOW-Schema-CRUD", "FLOW-Version-CRUD", "FLOW-Entity-CRUD",
    "FLOW-Namespace-CRUD", "FLOW-Entity360-CRUD", "FLOW-SchemaGraph-CRUD", "FLOW-Permissions-CRUD",
    "FLOW-Watcher-CRUD", "FLOW-Metadata-Read", "FLOW-DataSource-Extended", "FLOW-App-Misc",
    "FLOW-DS-Migration", "FLOW-Document-Extraction", "FLOW-Ingestion-Streams",
    "FLOW-Transformation-Connection", "SMOKE-Platform-Health",
]


def cfg(name):
    return json.load(open(os.path.join(ROOT, "config", "db-configs", name)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="karthik")
    ap.add_argument("--password", default="karthik12")
    ap.add_argument("--env", default="environments/minikube.postman_environment.json")
    ap.add_argument("--secret", default=os.environ.get("CLIENT_SECRET", "h7rKFLYmYX407iWrgcDJPx9N2L04V4So"))
    args = ap.parse_args()

    pg = cfg("postgres-datatype.json")
    csv = cfg("csv-datatype.json"); xls = cfg("excel-datatype.json")
    ev = {
        "client_secret": args.secret, "test_username": args.user, "test_password": args.password,
        "adminUsername": "admin", "adminPassword": "admin123",
        "kc_admin_user": "admin", "kc_admin_password": "admin123",
        "driverType": "POSTGRES", "dbHost": pg["dbHost"], "dbPort": pg["dbPort"],
        "dbName": pg["dbName"], "dbUser": pg["dbUser"], "dbPassword": pg["dbPassword"],
        "dbSchema": pg["dbSchema"], "driverClassName": pg["driverClassName"], "aesRandomIV": pg["aesRandomIV"],
        "s3_bucket": csv["bucket"], "s3_csv_bucket": csv["bucket"], "s3_csv_key": csv["key"],
        "s3_region": csv["region"], "s3_access_key": csv["accessKey"], "s3_secret_key": csv["secret"],
        "s3_csv_file": csv["file"], "s3_excel_bucket": xls["bucket"], "s3_excel_file": xls["file"],
    }
    newman = shutil.which("newman") or shutil.which("newman.cmd")
    if not newman:
        sys.exit("newman not found on PATH")

    results = []
    for fl in FLOWS:
        coll = f"flows/{fl}.postman_collection.json"
        if not os.path.exists(os.path.join(ROOT, coll)):
            results.append((fl, "MISSING", 0, 0)); continue
        jf = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        cmd = [newman, "run", coll, "-e", args.env, "--insecure",
               "--timeout-request", "60000", "-r", "json", "--reporter-json-export", jf]
        for k, v in ev.items():
            cmd += ["--env-var", f"{k}={v}"]
        print(f"\n=== {fl} ===", flush=True)
        try:
            subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            results.append((fl, "TIMEOUT", 0, 0)); print("  TIMEOUT"); continue
        try:
            rep = json.load(open(jf))["run"]["stats"]
            total = rep["assertions"]["total"]; failed = rep["assertions"]["failed"]
            status = "PASS" if failed == 0 and total > 0 else ("NO-ASSERTIONS" if total == 0 else "FAIL")
            results.append((fl, status, total, failed))
            print(f"  {status}: {total-failed}/{total} assertions")
        except Exception as e:
            results.append((fl, "ERROR", 0, 0)); print(f"  parse error: {e}")
        finally:
            try: os.remove(jf)
            except OSError: pass

    print("\n\n================ SUMMARY ================")
    print(f"{'Flow':32} {'Status':14} {'Pass/Total'}")
    for fl, st, total, failed in results:
        print(f"{fl:32} {st:14} {total-failed}/{total}")
    npass = sum(1 for _, st, *_ in results if st == "PASS")
    print(f"\n{npass}/{len(results)} flows fully PASS  (user={args.user}, env={os.path.basename(args.env)})")


if __name__ == "__main__":
    main()
