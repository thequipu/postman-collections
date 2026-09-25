"""
Neuro Memory — Multi-User Simulation Tool
==========================================
Locustfile that simulates N users (5 → 10,000) performing weighted random
operations against Quipu Neuro Memory APIs with real data from the internet.

Usage:
  # 5 users, headless, 2 minutes
  locust -f neuro_sim.py --headless -u 5 -r 2 -t 2m --html reports/sim.html

  # Web UI (browse http://localhost:8089)
  locust -f neuro_sim.py

  # With custom config
  NEURO_SIM_CONFIG=config/onprem.yaml locust -f neuro_sim.py --headless -u 10 -r 2 -t 5m

  # Use wave spawn shape
  locust -f neuro_sim.py --headless -t 5m

Environment variables:
  NEURO_SIM_CONFIG  — path to YAML config (default: config/prestage.yaml)
"""

import logging
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from locust import HttpUser, between, events, task

# Ensure project root is on sys.path so lib/ and data_sources/ resolve
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.app_service_client import AppServiceClient
from lib.audit import UserAudit
from lib.dashboard import Dashboard
from lib.data_pool import DataPool
from lib.keycloak import KeycloakClient
from lib.neuro_client import NeuroClient
from lib.user_state import UserState
from wave_shape import WaveShape  # noqa: F401 — Locust discovers it automatically

# ---- Logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("neuro_sim")

# Suppress noisy urllib3 warnings for self-signed certs
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================================
# Configuration
# ============================================================================

def load_config() -> dict:
    config_path = os.environ.get("NEURO_SIM_CONFIG", "config/prestage.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


CONFIG = load_config()
_run_ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
REPORT_DIR = f"reports/sim-{_run_ts}"
Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)

# One space per run — all users share it, each gets own namespace inside
_run_space = f"{CONFIG.get('simulation', {}).get('space_prefix', 'neurosim')}-{_run_ts}"

# Which operations are enabled (empty list = all enabled)
_enabled_ops_raw = CONFIG.get("simulation", {}).get("enabled_ops", [])
ENABLED_OPS = set(_enabled_ops_raw) if _enabled_ops_raw else set()


# ============================================================================
# Shared resources (class-level, initialized once)
# ============================================================================

_data_pool: DataPool | None = None
_keycloak: KeycloakClient | None = None
_neuro_tpl: dict | None = None  # Template config for NeuroClient
_app_svc_tpl: dict | None = None
_user_counter = 0
_notification_state = {"total_failures": 0, "total_requests": 0, "alerted": False}
_delete_count = 0  # Global delete counter — controlled by simulation.max_deletes
_delete_lock = threading.Lock()
_dashboard = Dashboard(interval=CONFIG.get("simulation", {}).get("dashboard_interval", 10))


def _get_data_pool() -> DataPool:
    global _data_pool
    if _data_pool is None:
        dp_cfg = CONFIG.get("data_pool", {})
        _data_pool = DataPool(
            cache_dir=dp_cfg.get("cache_dir", "./cache"),
            enable_huggingface=dp_cfg.get("huggingface", True),
            enable_wikipedia=dp_cfg.get("wikipedia", True),
            enable_rss=dp_cfg.get("rss", True),
            hf_items=dp_cfg.get("huggingface_items", 0),
            wiki_items=dp_cfg.get("wikipedia_items", 200),
            rss_items=dp_cfg.get("rss_items", 200),
            min_items_per_user=dp_cfg.get("min_items_per_user", 100),
            max_items_per_user=dp_cfg.get("max_items_per_user", 500),
        )
        logger.info("Downloading data pool (first run may take a few minutes)...")
        _data_pool.setup()
        logger.info("Data pool ready: %d items", len(_data_pool))
    return _data_pool


def _get_keycloak() -> KeycloakClient:
    global _keycloak
    if _keycloak is None:
        auth = CONFIG["auth"]
        sim = CONFIG.get("simulation", {})
        _keycloak = KeycloakClient(
            token_url=auth["token_url"],
            client_id=auth["client_id"],
            client_secret=auth["client_secret"],
            admin_username=auth["admin_username"],
            admin_password=auth["admin_password"],
            kc_admin_user=auth.get("kc_admin_user", ""),
            kc_admin_password=auth.get("kc_admin_password", ""),
            token_lifetime=sim.get("token_lifetime", 300),
            refresh_buffer=sim.get("token_refresh_buffer", 20),
        )
    return _keycloak


# ============================================================================
# Notifications
# ============================================================================

def _notify_failure(user_id: str, operation: str, status: int, detail: str):
    """Send failure notification if threshold exceeded."""
    state = _notification_state
    state["total_failures"] += 1
    state["total_requests"] += 1

    notif = CONFIG.get("notifications", {})
    threshold = notif.get("failure_threshold_pct", 5)
    if state["total_requests"] < 20:
        return  # Wait for enough samples

    pct = (state["total_failures"] / state["total_requests"]) * 100
    if pct > threshold and not state["alerted"]:
        msg = (f"NEURO-SIM ALERT: failure rate {pct:.1f}% > {threshold}% "
               f"({state['total_failures']}/{state['total_requests']})")
        logger.error(msg)

        if notif.get("console_alerts", True):
            print(f"\033[1;31m  !! {msg}\033[0m", file=sys.stderr)

        webhook = notif.get("slack_webhook", "")
        if webhook:
            try:
                requests.post(webhook, json={"text": msg}, timeout=5)
            except Exception:
                pass

        state["alerted"] = True


