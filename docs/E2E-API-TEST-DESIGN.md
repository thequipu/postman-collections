# Quipu API — End-to-End Automation: Design & Implementation Plan

**Status:** Chosen architecture = **Merged (§0)** · **Owner:** karthik · **Date:** 2026-07-08
**Scope:** All 13 Quipu Postman collections + cross-service E2E flows, runnable locally, in Postman, and in CI, across `local` / `onprem` / `stage` / `pre-prod` / `prod`.

---

## 0. Chosen Architecture — Merged Plan

We merge the two proposals along one principle:

> **Author the intelligence, generate the boilerplate.**

- **Plan 2 (Postman-native flows) is the primary layer** — humans author `FLOW –`/`SMOKE –` suites in Postman with real assertions, chaining, polling, and teardown. This is where test *meaning* lives.
- **Plan 1 contributes only its config-generation** — a small config generates the repetitive, error-prone parts: environment files, baseline (L0) tests on the reference collections, and CI wiring. We **drop** Plan 1's heavy `orchestrate.js` cross-collection runner and generated flow collections (Postman does chaining natively and better).

### Division of labor

| Concern | **GENERATED** (from Plan 1 config) | **AUTHORED** (Plan 2, in Postman) |
|---|---|---|
| Environments (`local/onprem/stage/pre-prod/prod`) | ✅ from `config/services.json` + `environments.json` — never hand-edit | — |
| Variable contract (identical keys everywhere) | ✅ enforced by the generator | consumed by every request |
| Baseline L0 tests on Layer-1 reference collections (status<400, valid JSON, no 5xx) | ✅ injected idempotently | — |
| Feature E2E flows (`FLOW –`), ordered steps, business assertions, chaining, polling, teardown | — | ✅ hand-built in Postman |
| Prod-safe smoke (`SMOKE –`), read-only | — | ✅ hand-built |
| Centralized Keycloak auth + `allow_destructive` guard | — | ✅ collection-level scripts |
| Running | `newman run` per suite/env (npm scripts) | Postman Runner (one-click) **or** the same npm/Newman scripts |
| CI gate | Jenkins + Vault (primary); GitHub Actions optional PR smoke | flows + baselines both run here |

### How the two halves meet
Both halves consume the **same generated environment files and the same variable contract**. A generated baseline run and a hand-authored flow run use identical `{{service_base_url}}` / `{{access_token}}` / `allow_destructive` — so nothing diverges. The config generates *plumbing*; Postman holds *behavior*.

### Pipeline
```
config/ ──(generator)──▶ environments/*.json           ┐
config/ ──(injector)───▶ Layer-1 baseline L0 tests     ├─▶ newman / Postman Runner ─▶ reports ─▶ Jenkins gate
humans  ──(Postman)────▶ flows/FLOW–*, flows/SMOKE–*    ┘
```

### What this supersedes below
§4–§9 describe Plan 1's full config-and-orchestrator design. Under the merged plan, **keep**: the config model for services/environments (§4.1–4.2) and baseline injection (§7). **Drop / demote to "not building"**: `orchestrate.js` journey runner (§8), generated `e2e/` collections, and `journeys.json` as an execution format (§4.4) — flows are authored in Postman instead. CI (§10) stays but **Jenkins is primary** (§8 of the pasted flow plan), GitHub Actions optional.

---

## 1. Goals & Principles

**Goals**
- Turn the existing Postman collections (contract docs, no assertions today) into an automated regression + E2E suite.
- One command runs a service, a group, or a full cross-service journey against any environment.
- Zero per-request copy-paste: tests and config are **generated from a single source of truth**.

**Principles**
1. **Config over code.** Services, ports, environments, credentials, and journeys live in JSON config. Adding a service or environment is a config edit, not a code change.
2. **Generic by default, specific where it pays.** Every request gets baseline assertions for free; deep assertions are added only where they add signal.
3. **Idempotent & self-cleaning.** Journeys create → verify → delete their own data so they can run repeatedly against shared `dev`/`staging`.
4. **Secrets never in git.** Real credentials come from git-ignored files or CI secrets; the collections carry only variable references.
5. **Deterministic chaining.** State flows between steps through an exported Postman environment, not hidden globals.

