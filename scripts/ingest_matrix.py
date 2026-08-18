#!/usr/bin/env python
"""Per-datasource ingestion matrix. Runs test_single_ds_fabric.py for each datasource case and
records: DS created? streams generated? create-streams status? tables landed vs expected? verdict.
Answers 'which of the 8 datasource cases actually ingest' and pins the 8-DS create-streams culprit.

Run: python scripts/ingest_matrix.py
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# (label, --source, extra args)
CASES = [
    ("postgres",  ["--source", "postgres"]),
    ("mysql",     ["--source", "mysql"]),
    ("mariadb",   ["--source", "mariadb"]),
    ("oracle",    ["--source", "oracle"]),
    ("snowflake", ["--source", "snowflake"]),
    ("mongo",     ["--source", "mongo"]),
    ("csv",       ["--source", "csv", "--csv-config", "csv-users.json"]),
    ("excel",     ["--source", "excel"]),
]


def run_case(label, extra):
    cmd = [sys.executable, os.path.join(ROOT, "scripts", "test_single_ds_fabric.py")] + extra
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=420)
        out = p.stdout + p.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + "\n[TIMEOUT]"
    created = "datasource: 201" in out or "datasource: 200" in out
    aborted = re.search(r"aborted at: (\S+)", out)
    m_streams = re.search(r"(\d+) streams generated", out)
    m_cs = re.search(r"create-streams: (\d+)", out)
    m_landed = re.search(r"landed: (\{.*\})", out)
    m_missing = re.search(r"FAILED TABLES.*?: (\[.*\])", out)
    validated = "ingestion VALIDATED" in out
    streams = m_streams.group(1) if m_streams else "-"
    cs = m_cs.group(1) if m_cs else "-"
    landed = m_landed.group(1) if m_landed else "{}"
    n_landed = landed.count(":")            # rough count of landed labels
    if not created:
        verdict = f"DS CREATE FAIL ({aborted.group(1) if aborted else '?'})"
    elif validated:
        verdict = "INGEST OK"
    elif m_missing:
        verdict = "INGEST FAIL (missing tables)"
    else:
        verdict = "INGEST FAIL"
    return dict(label=label, created=created, streams=streams, cs=cs,
                landed=n_landed, verdict=verdict)


def main():
    rows = []
    for label, extra in CASES:
        print(f"\n########## {label} ##########", flush=True)
        r = run_case(label, extra)
        rows.append(r)
        print(f"  -> created={r['created']} streams={r['streams']} create-streams={r['cs']} "
              f"landed={r['landed']} :: {r['verdict']}", flush=True)

    print("\n\n================= INGESTION MATRIX =================")
    print(f"{'Datasource':11} {'Created':8} {'Streams':8} {'CreateStreams':14} {'Landed':7} Verdict")
    for r in rows:
        print(f"{r['label']:11} {str(r['created']):8} {r['streams']:8} {r['cs']:14} {str(r['landed']):7} {r['verdict']}")
    ok = sum(1 for r in rows if r["verdict"] == "INGEST OK")
    print(f"\n{ok}/{len(rows)} datasource cases ingest data end-to-end.")


if __name__ == "__main__":
    main()