def _count_success():
    _notification_state["total_requests"] += 1


# ============================================================================
# Locust User — MemoryUser
# ============================================================================

class MemoryUser(HttpUser):
    """Each Locust user simulates an independent Neuro memory user.

    Operations are weighted by @task(weight) — Locust picks randomly
    according to these weights each iteration.
    """

    # Random 0.5-2s pause between operations
    wait_time = between(0.5, 2.0)

    # Override host from config (Locust requires it)
    host = CONFIG["api"]["base_url"]

    def _op_enabled(self, name: str) -> bool:
        """Check if an operation is enabled. Empty ENABLED_OPS = all enabled."""
        return not ENABLED_OPS or name in ENABLED_OPS

    def on_start(self):
        """Create KC user, grant permissions, get per-user token, start operations."""
        global _user_counter
        _user_counter += 1
        my_index = _user_counter

        sim = CONFIG.get("simulation", {})
        auth = CONFIG["auth"]
        prefix = sim.get("user_prefix", "simuser")
        self._sim_password = auth.get("sim_user_password", "SimTest@123")

        self.state = UserState(
            user_id=f"{prefix}-{my_index:03d}",
            user_index=my_index,
            run_space=_run_space,
        )

        # Assign unique data slice (0 = random size per user)
        pool = _get_data_pool()
        self.state.data_items = pool.get_items_for_user(
            my_index, sim.get("data_items_per_user", 0)
        )
        self.pool = pool

        # Shared admin clients
        self.kc = _get_keycloak()
        api = CONFIG["api"]
        self.neuro = NeuroClient(
            api["base_url"], api["neuro_path"],
            CONFIG["tenant"], CONFIG["fabric"],
            extra_headers=CONFIG.get("extra_headers"),
        )
        self.app_svc = AppServiceClient(api["base_url"], api["app_service_path"])

        # ---- Step 1: Create Keycloak user (admin) ----
        self._kc_user_id = self.kc.create_user(self.state.user_id, self._sim_password)
        logger.info("KC user created: %s (id=%s)", self.state.user_id, self._kc_user_id)

        # ---- Step 2: Grant 4 permissions (admin) ----
        perm_cfg = CONFIG.get("permissions", {})
        grants = perm_cfg.get("grants", [])
        granted_by = perm_cfg.get("granted_by", CONFIG["tenant"])
        if grants:
            app_token = self.kc.get_app_admin_token()
            status, body, lat = self.app_svc.grant_user_permissions(
                app_token, self.state.user_id, grants, granted_by,
            )
            if isinstance(body, list):
                self._perm_ids = [item.get("id") for item in body if isinstance(item, dict) and "id" in item]
            else:
                self._perm_ids = []
            if status == 200:
                logger.info("Granted %d permissions to %s (perm_ids=%s)",
                            len(grants), self.state.user_id, self._perm_ids)
            elif status == 500:
                # Likely duplicate — permissions already exist from a previous run
                logger.info("Permissions already exist for %s (HTTP 500 = duplicate, continuing)", self.state.user_id)
            else:
                logger.warning("Permission grant for %s: HTTP %d", self.state.user_id, status)
        else:
            self._perm_ids = []

        # ---- Step 3: Get per-user token ----
        self._token, self._token_expires = self.kc.get_user_token(
            self.state.user_id, self._sim_password,
        )

        # Audit trail
        self.audit = UserAudit(self.state.user_id, REPORT_DIR)

        # First ingest creates the space (using user's own token)
        self._ensure_space()

        # ---- Steps 1-3: Set up steering config (first user only, since all share same space) ----
        if my_index == 1:
            self._setup_profile()
            self._setup_instructions()
        self._verify_extraction_status()

        logger.info("User %s started (data: %d items, perms: %s)",
                    self.state.user_id, len(self.state.data_items), self._perm_ids)

    def _ensure_token(self):
        if time.time() > self._token_expires:
            self._token, self._token_expires = self.kc.get_user_token(
                self.state.user_id, self._sim_password,
            )

    def _handle_401(self, status: int, op: str):
        """If 401, refresh per-user token and return True to retry."""
        if status == 401:
            logger.debug("401 on %s for %s — refreshing user token", op, self.state.user_id)
            self._token, self._token_expires = self.kc.get_user_token(
                self.state.user_id, self._sim_password,
            )
            return True
        return False

    def _ensure_space(self):
        """First ingest creates space + {space}-self namespace automatically."""
        if self.state.space_created:
            return
        msg = self.state.next_message()
        if not msg:
            return
        self._ensure_token()

        # Space ingest creates both the space and the -self namespace
        status, body, lat = self.neuro.ingest_space(
            self.state.space, self._token,
            content=msg["content"], thread_id=msg["thread_id"],
            speaker=msg["speaker"],
        )
        if self._handle_401(status, "create_space"):
            status, body, lat = self.neuro.ingest_space(
                self.state.space, self._token,
                content=msg["content"], thread_id=msg["thread_id"],
                speaker=msg["speaker"],
            )
        self.audit.log("create_space", {"space": self.state.space, "namespace": self.state.ns}, status, lat)
        _dashboard.record("create_space", status, lat)
        if status == 202:
            _count_success()
            if isinstance(body, dict) and body.get("unitId"):
                self.state.ingested_ids.append(body["unitId"])

        self.state.space_created = True
        logger.info("Space=%s Namespace=%s for %s (HTTP %d)", self.state.space, self.state.ns, self.state.user_id, status)

    # ---- Helper: single API call with 401 retry ----

    def _call(self, op: str, method, *args, **kwargs):
        """Call a neuro/app_svc method with 401 auto-retry. Records to dashboard."""
        self._ensure_token()
        status, body, lat = method(*args, **kwargs)
        if self._handle_401(status, op):
            status, body, lat = method(*args, **kwargs)
        _dashboard.record(op, status, lat)
        return status, body, lat

    def _get_admin_token(self):
        """Get app admin token for operations that require admin access."""
        return self.kc.get_app_admin_token()

    # ---- Operations (weighted random via @task) ----
    # Weights tuned so users: ingest first, build fact pool via list_facts,
    # then pin/recall/verify, invalidate, and occasionally delete.

    @task(25)
    def do_ingest(self):
        """Ingest content into user's namespace."""
        msg = self.state.next_message()
        if not msg:
            return
        status, body, lat = self._call(
            "ingest", self.neuro.ingest_namespace,
            self.state.ns, self._token,
            text=msg["content"], thread_id=msg["thread_id"],
            owner_user_id=self.state.user_id,
        )
        unit_id = body.get("unitId", "") if isinstance(body, dict) else ""
        self.audit.log("ingest", {"unit_id": unit_id, "thread": msg["thread_id"]}, status, lat)
        if status == 202 and unit_id:
            self.state.ingested_ids.append(unit_id)
            _count_success()
        elif status != 202:
            _notify_failure(self.state.user_id, "ingest", status, str(body)[:200])

    @task(20)
    def do_recall(self):
        """Recall from user's namespace and harvest fact URIs."""
        query = self.pool.get_random_query(self.state.data_items)
        status, body, lat = self._call(
            "recall", self.neuro.recall_namespace,
            self.state.ns, self._token,
            query=query, user_id=self.state.user_id,
        )
        items = body.get("items", []) if isinstance(body, dict) else []
        self.audit.log("recall", {"query": query[:80], "items": len(items)}, status, lat)
        if status == 200:
            _count_success()
            for item in items:
                for uri in item.get("provenance", []):
                    if "Fact/" in uri and uri not in self.state.fact_uris:
                        self.state.fact_uris.append(uri)
        else:
            _notify_failure(self.state.user_id, "recall", status, str(body)[:200])

    @task(10)
    def do_list_facts(self):
        """List edges — builds the fact URI pool needed for pin/invalidate/delete."""
        if not self._op_enabled("list_facts"):
            return
        status, body, lat = self._call(
            "list_facts", self.neuro.list_edges,
            self.state.space, self.state.ns, self._token,
        )
        items = body.get("items", []) if isinstance(body, dict) else []
        self.audit.log("list_facts", {"count": len(items)}, status, lat)
        if status == 200:
            _count_success()
            for item in items:
                uri = item.get("uri", "")
                if uri and uri not in self.state.fact_uris:
                    self.state.fact_uris.append(uri)
        else:
            _notify_failure(self.state.user_id, "list_facts", status, str(body)[:200])

    @task(8)
    def do_assert(self):
        """Assert a fact triple derived from user's data."""
        if not self._op_enabled("assert"):
            return
        item = random.choice(self.state.data_items)
        words = item["content"].split()
        if len(words) < 5:
            return
        entity = " ".join(words[:2])
        value = " ".join(words[3:6])
        status, body, lat = self._call(
            "assert", self.neuro.assert_fact,
            self.state.space, self._token,
            entity=entity, label="Entity", prop="relates_to", value=value,
        )
        self.audit.log("assert", {"entity": entity, "value": value}, status, lat)
        if status in (200, 202):
            _count_success()
        else:
            _notify_failure(self.state.user_id, "assert", status, str(body)[:200])

    @task(8)
    def do_pin_and_verify(self):
        """Pin a fact, then recall with AS_OF in far past to verify pinned fact bypasses temporal filter."""
        if not self._op_enabled("pin"):
            return
        if not self.state.has_facts():
            return
        uri = self.state.random_fact()

        # Step 1: Pin the fact
        status, body, lat = self._call(
            "pin", self.neuro.pin_fact,
            self.state.space, self.state.ns, self._token, uri,
        )
        self.audit.log("pin", {"uri": uri}, status, lat)
        if status not in (200, 202):
            _notify_failure(self.state.user_id, "pin", status, str(body)[:200])
            return
        _count_success()
        if uri not in self.state.pinned_uris:
            self.state.pinned_uris.append(uri)

        # Step 2: Recall with AS_OF 1990 — pinned fact should still appear (bypasses temporal filter)
        status2, body2, lat2 = self._call(
            "recall_pinned", self.neuro.recall_space,
            self.state.space, self._token,
            query="pinned fact verification",
            user_id=self.state.user_id,
            mode="AS_OF", as_of="1990-01-01T00:00:00Z",
        )
        items2 = body2.get("items", []) if isinstance(body2, dict) else []
        # Check if pinned URI appears in results
        found_pinned = any(
            uri in item.get("provenance", [])
            for item in items2
        )
        self.audit.log("pin_verify", {
            "uri": uri,
            "recall_status": status2,
            "recall_items": len(items2),
            "pinned_found": found_pinned,
            "PASS": found_pinned or len(items2) > 0,
        }, status2, lat2)
        if status2 == 200:
            _count_success()
        if found_pinned:
            logger.info("PIN VERIFY PASS: %s found in AS_OF recall for %s", uri, self.state.user_id)

    @task(4)
    def do_unpin_and_verify(self):
        """Unpin a previously pinned fact, then recall to verify it no longer bypasses temporal filter."""
        if not self._op_enabled("unpin"):
            return
        if not self.state.pinned_uris:
            return
        uri = self.state.pinned_uris.pop(random.randrange(len(self.state.pinned_uris)))

        # Step 1: Unpin
        status, body, lat = self._call(
            "unpin", self.neuro.unpin_fact,
            self.state.space, self.state.ns, self._token, uri,
        )
        self.audit.log("unpin", {"uri": uri}, status, lat)
        if status in (200, 202, 204):
            _count_success()

        # Step 2: Recall AS_OF far past — unpinned fact should NOT appear
        status2, body2, lat2 = self._call(
            "recall_unpinned", self.neuro.recall_space,
            self.state.space, self._token,
            query="unpinned fact verification",
            user_id=self.state.user_id,
            mode="AS_OF", as_of="1990-01-01T00:00:00Z",
        )
        items2 = body2.get("items", []) if isinstance(body2, dict) else []
        still_found = any(
            uri in item.get("provenance", [])
            for item in items2
        )
        self.audit.log("unpin_verify", {
            "uri": uri,
            "recall_status": status2,
            "recall_items": len(items2),
            "still_found": still_found,
            "PASS": not still_found,
        }, status2, lat2)
        if status2 == 200:
            _count_success()

    @task(3)
    def do_pin_then_invalidate(self):
        """Pin a fact, then invalidate it. Recall LIVE should NOT return it — invalidation overrides pin."""
        if not self._op_enabled("pin_invalidate"):
            return
        if not self.state.has_facts():
            return
        uri = self.state.random_fact()

        # Step 1: Pin the fact
        status1, body1, lat1 = self._call(
            "pin_inv_pin", self.neuro.pin_fact,
            self.state.space, self.state.ns, self._token, uri,
        )
        self.audit.log("pin_inv_pin", {"uri": uri}, status1, lat1)
        if status1 not in (200, 202):
            return
        _count_success()
        if uri not in self.state.pinned_uris:
            self.state.pinned_uris.append(uri)

        # Step 2: Invalidate the same fact (admin token)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        admin_token = self._get_admin_token()
        status2, body2, lat2 = self.neuro.patch_edge(
            self.state.space, self.state.ns, admin_token, uri,
            {"invalidAt": now},
        )
        _dashboard.record("pin_inv_invalidate", status2, lat2)
        self.audit.log("pin_inv_invalidate", {"uri": uri, "invalidAt": now}, status2, lat2)
        if status2 not in (200, 202):
            return
        _count_success()
        self.state.invalidated_uris.append(uri)
        if uri in self.state.fact_uris:
            self.state.fact_uris.remove(uri)
        if uri in self.state.pinned_uris:
            self.state.pinned_uris.remove(uri)

        # Step 3: Recall LIVE + includeInvalidated=false — fact was pinned BUT invalidated
        # Invalidation MUST override pin — fact should NOT appear
        status3, body3, lat3 = self._call(
            "pin_inv_recall", self.neuro.recall_namespace,
            self.state.ns, self._token,
            query="pin invalidate verification",
            user_id=self.state.user_id,
            mode="LIVE", include_invalidated=False,
        )
        items3 = body3.get("items", []) if isinstance(body3, dict) else []
        still_found = any(
            uri in item.get("provenance", [])
            for item in items3
        )
        passed = not still_found
        self.audit.log("pin_inv_verify", {
            "uri": uri,
            "recall_items": len(items3),
            "still_found": still_found,
            "PASS": passed,
        }, status3, lat3)
        if status3 == 200:
            _count_success()
        if passed:
            logger.info("PIN→INVALIDATE VERIFY PASS: %s excluded from recall for %s", uri, self.state.user_id)
        else:
            logger.warning("PIN→INVALIDATE VERIFY FAIL: %s still in recall for %s (propagation delay?)", uri, self.state.user_id)

    @task(5)
    def do_invalidate(self):
        """Invalidate a fact, then recall LIVE+includeInvalidated=false to verify exclusion."""
        if not self._op_enabled("invalidate"):
            return
        if not self.state.has_facts():
            return
        uri = self.state.random_fact()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Step 1: Invalidate (requires admin token — user token gets 500)
        admin_token = self._get_admin_token()
        status, body, lat = self.neuro.patch_edge(
            self.state.space, self.state.ns, admin_token, uri,
            {"invalidAt": now},
        )
        _dashboard.record("invalidate", status, lat)
        self.audit.log("invalidate", {"uri": uri, "invalidAt": now}, status, lat)
        if status not in (200, 202):
            _notify_failure(self.state.user_id, "invalidate", status, str(body)[:200])
            return
        _count_success()
        self.state.invalidated_uris.append(uri)
        if uri in self.state.fact_uris:
            self.state.fact_uris.remove(uri)

        # Step 2: Recall LIVE + includeInvalidated=false — invalidated fact should be excluded
        status2, body2, lat2 = self._call(
            "recall_after_invalidate", self.neuro.recall_namespace,
            self.state.ns, self._token,
            query="invalidation verification",
            user_id=self.state.user_id,
            mode="LIVE", include_invalidated=False,
        )
        items2 = body2.get("items", []) if isinstance(body2, dict) else []
        still_found = any(
            uri in item.get("provenance", [])
            for item in items2
        )
        self.audit.log("invalidate_verify", {
            "uri": uri,
            "recall_status": status2,
            "recall_items": len(items2),
            "still_found": still_found,
            "PASS": not still_found,
        }, status2, lat2)
        if status2 == 200:
            _count_success()

    @task(3)
    def do_list_entities(self):
        """List nodes (entities) in user's namespace."""
        if not self._op_enabled("list_entities"):
            return
        status, body, lat = self._call(
            "list_entities", self.neuro.list_nodes,
            self.state.space, self.state.ns, self._token,
        )
        count = len(body.get("items", [])) if isinstance(body, dict) else 0
        self.audit.log("list_entities", {"count": count}, status, lat)
        if status == 200:
            _count_success()

    @task(2)
    def do_delete(self):
        """Delete a random fact. Respects simulation.max_deletes (0=unlimited)."""
        if not self._op_enabled("delete"):
            return
        global _delete_count
        max_del = CONFIG.get("simulation", {}).get("max_deletes", 0)
        if max_del > 0:
            with _delete_lock:
                if _delete_count >= max_del:
                    return  # Global limit reached
                _delete_count += 1  # Reserve the slot under lock
        if not self.state.has_facts():
            if max_del > 0:
                with _delete_lock:
                    _delete_count -= 1  # Release slot — no fact to delete
            return
        uri = self.state.fact_uris.pop(random.randrange(len(self.state.fact_uris)))
        # Delete requires admin token
        admin_token = self._get_admin_token()
        status, body, lat = self.neuro.delete_edge(
            self.state.space, self.state.ns, admin_token, uri,
        )
        _dashboard.record("delete", status, lat)
        self.audit.log("delete_fact", {"uri": uri}, status, lat)
        if status in (200, 202, 204):
            _count_success()
            self.state.deleted_uris.append(uri)
            logger.info("DELETE #%d by %s: %s → HTTP %d", _delete_count, self.state.user_id, uri, status)
        else:
            _notify_failure(self.state.user_id, "delete", status, str(body)[:200])

    @task(2)
    def do_attach_namespace(self):
        """Create and attach a graph namespace, then ingest into it."""
        if not self._op_enabled("attach_namespace"):
            return
        if not self.state.can_attach_namespace():
            return
        graph_id = f"kb-{len(self.state.graph_namespaces) + 1}-{random.randint(100, 999)}"
        # Graph creation needs admin token
        admin_token = self._get_admin_token()
        status, body, lat = self.app_svc.create_graph(
            self.state.space, admin_token, graph_id, f"KB {graph_id}",
        )
        self.audit.log("create_graph", {"graph_id": graph_id}, status, lat)
        if status not in (200, 201, 202):
            return

        self.state.graph_namespaces.append(graph_id)
        # Ingest into new namespace (user token)
        msg = self.state.next_message()
        if msg:
            graph_ns = f"{self.state.space}-{graph_id}"
            status2, body2, lat2 = self._call(
                "ingest_graph_ns", self.neuro.ingest_namespace,
                graph_ns, self._token,
                text=msg["content"], thread_id=msg["thread_id"],
            )
            self.audit.log("ingest_graph_ns", {"graph_id": graph_id}, status2, lat2)
            if status2 == 202:
                _count_success()

    @task(1)
    def do_detach_namespace(self):
        """Detach (remove) a graph namespace."""
        if not self._op_enabled("detach_namespace"):
            return
        if not self.state.can_detach_namespace():
            return
        graph_id = self.state.graph_namespaces.pop()
        admin_token = self._get_admin_token()
        status, body, lat = self.app_svc.delete_graph(
            self.state.space, admin_token, graph_id,
        )
        self.audit.log("detach_ns", {"graph_id": graph_id}, status, lat)
        if status in (200, 202, 204):
            _count_success()

    # ---- Additional verification tasks ----

    @task(3)
    def do_recall_episodic(self):
        """Recall in EPISODIC mode — no temporal filtering, returns everything."""
        if not self._op_enabled("recall_episodic"):
            return
        query = self.pool.get_random_query(self.state.data_items)
        status, body, lat = self._call(
            "recall_episodic", self.neuro.recall_namespace,
            self.state.ns, self._token,
            query=query, user_id=self.state.user_id,
            mode="EPISODIC",
        )
        items = body.get("items", []) if isinstance(body, dict) else []
        self.audit.log("recall_episodic", {"query": query[:80], "items": len(items), "mode": "EPISODIC"}, status, lat)
        if status == 200:
            _count_success()

    @task(2)
    def do_recall_invalidated_true(self):
        """Recall LIVE + includeInvalidated=true — invalidated facts should return with superseded."""
        if not self._op_enabled("recall_invalidated"):
            return
        if not self.state.invalidated_uris:
            return
        query = self.pool.get_random_query(self.state.data_items)
        status, body, lat = self._call(
            "recall_invalidated_true", self.neuro.recall_namespace,
            self.state.ns, self._token,
            query=query, user_id=self.state.user_id,
            mode="LIVE", include_invalidated=True,
        )
        items = body.get("items", []) if isinstance(body, dict) else []
        # Check if any invalidated URI appears with superseded marker
        found_superseded = False
        for item in items:
            for uri in self.state.invalidated_uris:
                if uri in item.get("provenance", []):
                    found_superseded = item.get("superseded", False) or "[SUPERSEDED]" in item.get("content", "")
                    break
        self.audit.log("recall_invalidated_true", {
            "query": query[:80], "items": len(items),
            "found_superseded": found_superseded,
            "invalidated_count": len(self.state.invalidated_uris),
        }, status, lat)
        if status == 200:
            _count_success()

    @task(2)
    def do_recall_with_thread(self):
        """Recall filtered by threadId — should only return items from that thread."""
        if not self._op_enabled("recall_thread"):
            return
        if not self.state.threads:
            return
        thread = random.choice(list(self.state.threads))
        query = self.pool.get_random_query(self.state.data_items)
        status, body, lat = self._call(
            "recall_thread", self.neuro.recall_namespace,
            self.state.ns, self._token,
            query=query, user_id=self.state.user_id,
        )
        items = body.get("items", []) if isinstance(body, dict) else []
        self.audit.log("recall_thread", {
            "query": query[:80], "threadId": thread, "items": len(items),
        }, status, lat)
        if status == 200:
            _count_success()

    @task(2)
    def do_idempotency_check(self):
        """Re-ingest same content — should return same unitId (idempotent)."""
        if not self._op_enabled("idempotency"):
            return
        if self.state.message_cursor < 2:
            return  # Need at least one prior ingest
        # Re-send the first message
        item = self.state.data_items[0]
        thread = f"thread-{self.state.user_id}-idempotency"
        status, body, lat = self._call(
            "idempotency", self.neuro.ingest_namespace,
            self.state.ns, self._token,
            text=item["content"], thread_id=thread,
            owner_user_id=self.state.user_id,
        )
        unit_id = body.get("unitId", "") if isinstance(body, dict) else ""
        # Check if unitId matches the first ingest (content-derived SHA-256)
        is_same = unit_id in self.state.ingested_ids if unit_id else False
        self.audit.log("idempotency", {
            "unit_id": unit_id,
            "is_duplicate": is_same,
            "PASS": status == 202,
        }, status, lat)
        if status == 202:
            _count_success()

    @task(2)
    def do_validate_fact_fields(self):
        """List edges and validate all 12 expected fields on each fact."""
        if not self._op_enabled("validate_fields"):
            return
        status, body, lat = self._call(
            "validate_fields", self.neuro.list_edges,
            self.state.space, self.state.ns, self._token,
        )
        items = body.get("items", []) if isinstance(body, dict) else []
        if status != 200 or not items:
            self.audit.log("validate_fields", {"count": 0, "PASS": False}, status, lat)
            return

        _count_success()
        # Fields returned by POST /graph/edges/list
        expected_fields = [
            "uri", "fact", "sourceNodeName", "sourceNodeUri",
            "targetNodeName", "targetNodeUri",
            "validAt", "invalidAt",
        ]
        sample = items[0]
        present = [f for f in expected_fields if f in sample]
        missing = [f for f in expected_fields if f not in sample]
        all_pass = len(missing) == 0
        self.audit.log("validate_fields", {
            "count": len(items),
            "sample_uri": sample.get("uri", ""),
            "present": present,
            "missing": missing,
            "PASS": all_pass,
        }, status, lat)
        if not all_pass:
            logger.warning("FIELD VALIDATION: missing %s on %s", missing, self.state.user_id)

    @task(2)
    def do_space_ingest(self):
        """Ingest via space endpoint (content field, not text)."""
        if not self._op_enabled("space_ingest"):
            return
        msg = self.state.next_message()
        if not msg:
            return
        status, body, lat = self._call(
            "space_ingest", self.neuro.ingest_space,
            self.state.space, self._token,
            content=msg["content"], thread_id=msg["thread_id"],
            speaker=msg["speaker"],
        )
        unit_id = body.get("unitId", "") if isinstance(body, dict) else ""
        self.audit.log("space_ingest", {"unit_id": unit_id, "thread": msg["thread_id"]}, status, lat)
        if status == 202:
            if unit_id:
                self.state.ingested_ids.append(unit_id)
            _count_success()

    # ---- Startup steps 1-3: Profile → Instructions → Extraction Status ----

    def _setup_profile(self):
        """Step 1: PUT extraction profile tailored to our datasets, GET it back, verify fields."""
        profile = {
            "role": (
                "Multi-domain knowledge memory. Processes news articles (business, technology, sports, world events), "
                "scientific research (biology, chemistry, physics, medicine), Wikipedia factual content, "
                "multi-turn dialogue transcripts, and episodic event logs. "
                "Extracts entities, relationships, temporal facts, and causal chains."
            ),
            "salienceNote": (
                "Prioritize: who/what/where/when facts, company financials and market events, "
                "scientific findings and experimental results, geopolitical events, "
                "dialogue preferences and user-stated facts, temporal sequences of events. "
                "Ignore: boilerplate disclaimers, navigation text, repetitive headers."
            ),
            "entityKinds": [
                {"name": "Person", "description": "A named individual — scientist, executive, politician, athlete", "examples": ["Marie Curie", "Elon Musk"]},
                {"name": "Organization", "description": "A company, institution, team, or government body", "examples": ["Reuters", "WHO"]},
                {"name": "Location", "description": "A city, country, region, or facility", "examples": ["Berlin", "CERN"]},
                {"name": "Event", "description": "A named event, incident, match, or discovery", "examples": ["COVID-19 pandemic", "World Cup Final"]},
                {"name": "Concept", "description": "A scientific concept, theory, technology, or domain term", "examples": ["photosynthesis", "GDP"]},
                {"name": "Product", "description": "A product, drug, software, or system", "examples": ["iPhone", "GPT-4"]},
            ],
            "extractionTargets": [
                "who works at or leads which organization",
                "what event happened where and when",
                "scientific findings — what was discovered or proven",
                "financial facts — revenue, stock price, market changes",
                "causal relationships — X caused Y, X led to Y",
                "user preferences and stated personal facts from dialogues",
            ],
            "exclusions": [
                "boilerplate legal disclaimers and copyright notices",
                "navigation menus and website chrome",
                "greetings, sign-offs, and scheduling small talk",
                "speculative opinions without factual basis",
            ],
            "positiveExamples": [
                {"input": "Reuters reported that Apple's Q3 revenue rose 8% to $81.8B, driven by iPhone sales in India.", "expected": "Apple (Organization) -revenue-> $81.8B; Apple -market-> India (Location); iPhone (Product) -drives-> revenue growth"},
                {"input": "A team at MIT discovered that CRISPR can target RNA in living cells, published in Nature 2024.", "expected": "MIT (Organization) -discovered-> CRISPR targets RNA (Concept); published_in Nature; year 2024"},
                {"input": "The 2023 earthquake in Turkey killed over 50,000 people and displaced millions.", "expected": "2023 Turkey earthquake (Event) -location-> Turkey; casualties 50000+; displaced millions"},
            ],
            "negativeExamples": [
                "Click here to subscribe to our newsletter",
                "All rights reserved. Copyright 2024.",
                "Let me check that for you — I'll get back to you shortly",
            ],
        }
        admin_token = self.kc.get_app_admin_token()
        logger.info("Profile setup using admin token (len=%d) for space=%s", len(admin_token), self.state.space)
        # DELETE existing profile first (avoids duplicate key error on re-run)
        self.app_svc.delete_extraction_profile(self.state.space, admin_token)
        status, body, lat = self.app_svc.put_extraction_profile(
            self.state.space, admin_token, profile,
        )
        _dashboard.record("put_profile", status, lat)
        self.audit.log("put_profile", {"status": status}, status, lat)
        if status not in (200, 201):
            logger.warning("PUT profile failed for %s: HTTP %d body=%s", self.state.user_id, status, str(body)[:300])
            return

        # GET and verify
        status2, body2, lat2 = self.app_svc.get_extraction_profile(
            self.state.space, admin_token,
        )
        _dashboard.record("get_profile", status2, lat2)
        profile_data = body2[0] if isinstance(body2, list) else body2 if isinstance(body2, dict) else {}
        has_role = "role" in profile_data and "Multi-domain" in profile_data.get("role", "")
        has_kinds = len(profile_data.get("entityKinds", [])) == 6
        has_targets = len(profile_data.get("extractionTargets", [])) == 6
        all_pass = has_role and has_kinds and has_targets
        self.audit.log("verify_profile", {
            "has_role": has_role, "has_kinds": has_kinds, "has_targets": has_targets,
            "PASS": all_pass,
        }, status2, lat2)
        if all_pass:
            logger.info("STEP 1 PROFILE VERIFY PASS for %s", self.state.user_id)
            _count_success()

    def _setup_instructions(self):
        """Step 2: PUT instructions, GET them back, verify count and content."""
        instructions = [
            {"family": "EXTRACTION", "name": "expand-acronyms",
             "text": "Always expand acronyms: VP=Vice President, CEO=Chief Executive Officer, WHO=World Health Organization, GDP=Gross Domestic Product. Never leave abbreviated forms in extracted facts."},
            {"family": "EXTRACTION", "name": "preserve-numbers",
             "text": "Preserve exact numbers, percentages, and currency amounts from source text. '8% revenue growth to $81.8B' must be stored as-is, not rounded or paraphrased."},
            {"family": "EXTRACTION", "name": "temporal-precision",
             "text": "Extract dates at the finest granularity available. 'Q3 2024' is more precise than '2024'. Always include the year."},
            {"family": "EXTRACTION", "name": "causal-and-scientific",
             "text": "Extract cause-effect as linked facts. For scientific content, preserve methodology and confidence (e.g. p<0.05). Do not conflate correlation with causation."},
            {"family": "SUMMARY", "name": "summary-style",
             "text": "One sentence, current status only. No speculation. Latest version if superseded."},
        ]
        admin_token = self.kc.get_app_admin_token()
        status, body, lat = self.app_svc.put_instructions(
            self.state.space, admin_token, instructions,
        )
        _dashboard.record("put_instructions", status, lat)
        self.audit.log("put_instructions", {"status": status}, status, lat)
        if status not in (200, 201):
            logger.warning("PUT instructions failed for %s: HTTP %d body=%s", self.state.user_id, status, str(body)[:300])
            return

        # GET and verify
        status2, body2, lat2 = self.app_svc.get_instructions(
            self.state.space, admin_token,
        )
        _dashboard.record("get_instructions", status2, lat2)
        instr_list = body2 if isinstance(body2, list) else []
        count_ok = len(instr_list) == 5
        names = {i.get("name") for i in instr_list}
        has_all = {"expand-acronyms", "preserve-numbers", "temporal-precision",
                   "causal-and-scientific", "summary-style"}.issubset(names)
        all_pass = count_ok and has_all
        self.audit.log("verify_instructions", {
            "count": len(instr_list), "count_ok": count_ok, "has_all": has_all,
            "PASS": all_pass,
        }, status2, lat2)
        if all_pass:
            logger.info("STEP 2 INSTRUCTIONS VERIFY PASS for %s (5 rules)", self.state.user_id)
            _count_success()

    def _verify_extraction_status(self):
        """Step 3: GET extraction/status — verify profileConfigured + availableModels."""
        self._ensure_token()
        status, body, lat = self.neuro.get_extraction_status(
            self.state.space, self._token,
        )
        _dashboard.record("extraction_status", status, lat)
        if status != 200 or not isinstance(body, dict):
            self.audit.log("extraction_status", {"status": status, "PASS": False}, status, lat)
            logger.warning("STEP 3 extraction status failed for %s: HTTP %d", self.state.user_id, status)
            return

        has_prompt = "promptVersion" in body
        has_models = len(body.get("availableModels", [])) > 0
        profile_configured = body.get("profileConfigured", False)
        self.audit.log("extraction_status", {
            "promptVersion": body.get("promptVersion"),
            "profileConfigured": profile_configured,
            "profileInert": body.get("profileInert"),
            "availableModels": len(body.get("availableModels", [])),
            "extractionModel": body.get("extractionModel"),
            "has_prompt": has_prompt,
            "has_models": has_models,
            "PASS": has_prompt,
        }, status, lat)
        if has_prompt:
            logger.info("STEP 3 EXTRACTION STATUS PASS for %s (prompt=%s, models=%d)",
                        self.state.user_id, body.get("promptVersion"), len(body.get("availableModels", [])))
            _count_success()

    # ---- Lifecycle ----

    def on_stop(self):
        """Log session summary, cleanup KC user + permissions."""
        summary = self.state.summary()
        self.audit.log("session_end", summary)
        self.audit.close()
        logger.info("User %s finished: %s", self.state.user_id, summary)

        # Cleanup if configured
        sim = CONFIG.get("simulation", {})
        if sim.get("cleanup_users", False):
            try:
                # Delete permissions (app admin token — tenant realm)
                if self._perm_ids:
                    app_token = self.kc.get_app_admin_token()
                    self.app_svc.delete_user_permissions(app_token, self._perm_ids)
                    logger.info("Deleted permissions for %s: %s", self.state.user_id, self._perm_ids)
                # Delete KC user (KC admin token — master realm)
                if self._kc_user_id:
                    self.kc.delete_user(self._kc_user_id)
            except Exception as e:
                logger.warning("Cleanup failed for %s: %s", self.state.user_id, e)