---

## 2. Architecture Overview

```
                    ┌──────────────────────────────────────────────┐
                    │                config/ (source of truth)      │
                    │  services.json  environments.json  journeys.json│
                    │  credentials.<env>.json (git-ignored)  data/*.csv│
                    └───────────────┬──────────────────────────────┘
                                    │  (read by build + run tooling)
              ┌─────────────────────┼─────────────────────────┐
              ▼                     ▼                          ▼
     ┌────────────────┐   ┌───────────────────┐      ┌──────────────────┐
     │  build:env     │   │  build:tests      │      │  orchestrate.js  │
     │ generate       │   │ inject baseline   │      │ resolve run plan │
     │ environments/  │   │ collection-level  │      │ chain collections│
     │ *.json         │   │ test events       │      │ export env state │
     └───────┬────────┘   └─────────┬─────────┘      └────────┬─────────┘
             │                      │                         │
             └──────────────┬───────┴─────────────────────────┘
                            ▼
                    ┌───────────────┐        ┌───────────────────────────┐
                    │    newman     │──────▶ │ reports/ (htmlextra + JUnit)│
                    │  (per run)    │        └───────────────────────────┘
                    └───────────────┘
                            ▲
                            │ invoked by
             ┌──────────────┴───────────────┐
             │ npm scripts / Docker / CI (Actions matrix) │
             └────────────────────────────────────────────┘
```

**Flow:** `config/` is read by (a) a small build step that generates `environments/*.json` and injects baseline test events into the collections, and (b) an orchestrator that resolves a "run plan" (which collections, in what order, chaining state) and drives Newman. Reports are emitted per run and aggregated in CI.

---

## 3. Directory Layout

```
postman-collections/
├── collections/                 # existing 13 (unchanged shape; baseline tests injected by build)
├── e2e/                         # cross-service journey collections (generated or hand-authored)
├── environments/                # GENERATED per env from config — do not hand-edit
│   ├── local.postman_environment.json
│   ├── dev.postman_environment.json
│   └── staging.postman_environment.json
├── config/
│   ├── services.json            # service registry: name, collection file, port/path, token var
│   ├── environments.json        # per-env host + non-secret defaults (tenantId, realm, thresholds)
│   ├── journeys.json            # ordered cross-service scenarios
│   ├── ci.json                  # CI: runner per env, suites, priority gating
│   ├── credentials.example.json # template (committed)
│   ├── credentials.local.json   # real secrets (GIT-IGNORED)
│   └── data/                    # iteration data for data-driven runs (*.csv / *.json)
├── scripts/
│   ├── build-env.js             # config → environments/*.json
│   ├── inject-tests.js          # config + snippets → collection-level test events
│   ├── orchestrate.js           # run plan resolver + newman driver (journeys)
│   └── snippets/                # reusable pm.* test/prerequest snippets
│       ├── baseline.test.js
│       └── token-fanout.prerequest.js
├── reports/                     # GIT-IGNORED newman output (html, xml, json)
├── package.json                 # npm scripts (per-service, group, e2e)
├── Dockerfile  docker-compose.yml
├── .github/workflows/api-tests.yml
├── .gitignore
└── docs/E2E-API-TEST-DESIGN.md  # this file
```

---

## 4. The Config Model (the generic core)

Everything generic derives from four files.

### 4.1 `config/services.json` — service registry

The single place that knows what services exist and how they're addressed. Solves the **token-name drift** and **per-service base URL** problems.

