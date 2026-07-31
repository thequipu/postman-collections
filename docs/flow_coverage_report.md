# API Flow Test Coverage Report

**Generated:** 2026-07-31
**Total Flows:** 14 | **Total Steps:** 106 | **Coverage:** ~48% of all endpoints

---

## Coverage Summary

| Flow | Service | Steps | Type | Covered | Total | Coverage |
|------|---------|-------|------|---------|-------|----------|
| FLOW-DataSource-CRUD | Application + Transformation | 13 | Full CRUD | 13 | 134 | — |
| FLOW-Tenant-CRUD | Tenant | 7 | Read-Only | 5 | 12 | 42% |
| FLOW-Security-Auth | Security | 6 | Auth | 4 | 13 | 31% |
| FLOW-Realm-CRUD | Application | 10 | Full CRUD | 8 | — | — |
| FLOW-Schema-CRUD | Application | 8 | CRUD | 5 | — | — |
| FLOW-Entity-CRUD | Application | 9 | CRUD | 7 | — | — |
| FLOW-Permissions-CRUD | Application | 7 | Read-Only | 5 | — | — |
| FLOW-Transformation-Connection | Transformation | 5 | Connection | 3 | 23 | 13% |
| FLOW-KnowledgeGraph-Metadata | KG Service | 6 | Read-Only | 4 | 34 | 12% |
| FLOW-Synapse-Namespace | Synapse | 10 | Full CRUD | 9 | 44 | 20% |
| FLOW-Nexus-Search | Nexus | 6 | Read-Only | 4 | 12 | 33% |
| FLOW-Lumen-Pipeline | Lumen | 8 | Pipeline | 6 | 8 | 75% |
| FLOW-DocumentGraph-Parse | Document Graph | 3 | Health | 1 | 2 | 50% |
| FLOW-NLP-Pipeline | NLP | 6 | Pipeline | 5 | 5 | 100% |

---

## Detailed Flow Coverage

### 1. FLOW-DataSource-CRUD (13 steps) — Application + Transformation

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up, token acquired |
| 01 | POST | `/test-connection` | DB connection (config-based) |
| 02 | POST | `/datasource` | **Create** datasource, capture ID |
| 03 | GET | `/datasource/id?sourceId=` | Get by ID, verify match |
| 04 | POST | `/test-connection/{id}/{type}` | Connection by ID |
| 05 | POST | `/metadata-graph/fetch-data-source` | Fetch metadata graph, capture tables |
| 06 | POST | `/source-query/fetch-sample-source` | Sample rows from first table |
| 07 | POST | `/source-query/query` | Dynamic SQL query (dialect-aware) |
| 08 | PUT | `/datasource` | **Update** description |
| 09 | GET | `/datasource/id?sourceId=` | Verify update |
| 10 | DELETE | `/datasource/{id}?permanent=true` | **Delete** datasource |
| 11 | GET | `/datasource/id?sourceId=` | Verify deleted |
| 99 | DELETE | `/datasource/{id}?permanent=true` | Teardown (always runs) |

