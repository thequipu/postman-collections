#!/usr/bin/env python
"""End-to-end single-datasource fabric test WITH real ingestion validation.

Postgres DS -> schema (+prefix) -> save-schema-version (MinIO) -> schema-graph (Neo4j UI)
-> realm -> synapse namespace (historic ingest) -> streams/generate (REAL per-entity SQL)
-> start -> wait -> ingestion status -> assert data actually landed (namespace stats.labels).

Unlike the old flow (SELECT 1 + accept-any-status), this verifies ingestion really happened.
Run: python scripts/test_single_ds_fabric.py [--keep]
"""
import argparse, json, os, re, ssl, sys, time, urllib.request, urllib.parse

ssl._create_default_https_context = ssl._create_unverified_context
KC = "https://kc-quipueks.thequipu.in/realms/eksquipu/protocol/openid-connect/token"
APP = "https://api-quipueks.thequipu.in/applicationService"
KG = "https://api-quipueks.thequipu.in/knowledgeGraphService"
TR = "https://api-quipueks.thequipu.in/transformationService"
TEN = "eksquipu"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DT = {"int8": "BIGINT", "int4": "INTEGER", "int2": "SMALLINT", "varchar": "VARCHAR",
      "bpchar": "VARCHAR", "text": "VARCHAR", "bool": "BOOLEAN", "float8": "DOUBLE",
      "numeric": "DECIMAL", "timestamp": "TIMESTAMP", "date": "DATE", "uuid": "VARCHAR"}