```json
{
  "services": [
    { "key": "security",    "name": "Quipu Security Service", "collection": "Quipu Security Service.postman_collection.json",
      "port": 3032, "basePath": "",       "tokenVar": "accessToken", "needsAuth": false, "needsTenant": true },
    { "key": "tenant",      "name": "Quipu Tenant Service",   "collection": "Quipu Tenant Service.postman_collection.json",
      "port": 3031, "basePath": "/admin", "tokenVar": "token",       "needsAuth": true,  "needsTenant": true },
    { "key": "app",         "name": "Quipu Application Service","collection": "Quipu Application Service.postman_collection.json",
      "port": 3033, "basePath": "",       "tokenVar": "token",       "needsAuth": true,  "needsTenant": true },
    { "key": "kg",          "name": "Quipu Knowledge Graph Service", "collection": "Quipu Knowledge Graph Service.postman_collection.json",
      "port": 3034, "basePath": "",       "tokenVar": "token",       "needsAuth": true,  "needsTenant": true },
    { "key": "instance",    "name": "Quipu Instance Manager", "collection": "Quipu Instance Manager.postman_collection.json",
      "port": 3035, "basePath": "",       "tokenVar": "token",       "needsAuth": true,  "needsTenant": true },
    { "key": "transform",   "name": "Quipu Transformation Service", "collection": "Quipu Transformation Service.postman_collection.json",
      "port": 3036, "basePath": "",       "tokenVar": "token",       "needsAuth": true,  "needsTenant": true },
    { "key": "llm",         "name": "LLM Service",            "collection": "LLM Service.postman_collection.json",
      "port": 3038, "basePath": "",       "tokenVar": "bearerToken", "needsAuth": true,  "needsTenant": true },
    { "key": "nexus",       "name": "Quipu Nexus",            "collection": "Quipu Nexus.postman_collection.json",
      "port": 3040, "basePath": "",       "tokenVar": "token",       "needsAuth": true,  "needsTenant": true },
    { "key": "loadbalancer","name": "Quipu Load Balancer Service", "collection": "Quipu Load Balancer Service.postman_collection.json",
      "port": 4040, "basePath": "",       "tokenVar": "token",       "needsAuth": true,  "needsTenant": true },
    { "key": "docgraph",    "name": "Quipu Document Graph",   "collection": "Quipu Document Graph.postman_collection.json",
      "port": 3048, "basePath": "",       "tokenVar": null,          "needsAuth": false, "needsTenant": false },
    { "key": "nlp",         "name": "Quipu NLP",              "collection": "Quipu NLP.postman_collection.json",
      "port": 8009, "basePath": "",       "tokenVar": null,          "needsAuth": false, "needsTenant": false },
    { "key": "synapse",     "name": "Quipu Synapse",          "collection": "Quipu Synapse.postman_collection.json",
      "port": 8001, "basePath": "",       "tokenVar": "token",       "needsAuth": true,  "needsTenant": true },
    { "key": "keycloak",    "name": "Access_Token",           "collection": "Access_Token.postman_collection.json",
      "url": "authUrl", "tokenVar": null, "needsAuth": false, "needsTenant": false }
  ]
}
```

`build-env.js` turns each `{key, port, basePath}` into a `<key>BaseUrl` variable (e.g. `securityBaseUrl`) per environment, so a cross-service journey references `{{appBaseUrl}}`, `{{nexusBaseUrl}}`, etc., with no name collisions.

### 4.2 `config/environments.json` — per-target, non-secret

```json
{
  "environments": {
    "local":   { "host": "http://localhost", "scheme": "byPort", "authUrl": "https://ui-login.thequipu.in", "tenantId": "onpremquipu", "realm": "onpremquipu", "maxResponseMs": 3000 },
    "dev":     { "host": "https://dev.thequipu.in", "scheme": "byPathPrefix", "authUrl": "https://ui-login.thequipu.in", "tenantId": "TODO", "realm": "TODO", "maxResponseMs": 5000 },
    "staging": { "host": "https://staging.thequipu.in", "scheme": "byPathPrefix", "authUrl": "https://ui-login.thequipu.in", "tenantId": "TODO", "realm": "TODO", "maxResponseMs": 5000 }
  }
}
```

- `scheme: byPort` → `local` builds `http://localhost:3033`.
- `scheme: byPathPrefix` → hosted envs build `https://dev.thequipu.in/app`, `/security`, … (gateway routing). The `key→pathPrefix` map lives in `services.json` too if hosted routing differs from ports. **`TODO`s are the only thing you must fill for dev/staging.**

### 4.3 `config/credentials.<env>.json` — secrets (git-ignored)

```json
{
  "username": "user@example.com",
  "password": "•••",
  "otp": "",                    // filled at runtime or via TOTP step
  "clientId": "onpremquipu-client",
  "clientSecret": "•••",        // moved out of Access_Token collection
  "adminUsername": "•••",
  "adminPassword": "•••"
}
```