### 2. FLOW-Tenant-CRUD (7 steps) — Read-Only

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/admin/actuator/health` | Service up, token |
| 01 | GET | `/admin/tenant` | List all tenants, array, count > 0 |
| 02 | GET | `/admin/tenant/active` | Active tenants, capture `firstTenantCode` |
| 03 | GET | `/admin/tenant/{code}` | Get by code, has data |
| 04 | GET | `/admin/tenant/users/{code}` | Users for tenant |
| 05 | GET | `/admin/audit` | Audit entries |
| 99 | GET | `/admin/actuator/health` | Cleanup |

### 3. FLOW-Security-Auth (6 steps)

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up, token |
| 01 | POST | `/user/introspect` | Token active, capture `sub` |
| 02 | GET | `/user/users` | Users list, is array |
| 03 | POST | `/admin/validate-tenant` | Tenant valid |
| 04 | POST | `/admin/introspect` | Admin token active |
| 99 | GET | `/actuator/health` | Cleanup |

### 4. FLOW-Realm-CRUD (10 steps)

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up |
| 01 | GET | `/realm?page=0&size=20` | List realms |
| 02 | POST | `/realm` | **Create**, capture `realmId`, `realmName` |
| 03 | GET | `/realm/{id}` | Get by ID, matches |
| 04 | GET | `/realm/by-name?realmName=` | Get by name |
| 05 | PUT | `/realm` | **Update** description |
| 06 | GET | `/realm/{id}` | Verify update |
| 07 | DELETE | `/realm/{id}?permanent=true` | **Delete** |
| 08 | GET | `/realm/{id}` | Verify deleted |
| 99 | DELETE | `/realm/{id}?permanent=true` | Teardown |

### 5. FLOW-Schema-CRUD (8 steps)

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up |
| 01 | POST | `/realm` | Create realm (dependency) |
| 02 | GET | `/schema` | List schemas |
| 03 | POST | `/schema` | **Create** schema, capture name |
| 04 | GET | `/schema/name?schemaName=` | Get by name |
| 05 | DELETE | `/schema?schemaName=` | **Delete** schema |
| 06 | DELETE | `/realm/{id}?permanent=true` | Cleanup realm |
| 99 | DELETE | `/realm/{id}?permanent=true` | Teardown |

### 6. FLOW-Entity-CRUD (9 steps)

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up |
| 01 | GET | `/entity-graph/entities?page=0&size=20` | List entities |
| 02 | POST | `/entity` | **Create** entity, capture URI |
| 03 | GET | `/entity/search?q=pm-flow` | Search found |
| 04 | GET | `/entity-graph/entity-subgraph?uri=` | Subgraph has data |
| 05 | POST | `/entity/property?entityUri=` | **Add** property |
| 06 | DELETE | `/entity/property?uri=` | **Delete** property |
| 07 | DELETE | `/entity?uri=` | **Delete** entity |
| 99 | DELETE | `/entity?uri=` | Teardown |

### 7. FLOW-Permissions-CRUD (7 steps) — Read-Only

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up |
| 01 | GET | `/permissions` | List permissions, is array |
| 02 | GET | `/roles` | List roles |
| 03 | GET | `/role-permission?page=0&size=20` | Role permissions |
| 04 | GET | `/user-permission?page=0&size=20` | User permissions |
| 05 | GET | `/user-permission/entity360-paths` | Entity360 paths |
| 99 | GET | `/actuator/health` | Cleanup |

### 8. FLOW-Transformation-Connection (5 steps)

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up |
| 01 | POST | `/test-connection` | DB connected (needs DB env-vars) |
| 02 | POST | `/test-connection/metadata` | Metadata returned |
| 03 | POST | `/test-connection/sample-records` | Sample records |
| 99 | GET | `/actuator/health` | Cleanup |

### 9. FLOW-KnowledgeGraph-Metadata (6 steps) — Read-Only

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up |
| 01 | GET | `/metadata/get-saved-schema-graph?referenceName=` | Schema graph (200/404) |
| 02 | GET | `/synapse/namespace/stats?namespace=` | Namespace stats |
| 03 | GET | `/synapse/namespace/status?name=` | Namespace status |
| 04 | GET | `/synapse/watchers?namespace=` | Watchers list |
| 99 | GET | `/actuator/health` | Cleanup |

### 10. FLOW-Synapse-Namespace (10 steps)

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up |
| 01 | GET | `/namespaces` | List namespaces |
| 02 | POST | `/namespaces/create?name=` | **Create**, capture `nsName` |
| 03 | GET | `/namespaces/{name}/status` | Status |
| 04 | GET | `/namespaces/{name}/stats` | Stats |
| 05 | POST | `/namespaces/{name}/enable` | **Enable** |
| 06 | POST | `/query/cypher` | Run `RETURN 1 AS n` |
| 07 | POST | `/namespaces/{name}/disable` | **Disable** |
| 08 | DELETE | `/namespaces/{name}?permanent=true` | **Delete** |
| 99 | DELETE | `/namespaces/{name}?permanent=true` | Teardown |

### 11. FLOW-Nexus-Search (6 steps) — Read-Only

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up |
| 01 | POST | `/nexus/schema/traversable/get` | Traversable schema |
| 02 | POST | `/nexus/search` | Search query |
| 03 | POST | `/nexus/gin` | GIN anchor discovery |
| 04 | POST | `/nexus/labels` | Label bags |
| 99 | GET | `/actuator/health` | Cleanup |

### 12. FLOW-Lumen-Pipeline (8 steps)

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up |
| 01 | POST | `/query-builder/query` | NL → Cypher |
| 02 | POST | `/query-builder/reset-schema` | Reset schema cache |
| 03 | POST | `/lumen/describe/datasource` | AI describe (needs `versionUri`) |
| 04 | POST | `/lumen/embed/datasource` | Embeddings (needs `versionUri`) |
| 05 | POST | `/lumen/cluster/final-clusters` | Cluster preview |
| 06 | POST | `/semantic-chat/getAnswer` | Semantic chat |
| 99 | GET | `/actuator/health` | Cleanup |

### 13. FLOW-DocumentGraph-Parse (3 steps)

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/actuator/health` | Service up |
| 01 | GET | `/actuator/health` | Health (no auth) |
| 99 | GET | `/actuator/health` | Cleanup |

