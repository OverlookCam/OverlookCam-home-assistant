from __future__ import annotations

import json
import logging
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

LOGGER = logging.getLogger("overlookcam-relay")
DEFAULT_PUSH_URL = "https://push.overlookcam.com"


@dataclass(frozen=True)
class InstallationCredentials:
    installation_id: str
    installation_token: str


class HostedPushClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OVERLOOKCAM_PUSH_URL", DEFAULT_PUSH_URL).strip().rstrip("/") or DEFAULT_PUSH_URL
        if not self.base_url.startswith("https://") and not self.base_url.startswith("http://127.0.0.1") and not self.base_url.startswith("http://localhost"):
            raise RuntimeError("OVERLOOKCAM_PUSH_URL must use HTTPS except for localhost testing")
        self.state_path = Path(os.getenv("OVERLOOKCAM_INSTALLATION_STATE", "/data/installation.json"))
        self.registration_token = os.getenv("OVERLOOKCAM_REGISTRATION_TOKEN", "").strip() or None
        self.relay_version = os.getenv("OVERLOOKCAM_RELAY_VERSION", "development").strip() or "development"
        self.platform = os.getenv("OVERLOOKCAM_RELAY_PLATFORM", "").strip() or self._platform_name()
        self.client = httpx.Client(timeout=httpx.Timeout(15.0))
        self.credentials = self._load_or_register()

    def _platform_name(self) -> str:
        machine = platform.machine().lower() or "unknown"
        return f"linux-{machine}"

    def close(self) -> None:
        self.client.close()

    def _load_or_register(self) -> InstallationCredentials:
        if self.state_path.is_file():
            try:
                payload = json.loads(self.state_path.read_text(encoding="utf-8"))
                installation_id = str(payload["installation_id"]).strip()
                installation_token = str(payload["installation_token"]).strip()
            except Exception as exc:
                raise RuntimeError(f"Invalid installation state at {self.state_path}") from exc
            if installation_id and installation_token:
                return InstallationCredentials(installation_id, installation_token)
        return self._register()

    def _register(self) -> InstallationCredentials:
        headers: dict[str, str] = {}
        if self.registration_token:
            headers["Authorization"] = f"Bearer {self.registration_token}"
        try:
            response = self.client.post(
                f"{self.base_url}/v1/installations/register",
                headers=headers,
                json={"relay_version": self.relay_version, "platform": self.platform},
            )
        except Exception as exc:
            raise RuntimeError("Unable to reach OverlookCam Push Service for installation registration") from exc
        if response.status_code != 201:
            raise RuntimeError(f"Push Service registration failed with HTTP {response.status_code}")
        payload = response.json()
        credentials = InstallationCredentials(
            installation_id=str(payload["installation_id"]),
            installation_token=str(payload["installation_token"]),
        )
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps({
            "installation_id": credentials.installation_id,
            "installation_token": credentials.installation_token,
        }, indent=2) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self.state_path)
        LOGGER.info("Registered relay installation %s", credentials.installation_id)
        return credentials

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.credentials.installation_token}"}

    def publish_sources(self, sources: list[dict[str, str]]) -> bool:
        try:
            response = self.client.put(
                f"{self.base_url}/v1/installations/{self.credentials.installation_id}/sources",
                headers=self.auth_headers,
                json={"sources": sources},
            )
        except Exception:
            LOGGER.warning("Unable to publish Frigate source inventory", exc_info=True)
            return False
        if response.status_code == 404:
            LOGGER.warning("Push Service does not yet support source inventory")
            return False
        if response.status_code != 200:
            LOGGER.warning("Push Service source inventory update returned HTTP %s", response.status_code)
            return False
        return True

    def submit_event(self, payload: dict[str, Any]) -> tuple[bool, int, int, int]:
        url = f"{self.base_url}/v1/installations/{self.credentials.installation_id}/events"
        try:
            response = self.client.post(url, headers=self.auth_headers, json=payload)
        except Exception:
            LOGGER.exception("Push Service request failed for event %s", payload.get("event_id", "unknown"))
            return False, 0, 0, 1
        if response.status_code != 202:
            LOGGER.error("Push Service rejected event %s with HTTP %s", payload.get("event_id", "unknown"), response.status_code)
            return False, 0, 0, 1
        data = response.json()
        return bool(data.get("accepted", False)), int(data.get("devices", 0)), int(data.get("delivered", 0)), int(data.get("failed", 0))

    def create_pairing_code(self) -> dict[str, str]:
        response = self.client.post(
            f"{self.base_url}/v1/installations/{self.credentials.installation_id}/pairing-codes",
            headers=self.auth_headers,
        )
        if response.status_code != 201:
            raise RuntimeError(f"Pairing-code request failed with HTTP {response.status_code}")
        payload = response.json()
        return {"pairing_code": str(payload["pairing_code"]), "expires_at": str(payload["expires_at"])}

    def create_claim_code(self) -> dict[str, str]:
        response = self.client.post(
            f"{self.base_url}/v1/installations/{self.credentials.installation_id}/claim-codes",
            headers=self.auth_headers,
        )
        if response.status_code != 201:
            raise RuntimeError(f"Claim-code request failed with HTTP {response.status_code}")
        payload = response.json()
        return {"claim_code": str(payload["claim_code"]), "expires_at": str(payload["expires_at"])}