A committed `credentials.example.json` documents the shape. CI injects these from repository secrets.

### 4.4 `config/journeys.json` — ordered cross-service scenarios

A journey is a list of steps; each step names a service, a request inside that collection (by folder/name path), what it must assert, and what to capture. This is what makes E2E **declarative**.

```json
{
  "journeys": [
    {
      "key": "onboarding",
      "title": "Tenant onboarding → login → authorized call",
      "steps": [
        { "service": "tenant",   "request": "Create Tenant",          "capture": { "tenantId": "$.id" } },
        { "service": "security", "request": "01 — User Authentication/Login", "expect": { "status": 200, "jsonHas": "access_token" }, "captureToken": true },
        { "service": "app",      "request": "01 — DataSource/Get All DataSources", "expect": { "status": 200, "jsonIsArray": "$" } }
      ]
    },
    {
      "key": "ingest-to-answer",
      "title": "Ingest a source → build graph → NL search → RAG answer",
      "steps": [
        { "service": "app",       "request": "01 — DataSource/Create DataSource", "capture": { "datasourceId": "$.id" } },
        { "service": "app",       "request": "02 — Realm/Create Realm",           "capture": { "realmId": "$.id" } },
        { "service": "app",       "request": "03 — Schema/Create Schema",         "capture": { "schemaId": "$.id" } },
        { "service": "transform", "request": "Run Transformation",                "expect": { "status": 200 } },
        { "service": "synapse",   "request": "Query/Run Cypher",                  "expect": { "status": 200 } },
        { "service": "nexus",     "request": "Search",                            "expect": { "status": 200, "jsonHas": "results" } },
        { "service": "llm",       "request": "Context Question Answer/Get Answer","expect": { "status": 200, "jsonHas": "answer" } }
      ],
      "teardown": [
        { "service": "app", "request": "03 — Schema/Delete Schema" },
        { "service": "app", "request": "02 — Realm/Delete Realm" },
        { "service": "app", "request": "01 — DataSource/Delete DataSource" }
      ]
    }
  ]
}
```

> Request paths above are illustrative — `orchestrate.js` resolves them against the real folder/name tree and fails loudly if a path doesn't exist, so journeys can't silently drift from the collections.

---

## 5. Variable & Token Strategy

- **Base URLs:** generated as `<serviceKey>BaseUrl` per environment. No two services share a var name.
- **Token fan-out:** a shared `prerequest`/`test` snippet, run after any auth response, writes the token into **all three** names so every downstream collection works regardless of which it reads:
  ```js
  const t = pm.response.json().access_token;
  if (t) ['accessToken','token','bearerToken'].forEach(k => pm.environment.set(k, t));
  ```
- **IDs & handoff:** captured with JSONPath into env vars (`datasourceId`, `realmId`, …) and consumed by later steps via `{{datasourceId}}`.
- **Single source of truth for values:** `tenantId`, `realm`, thresholds come from `environments.json`; secrets from `credentials.<env>.json`. Collections never hardcode them.

---

## 6. Test Layers

| Layer | Applied to | Mechanism | Examples |
|---|---|---|---|
| **L0 Baseline** | every request in all 13 | injected **collection-level** `test` event | status < 400; `responseTime < {{maxResponseMs}}`; valid JSON when body present; never 5xx |
| **L1 Auth** | Security/Tenant/Keycloak auth requests | per-request `test` | returns `access_token`; 401 on bad creds; refresh rotates token; token fan-out |
| **L2 Contract** | core CRUD (App 133, Synapse 44, KG 34, Transform 23, …) | per-request `test` + capture | response shape, required fields, created `id` captured, list endpoints return arrays |
| **L3 Journey** | `e2e/` scenarios from `journeys.json` | orchestrated multi-collection run | create→verify→query→answer→teardown, chained via exported env |

**L0 is the leverage point:** one injected collection-level event covers ~290 requests. `inject-tests.js` adds it idempotently (keyed by a marker comment) so re-running the build never duplicates events, and hand-written L1/L2 tests are preserved.

---

## 7. Generic Test Injection (`inject-tests.js`)

