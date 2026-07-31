# Flow Suites (Layer 2)

Feature-oriented, environment-portable API flows. These **duplicate** requests from the
per-service reference collections in `../collections/` but add assertions, chaining, and
use **only variables** — never hardcoded hosts, tokens, or IDs.

## Layers
- **Layer 1 — API Reference:** `../collections/*` — per-service docs & ad-hoc testing.
- **Layer 2 — Flow Suites:** `flows/*` — ordered, asserted, end-to-end scenarios.

## Naming
- `SMOKE – <Area>` — read-only, **prod-safe**. The only suites run against prod.
- `FLOW – <Feature>: <Scenario>` — full E2E (create → verify → teardown). Non-prod only.

## Environments
`../environments/{local,onprem,stage,pre-prod,prod}.postman_environment.json` — identical variable
keys, different values. `local` and `onprem` both target `http://localhost:<port>`; `local` is
for a developer's own stack (point `keycloak_token_url` at a local Keycloak if you run one).
Secrets (`client_secret`, `test_username`, `test_password`) ship
**blank**; fill the *Current Value* locally or inject at runtime in CI. `prod` sets
`allow_destructive=false`, which the collection Pre-request script enforces.

## Run
```bash
npm i -g newman newman-reporter-htmlextra

# prod-safe smoke against any environment
npm run smoke:onprem
newman run "flows/SMOKE-Platform-Health.postman_collection.json" \
  -e environments/stage.postman_environment.json \
  --env-var "client_secret=$KEYCLOAK_CLIENT_SECRET" \
  --env-var "test_password=$TEST_USER_PASSWORD" \
  -r cli,htmlextra,junit --timeout-request 30000
```

## What's here now
- `SMOKE-Platform-Health.postman_collection.json` — read-only health probe for all 12
  runtime services. Centralized Keycloak auth + destructive-verb guard baked in at the
  collection level. This is the **base testing flow**; `FLOW –` suites follow the same pattern.

## Conventions
- Steps numbered `00…99`; `00 Setup` + `99 Teardown` in every `FLOW –` suite.
- Every step asserts status code **and** ≥1 business field.
- Chaining state lives in collection variables; cleared in `00 Setup`.
- Health paths for FastAPI services (`docgraph`, `nlp`) are assumed `/health` — adjust if needed.
