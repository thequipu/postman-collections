"""Neuro Memory API client — all ingest, recall, graph, pin, edge operations."""

import logging
import time
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


class NeuroClient:
    """Stateless HTTP client for Quipu Neuro Memory APIs."""

    def __init__(self, base_url: str, neuro_path: str, tenant: str, fabric: str,
                 extra_headers: dict | None = None, verify_ssl: bool = False):
        self.base = f"{base_url}{neuro_path}"
        self.tenant = tenant
        self.fabric = fabric
        self.verify = verify_ssl
        self._extra = extra_headers or {}

    def _headers(self, token: str) -> dict:
        h = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": self.tenant,
            "X-Fabric": self.fabric,
            "Content-Type": "application/json",
        }
        h.update(self._extra)
        return h

    def _request(self, method: str, path: str, token: str,
                 json_body: dict | None = None) -> tuple[int, dict | str, float]:
        """Execute request, return (status, body, latency_ms)."""
        url = f"{self.base}{path}"
        t0 = time.perf_counter()
        resp = requests.request(
            method, url, headers=self._headers(token),
            json=json_body, verify=self.verify, timeout=60,
        )
        latency = (time.perf_counter() - t0) * 1000
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body, latency

    # ---- Space ingest ----
    def ingest_space(self, space: str, token: str, content: str,
                     thread_id: str = "", speaker: str = "",
                     occurred_at: str = "", content_type: str = "text/plain",
                     role: str = "") -> tuple[int, Any, float]:
        payload: dict[str, Any] = {"content": content, "contentType": content_type}
        if thread_id:
            payload["threadId"] = thread_id
        if speaker:
            payload["speaker"] = speaker
        if occurred_at:
            payload["occurredAt"] = occurred_at
        if role:
            payload["role"] = role
        return self._request("POST", f"/v1/spaces/{space}/ingest", token, payload)

    # ---- Namespace ingest (text field, not content) ----
    def ingest_namespace(self, namespace: str, token: str, text: str,
                         thread_id: str = "", owner_user_id: str = "",
                         occurred_at: str = "", source_type: str = "USER",
                         content_type: str = "text/plain") -> tuple[int, Any, float]:
        payload: dict[str, Any] = {
            "text": text,
            "contentType": content_type,
            "sourceType": source_type,
        }
        if thread_id:
            payload["threadId"] = thread_id
        if owner_user_id:
            payload["ownerUserId"] = owner_user_id
        if occurred_at:
            payload["occurredAt"] = occurred_at
        return self._request("POST", f"/v1/memories/{namespace}/ingest", token, payload)

    # ---- Graph ingest ----
    def ingest_graph(self, space: str, graph_id: str, token: str,
                     content: str, thread_id: str = "",
                     content_type: str = "text/plain") -> tuple[int, Any, float]:
        payload: dict[str, Any] = {"content": content, "contentType": content_type}
        if thread_id:
            payload["threadId"] = thread_id
        return self._request("POST", f"/v1/spaces/{space}/graphs/{graph_id}/ingest", token, payload)

    # ---- Assert (fact triple) ----
    def assert_fact(self, space: str, token: str, entity: str,
                    label: str, prop: str, value: str,
                    world_time: bool = False,
                    valid_from: str = "", valid_to: str = "") -> tuple[int, Any, float]:
        payload: dict[str, Any] = {
            "entitySurfaceForm": entity,
            "label": label,
            "property": prop,
            "value": value,
            "worldTime": world_time,
        }
        if valid_from:
            payload["validFrom"] = valid_from
        if valid_to:
            payload["validTo"] = valid_to
        return self._request("POST", f"/v1/spaces/{space}/assert", token, payload)

    # ---- Namespace assert ----
    def assert_fact_ns(self, namespace: str, token: str, entity: str,
                       label: str, prop: str, value: str,
                       world_time: bool = False) -> tuple[int, Any, float]:
        payload = {
            "entitySurfaceForm": entity,
            "label": label,
            "property": prop,
            "value": value,
            "worldTime": world_time,
        }
        return self._request("POST", f"/v1/memories/{namespace}/assert", token, payload)

    # ---- Recall (space) ----
    def recall_space(self, space: str, token: str, query: str,
                     user_id: str = "", mode: str = "LIVE",
                     include_invalidated: bool = False,
                     token_budget: int = 2000,
                     thread_id: str = "",
                     as_of: str = "") -> tuple[int, Any, float]:
        payload: dict[str, Any] = {
            "query": query,
            "mode": mode,
            "includeInvalidated": include_invalidated,
            "tokenBudget": token_budget,
        }
        if user_id:
            payload["userId"] = user_id
        if thread_id:
            payload["threadId"] = thread_id
        if as_of:
            payload["asOf"] = as_of
        return self._request("POST", f"/v1/spaces/{space}/recall", token, payload)

    # ---- Recall (namespace) ----
    def recall_namespace(self, namespace: str, token: str, query: str,
                         user_id: str = "", mode: str = "LIVE",
                         include_invalidated: bool = False,
                         token_budget: int = 2000) -> tuple[int, Any, float]:
        payload: dict[str, Any] = {
            "query": query,
            "mode": mode,
            "includeInvalidated": include_invalidated,
            "tokenBudget": token_budget,
        }
        if user_id:
            payload["userId"] = user_id
        return self._request("POST", f"/v1/memories/{namespace}/recall", token, payload)

    # ---- Edges list (POST /v1/spaces/{space}/graph/edges/list) ----
    def list_edges(self, space: str, namespace: str,
                   token: str, limit: int = 20) -> tuple[int, Any, float]:
        payload = {"namespaceId": namespace, "limit": limit, "cursor": None}
        return self._request("POST", f"/v1/spaces/{space}/graph/edges/list", token, payload)

    # ---- Nodes list (POST /v1/spaces/{space}/graph/nodes/list) ----
    def list_nodes(self, space: str, namespace: str,
                   token: str, limit: int = 20) -> tuple[int, Any, float]:
        payload = {"namespaceId": namespace, "limit": limit, "cursor": None}
        return self._request("POST", f"/v1/spaces/{space}/graph/nodes/list", token, payload)

    # ---- Pin (POST /v1/spaces/{space}/graph/edge/pin?namespaceId=...&uri=...) ----
    def pin_fact(self, space: str, namespace: str, token: str,
                 fact_uri: str) -> tuple[int, Any, float]:
        uri_enc = quote(fact_uri, safe="")
        return self._request(
            "POST",
            f"/v1/spaces/{space}/graph/edge/pin?namespaceId={namespace}&uri={uri_enc}",
            token,
        )

    # ---- Unpin (DELETE /v1/spaces/{space}/graph/edge/pin?namespaceId=...&uri=...) ----
    def unpin_fact(self, space: str, namespace: str, token: str,
                   fact_uri: str) -> tuple[int, Any, float]:
        uri_enc = quote(fact_uri, safe="")
        return self._request(
            "DELETE",
            f"/v1/spaces/{space}/graph/edge/pin?namespaceId={namespace}&uri={uri_enc}",
            token,
        )

    # ---- Patch edge (PATCH /v1/spaces/{space}/graph/edge?uri=...) ----
    def patch_edge(self, space: str, namespace: str, token: str,
                   fact_uri: str, patch: dict) -> tuple[int, Any, float]:
        uri_enc = quote(fact_uri, safe="/")  # keep / intact, encode # and spaces
        return self._request(
            "PATCH",
            f"/v1/spaces/{space}/graph/edge?uri={uri_enc}",
            token, patch,
        )

    # ---- Delete edge (DELETE /v1/spaces/{space}/graph/edge?uri=...) ----
    def delete_edge(self, space: str, namespace: str, token: str,
                    fact_uri: str) -> tuple[int, Any, float]:
        uri_enc = quote(fact_uri, safe="/")  # keep / intact
        return self._request(
            "DELETE",
            f"/v1/spaces/{space}/graph/edge?uri={uri_enc}",
            token,
        )

    # ---- Scopes ----
    def list_scopes(self, space: str, token: str) -> tuple[int, Any, float]:
        return self._request("GET", f"/v1/spaces/{space}/scopes", token)