- Reads `scripts/snippets/baseline.test.js`, wraps it with a marker (`// @quipu-baseline v1`).
- For each collection: ensures a top-level `event[]` entry `listen:"test"` containing the marked snippet; replaces an existing marked block, leaves everything else untouched.
- Output stays **v2.1.0 schema-compatible** so `.postman/resources.yaml` cloud sync keeps working.
- Runs in CI as a check: if injecting changes a file, the build failed to commit generated tests → fail fast.

---

## 8. Orchestrator & Runner (`orchestrate.js` + npm)

**Per-service (plain Newman):**
```jsonc
// package.json (excerpt)
"scripts": {
  "build":        "node scripts/build-env.js && node scripts/inject-tests.js",
  "test:security":"newman run \"collections/Quipu Security Service.postman_collection.json\" -e environments/${ENV:-local}.postman_environment.json -r cli,htmlextra,junit",
  "test:app":     "newman run \"collections/Quipu Application Service.postman_collection.json\" -e environments/${ENV:-local}.postman_environment.json -r cli,htmlextra,junit",
  "test:all":     "node scripts/orchestrate.js --all",
  "test:e2e":     "node scripts/orchestrate.js --journeys",
  "test:journey": "node scripts/orchestrate.js --journey"
}
```

**Journeys (orchestrator):** `orchestrate.js`
1. Loads `services/environments/journeys` + selected env.
2. For each journey, walks steps: runs the specific request via `newman run <collection> --folder/--item`, passing a **shared environment file** that it `--export-environment`s after every step, so captured tokens/IDs flow to the next step.
3. Applies per-step `expect`/`capture` as an injected item-level test (built from the step config), collects pass/fail, runs `teardown` even on failure.
4. Emits a combined report + non-zero exit on any failure (CI gate).

Run examples:
```bash
ENV=local  npm run build && npm run test:all
ENV=dev    npm run test:e2e
ENV=staging node scripts/orchestrate.js --journey ingest-to-answer
```

---

## 9. Reporting

- **CLI** (fast feedback) + **htmlextra** (`reports/<env>/<service>.html`) + **JUnit XML** (CI test tab).
- Orchestrator writes a **journey summary** (`reports/<env>/journeys.json`) with per-step status and captured values (secrets redacted).
- Artifacts uploaded in CI.

---

## 10. CI/CD (GitHub Actions — config-driven)

Platform is confirmed **GitHub Actions** (`github.com/thequipu/postman-collections`). The pipeline supports **all triggers, both runner types, and priority-based gating**, all driven by config so behavior changes without editing YAML.

### 10.1 What drives it — `config/ci.json`

```json
{
  "environments": {
    "local":   { "runner": ["self-hosted","quipu-local"], "githubEnvironment": null,      "reachable": "internal" },
    "dev":      { "runner": "ubuntu-latest",                "githubEnvironment": "dev",     "reachable": "public"   },
    "staging":  { "runner": ["self-hosted","quipu-staging"],"githubEnvironment": "staging", "reachable": "internal" }
  },
  "suites": {
    "smoke":    { "layers": ["L0","L1"],               "priority": "P0", "gate": "block"  },
    "contract": { "layers": ["L0","L1","L2"],          "priority": "P1", "gate": "block"  },
    "e2e":      { "journeys": ["onboarding","ingest-to-answer"], "priority": "P2", "gate": "report" }
  },
  "priorityGate": { "P0": "block", "P1": "block", "P2": "report" }
}
```

- **Runner per environment** covers the "all conditions" answer: `dev` uses **GitHub-hosted** (`ubuntu-latest`), `staging`/`local` use a **self-hosted** runner (labels) inside the private network. `runs-on: ${{ fromJSON(inputs.runner) }}` — flip a value in config, not the workflow.
- **Priority-based gating** covers "based on use-case priority": each suite/journey carries a `priority` (P0/P1/P2…); the reusable workflow blocks the build on failures at `block` priorities and only publishes reports for `report` ones. Promote a suite from report→block by editing `ci.json`.

Each journey/step in `journeys.json` may also carry its own `priority`, so a single E2E run can hard-fail on a P0 step (login broken) while treating a P2 step (RAG answer quality) as report-only.

