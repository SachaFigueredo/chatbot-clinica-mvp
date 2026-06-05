from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings
from app.domain.interfaces.messaging import MessagingProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_SECONDS = 15
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0

# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class EvolutionAPIProvider(MessagingProvider):
    """Evolution API v2 adapter implementing MessagingProvider.

    Evolution API is a self-hosted WhatsApp gateway that exposes a REST API.
    Each tenant maps to a named *instance* (usually the tenant slug).

    Authentication uses the ``apikey`` header (or query parameter) configured
    via ``settings.evolution_api_key``.
    """

    def __init__(self, instance_name: str) -> None:
        self._instance = instance_name
        self._base_url = settings.evolution_api_url.rstrip("/")
        self._api_key = settings.evolution_api_key

    # -- Internal helpers ----------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._api_key,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with retries and exponential backoff."""
        url = self._url(path)
        headers = self._headers()

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS)
                ) as client:
                    resp = await client.request(
                        method,
                        url,
                        headers=headers,
                        json=json_body,
                    )

                if resp.status_code in (401, 403):
                    logger.error(
                        "Evolution API auth error (status=%d): %s",
                        resp.status_code,
                        resp.text,
                    )
                    resp.raise_for_status()

                if resp.status_code >= 500:
                    logger.warning(
                        "Evolution API server error (attempt %d/%d): %d %s",
                        attempt,
                        MAX_RETRIES,
                        resp.status_code,
                        resp.text[:200],
                    )
                    if attempt == MAX_RETRIES:
                        resp.raise_for_status()
                    await asyncio.sleep(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                    continue

                resp.raise_for_status()
                return resp.json() if resp.text else {}

            except httpx.TimeoutException:
                logger.warning(
                    "Evolution API timeout (attempt %d/%d)",
                    attempt,
                    MAX_RETRIES,
                )
                if attempt == MAX_RETRIES:
                    raise
                await asyncio.sleep(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))

            except httpx.HTTPStatusError:
                raise

        # Should not reach here, but satisfy the return type.
        return {}

    # -- Public API ----------------------------------------------------------

    async def send_text(self, to: str, text: str) -> str:
        """Send a plain text message via Evolution API.

        POST ``/message/sendText/{instance}``
        """
        body = {
            "number": to,
            "text": text,
        }
        data = await self._request(
            "POST",
            f"/message/sendText/{self._instance}",
            json_body=body,
        )
        # Evolution API v2 returns the message key under ``data.key.id``
        key = data.get("key", {})
        return key.get("id", "") or data.get("messageId", "")

    async def send_template(
        self, to: str, template_name: str, params: list[str]
    ) -> str:
        """Send a template message via Evolution API.

        POST ``/message/sendMedia/{instance}``

        The actual template identification depends on Evolution API version.
        For v2, templates are sent via the media endpoint with a template
        payload.
        """
        body = {
            "number": to,
            "template": {
                "name": template_name,
                "params": params,
            },
        }
        data = await self._request(
            "POST",
            f"/message/sendMedia/{self._instance}",
            json_body=body,
        )
        key = data.get("key", {})
        return key.get("id", "") or data.get("messageId", "")

    async def get_instance_status(self) -> dict:
        """Return the connection state of the instance.

        GET ``/instance/connectionState/{instance}``
        """
        return await self._request(
            "GET",
            f"/instance/connectionState/{self._instance}",
        )
