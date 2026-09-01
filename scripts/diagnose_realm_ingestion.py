#!/usr/bin/env python
"""Diagnose realm ingestion: step-by-step trace with detailed output at each stage.

Creates a SINGLE Postgres datasource, builds schema+entities+realm, generates streams,
triggers ingestion, and inspects every intermediate result to find where 0-rows comes from.

Usage:
  python scripts/diagnose_realm_ingestion.py [--env environments/minikube.postman_environment.json]
"""
import argparse, json, os, ssl, sys, time, urllib.request, urllib.parse

ssl._create_default_https_context = ssl._create_unverified_context

def load_env(path):
    vals = {}
    with open(path) as f:
        for v in json.load(f).get("values", []):
            if v.get("enabled", True):
                vals[v["key"]] = v.get("value", "")
    return vals

def load_secrets(path):
    vals = {}
    if not os.path.exists(path):
        return vals
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            if k:
                vals[k] = v
    return vals

# --HTTP helpers --

def api(method, url, body=None, headers=None, label=""):
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            code = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        code = e.code
    try:
        result = json.loads(raw)
    except Exception:
        result = raw
    status = "OK" if code < 400 else "FAIL"
    print(f"  [{status}] {method} {url.split('?')[0].split('/')[-1]}  -> {code}")
    if code >= 400:
        msg = result if isinstance(result, str) else json.dumps(result)[:200]
        print(f"         {msg}")
    return code, result

