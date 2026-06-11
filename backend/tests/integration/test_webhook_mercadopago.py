"""Integration tests for the Mercado Pago webhook endpoint.

Routes under test:
- ``POST /api/v1/webhooks/mercadopago`` — receive MP notifications
"""

import hashlib
import hmac
import json

import pytest

from app.config import settings

MP_WEBHOOK_URL = "/api/v1/webhooks/mercadopago"


def _compute_signature(body: bytes, request_id: str, ts: str) -> str:
    """Compute a valid MP-style X-Signature for test requests."""
    secret = settings.mp_webhook_secret or "test-webhook-secret-for-testing"
    template = f"id:{request_id};request-id:{request_id};ts:{ts};"
    data_to_sign = template + body.decode("utf-8")
    v1_hash = hmac.new(
        key=secret.encode("utf-8"),
        msg=data_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"ts={ts},v1={v1_hash}"


# ---------------------------------------------------------------------------
# POST /webhooks/mercadopago
# ---------------------------------------------------------------------------


class TestWebhookMercadoPago:
    """POST /api/v1/webhooks/mercadopago — receive MP notifications."""

    async def test_invalid_signature_returns_401_no_db_change(
        self, async_client_raw, db_session, test_tenant
    ):
        """Task 6.5: Invalid X-Signature → 401, nothing modified in DB."""
        # Record original tenant state
        original_plan = test_tenant.plan
        original_status = test_tenant.status

        body = {
            "action": "payment.created",
            "type": "payment",
            "data": {"id": "123456789"},
        }
        raw_body = json.dumps(body).encode("utf-8")

        resp = await async_client_raw.post(
            MP_WEBHOOK_URL,
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": "ts=1,v1=invalid-signature",
            },
        )
        assert resp.status_code == 401, (
            f"Expected 401, got {resp.status_code}: {resp.text}"
        )

        # Verify no DB changes
        await db_session.refresh(test_tenant)
        assert test_tenant.plan == original_plan
        assert test_tenant.status == original_status

    async def test_valid_signature_processes_subscription_authorized(
        self, async_client_raw, db_session, test_tenant
    ):
        """A valid subscription_authorized event activates the tenant."""
        # Set tenant as suspended trial with a known MP subscription ID
        test_tenant.plan = "trial"
        test_tenant.status = "suspended"
        test_tenant.mercadopago_subscription_id = "preapp-123"
        db_session.add(test_tenant)
        await db_session.commit()

        body = {
            "action": "subscription.authorized",
            "type": "subscription_authorized",
            "data": {"id": "preapp-123"},
        }
        raw_body = json.dumps(body).encode("utf-8")
        request_id = "req-valid-1"
        ts = "1700000000"
        signature = _compute_signature(raw_body, request_id, ts)

        resp = await async_client_raw.post(
            MP_WEBHOOK_URL,
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature,
                "X-Request-Id": request_id,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ok"

        # Verify DB state changed
        await db_session.refresh(test_tenant)
        assert test_tenant.plan == "subscription", (
            f"Expected subscription, got {test_tenant.plan}"
        )
        assert test_tenant.status == "active", (
            f"Expected active, got {test_tenant.status}"
        )

    async def test_valid_signature_processes_subscription_cancelled(
        self, async_client_raw, db_session, test_tenant
    ):
        """A valid subscription_cancelled event suspends the tenant."""
        # Set tenant as active subscription
        test_tenant.plan = "subscription"
        test_tenant.status = "active"
        test_tenant.mercadopago_subscription_id = "preapp-456"
        db_session.add(test_tenant)
        await db_session.commit()

        body = {
            "action": "subscription.cancelled",
            "type": "subscription_cancelled",
            "data": {"id": "preapp-456"},
        }
        raw_body = json.dumps(body).encode("utf-8")
        request_id = "req-cancel-1"
        ts = "1700000001"
        signature = _compute_signature(raw_body, request_id, ts)

        resp = await async_client_raw.post(
            MP_WEBHOOK_URL,
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature,
                "X-Request-Id": request_id,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ok"

        # Verify DB state changed
        await db_session.refresh(test_tenant)
        assert test_tenant.status == "suspended", (
            f"Expected suspended, got {test_tenant.status}"
        )
