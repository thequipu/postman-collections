# Neuro Memory Simulation Tool

Multi-user load testing tool for Quipu Neuro Memory APIs. Creates real Keycloak users, grants permissions, sets up extraction profiles, and runs weighted random operations with per-user tokens.

## Prerequisites

```bash
cd d:/quipu/postman-collections/tools/neuro-sim
pip install -r requirements.txt
```

## Quick Start

```bash
# 3 users, all operations, ~3 min
NEURO_SIM_CONFIG=config/test-5users.yaml locust -f neuro_sim.py --headless --html reports/test.html

# Web UI (interactive)
NEURO_SIM_CONFIG=config/test-5users.yaml locust -f neuro_sim.py
# Open http://localhost:8089
```

## First Run — Data Download

First run downloads **1.6M items (710 MB)** from HuggingFace + Wikipedia + RSS:

| Source | Items | Size | Content |
|--------|-------|------|---------|
| LMEB (Long-Term Memory Eval Benchmark) | 1,235,919 | 645 MB | Dialogue, episodic, semantic, procedural |
| MemoryAgentBench | 234,892 | 134 MB | Memory conflicts, multi-turn retrieval |
| AG News | 120,000 | 35 MB | Real news: business, tech, sports, world |
| SQuAD | 18,889 | 15 MB | Wikipedia paragraphs |
| SciQ | 10,388 | 6 MB | Science Q&A with explanations |
| Wikipedia API | ~200 | 50 KB | Random article summaries |
| BBC RSS | ~100 | 21 KB | Live news feeds |

Takes ~2 min first time. Cached to `cache/` — subsequent runs load instantly.

To skip HuggingFace (faster, smaller pool):
```yaml
data_pool:
  huggingface: false   # only Wikipedia + RSS (~100 items)
```

## How It Works

### Startup (once per run)

1. Load data pool from cache
2. Verify KC admin token (master realm) + app admin token (tenant realm)
3. Generate fresh space name: `neurosim-test-{timestamp}`

### Per User Setup (in waves)

1. **Create Keycloak user** via admin API (master realm)
2. **Grant 4 permissions** via applicationService:
   - MEMORY_SPACE → MANAGE
   - DATA_FABRIC → VIEW
   - NAMESPACE → MANAGE
   - KNOWLEDGE_GRAPH → MANAGE
3. **Get per-user token** (own credentials)
4. **First ingest** creates the space + namespace
5. **Step 1: PUT extraction profile** (6 entity kinds, dataset-specific)
6. **Step 2: PUT instructions** (5 extraction rules)
7. **Step 3: Verify extraction status** (promptVersion, models)

### Operations Loop (random weighted, per user)

| Operation | Weight | Description |
|-----------|--------|-------------|
| ingest | 25 | Write content to namespace |
| recall (LIVE) | 20 | Search + harvest fact URIs |
| list_facts | 10 | Build fact URI pool |
| assert | 8 | Create fact triples |
| pin + verify | 8 | Pin fact → recall AS_OF 1990 → verify it appears |
| invalidate + verify | 5 | PATCH invalidAt → recall LIVE → verify excluded |
| unpin + verify | 4 | Unpin → recall AS_OF → verify removed |
| pin→invalidate | 3 | Pin then invalidate → verify invalidation overrides pin |
| recall_episodic | 3 | Recall EPISODIC mode (no time filter) |
| list_entities | 3 | List nodes in namespace |
| recall_thread | 2 | Recall filtered by threadId |
| recall_invalidated_true | 2 | Recall with superseded facts |
| space_ingest | 2 | Ingest via space endpoint |
| attach_namespace | 2 | Create graph + ingest |
| idempotency | 2 | Re-ingest same content → same unitId |
| validate_fields | 2 | Check 8 expected fields on facts |
| delete | 2 | Delete edge (max 1 per test) |
| detach_namespace | 1 | Delete graph namespace |

### Three Token Types

| Token | Who | Used For |
|-------|-----|----------|
| KC admin | `admin` on master realm + `admin-cli` | Create/delete Keycloak users |
| App admin | `karthik` on tenant realm | Grant permissions, PATCH/DELETE edges, PUT profile/instructions |
| User token | `nsim-karthik-NNN` on tenant realm | ALL Neuro operations: ingest, recall, assert, pin, list |

### Live Dashboard

Prints every 10 seconds:
```
  ┌─── NEURO-SIM DASHBOARD [10:23:30] ── 60s elapsed ───
  │ Total: 130 ops │ 2.6 ops/sec │ Errors: 0 │ Rate: 0.0%
  ├──────────────────────────────────────────────────────
  │ Operation         Count  Err  ops/s    p50    p95    p99
  │ ingest               35    0   0.6   800ms 1200ms 1500ms
  │ recall               28    0   0.5  3000ms 5000ms 8000ms
  │ pin                  12    0   0.2   900ms 1100ms 1300ms
  └──────────────────────────────────────────────────────
```