### 10.2 Reusable workflow — `.github/workflows/_api-tests.yml`

One parameterized workflow, called by every trigger. Inputs: `environment`, `suite`, `runner`, `gate`.

```yaml
on:
  workflow_call:
    inputs:
      environment: { type: string, required: true }
      suite:       { type: string, required: true }   # smoke | contract | e2e
      runner:      { type: string, required: true }    # "ubuntu-latest" or '["self-hosted","quipu-staging"]'
      gate:        { type: string, default: "block" }  # block | report
jobs:
  run:
    runs-on: ${{ fromJSON(inputs.runner) }}
    environment: ${{ inputs.environment }}            # GitHub Environment → scoped secrets + approvals
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: npm }
      - run: npm ci && npm i -g newman newman-reporter-htmlextra
      - name: Write credentials from secrets
        run: node scripts/write-credentials.js
        env:
          ENV: ${{ inputs.environment }}
          QUIPU_USERNAME:      ${{ secrets.QUIPU_USERNAME }}
          QUIPU_PASSWORD:      ${{ secrets.QUIPU_PASSWORD }}
          QUIPU_CLIENT_SECRET: ${{ secrets.QUIPU_CLIENT_SECRET }}
      - name: Build (generate envs + inject tests) & verify generated files current
        run: npm run build && git diff --exit-code environments/ collections/
      - name: Run suite
        run: node scripts/orchestrate.js --suite ${{ inputs.suite }} --gate ${{ inputs.gate }}
        env: { ENV: ${{ inputs.environment }} }
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: reports-${{ inputs.environment }}-${{ inputs.suite }}, path: reports/** }
      - name: Publish JUnit
        if: always()
        uses: mikepenz/action-junit-report@v4
        with: { report_paths: "reports/**/junit*.xml" }
```

`orchestrate.js --gate` reads `ci.json`/step priorities and sets the exit code: non-zero only when a `block`-priority check fails; `report` failures are surfaced in the summary but exit 0. `git diff --exit-code` enforces that generated env files and injected tests are committed (no drift).

### 10.3 Trigger workflows (all four)

| Trigger | File | Calls | Env / Suite |
|---|---|---|---|
| **PR smoke** | `pr-smoke.yml` — `on: pull_request` (paths `collections/**`,`config/**`) | `_api-tests` | dev · `smoke` · block |
| **Push to main** | `on-push.yml` — `on: push: branches:[main]` | `_api-tests` | dev · `contract` · block |
| **Nightly full E2E** | `nightly.yml` — `on: schedule: cron "0 2 * * *"` | `_api-tests` (matrix `dev`+`staging`) | `e2e` · gate from `ci.json` |
| **Manual** | `dispatch.yml` — `on: workflow_dispatch` (inputs: environment, suite) | `_api-tests` | user-selected |

Example caller:
```yaml
# nightly.yml
on: { schedule: [{ cron: "0 2 * * *" }] }
jobs:
  e2e:
    strategy: { matrix: { env: [dev, staging] } }
    uses: ./.github/workflows/_api-tests.yml
    with:
      environment: ${{ matrix.env }}
      suite: e2e
      runner: ${{ matrix.env == 'dev' && 'ubuntu-latest' || '["self-hosted","quipu-staging"]' }}
      gate: report
    secrets: inherit
```

### 10.4 Secrets & environments

- Each target is a **GitHub Environment** (`dev`, `staging`) holding its own scoped secrets (`QUIPU_USERNAME`, `QUIPU_PASSWORD`, `QUIPU_CLIENT_SECRET`, …) and optional required-reviewer protection for staging.
- `scripts/write-credentials.js` materializes `config/credentials.<env>.json` from env vars at runtime; reports redact `password|secret|token|otp`.

### 10.5 Self-hosted runner (for internal dev/staging/local)

A short `docs/RUNNER-SETUP.md` (delivered in S4) covers registering a self-hosted runner with labels `quipu-staging` / `quipu-local` on a host inside the private network, or running the Docker image (§11) as the runner. This is what makes internal-only environments reachable from CI.

---

## 11. Docker

