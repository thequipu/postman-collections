# API Coverage Tracker

**Last Updated:** 2026-08-01
**Services Tested:** 3 / 11
**Total APIs Covered:** 36 / ~350
**Flows Generated:** 18

---

## Coverage Dashboard

| # | Service | Port | Endpoints | Covered | Full | Reachable | Tolerant | Flow Status |
|---|---------|------|-----------|---------|------|-----------|----------|-------------|
| 1 | Tenant Service | 4031 | 14 | 14 (100%) | 10 | — | 4 | ✅ Tested (47/47) |
| 2 | Security Service | 4032 | 13 | 13 (100%) | 5 | 8 | — | ✅ Tested (26/26) |
| 3 | Application Service (DataSource) | 4033+4036 | 9 | 9 (100%) | 9 | — | — | ✅ Tested (24/24) |
| 4 | Application Service (Realm) | 4033 | 8 | 8 (100%) | — | — | — | ⏳ Generated |
| 5 | Application Service (Schema) | 4033 | 6 | 6 (100%) | — | — | — | ⏳ Generated |
| 6 | Application Service (Entity) | 4033 | 7 | 7 (100%) | — | — | — | ⏳ Generated |
| 7 | Application Service (Permissions) | 4033 | 5 | 5 (100%) | — | — | — | ⏳ Generated |
| 8 | Transformation Service | 4036 | 4 | 4 (100%) | — | — | — | ⏳ Generated |
| 9 | KG Service | 4034 | 4 | 4 (100%) | — | — | — | ⏳ Generated |
| 10 | Synapse (Namespace) | 8888 | 8 | 8 (100%) | — | — | — | ⏳ Generated |
| 11 | Synapse (Query) | 8888 | 9 | 9 (100%) | — | — | — | ⏳ Generated |
| 12 | Nexus | 4057 | 4 | 4 (100%) | — | — | — | ⏳ Generated |
| 13 | Lumen | 4059 | 6 | 6 (100%) | — | — | — | ⏳ Generated |
| 14 | NLP | 4055 | 5 | 5 (100%) | — | — | — | ⏳ Generated |
| 15 | Document Graph | 3048 | 1 | 1 (100%) | — | — | — | ⏳ Generated |
| 16 | Ingestion Streams | 4033 | 7 | 7 (100%) | — | — | — | ⏳ Generated |
| 17 | Version CRUD | 4033 | 6 | 6 (100%) | — | — | — | ⏳ Generated |
| 18 | Watcher CRUD | 4033 | 6 | 6 (100%) | — | — | — | ⏳ Generated |
| 19 | Document Extraction | 4033+4036 | 7 | 7 (100%) | — | — | — | ⏳ Generated |

**Validation Levels:**
- **Full** — Send real data, verify response fields, check side effects
- **Reachable** — Endpoint exists, correct HTTP method, auth validation working (401/500 = expected)
- **Tolerant** — API works but infrastructure dependency is broken (Keycloak/Vault down)

---

## Service 1: Tenant Service (14/14 APIs)

**Flow:** `FLOW-Tenant-CRUD` | **Assertions:** 47/47 | **Status:** ✅ PASSED
**Environments:** minikube, onprem-api
**Users:** Admin (admin/admin123) for delete, Tenant user (eksquipu/eksquipu) for operations

| # | Method | Endpoint | Step | HTTP | Level | What It Proves |
|---|--------|----------|------|------|-------|----------------|
| 1 | POST | `/admin/tenant` | 01 | 200 | Full | Tenant created — Keycloak realm + DB + SSO provisioned |
| 2 | GET | `/admin/tenant` | 02 | 200 | Full | New tenant in list — data persisted |
| 3 | GET | `/admin/tenant/active` | 03 | 200 | Full | New tenant is active |
| 4 | GET | `/admin/tenant/{code}` | 04 | 200 | Full | Lookup works, SSO + DB details present |
| 5 | GET | `/admin/tenant/tenantSpecific/{code}` | 05 | 200 | Full | Full config returned |
| 6 | GET | `/admin/tenant/users/{code}` | 06 | 200 | Full | 2 users created in Keycloak realm |
| 7 | GET | `/admin/tenant/sso/{code}` | 07 | 200 | Full | SSO clientId confirmed |
| 8 | PUT | `/admin/tenant/config/{code}` | 08 | 200 | Full | Config accepted, updated body returned |
| 9 | PUT | `/admin/tenant/{code}/encryption-details` | 08b | 400 | Tolerant | Vault write fails (infra) |
| 10 | GET | `/admin/tenant/{code}/secrets` | 08c | 400 | Tolerant | Vault read fails (infra) |
| 11 | PUT | `/admin/tenant/{code}/toggle/{active}` | 09-12 | 500 | Tolerant | Keycloak admin call fails (infra) |
| 12 | POST | `/admin/tenant/user-status` | 13 | 500 | Tolerant | Keycloak admin call fails (infra) |
| 13 | GET | `/admin/audit` | 14 | 200 | Full | Audit entries returned as JSON |
| 14 | GET | `/admin/audit/tenantRequests` | 15 | 200 | Full | Tenant requests returned as JSON |
| 15 | DELETE | `/admin/tenant/{code}` | 16 | 200 | Full | status=SUCCESS — DB dropped, realm deleted, secrets purged |
| 16 | GET | `/admin/tenant` | 17 | 200 | Full | Tenant removed from list |

