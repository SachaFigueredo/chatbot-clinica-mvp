"""Mercado Pago billing service — subscription preapproval and webhook verification."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MP_API_BASE = "https://api.mercadopago.com"


class BillingServiceError(Exception):
    """Raised when a Mercado Pago API call fails."""


class BillingService:
    """Stateless service for Mercado Pago billing operations.

    All methods are static — the service is a namespace of related
    operations, not an object with state.
    """

    # ------------------------------------------------------------------
    # Preapproval (recurring subscription)
    # ------------------------------------------------------------------

    @staticmethod
    async def create_preapproval(
        payer_email: str,
        external_reference: str,
        reason: str,
        transaction_amount: float = 29.99,
        access_token: str | None = None,
    ) -> dict[str, str]:
        """Create a Mercado Pago preapproval (recurring subscription).

        Returns the preapproval ID and checkout init point URL.

        Raises ``BillingServiceError`` on MP API failure.
        """
        token = access_token or settings.mp_access_token
        if not token:
            raise BillingServiceError("MP_ACCESS_TOKEN is not configured")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Derive front-end base URL from notification URL for back_urls
        _back_url_base = "http://localhost:3000"
        if settings.mp_notification_url:
            _back_url_base = settings.mp_notification_url.split("/api/")[0]

        body: dict[str, Any] = {
            "reason": reason,
            "auto_recurring": {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": transaction_amount,
                "currency_id": "ARS",
            },
            "payer_email": payer_email,
            "back_urls": {
                "success": f"{_back_url_base}/settings/billing?status=success",
                "failure": f"{_back_url_base}/settings/billing?status=failure",
                "pending": f"{_back_url_base}/settings/billing?status=pending",
            },
            "auto_return": "approved",
            "notification_url": settings.mp_notification_url or "",
            "external_reference": external_reference,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{MP_API_BASE}/preapproval",
                headers=headers,
                json=body,
                timeout=30,
            )
            if resp.status_code != 201:
                logger.error(
                    "MP preapproval failed: %s %s",
                    resp.status_code,
                    resp.text,
                )
                raise BillingServiceError(
                    f"Mercado Pago error: {resp.status_code}"
                )
            data = resp.json()
            return {
                "id": data["id"],
                "init_point": data["init_point"],
            }

    # ------------------------------------------------------------------
    # Payment lookup (for webhook resolution)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_payment(
        payment_id: str,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a payment from MP by its ID.

        Returns the full payment response dict.
        """
        token = access_token or settings.mp_access_token
        if not token:
            raise BillingServiceError("MP_ACCESS_TOKEN is not configured")

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MP_API_BASE}/v1/payments/{payment_id}",
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Webhook signature verification
    # ------------------------------------------------------------------

    @staticmethod
    def verify_webhook_signature(
        body: bytes,
        x_signature: str,
        x_request_id: str | None = None,
        webhook_secret: str | None = None,
    ) -> bool:
        """Verify a Mercado Pago webhook ``X-Signature`` header.

        MP sends signatures in the format::

            ts={timestamp},v1={hex_hash}

        The ``v1`` hash is computed as::

            HMAC-SHA256(secret, "id:{request_id};"
                               "request-id:{request_id};"
                               "ts:{timestamp};"
                               + body)

        Returns ``True`` when the signature is valid, ``False`` otherwise.
        """
        secret = webhook_secret or settings.mp_webhook_secret
        if not secret or not x_signature:
            return False

        # Parse ``ts=...,v1=...`` format
        parts: dict[str, str] = {}
        for pair in x_signature.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                parts[key.strip()] = value.strip()

        ts = parts.get("ts")
        v1_hash = parts.get("v1")

        if not ts or not v1_hash:
            return False

        # Build the template that MP signs
        req_id = x_request_id or ""
        template = f"id:{req_id};request-id:{req_id};ts:{ts};"
        data_to_verify = template + body.decode("utf-8")

        expected = hmac.new(
            key=secret.encode("utf-8"),
            msg=data_to_verify.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, v1_hash)