```dockerfile
FROM node:20-alpine
WORKDIR /suite
COPY package*.json ./
RUN npm ci --omit=dev && npm i -g newman newman-reporter-htmlextra
COPY . .
ENTRYPOINT ["npm","run"]
```
```bash
docker run --rm -e ENV=dev -v "$PWD/reports:/suite/reports" quipu/api-tests test:e2e
```
`docker-compose.yml` optionally brings up the local stack + this runner for a hermetic `local` run.

---

## 12. Secrets Management

- `Access_Token` collection's hardcoded `client_secret` → removed, replaced with `{{clientSecret}}`.
- `credentials.*.json` git-ignored; `credentials.example.json` committed.
- CI: values from repository/organization secrets, written to the file at runtime, never logged (reports redact `password|secret|token|otp`).

---

## 13. Data-Driven Testing

- `config/data/*.csv|json` drive iteration (multiple tenants, multiple query inputs) via `newman run ... -d config/data/tenants.csv`.
- Journeys accept an optional `dataFile` so the same scenario runs across N tenants in one invocation.

---

## 14. Implementation Plan (phased, each slice runnable)

| Slice | Deliverables | Acceptance criteria |
|---|---|---|
| **S1 Foundation** | `config/*` (services, environments, credentials.example), `build-env.js`, generated `environments/{local,dev,staging}`, `.gitignore`, `package.json`, baseline snippet + `inject-tests.js`, secret extraction from Access_Token, Docker + CI skeleton | `npm run build` regenerates env files; `ENV=local npm run test:security` runs with L0 baseline green against a reachable stack; no secrets in git |
| **S2 Core contract tests** | L1 auth + L2 assertions & ID capture for Security, Tenant, Application, Synapse, Nexus, LLM | Each `test:<svc>` asserts real shape; created IDs captured; token fan-out verified |
| **S3 Remaining services** | L2 for KG, Instance Mgr, Transformation, Load Balancer, Document Graph, NLP, Access_Token | All 13 have ≥ L0+L1 where auth applies; `test:all` green |
| **S4 Journeys + CI wiring** | `journeys.json` (onboarding, ingest-to-answer), `orchestrate.js`, `e2e/` outputs, `config/ci.json`, reusable `_api-tests.yml` + all 4 trigger workflows (PR smoke, on-push, nightly, dispatch), `write-credentials.js`, `RUNNER-SETUP.md`, htmlextra/JUnit reports | `ENV=dev npm run test:e2e` runs both journeys with teardown; PR smoke gates on P0/P1; nightly runs dev+staging matrix; priority gating honored (block vs report) |

Dependencies: S1 → (S2, S3 parallel) → S4. CI is introduced as a **skeleton in S1** (reusable workflow + PR smoke calling `test:security`) and completed in S4.

---

## 15. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Hosted routing (dev/staging) differs from local ports | `scheme` + optional `pathPrefix` per service in config; only `TODO` hosts to fill |
| Shared-env data pollution | idempotent journeys with `teardown`; unique names via `{{$guid}}`/timestamps |
| Token drift breaks chaining | fan-out snippet writes all three token vars |
| OTP in login blocks automation | env-provided `otp`, or a TOTP prerequest step, or a test user with OTP disabled |
| Editing collections breaks cloud sync | injection stays v2.1.0-schema-valid; marker-based idempotent edits |
| Flaky async pipelines (ingest→graph) | poll-with-retry step type in orchestrator (retry until condition or timeout) |

---

## 16. Open Items to Confirm Before/During S1

1. **dev/staging hostnames + routing** (port-based vs gateway path prefixes).
2. **Login/OTP:** is there a test user with OTP disabled, or should the harness compute a TOTP?
3. **Async completion signals:** for Transformation/ingest, what response/endpoint indicates "done" (for the poll step)?
4. **CI:** ✅ GitHub Actions confirmed, config-driven (§10). Remaining inputs: (a) self-hosted runner host + labels for internal `staging`/`local`; (b) which GitHub Environment names/secrets already exist; (c) confirm nightly cron time (assumed 02:00 UTC).

---

*Next action on approval: build Slice 1 (foundation) — config, generated environments, baseline injection, secret extraction, Docker + CI skeleton.*
