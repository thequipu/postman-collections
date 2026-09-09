"""applicationService client — graph CRUD + user permission management."""

import logging
import time

import requests

logger = logging.getLogger(__name__)


class AppServiceClient:
    """HTTP client for Quipu applicationService."""

    def __init__(self, base_url: str, app_service_path: str,
                 verify_ssl: bool = False):
        self.base = f"{base_url}{app_service_path}"
        self.verify = verify_ssl

    def _headers(self, token: str, accept: str = "application/json") -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, token: str,
                 json_body=None,
                 accept: str = "application/json") -> tuple[int, dict | str | list, float]:
        url = f"{self.base}{path}"
        t0 = time.perf_counter()
        resp = requests.request(
            method, url, headers=self._headers(token, accept),
            json=json_body, verify=self.verify, timeout=60,
        )
        latency = (time.perf_counter() - t0) * 1000
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body, latency

    # ---- Graph CRUD ----

    _SPACE_ACCEPT = "application/vnd.quipu.space+json;version=1.0.0"

    def create_graph(self, space: str, token: str,
                     graph_id: str, label: str) -> tuple[int, dict | str, float]:
        payload = {"graphId": graph_id, "label": label}
        return self._request("POST", f"/space/by-name/{space}/graph", token, payload, self._SPACE_ACCEPT)

    def delete_graph(self, space: str, token: str,
                     graph_id: str) -> tuple[int, dict | str, float]:
        return self._request("DELETE", f"/space/by-name/{space}/graph/{graph_id}", token, accept=self._SPACE_ACCEPT)

    def list_graphs(self, space: str, token: str) -> tuple[int, dict | str, float]:
        return self._request("GET", f"/space/by-name/{space}/graph", token, accept=self._SPACE_ACCEPT)

    # ---- Extraction Profile / Instructions / Model ----

    def put_extraction_profile(self, space: str, token: str,
                               profile: dict) -> tuple[int, dict | str, float]:
        return self._request("PUT", f"/space/by-name/{space}/extraction-profile", token, profile, self._SPACE_ACCEPT)

    def get_extraction_profile(self, space: str, token: str) -> tuple[int, dict | str, float]:
        return self._request("GET", f"/space/by-name/{space}/extraction-profile", token, accept=self._SPACE_ACCEPT)

    def put_instructions(self, space: str, token: str,
                         instructions: list[dict]) -> tuple[int, list | str, float]:
        return self._request("PUT", f"/space/by-name/{space}/instructions", token, instructions, self._SPACE_ACCEPT)

    def get_instructions(self, space: str, token: str) -> tuple[int, list | str, float]:
        return self._request("GET", f"/space/by-name/{space}/instructions", token, accept=self._SPACE_ACCEPT)

    def put_model_selection(self, space: str, token: str,
                            selection: dict) -> tuple[int, dict | str, float]:
        return self._request("PUT", f"/space/by-name/{space}/model-selection", token, selection, self._SPACE_ACCEPT)

    # ---- User Permissions ----

    def grant_user_permissions(self, token: str, username: str,
                               grants: list[dict],
                               granted_by: str) -> tuple[int, list | str, float]:
        """Grant permissions to a user. Sends all 4 grants in one POST.

        grants: list of {"entityId": int, "entityType": str, "permission_id": int}
        """
        payload = []
        for g in grants:
            payload.append({
                "entityId": g["entityId"],
                "entityType": g["entityType"],
                "userIdentifier": username,
                "permission": {"id": g["permission_id"]},
                "grantedBy": granted_by,
            })
        return self._request("POST", "/user-permission", token, payload, accept="*/*")

    def get_user_permission_ids(self, token: str,
                                username: str) -> list[int]:
        """Get all permission record IDs for a user (for cleanup)."""
        status, body, _ = self._request(
            "GET",
            f"/user-permission/permission_by_userid?userId={username}&page=0&size=100",
            token, accept="*/*",
        )
        if status != 200 or not isinstance(body, dict):
            return []
        content = body.get("content", [])
        return [item["id"] for item in content if "id" in item]

    def delete_user_permissions(self, token: str, ids: list[int]) -> tuple[int, str, float]:
        """Delete permission records by IDs."""
        if not ids:
            return 200, "no ids", 0.0
        id_str = ",".join(str(i) for i in ids)
        return self._request("DELETE", f"/user-permission/delete?ids={id_str}", token, accept="*/*")