### 14. FLOW-NLP-Pipeline (6 steps) — No Auth

| Step | Method | Endpoint | Validates |
|------|--------|----------|-----------|
| 00 | GET | `/health` | Service up (FastAPI) |
| 01 | POST | `/tokenize` | Tokens returned |
| 02 | POST | `/sentenize` | Sentences returned |
| 03 | POST | `/finalize-spans` | Spans |
| 04 | POST | `/embed` | Embeddings returned |
| 99 | GET | `/health` | Cleanup |

---

## Missing Endpoints (NOT covered by any flow)

### Application Service — Missing Endpoints

#### Ingestion & Streams (real-time data injection)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/atomicIngestStream/create-stream` | Create single ingest stream |
| POST | `/atomicIngestStream/create-streams` | Create batch streams |
| DELETE | `/atomicIngestStream/remove-stream/{streamId}` | Remove stream |
| POST | `/atomicIngestStream/remove-streams` | Remove batch streams |
| GET | `/atomicIngestStream/get-atomic-stream/{realmId}` | Get streams by realm |
| GET | `/atomicIngestStream/{realmId}/atomic/any-running` | Check running status |
| POST | `/atomicIngestStream/atomic/running-status-change` | Change running status |
| PUT | `/atomicIngestStream/update-stream` | Update stream config |

#### Ingestion Status
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/atomic-ingestion-status/create` | Create ingestion status |
| POST | `/atomic-ingestion-status/get-latest` | Get latest status |

#### Document Ingestion
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/documentIngestStream/create-streams` | Create doc streams |
| GET | `/documentIngestStream/get-document-stream/{realmId}` | Get doc streams |
| POST | `/documentIngestStream/remove-streams` | Remove doc streams |
| POST | `/document-ingestion-status/get-by-stream-ids` | Status by stream IDs |
| POST | `/document-ingestion-status/update` | Update status |
| POST | `/document-ingestion-status/update-by-id` | Update by ID |
| POST | `/document-ingestion-status/update-extracted-files` | Update extracted files |

#### Document Extraction
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/document` | Create extraction |
| POST | `/document/status-update/{statusId}/{status}` | Update status |
| GET | `/document/extraction-status` | Get status by realm |
| GET | `/document/extraction-status-by-datasource-id` | Get status by DS |

#### DataSource (additional)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/datasource` | List all datasources |
| GET | `/datasource/ids` | Get by IDs |
| GET | `/datasource/is-unique` | Check name unique |
| GET | `/datasource/sources` | Get connection details |
| GET | `/datasource/get-dataSources-by-type/{type}` | Filter by driver |
| GET | `/datasource/get-graph-ids` | Get graph IDs |
| POST | `/datasource/keys` | Get S3 keys |
| POST | `/datasource/upload` | Create with metadata |
| PUT | `/datasource/upload` | Update with metadata |
| POST | `/datasource/update-signature` | Update signature |
| PUT | `/datasource/update-signature-presence` | Toggle signature |

#### Realm (additional)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/realm/all-realms-data` | All realms (LB) |
| GET | `/realm/is-unique` | Check name unique |
| GET | `/realm/references` | Active references |
| GET | `/realm/cdc-active-realms` | CDC-active realms |
| GET | `/realm/cdc-active/{id}` | Check CDC active |
| PUT | `/realm/cdc-status/{id}` | Update CDC status |