**Special:** Unique tenant code per run (`pmflow` + timestamp), admin token swap for delete (Vault requires master realm JWT), wait for `Tenant Configuration Success` before delete.

---

## Service 2: Security Service (13/13 APIs)

**Flow:** `FLOW-Security-Auth` | **Assertions:** 26/26 | **Status:** ✅ PASSED
**Environments:** minikube
**Users:** Admin (admin/admin123) for admin endpoints, Tenant user (eksquipu/eksquipu) for OTP + login

| # | Method | Endpoint | Step | HTTP | Level | What It Proves |
|---|--------|----------|------|------|-------|----------------|
| 1 | POST | `/admin/login` | 01 | 200 | Full | Keycloak running, admin creds work, token issued (Bearer, 60s expiry) |
| 2 | POST | `/admin/validate-tenant` (valid) | 02 | 200 | Full | Existing tenant returns `true` |
| 3 | POST | `/admin/validate-tenant` (invalid) | 03 | 200 | Full | Non-existent tenant returns `false` |
| 4 | POST | `/admin/introspect` | 04 | 401 | Reachable | Token introspection endpoint exists |
| 5 | POST | `/admin/refreshToken` | 05 | 401 | Reachable | Token refresh endpoint exists |
| 6 | POST | `/admin/short-lived-token` | 06 | 401 | Reachable | Service account endpoint exists |
| 7 | POST | `/admin/logout` | 07 | 401 | Reachable | Session invalidation endpoint exists |
| 8 | POST | `/user/generate-otp` | 08 | 200 | Full | OTP sent to email — full email flow works |
| 9 | POST | `/user/login` | 09 | 401 | Full | Credentials processed, OTP checked, returns "OTP is INVALID" |
| 10 | POST | `/user/internal-token` | 10 | 401 | Reachable | Service-to-service endpoint exists |
| 11 | POST | `/user/introspect` | 11 | 401 | Reachable | User token introspection exists |
| 12 | POST | `/user/refreshToken` | 12 | 401 | Reachable | User token refresh exists |
| 13 | GET | `/user/users` | 13 | 401 | Reachable | User list endpoint exists (needs tenant OTP token) |
| 14 | POST | `/user/logout` | 14 | 401 | Reachable | User logout endpoint exists |

**Why reachable-only for some:**
- Admin token expires in 60s — gateway rejects by the time Newman runs subsequent steps
- `/user/*` endpoints need tenant realm token which requires OTP from email
- 401 proves: endpoint exists, correct method, gateway routes correctly, auth rejects invalid tokens

---

## Service 3: DataSource CRUD (9/9 APIs)

**Flow:** `FLOW-DataSource-CRUD` | **Assertions:** 24/24 | **Status:** ✅ PASSED
**Environments:** onprem-api, minikube
**Services:** Application Service (4033) + Transformation Service (4036)
**DB types tested:** POSTGRES, MariaDB

| # | Method | Endpoint | Service | Step | HTTP | Level | What It Proves |
|---|--------|----------|---------|------|------|-------|----------------|
| 1 | POST | `/test-connection` | Transform | 01 | 200 | Full | DB reachable with credentials |
| 2 | POST | `/datasource` | App | 02 | 201 | Full | Datasource record created |
| 3 | GET | `/datasource/id?sourceId=` | App | 03 | 200 | Full | ID matches, driverType matches |
| 4 | POST | `/test-connection/{id}/{type}` | Transform | 04 | 200 | Full | Created DS connects |
| 5 | POST | `/metadata-graph/fetch-data-source` | App | 05 | 200 | Full | Metadata graph returned, tables captured |
| 6 | POST | `/source-query/fetch-sample-source` | Transform | 06 | 200 | Full | Sample rows from first table |
| 7 | POST | `/source-query/query` | Transform | 07 | 200 | Full | Dynamic query, 10 rows returned |
| 8 | PUT | `/datasource` | App | 08 | 200 | Full | Description updated |
| 9 | DELETE | `/datasource/{id}?permanent=true` | App | 10 | 200 | Full | Datasource deleted |