## Configuration

### Change Number of Users

```yaml
waves:
  - [3, 5]       # 3 users over 5s
  - [5, 10]      # +5 more over 10s = 8 total
  - [10, 20]     # +10 more over 20s = 18 total
```

### Change Run Duration

```yaml
simulation:
  hold_after_waves: 180   # seconds after last wave, then stop
```

### Enable/Disable Operations

```yaml
simulation:
  enabled_ops: []            # empty = all enabled
  # Or pick specific ones:
  enabled_ops:
    - ingest
    - recall
    - assert
```

### Limit Deletes

```yaml
simulation:
  max_deletes: 1   # only 1 delete per run (0 = unlimited)
```

### User Cleanup

```yaml
simulation:
  cleanup_users: false  # default: keep users for re-runs
  cleanup_users: true   # delete KC users + permissions on stop
```

### Different Environment

```bash
NEURO_SIM_CONFIG=config/onprem.yaml locust -f neuro_sim.py --headless
```

## Artifacts

### Reports Directory

Each run creates `reports/sim-{timestamp}/`:
```
reports/sim-20260921T135926Z/
  ├── nsim-karthik-001.jsonl    # per-user audit trail
  ├── nsim-karthik-002.jsonl
  └── nsim-karthik-003.jsonl
```

### JSONL Audit Trail

Every operation logged with:
```json
{
  "seq": 1,
  "ts": "2026-09-21T13:59:26.000Z",
  "user": "nsim-karthik-001",
  "op": "ingest",
  "status": 202,
  "latency_ms": 800.5,
  "unit_id": "7d7488f8-bf9f-33dc-92a8-17ada7e550c4",
  "thread": "thread-nsim-karthik-001-finance"
}
```

### Analyze Results

```bash
# Operation counts
cat reports/sim-*/nsim-*.jsonl | python -c "
import sys, json, collections
ops = collections.Counter()
for line in sys.stdin:
    ops[json.loads(line)['op']] += 1
for op, c in ops.most_common():
    print(f'  {op:25s} {c}')
"

# Pin verification
cat reports/sim-*/nsim-*.jsonl | python -c "
import sys, json
p = t = 0
for line in sys.stdin:
    r = json.loads(line)
    if r['op'] == 'pin_verify':
        t += 1
        if r.get('PASS') or r.get('pinned_found'): p += 1
print(f'Pin verify: {p}/{t} PASS')
"

# Latency percentiles
cat reports/sim-*/nsim-*.jsonl | python -c "
import sys, json, statistics
lats = {}
for line in sys.stdin:
    r = json.loads(line)
    if r['latency_ms'] > 0:
        lats.setdefault(r['op'], []).append(r['latency_ms'])
for op in sorted(lats):
    l = sorted(lats[op])
    p50 = statistics.median(l)
    p95 = l[int(len(l)*0.95)] if len(l) > 1 else l[0]
    print(f'  {op:25s} p50={p50:.0f}ms  p95={p95:.0f}ms  count={len(l)}')
"
```

### Locust HTML Report

Generated with `--html` flag:
```bash
locust -f neuro_sim.py --headless --html reports/test.html
```

## Project Structure

```
tools/neuro-sim/
├── neuro_sim.py              # Main Locust file + MemoryUser class
├── wave_shape.py             # Configurable wave spawn shape
├── lib/
│   ├── keycloak.py           # KC admin + app admin + per-user tokens
│   ├── neuro_client.py       # All Neuro API calls
│   ├── app_service_client.py # Graph CRUD + permissions + profile/instructions
│   ├── data_pool.py          # Cache-through data pool
│   ├── user_state.py         # Per-user state machine
│   ├── audit.py              # JSONL audit trail
│   └── dashboard.py          # Live console dashboard
├── data_sources/
│   ├── memory_benchmarks.py  # LMEB + MemoryAgentBench + AG News + SQuAD + SciQ
│   ├── wikipedia_source.py   # Wikipedia random articles
│   └── news_source.py        # BBC RSS feeds
├── config/
│   ├── test-5users.yaml      # Test config (prestage)
│   ├── prestage.yaml         # Full prestage config
│   └── onprem.yaml           # Onprem config
├── cache/                    # Downloaded data (gitignored)
├── reports/                  # Test reports (gitignored)
├── requirements.txt
└── setup.py
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `401 on master realm` | Check `kc_admin_user`/`kc_admin_password` in config |
| `403 on create user` | Need KC master realm admin |
| `406 on user-permission` | Accept header must be `*/*` |
| `500 on PATCH/DELETE edge` | These need admin token (already handled) |
| `500 on grant permissions` | Duplicate — users already have perms from previous run |
| `No data pool` | First run needs internet. Check `cache/` dir |
| `Pin verify FAIL` | Projection delay — increase `hold_after_waves` for more time |
| `Invalidate verify FAIL` | Projection delay — fact takes 10-60s to settle |