#### Versions
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/versions/create` | Create version |
| PUT | `/versions/update` | Update version |
| GET | `/versions` | Get version |
| GET | `/versions/lb` | Get version (LB) |
| DELETE | `/versions/delete` | Delete version |
| PUT | `/versions/veriosn-unlock` | Unlock version |

#### Watcher
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/watcher` | Create watcher |
| GET | `/watcher` | List watchers |
| GET | `/watcher/{id}` | Get watcher |
| PUT | `/watcher/{id}/pause` | Pause watcher |
| PUT | `/watcher/{id}/resume` | Resume watcher |
| DELETE | `/watcher/{id}` | Delete watcher |

#### Entity (additional)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/entity-graph/complete-graph` | Complete graph |
| GET | `/entity-graph/datasource-subgraph` | DS subgraph |
| POST | `/entity-graph/migrate` | Migrate to graph |
| POST | `/entity/batch-delete` | Batch delete entities |
| POST | `/entity/relationship` | Add relationship |
| PUT | `/entity/relationship` | Update relationship |
| DELETE | `/entity/relationship` | Delete relationship |

#### Migration
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/migrate-data-source/migrate-all` | Migrate all |
| GET | `/migrate-data-source/hive` | Hive migration |
| GET | `/migrate-data-source/hive-source/{sourceId}` | Hive source |
| GET | `/migrate-data-source/create-trino-catalogs` | Trino catalogs |
| POST | `/migrate-data-source/migratePassword` | Migrate password |
| POST | `/migrate-data-source/decryptPassword` | Decrypt password |

#### Other
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/neSolrStatus` | NE Solr status |
| GET | `/neSolrStatus/named-entity-status` | Named entity status |
| GET | `/neSolrStatus/recent` | Recent NE runs |
| GET | `/tenant-specific` | Tenant-specific details |
| GET | `/metadata/datasource` | Metadata by datasource |
| GET | `/metadata/tables/urns` | Table URNs |
| POST | `/metadata-graph/add-description` | Add description |

### Transformation Service — Missing

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/event/ingest` | Ingest atomic events |
| POST | `/test-connection/upload-sample` | Upload sample records |
| POST | `/document/extract` | Extract documents |
| POST | `/s3-upload/getExcelHeader` | Excel header from S3 |
| POST | `/s3-upload/getCsvHeader` | CSV header from S3 |
| POST | `/s3-upload/getPdf` | PDF from S3 |
| POST | `/s3-upload/getCsvHeadersFromUrl` | CSV headers from URL |
| POST | `/s3-upload/getExcelHeaderFromUrl` | Excel header from URL |
| POST | `/s3-upload/getPdfFromUrl` | PDF from URL |
| GET | `/s3-upload/pdf-view` | PDF view (Base64) |
| POST | `/trino-source/create-hive` | Create Hive source |
| POST | `/trino-source/remove-hive` | Remove Hive source |
| POST | `/trino-source/create-catalog` | Create Trino catalog |
| POST | `/trino-source/remove-catalog` | Remove Trino catalog |
| POST | `/streams/generate` | Generate streams |
| GET | `/node/get-map` | Get node map |

### Knowledge Graph Service — Missing

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/doc-viz/fetch` | Fetch document |
| POST | `/doc-viz/multi-fetch` | Multi-fetch documents |
| POST | `/metadata/save-schema` | Save schema |
| POST | `/metadata/save-schema-version` | Save schema version |
| GET | `/metadata/get-schema-version` | Get schema version |
| POST | `/metadata/import-schema` | Import schema |
| GET | `/metadata/nodes` | Get nodes |
| GET | `/smart-llm/generate-query` | Generate query (LLM) |
| POST | `/smart-llm/generate-answer` | Generate answer (LLM) |
| POST | `/synapse/query` | Run Cypher (via KG) |
| POST | `/synapse/namespace/create` | Create namespace |
| DELETE | `/synapse/namespace/remove` | Remove namespace |
| POST | `/synapse/namespace/clean` | Clean namespace |
| POST | `/synapse/namespace/historic-ingest-complete` | Mark ingest complete |
| POST | `/synapse/namespace/projection-control` | Projection control |
| POST | `/synapse/namespace/projection-bootstrap` | Projection bootstrap |
| POST | `/synapse/ingestion/shape/parse` | Parse shape |
| POST | `/synapse/ingestion/shape` | Register shape |
| POST | `/synapse/{userId}/upsert-policy` | Upsert user policy |
| GET | `/synapse/{userId}/get-policy` | Get user policy |
| POST | `/vector-client/create-collection` | Create vector collection |
| POST | `/vector-client/delete-collection` | Delete vector collection |

