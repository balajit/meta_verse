from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class RemoteClientError(Exception):
    """Raised when remote control plane communication fails."""
    pass


class RemoteModeClient:
    def __init__(self, base_url: str, api_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    def submit_remote_build(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        url = f"{self.base_url}/v1/build/submit"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "X-Idempotency-Key": idempotency_key
        }
        logger.info("sending_remote_build_request", url=url)

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error("remote_client_http_error", error=str(e))
            raise RemoteClientError(f"Remote control plane request failed: {e}") from e