def get_token(kc_url, client_id, client_secret, username, password):
    data = urllib.parse.urlencode({
        "grant_type": "password", "client_id": client_id,
        "client_secret": client_secret, "username": username, "password": password,
    }).encode()
    req = urllib.request.Request(kc_url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="environments/minikube.postman_environment.json")
    parser.add_argument("--secrets", default=None, help="Secrets .env file (default: download from S3)")
    args = parser.parse_args()

    env = load_env(args.env)
    APP = env["app_base_url"]
    TXN = env["transform_base_url"]
    KG  = env["kg_base_url"]
    TENANT = env.get("tenant_id", "eksquipu")

    # Load secrets
    if args.secrets and os.path.exists(args.secrets):
        sec = load_secrets(args.secrets)
    else:
        import subprocess, tempfile
        tmp = os.path.join(tempfile.gettempdir(), "_diag_secrets.env")
        subprocess.run(["aws", "s3", "cp", "s3://quipu-api-tests/config/secrets/minikube.secrets.env", tmp],
                       capture_output=True)
        sec = load_secrets(tmp)
        os.unlink(tmp)

    print("=" * 70)
    print("  REALM INGESTION DIAGNOSTIC")
    print("=" * 70)

    # --Auth --
    print("\n--1. Auth --")
    token = get_token(
        env["keycloak_token_url"],
        env.get("client_id", "eksquipu-client"),
        sec.get("client_secret", ""),
        sec.get("test_username", "eksquipu"),
        sec.get("test_password", "eksquipu"))
    print(f"  Token acquired (len={len(token)})")

    hdr = {"Authorization": f"Bearer {token}", "X-TENANT-ID": TENANT, "Content-Type": "application/json"}

    # --Health --
    print("\n--2. Health checks --")
    api("GET", f"{APP}/actuator/health", headers=hdr, label="app")
    api("GET", f"{TXN}/actuator/health", headers=hdr, label="txn")
    api("GET", f"{KG}/actuator/health", headers=hdr, label="kg")

    # --Create DS --
    print("\n--3. Create Postgres datasource --")
    ds_body = {
        "name": f"diag_pg_{int(time.time())}",
        "driverType": sec.get("driverType", "POSTGRES"),
        "dbHostName": sec.get("dbHost", ""),
        "dbPort": int(sec.get("dbPort", "5433")),
        "databaseName": sec.get("dbName", ""),
        "dbUserName": sec.get("dbUser", ""),
        "dbPassword": sec.get("dbPassword", ""),
        "aesRandomIV": sec.get("aesRandomIV", ""),
        "dbSchema": sec.get("dbSchema", "public"),
        "driverClassName": sec.get("driverClassName", "org.postgresql.Driver"),
        "deleted": False
    }
    code, ds = api("POST", f"{APP}/datasource", ds_body, hdr)
    ds_data = ds.get("dataSourceModel", ds.get("data", ds)) if isinstance(ds, dict) else {}
    ds_id = ds_data.get("id") or ds_data.get("sourceId")
    ds_cat = ds_data.get("dataCatalogName", "")
    print(f"  dsId={ds_id}  dataCatalogName={ds_cat}")

    if not ds_id:
        print("ABORT: datasource creation failed")
        return

    # --Fetch metadata --
    print("\n--4. Fetch metadata (entities) --")
    code, meta = api("POST", f"{APP}/metadata-graph/fetch-data-source", {"uri": ds_cat}, hdr)
    tables = meta.get("hasTableEdges", []) if isinstance(meta, dict) else []
    print(f"  Tables found: {len(tables)}")
    for te in tables:
        tn = te.get("tableNode", {})
        cols = tn.get("hasPropertyEdges", [])
        print(f"    {tn.get('label', '?')} — {len(cols)} columns")

    # --Create schema --
    print("\n--5. Create schema --")
    schema_name = f"diag_schema_{int(time.time())}"
    prefix = schema_name.replace("_", "-")
    code, schema = api("POST", f"{APP}/schema",
                       {"schemaName": schema_name, "prefix": prefix, "description": "diagnostic"}, hdr)
    s_data = schema.get("schemaModel", schema.get("data", schema)) if isinstance(schema, dict) else {}
    schema_id = s_data.get("id") or s_data.get("schemaId")
    print(f"  schemaId={schema_id}  prefix={prefix}")

    # --Create entities one-by-one --
    print("\n--6. Create entities --")
    entity_uris = []
    for te in tables:
        tn = te.get("tableNode", {})
        nid = tn.get("nodeId", "")
        segs = nid.split(":")
        ds_name = segs[-2] if len(segs) >= 2 else "ds"
        ds_urn = ":".join(segs[:-1])
        ent_prefix = f"http://{ds_name}.in/"

        cols = tn.get("hasPropertyEdges", [])
        props = []
        for pe in cols:
            pn = pe.get("propertyNode", {})
            props.append({
                "label": pn.get("label", ""),
                "dataType": pn.get("dataType", "VARCHAR"),
                "primaryKey": bool(pn.get("primaryKey")),
                "uniqueKey": bool(pn.get("uniqueKey")),
                "foreignKey": bool(pn.get("foreignKey")),
                "nullable": pn.get("nullable", True) is not False,
                "mappedColumnUri": pn.get("nodeId") or pn.get("uri", ""),
                "mappedColumnUris": [pn.get("nodeId") or pn.get("uri", "")]
            })

        ent_body = {
            "label": tn.get("label", ""),
            "prefix": ent_prefix,
            "dataSourceUri": ds_urn,
            "namedEntity": False,
            "description": "",
            "tags": [],
            "properties": props
        }
        code, ent = api("POST", f"{APP}/entity", ent_body, hdr)
        eu = ent.get("entityUri", "?") if isinstance(ent, dict) else "?"
        entity_uris.append(eu)
        print(f"    -> {tn.get('label')}: {eu} ({len(props)} props)")

    # --Fetch entity-graph subgraph and build schema-graph --
    print("\n--7. Assemble schema graph from entity-graph --")
    nid0 = tables[0]["tableNode"]["nodeId"] if tables else ""
    segs0 = nid0.split(":")
    ds_urn0 = ":".join(segs0[:-1])

    code, subgraph = api("GET", f"{APP}/entity-graph/datasource-subgraph?uri={urllib.parse.quote(ds_urn0)}", headers=hdr)
    nodes = subgraph.get("nodes", []) if isinstance(subgraph, dict) else []
    links = subgraph.get("links", []) if isinstance(subgraph, dict) else []
    entity_nodes = [n for n in nodes if n.get("node_type") == "Node"]
    print(f"  Subgraph: {len(nodes)} nodes, {len(links)} links, {len(entity_nodes)} entities")

    # Stamp nodeId and schemaId
    for n in nodes:
        n["nodeId"] = prefix + (n.get("uri") or n.get("id") or "")
        n["schemaId"] = schema_id

    # Add version node
    version_uri = f"{prefix}Version#v1"
    nodes.append({"node_type": "Version", "id": version_uri, "uri": version_uri,
                  "nodeId": version_uri, "label": "v1", "schemaId": schema_id, "tags": []})
    for en in entity_nodes:
        links.append({"source": version_uri, "target": en.get("id") or en.get("uri"),
                      "relationship": "Has_Node", "direction": "FORWARD", "node_uri": version_uri})

    sg_body = {
        "prefix": prefix, "schemaName": schema_name,
        "schemaUri": f"{prefix}Schema#{schema_name}",
        "nodes": nodes, "links": links,
        "versionsModel": {
            "versionName": "v1", "description": "", "defaultVersion": False,
            "latest": True, "deleted": False, "versionLocked": False,
            "dataSourceIds": [int(ds_id)], "entity360Flows": []
        }
    }
    print(f"\n--8. POST /schema-graph ({len(nodes)} nodes, {len(links)} links) --")
    code, sg_resp = api("POST", f"{APP}/schema-graph", sg_body, hdr)
    version_id = sg_resp.get("versionId") if isinstance(sg_resp, dict) else None
    print(f"  versionId={version_id}")

    # --Create realm --
    print("\n--9. Create realm --")
    realm_name = f"diag_realm_{int(time.time())}"
    realm_ref = realm_name.replace("_", "") + TENANT
    realm_body = {
        "name": realm_name, "description": "diagnostic",
        "schemaName": schema_name, "versionId": int(version_id) if version_id else 0,
    }
    code, realm = api("POST", f"{APP}/realm", realm_body, hdr)
    r_data = realm.get("realmModel", realm.get("data", realm)) if isinstance(realm, dict) else {}
    realm_id = r_data.get("id") or r_data.get("realmId")
    realm_ref = r_data.get("realmReferenceName", realm_ref)
    print(f"  realmId={realm_id}  ref={realm_ref}")

    if not realm_id:
        print("ABORT: realm creation failed")
        # Cleanup schema/ds
        api("DELETE", f"{APP}/schema-graph?schemaId={schema_id}", headers=hdr)
        api("DELETE", f"{APP}/versions/delete?versionId={version_id}", headers=hdr)
        api("DELETE", f"{APP}/schema?schemaName={schema_name}", headers=hdr)
        api("DELETE", f"{APP}/datasource/{ds_id}", headers=hdr)
        return

    # --Create synapse namespace --
    print("\n--10. Create synapse namespace --")
    ns_body = {"name": realm_ref, "realmId": int(realm_id) if realm_id else 0}
    code, ns = api("POST", f"{KG}/synapse/namespace/create", ns_body, hdr)

    # --Wait for namespace UP --
    print("\n--11. Wait namespace UP --")
    for attempt in range(30):
        time.sleep(4)
        code, st = api("GET", f"{KG}/synapse/namespace/status?name={realm_ref}", headers=hdr)
        status = st.get("status", "?").upper() if isinstance(st, dict) else "?"
        print(f"  attempt {attempt}: {status}")
        if status == "UP":
            break
        if code >= 500:
            print(f"  STOP: 500 from namespace status (synapse not configured)")
            break
    else:
        print(f"  TIMEOUT: namespace never reached UP after 30 attempts")

    # --Generate streams --
    print("\n--12. Generate streams --")
    code, streams = api("POST", f"{TXN}/streams/generate", {"realmId": int(realm_id)}, hdr)
    stream_list = streams if isinstance(streams, list) else []
    print(f"  Streams generated: {len(stream_list)}")

    # --INSPECT stream SQL — this is critical --
    print("\n--13. INSPECT STREAM SQL --")
    for i, s in enumerate(stream_list[:5]):
        print(f"\n  Stream [{i}]: {s.get('name', '?')}")
        print(f"    streamType: {s.get('streamType', '?')}")
        print(f"    sqlQuery:   {s.get('sqlQuery', '(none)')}")
        print(f"    realmId:    {s.get('realmId', '?')}")
        print(f"    dataSourceId: {s.get('dataSourceId', '?')}")
        if s.get("columnMappings"):
            print(f"    columnMappings: {len(s['columnMappings'])} cols")
    if len(stream_list) > 5:
        print(f"\n  ... and {len(stream_list)-5} more streams")
    if stream_list:
        print(f"\n  ALL KEYS in stream[0]: {list(stream_list[0].keys())}")
        print(f"\n  FULL stream[0] JSON:")
        print(f"  {json.dumps(stream_list[0], indent=2)[:1000]}")

    # --Create Trino/Hive catalog BEFORE ingestion --
    print("\n--14. Create Trino/Hive catalog --")
    table_names = [te.get("tableNode", {}).get("label", "") for te in tables]
    hive_body = {"dataSource": {"id": int(ds_id)}, "metadataTables": table_names, "shape": {}}
    code, hive = api("POST", f"{TXN}/trino-source/create-hive", hive_body, hdr)
    print(f"  create-hive response: {json.dumps(hive)[:300] if isinstance(hive, dict) else str(hive)[:300]}")

    # --Stamp realmId and save streams --
    print("\n--15. Save streams (create-streams) --")
    for s in stream_list:
        s["realmId"] = int(realm_id)
    code, cr = api("POST", f"{APP}/atomicIngestStream/create-streams",
                   stream_list, hdr)
    print(f"  create-streams: {code}")

    # --Trigger ingestion --
    print("\n--16. Trigger event/ingest --")
    code, ig = api("POST",
                   f"{TXN}/event/ingest?truncate=false&seedSequenceFromJournal=false&forceIngest=true",
                   stream_list, hdr)
    print(f"  event/ingest: {code}")
    if isinstance(ig, dict):
        print(f"  response: {json.dumps(ig)[:300]}")

    # --Poll for ingestion results --
    print("\n--17. Poll namespace stats (6 attempts, 10s apart) --")
    for attempt in range(6):
        time.sleep(10)
        code, stats = api("GET", f"{KG}/synapse/namespace/stats?namespace={realm_ref}", headers=hdr)
        if isinstance(stats, dict):
            labels = stats.get("labels", [])
            landed = {l["label"]: l.get("count", 0) for l in labels if l.get("count", 0) > 0}
            print(f"  attempt {attempt}: landed={json.dumps(landed) if landed else '{}'}")
            if landed:
                print(f"  OK: DATA LANDED!")
                break
        else:
            print(f"  attempt {attempt}: {code} {str(stats)[:100]}")
    else:
        print(f"\n  FAIL: NO DATA LANDED after 60s")

    # --Additional diagnostics --
    print("\n--18. Additional diagnostics --")

    # Check if streams are actually saved
    print("  Checking saved streams via GET /atomicIngestStream:")
    code, saved = api("GET", f"{APP}/atomicIngestStream?realmId={realm_id}", headers=hdr)
    if isinstance(saved, list):
        print(f"    Saved streams: {len(saved)}")
        for s in saved[:3]:
            print(f"      {s.get('name','?')} streamType={s.get('streamType','?')} sql={str(s.get('sqlQuery',''))[:100]}")
    elif isinstance(saved, dict):
        content = saved.get("content", saved.get("data", []))
        if isinstance(content, list):
            print(f"    Saved streams: {len(content)}")
            for s in content[:3]:
                print(f"      {s.get('name','?')} streamType={s.get('streamType','?')} sql={str(s.get('sqlQuery',''))[:100]}")

    # Check synapse namespace details
    print("\n  Checking synapse namespace details:")
    code, ns_detail = api("GET", f"{KG}/synapse/namespace/status?name={realm_ref}", headers=hdr)
    if isinstance(ns_detail, dict):
        for k in ["status", "message", "error", "synapseUrl"]:
            if k in ns_detail:
                print(f"    {k}: {ns_detail[k]}")
        print(f"    Full response keys: {list(ns_detail.keys())}")

    # --Cleanup --
    print("\n--19. Cleanup --")
    api("DELETE", f"{KG}/synapse/namespace/remove?name={realm_ref}&permanent=true", headers=hdr)
    api("DELETE", f"{APP}/realm/{realm_id}?permanent=false", headers=hdr)
    api("DELETE", f"{APP}/schema-graph?schemaId={schema_id}", headers=hdr)
    api("DELETE", f"{APP}/versions/delete?versionId={version_id}", headers=hdr)
    api("DELETE", f"{APP}/schema?schemaName={schema_name}", headers=hdr)
    api("DELETE", f"{APP}/datasource/{ds_id}", headers=hdr)

    print("\n" + "=" * 70)
    print("  DIAGNOSTIC COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
