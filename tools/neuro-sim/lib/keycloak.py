"""Keycloak token + admin user management for Neuro simulation."""

import logging
import time

import requests

logger = logging.getLogger(__name__)


class KeycloakClient:
    """Manages OAuth2 tokens and user lifecycle via Keycloak admin API."""

    def __init__(self, token_url: str, client_id: str, client_secret: str,
                 admin_username: str, admin_password: str,
                 kc_admin_user: str = "", kc_admin_password: str = "",
                 token_lifetime: int = 300, refresh_buffer: int = 20):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.token_lifetime = token_lifetime
        self.refresh_buffer = refresh_buffer

        # Derive URLs from token URL
        # token_url: https://host/realms/quipuprestage/protocol/openid-connect/token
        parts = self.token_url.split("/realms/")
        self._kc_base = parts[0]  # https://host
        self._realm = parts[1].split("/")[0]  # quipuprestage

        # Keycloak admin API uses master realm + admin-cli client
        self._admin_token_url = f"{self._kc_base}/realms/master/protocol/openid-connect/token"
        self._admin_base = f"{self._kc_base}/admin/realms/{self._realm}"
        self._kc_admin_user = kc_admin_user or admin_username
        self._kc_admin_password = kc_admin_password or admin_password

        # Admin token cache
        self._admin_token = None
        self._admin_expires = 0.0

    # ---- Admin token (for user/space management) ----

    def get_admin_token(self) -> str:
        """Get Keycloak admin token (master realm, admin-cli client)."""
        if self._admin_token and time.time() < self._admin_expires:
            return self._admin_token

        payload = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": self._kc_admin_user,
            "password": self._kc_admin_password,
        }
        resp = requests.post(self._admin_token_url, data=payload, verify=False, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        self._admin_token = data["access_token"]
        expires_in = data.get("expires_in", self.token_lifetime)
        self._admin_expires = time.time() + expires_in - self.refresh_buffer
        logger.debug("Admin token refreshed, expires in %ds", expires_in)
        return self._admin_token

    def force_refresh_admin(self) -> str:
        self._admin_expires = 0
        return self.get_admin_token()

    def get_app_admin_token(self) -> str:
        """Get app admin token (tenant realm — for applicationService calls like granting permissions)."""
        payload = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.admin_username,
            "password": self.admin_password,
        }
        resp = requests.post(self.token_url, data=payload, verify=False, timeout=30)
        resp.raise_for_status()
        return resp.json()["access_token"]

    # ---- User CRUD (Keycloak admin API) ----

    def create_user(self, username: str, password: str) -> str:
        """Create a Keycloak user. Returns the user's Keycloak ID."""
        admin_token = self.get_admin_token()
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "username": username,
            "enabled": True,
            "credentials": [{
                "type": "password",
                "value": password,
                "temporary": False,
            }],
        }
        resp = requests.post(
            f"{self._admin_base}/users",
            json=payload, headers=headers, verify=False, timeout=30,
        )
        if resp.status_code == 409:
            logger.info("User %s already exists, looking up ID", username)
            return self._get_user_id(username)
        resp.raise_for_status()

        location = resp.headers.get("Location", "")
        user_id = location.rstrip("/").split("/")[-1]
        logger.info("Created Keycloak user %s (id=%s)", username, user_id)
        return user_id

    def _get_user_id(self, username: str) -> str:
        """Look up user's Keycloak ID by username."""
        admin_token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(
            f"{self._admin_base}/users",
            params={"username": username, "exact": "true"},
            headers=headers, verify=False, timeout=30,
        )
        resp.raise_for_status()
        users = resp.json()
        if users:
            return users[0]["id"]
        raise ValueError(f"User {username} not found in Keycloak")

    def delete_user(self, kc_user_id: str):
        """Delete a Keycloak user by their ID."""
        admin_token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.delete(
            f"{self._admin_base}/users/{kc_user_id}",
            headers=headers, verify=False, timeout=30,
        )
        if resp.status_code == 404:
            logger.warning("User %s already deleted", kc_user_id)
            return
        resp.raise_for_status()
        logger.info("Deleted Keycloak user %s", kc_user_id)

    # ---- Per-user token ----

    def get_user_token(self, username: str, password: str) -> tuple[str, float]:
        """Get access token for a specific user. Returns (token, expires_at)."""
        payload = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": username,
            "password": password,
        }
        resp = requests.post(self.token_url, data=payload, verify=False, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", self.token_lifetime)
        expires_at = time.time() + expires_in - self.refresh_buffer
        return token, expires_at