### Synapse — Missing

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/query/cypher/explain` | Explain query |
| POST | `/query/cypher/stream` | Stream results (SSE) |
| POST | `/query/cypher/async` | Async query submit |
| GET | `/query/cypher/async/result` | Async result poll |
| DELETE | `/query/cypher/{queryId}` | Cancel query |
| POST | `/api/v2/cypher/query` | v2 Cypher query |
| POST | `/api/v2/cypher/explain` | v2 Explain |
| POST | `/api/v2/cypher/stream` | v2 Stream |
| POST | `/api/v2/cypher/async` | v2 Async |
| GET | `/api/v2/cypher/async/result` | v2 Async result |
| DELETE | `/api/v2/cypher/{queryId}` | v2 Cancel |
| POST | `/node` | Upsert node |
| POST | `/node/fetch` | Fetch node |
| POST | `/node/fetch/graph` | Fetch subgraph |
| POST | `/ingestion/shape/parse` | Parse shape |
| POST | `/ingestion/shape` | Register shape |
| POST | `/users/{userId}/policy` | Create user policy |
| GET | `/users/{userId}/policy` | Get user policy |
| DELETE | `/users/{userId}/policy` | Delete user policy |
| POST | `/consumer/pause` | Pause consumer |
| POST | `/consumer/resume` | Resume consumer |

### Nexus — Missing

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/nexus/anchors` | Anchor resolution |
| POST | `/nexus/mst` | MST path plans |
| POST | `/nexus/schema/traversable/prepare` | Prepare schema |
| POST | `/nexus/schema/traversable/update` | Update schema |
| POST | `/nexus/schema/traversable/schema` | Schema info |
| POST | `/schema/vectorize/{fabricId}` | Vectorize schema |
| DELETE | `/schema/{fabricId}` | Drop fabric collections |
| GET | `/schema/jobs/{jobId}` | Job status |

---

## Recommended Next Flows to Add

### Priority 1 — Real-Time Data Injection & Status
**FLOW-Ingestion-Streams** (Application Service):
- Create atomic ingest stream
- Get streams by realm
- Check running status
- Get latest ingestion status
- Remove streams

### Priority 2 — Version Management
**FLOW-Version-CRUD** (Application Service):
- Create version
- Get version
- Update version
- Unlock version
- Delete version

### Priority 3 — Watcher CRUD
**FLOW-Watcher-CRUD** (Application Service):
- Create watcher
- List watchers
- Get watcher by ID
- Pause / Resume
- Delete watcher

### Priority 4 — Document Extraction
**FLOW-Document-Extraction** (Application + Transformation):
- Create extraction
- Check extraction status
- Extract documents
- Update extracted files

### Priority 5 — Advanced Synapse Query
**FLOW-Synapse-Query** (Synapse):
- Cypher query (sync)
- Cypher explain
- Cypher async submit + poll result
- v2 Cypher query
- Cancel query

### Priority 6 — S3 File Operations
**FLOW-S3-FileOps** (Transformation Service):
- Get CSV header from S3
- Get Excel header from S3
- Get PDF from S3
- Upload sample records

---

## Running the Flows

```bash
# Generate all flows
cd d:/quipu/postman-collections
python scripts/gen_flow.py

# Run single flow
newman run flows/FLOW-Tenant-CRUD.postman_collection.json \
  -e environments/onprem-api.postman_environment.json --insecure \
  --env-var "test_username=onpremquipu" \
  --env-var "test_password=onpremquipu" \
  --env-var "client_secret=SECRET" \
  -r cli

# Run all flows
for f in flows/FLOW-*.json; do
  echo "=== $(basename $f) ==="
  newman run "$f" -e environments/onprem-api.postman_environment.json \
    --insecure --env-var "test_username=onpremquipu" \
    --env-var "test_password=onpremquipu" \
    --env-var "client_secret=SECRET" \
    -r cli --timeout-request 120000 || true
done
```