def req(url, data=None, method="GET", H=None, form=False):
    h = dict(H or {}); body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode(); h["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode(); h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, method=method)
    for k, v in h.items():
        r.add_header(k, v)
    try:
        x = urllib.request.urlopen(r); return x.status, x.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def check(label, res, ok=(200, 201)):
    st, body = res
    if st in ok:
        print(f"  [OK ] {label}: {st}")
    else:
        print(f"  [FAIL] {label}: {st} :: {body[:200]}")
        raise SystemExit(f"aborted at: {label}")
    return body


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--keep", action="store_true")
    ap.add_argument("--source", default="postgres",
                    help="datasource type: postgres|mysql|mariadb|oracle|snowflake|mongo|csv|excel")
    ap.add_argument("--csv-config", default=None,
                    help="override config file for CSV/S3 source (e.g. csv-users.json)")
    args = ap.parse_args()
    SRC = args.source
    cfg_file = (args.csv_config if (SRC == "csv" and args.csv_config) else f"{SRC}-datatype.json")
    cfg = json.load(open(os.path.join(ROOT, "config", "db-configs", cfg_file)))
    IS_S3 = "bucket" in cfg
    DRIVER = cfg.get("driverType", SRC.upper())
    tok = json.loads(req(KC, {"grant_type": "password", "client_id": "eksquipu-client",
        "client_secret": "h7rKFLYmYX407iWrgcDJPx9N2L04V4So", "username": "eksquipu",
        "password": "eksquipu"}, "POST", form=True)[1])["access_token"]
    H = {"Authorization": "Bearer " + tok, "X-TENANT-ID": TEN}
    MT = {**H, "Accept": "application/vnd.quipu.rdf.meta-data+json;version=1.0.0"}
    ts = int(time.time())

    mongo_shape = {}   # collection label -> [field names], populated for MONGO (see below)
    print(f"1) Create {DRIVER} datasource")
    if IS_S3:
        # S3-backed (CSV/Excel): files[] with columnDetails (server NPEs on null). CSV needs raw
        # accessKey/secret (no aesRandomIV); Excel uses server IAM (omit creds if absent in config).
        if cfg.get("columns"):
            cols = [(c["name"], c.get("type", "STRING"), c.get("primaryKey", False), c.get("uniqueKey", False))
                    for c in cfg["columns"]]
        else:
            cols = [("id", "INTEGER", True, True), ("name", "STRING", False, False),
                    ("email", "STRING", False, False), ("age", "INTEGER", False, False),
                    ("salary", "DOUBLE", False, False), ("department", "STRING", False, False),
                    ("hire_date", "STRING", False, False), ("is_active", "STRING", False, False)]
        ds = {"name": f"pm_single_{SRC}_{ts}", "driverType": DRIVER,
              "bucket": cfg["bucket"], "key": cfg["key"], "region": cfg["region"], "deleted": False,
              "files": [{"key": cfg["file"], "columnDetails": [
                  {"name": n, "type": t, "nullable": not pk, "primaryKey": pk, "uniqueKey": uk}
                  for n, t, pk, uk in cols]}]}
        if cfg.get("accessKey"):
            ds["accessKey"] = cfg["accessKey"]; ds["secret"] = cfg["secret"]
    else:
        ds = {"name": f"pm_single_{SRC}_{ts}", "driverType": DRIVER, "dbHostName": cfg["dbHost"],
              "dbPort": cfg["dbPort"], "databaseName": cfg["dbName"], "dbUserName": cfg["dbUser"],
              "dbPassword": cfg["dbPassword"], "aesRandomIV": cfg["aesRandomIV"], "dbSchema": cfg["dbSchema"],
              "driverClassName": cfg["driverClassName"], "deleted": False}
        if DRIVER == "MONGO":
            # Mongo is a document DB — creation REQUIRES both the real shapeCypher (maps the
            # collections) AND a shapeParseResult (server NPEs on null even though it doesn't
            # persist it). Read the real shapeCypher from config and derive shapeParseResult.
            # Also record collection->fields so the graph builder can synthesize column nodes
            # (mongo fetch-data-source returns tables with 0 columns).
            sc = cfg["shapeCypher"]
            ds["shapeCypher"] = sc
            shape_nodes = []
            for m in re.finditer(r"\(g\d+:(\w+)\s*\{([^}]*)\}\)", sc):
                fields = [p.group(1) for p in re.finditer(r"(\w+):\s*'(\$[^']*)'", m.group(2))
                          if p.group(1) != "uri"]
                mongo_shape[m.group(1)] = fields
                shape_nodes.append({"label": m.group(1), "prefix": "http://mongo.in/",
                                    "properties": [{"jsonPath": "$." + f, "propertyName": f} for f in fields],
                                    "uriProperty": "$._id", "edgeShapes": []})
            ds["shapeParseResult"] = {"shape": {"prefix": "http://mongo.in/", "nodes": shape_nodes,
                                                "namespace": "public", "shapeType": "CYPHER_DSL"},
                                      "constraints": []}
    d = json.loads(check("datasource", req(APP + "/datasource", ds, "POST", H)))
    dd = d.get("dataSourceModel", d); dsId, cat = dd["id"], dd["dataCatalogName"]
    print(f"     dsId={dsId} cat={cat}")

    print("2) Fetch metadata + build schema graph")
    meta = json.loads(req(APP + "/metadata-graph/fetch-data-source", {"uri": cat}, "POST", H)[1])
    edges = meta.get("hasTableEdges", [])
    sname = f"pm_single_schema_{ts}"; prefix = f"http://pm_single_{ts}.in/"
    check("schema", req(APP + "/schema", {"schemaName": sname, "prefix": prefix, "description": "single-ds"}, "POST", H))
    P = prefix; vuri = P + "Version#v1"

    def nid(u): return P + u
    nodes = [{"node_type": "Version", "id": vuri, "uri": vuri, "nodeId": vuri, "label": "v1", "tags": [], "description": ""}]
    links = []
    t0 = edges[0]["tableNode"]; segs = t0["nodeId"].split(":")
    dsName = segs[-2]; dsShort = ":".join(segs[:-1]); entPrefix = f"http://{dsName}.in/"
    nodes.append({"node_type": "data_source", "id": dsShort, "node_id": dsShort, "uri": dsShort, "nodeId": nid(dsShort), "label": dsName, "driverType": DRIVER, "dataSourceID": dsId})
    for te in edges:
        tn = te["tableNode"]; tShort, tLong, tLabel = tn["nodeId"], tn["uri"], tn["label"]
        nodes.append({"node_type": "table", "id": tShort, "node_id": tShort, "uri": tLong, "nodeId": nid(tLong), "label": tLabel})
        links.append({"source": dsShort, "target": tShort, "relationship": "has_tables", "direction": "FORWARD"})
        entUri = entPrefix + "Node#" + tLabel
        nodes.append({"node_type": "Node", "id": entUri, "uri": entUri, "nodeId": nid(entUri), "label": tLabel, "entityLabel": tLabel, "namedEntity": False, "prefix": entPrefix, "tags": []})
        links.append({"source": vuri, "target": entUri, "relationship": "Has_Node", "direction": "FORWARD", "node_uri": vuri})
        for pe in tn.get("hasPropertyEdges", []):
            pn = pe["propertyNode"]; cShort, cLong, cLabel = pn["nodeId"], pn["uri"], pn["label"]
            ndt = DT.get((pn.get("dataType") or "").lower(), (pn.get("dataType") or "VARCHAR").upper())
            nodes.append({"node_type": "property", "id": cShort, "node_id": cShort, "uri": cLong, "nodeId": nid(cLong), "label": cLabel, "dataType": pn.get("dataType"), "data_type": pn.get("dataType"), "primaryKey": bool(pn.get("primaryKey")), "primary_key": bool(pn.get("primaryKey")), "uniqueKey": bool(pn.get("uniqueKey")), "foreignKey": bool(pn.get("foreignKey")), "nullable": pn.get("nullable") is not False})
            links.append({"source": tShort, "target": cShort, "relationship": "has_property", "direction": "FORWARD"})
            npUri = entPrefix + "NodeProperty#" + tLabel + "#" + cLabel
            nodes.append({"node_type": "Node Property", "id": npUri, "uri": npUri, "nodeId": nid(npUri), "label": cLabel, "dataType": ndt, "data_type": ndt, "primaryKey": bool(pn.get("primaryKey")), "primary_key": bool(pn.get("primaryKey")), "uniqueKey": bool(pn.get("uniqueKey")), "tags": []})
            links.append({"source": entUri, "target": npUri, "relationship": "has_node_property", "direction": "FORWARD", "node_uri": entUri, "prefix": entPrefix})
            links.append({"source": npUri, "target": cShort, "relationship": "maps_to_column", "direction": "FORWARD", "node_uri": entUri})
        # MONGO: fetch-data-source returns 0 columns per collection — synthesize property/NodeProperty
        # nodes from the shapeCypher fields so the stream generator has columns to SELECT.
        if DRIVER == "MONGO" and not tn.get("hasPropertyEdges") and tLabel in mongo_shape:
            for fld in mongo_shape[tLabel]:
                cShort = tShort + ":" + fld; cLong = tLong + ":" + fld; ndt = "VARCHAR"
                nodes.append({"node_type": "property", "id": cShort, "node_id": cShort, "uri": cLong, "nodeId": nid(cLong), "label": fld, "dataType": ndt, "data_type": ndt, "primaryKey": False, "primary_key": False, "uniqueKey": False, "foreignKey": False, "nullable": True})
                links.append({"source": tShort, "target": cShort, "relationship": "has_property", "direction": "FORWARD"})
                npUri = entPrefix + "NodeProperty#" + tLabel + "#" + fld
                nodes.append({"node_type": "Node Property", "id": npUri, "uri": npUri, "nodeId": nid(npUri), "label": fld, "dataType": ndt, "data_type": ndt, "primaryKey": False, "primary_key": False, "uniqueKey": False, "tags": []})
                links.append({"source": entUri, "target": npUri, "relationship": "has_node_property", "direction": "FORWARD", "node_uri": entUri, "prefix": entPrefix})
                links.append({"source": npUri, "target": cShort, "relationship": "maps_to_column", "direction": "FORWARD", "node_uri": entUri})
    ent_ct = len([n for n in nodes if n["node_type"] == "Node"])
    print(f"     built {len(nodes)} nodes ({ent_ct} entities), {len(links)} links")

    print("3) Create version via applicationService /schema-graph (Neo4j + versionsModel) — NO MinIO")
    # The UI does NOT call KG save-schema-version (MinIO). It posts the graph + versionsModel to
    # applicationService /schema-graph, which saves to Neo4j and MINTS the versionId in the response.
    schema_uri = f"{P}Schema#{sname}"
    sg_body = check("schema-graph (version)", req(APP + "/schema-graph",
        {"prefix": P, "schemaName": sname, "schemaUri": schema_uri, "nodes": nodes, "links": links,
         "versionsModel": {"versionName": "v1", "description": "", "defaultVersion": False,
                           "latest": True, "deleted": False, "versionLocked": False,
                           "dataSourceIds": [dsId], "entity360Flows": []}}, "POST", H))
    try:
        versionId = json.loads(sg_body).get("versionId")
    except Exception:
        versionId = None
    if not versionId:
        print("     !! /schema-graph returned no versionId"); sys.exit(2)
    print(f"     versionId={versionId}")

    print("4) Create realm (fabric)")
    rm = json.loads(check("realm", req(APP + "/realm", {"name": f"pm_single_fabric_{ts}", "description": "single-ds fabric", "schemaName": sname, "versionId": versionId}, "POST", H))).get("realmModel", {})
    rid, ref = rm["id"], rm["referenceName"]; print(f"     realmId={rid} ref={ref}")

    print("5) Create Synapse namespace (historic ingest)")
    check("namespace/create", req(KG + "/synapse/namespace/create", {"name": ref, "schemaName": sname, "schemaVersion": "v1", "requiresHistoricIngest": True, "type": None, "vectorIngestionRequired": True}, "POST", H))

    print("5b) Wait for namespace READY (synapse/namespace/status) before ingesting")
    ns_ready = False
    for i in range(18):                     # up to 90s
        stc, stb = req(KG + f"/synapse/namespace/status?name={ref}", H=H)
        try:
            state = (json.loads(stb).get("status") or "").strip()
        except Exception:
            state = (stb or "").strip().strip('"')
        print(f"     t={i * 5}s status={stc} :: {state}")
        if stc == 200 and state.upper() in ("UP", "ACTIVE", "READY", "RUNNING"):
            ns_ready = True; print(f"     namespace READY ({state}) after ~{i * 5}s"); break
        time.sleep(5)
    if not ns_ready:
        print("     WARN: namespace not confirmed READY after 90s; proceeding anyway")
    time.sleep(10)                          # settle before firing ingestion

    print("6) Generate REAL ingest streams (per-entity SQL)")
    sc, sbody = req(TR + "/streams/generate", {"realmId": rid}, "POST", H)
    check("streams/generate", (sc, sbody))
    streams = json.loads(sbody)
    streams = streams if isinstance(streams, list) else streams.get("data", [])
    for s in streams:            # generate returns realmId=null; downstream needs it set
        s["realmId"] = rid
    print(f"     {len(streams)} streams generated:")
    for s in streams[:6]:
        print(f"       {s.get('name')} :: {str(s.get('sqlQuery'))[:70].replace(chr(10), ' ')}")
    if not streams:
        print("\n=== RESULT: NO streams generated — ingestion cannot run ==="); sys.exit(1)

    print("6b) Save streams (create-streams) — REQUIRED, else event/ingest persists nothing")
    svc, svb = req(APP + "/atomicIngestStream/create-streams", streams, "POST", H)
    saved = json.loads(svb) if svc in (200, 201) else []
    sids = [s.get("id") for s in saved if isinstance(s, dict) and s.get("id")]
    print(f"     create-streams: {svc}, saved stream ids: {sids}")

    print("7) Run ingestion (event/ingest — executes the stream SQL via Trino)")
    ic, ib = req(TR + "/event/ingest?truncate=false&seedSequenceFromJournal=false&forceIngest=false",
                 streams, "POST", H)
    print(f"     event/ingest: {ic} :: {ib[:300]}")

    expected = [s.get("name") for s in streams if s.get("name")]
    print(f"8) VERIFY EVERY table landed (expected {len(expected)}: {expected})")
    landed = {}
    for i in range(18):                     # up to 90s
        st, b = req(KG + f"/synapse/namespace/stats?namespace={ref}", H=H)
        try:
            labels = json.loads(b).get("labels", [])
        except Exception:
            labels = []
        landed = {l.get("label"): l.get("count", 0) for l in labels if l.get("count", 0) > 0}
        if expected and all(name in landed for name in expected):
            break
        if i == 8:                          # ~40s in, still missing — re-fire once
            req(TR + "/event/ingest?truncate=false&seedSequenceFromJournal=false&forceIngest=true",
                streams, "POST", H)
            print("     (re-fired event/ingest with forceIngest=true)")
        time.sleep(5)
    missing = [name for name in expected if name not in landed]
    print(f"     landed: {landed}")
    # Strict: ANY table that failed to ingest fails the whole flow (per user directive)
    ok = bool(expected) and not missing
    if missing:
        print(f"     FAILED TABLES (Trino/data error, no rows): {missing}")
        errs = req(APP + "/atomic-ingestion-status/get-latest", sids or [0], "POST", H)[1]
        print(f"     ingestion-status detail: {errs[:500]}")
    print("\n=== RESULT: ingestion",
          "VALIDATED — ALL tables in graph" if ok else f"FAILED — {len(missing)}/{len(expected)} table(s) did not ingest",
          "===")
    print(f"realmId={rid} ref={ref} schema={sname}" + ("  (kept)" if args.keep else ""))
    if not args.keep:
        req(KG + f"/synapse/namespace/remove?name={ref}&permanent=true", method="DELETE", H=H)
        req(APP + f"/realm/{rid}?permanent=false", method="DELETE", H=H)
        req(APP + f"/schema?schemaName={urllib.parse.quote(sname)}", method="DELETE", H=H)
        req(APP + f"/datasource/{dsId}", method="DELETE", H=H)
        print("cleaned up (soft).")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