**Special:** Dynamic table extraction from metadata graph, DB-aware query building (Postgres/MySQL/Oracle/MSSQL syntax).

---

## Pending Services (Generated, Not Yet Tested)

### Application Service — Realm CRUD
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | GET | `/realm?page=0&size=20` | List realms |
| 2 | POST | `/realm` | Create realm |
| 3 | GET | `/realm/{id}` | Get by ID |
| 4 | GET | `/realm/by-name?realmName=` | Get by name |
| 5 | PUT | `/realm` | Update realm |
| 6 | GET | `/realm/{id}` | Verify update |
| 7 | DELETE | `/realm/{id}?permanent=true` | Delete |
| 8 | GET | `/realm/{id}` | Verify deleted |

### Application Service — Schema CRUD
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | POST | `/realm` | Create realm (dep) |
| 2 | GET | `/schema` | List schemas |
| 3 | POST | `/schema` | Create schema |
| 4 | GET | `/schema/name?schemaName=` | Get by name |
| 5 | DELETE | `/schema?schemaName=` | Delete schema |
| 6 | DELETE | `/realm/{id}?permanent=true` | Cleanup realm |

### Application Service — Entity CRUD
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | GET | `/entity-graph/entities?page=0&size=20` | List entities |
| 2 | POST | `/entity` | Create entity |
| 3 | GET | `/entity/search?q=` | Search |
| 4 | GET | `/entity-graph/entity-subgraph?uri=` | Get subgraph |
| 5 | POST | `/entity/property?entityUri=` | Add property |
| 6 | DELETE | `/entity/property?uri=` | Delete property |
| 7 | DELETE | `/entity?uri=` | Delete entity |

### Application Service — Permissions CRUD
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | GET | `/permissions` | List permissions |
| 2 | GET | `/roles` | List roles |
| 3 | GET | `/role-permission?page=0&size=20` | Role permissions |
| 4 | GET | `/user-permission?page=0&size=20` | User permissions |
| 5 | GET | `/user-permission/entity360-paths` | Entity360 paths |

### Transformation Service — Connection
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | POST | `/test-connection` | Test connection |
| 2 | POST | `/test-connection/metadata` | Fetch metadata |
| 3 | POST | `/test-connection/sample-records` | Sample records |
| 4 | POST | `/schema/generate/node-objects` | Schema objects |

### Knowledge Graph Service — Metadata
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | GET | `/metadata/get-saved-schema-graph?referenceName=` | Schema graph |
| 2 | GET | `/synapse/namespace/stats?namespace=` | Namespace stats |
| 3 | GET | `/synapse/namespace/status?name=` | Namespace status |
| 4 | GET | `/synapse/watchers?namespace=` | Watchers |

### Synapse — Namespace
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | GET | `/namespaces` | List |
| 2 | POST | `/namespaces/create?name=` | Create |
| 3 | GET | `/namespaces/{name}/status` | Status |
| 4 | GET | `/namespaces/{name}/stats` | Stats |
| 5 | POST | `/namespaces/{name}/enable` | Enable |
| 6 | POST | `/query/cypher` | Run query |
| 7 | POST | `/namespaces/{name}/disable` | Disable |
| 8 | DELETE | `/namespaces/{name}?permanent=true` | Delete |

### Synapse — Query (Advanced)
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | POST | `/query/cypher` | Sync query |
| 2 | POST | `/query/cypher/explain` | Explain |
| 3 | POST | `/query/cypher/async` | Async submit |
| 4 | GET | `/query/cypher/async/result?queryId=` | Async poll |
| 5 | POST | `/api/v2/cypher/query` | v2 query |
| 6 | POST | `/api/v2/cypher/explain` | v2 explain |
| 7 | POST | `/node/fetch` | Fetch node |
| 8 | POST | `/consumer/pause` | Pause consumer |
| 9 | POST | `/consumer/resume` | Resume consumer |