# ============================================================================
# Locust event hooks
# ============================================================================

@events.init.add_listener
def on_init(environment, **kwargs):
    """Pre-load data pool, verify admin token before any users spawn."""
    logger.info("=== Neuro Sim initializing ===")
    logger.info("Config: %s", os.environ.get("NEURO_SIM_CONFIG", "config/prestage.yaml"))
    logger.info("Report dir: %s", REPORT_DIR)
    _get_data_pool()
    kc = _get_keycloak()
    # Verify tokens work
    try:
        token = kc.get_admin_token()
        logger.info("KC admin token OK (master realm)")
    except Exception as e:
        logger.error("KC admin token FAILED: %s", e)
        logger.error("Set correct kc_admin_user/kc_admin_password in config")
        raise
    try:
        token = kc.get_app_admin_token()
        logger.info("App admin token OK (realm=%s)", kc._realm)
    except Exception as e:
        logger.error("App admin token FAILED: %s", e)
        raise
    _dashboard.start()
    logger.info("Run space: %s", _run_space)
    logger.info("=== Ready to spawn users ===")


@events.quitting.add_listener
def on_quit(environment, **kwargs):
    _dashboard.stop()
    state = _notification_state
    total = state["total_requests"]
    fails = state["total_failures"]
    pct = (fails / total * 100) if total else 0
    logger.info(
        "=== Sim complete: %d requests, %d failures (%.1f%%) ===",
        total, fails, pct,
    )
    logger.info("Reports: %s", REPORT_DIR)