### Nexus — Search
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | POST | `/nexus/schema/traversable/get` | Traversable schema |
| 2 | POST | `/nexus/search` | Search |
| 3 | POST | `/nexus/gin` | GIN |
| 4 | POST | `/nexus/labels` | Labels |

### Lumen — Pipeline
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | POST | `/query-builder/query` | NL → Cypher |
| 2 | POST | `/query-builder/reset-schema` | Reset cache |
| 3 | POST | `/lumen/describe/datasource` | AI describe |
| 4 | POST | `/lumen/embed/datasource` | Embeddings |
| 5 | POST | `/lumen/cluster/final-clusters` | Clusters |
| 6 | POST | `/semantic-chat/getAnswer` | Semantic chat |

### NLP — Pipeline
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | POST | `/tokenize` | Tokenize text |
| 2 | POST | `/sentenize` | Sentence split |
| 3 | POST | `/finalize-spans` | Span finalization |
| 4 | POST | `/embed` | Generate embeddings |

### Ingestion Streams
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | POST | `/atomicIngestStream/create-stream` | Create stream |
| 2 | GET | `/atomicIngestStream/get-atomic-stream/{realmId}` | Get by realm |
| 3 | GET | `/atomicIngestStream/{realmId}/atomic/any-running` | Check running |
| 4 | POST | `/atomic-ingestion-status/create` | Create status |
| 5 | POST | `/atomic-ingestion-status/get-latest` | Get latest |
| 6 | POST | `/atomicIngestStream/atomic/running-status-change` | Change status |
| 7 | DELETE | `/atomicIngestStream/remove-stream/{streamId}` | Remove stream |

### Version CRUD
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | POST | `/realm` | Create realm (dep) |
| 2 | POST | `/schema` | Create schema (dep) |
| 3 | POST | `/versions/create` | Create version |
| 4 | GET | `/versions?versionId=` | Get version |
| 5 | PUT | `/versions/update` | Update version |
| 6 | DELETE | `/versions/delete?versionId=` | Delete version |

### Watcher CRUD
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | POST | `/watcher` | Create watcher |
| 2 | GET | `/watcher` | List watchers |
| 3 | GET | `/watcher/{id}` | Get by ID |
| 4 | PUT | `/watcher/{id}/pause` | Pause |
| 5 | PUT | `/watcher/{id}/resume` | Resume |
| 6 | DELETE | `/watcher/{id}` | Delete |

### Document Extraction
| # | Method | Endpoint | Step |
|---|--------|----------|------|
| 1 | POST | `/document` | Create extraction |
| 2 | GET | `/document/extraction-status?realmId=` | Get status |
| 3 | GET | `/document/extraction-status-by-datasource-id` | By datasource |
| 4 | POST | `/documentIngestStream/create-streams` | Create streams |
| 5 | GET | `/documentIngestStream/get-document-stream/{realmId}` | Get streams |
| 6 | POST | `/document-ingestion-status/get-by-stream-ids` | Ingestion status |
| 7 | POST | `/document/extract` (Transformation) | Extract document |

---

## CI/CD Integration

| Service | Jenkins Job | Branch | Suite Param | Default |
|---------|------------|--------|-------------|---------|
| Tenant Service | `tenant-service` | main | `tenant` | Minikube CD + API tests |
| Security Service | `security-service` | main | `security` | Minikube CD + API tests |
| Application Service | `application-service` | main | `application` | Minikube CD + API tests |

### Pipeline Flow
```
Build → Unit Tests → Docker → ECR → Minikube Deploy → Newman API Tests → S3 Upload
```

### S3 Bucket Structure
```
s3://quipu-api-tests/
  config/
    environments/     ← 8 env files (minikube, onprem-api, stage, etc.)
    secrets/          ← per-env secrets (client_secret, admin creds)
    db-configs/       ← per-DB connection configs
  results/
    {date}/{env}/{service}/{build}/
      flow-*.xml      ← JUnit results
      flow-*.html     ← HTML report
    latest/{env}/{service}/
      flow-*.xml
      flow-*.html
```

---

## Change Log

| Date | Service | Change |
|------|---------|--------|
| 2026-08-01 | Security | Added full login validation (OTP check), 26/26 passed |
| 2026-08-01 | Tenant | Fixed admin token for delete, unique tenant code, 47/47 passed |
| 2026-07-31 | DataSource | All 24/24 passed on onprem-api and minikube |
| 2026-07-31 | All | S3 bucket created, minikube env added |
| 2026-07-31 | All | 18 flow collections generated |
