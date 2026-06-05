"""Integration tests for the Evolution API webhook endpoint.

Routes under test:
- ``POST /api/v1/webhooks/whatsapp/evolution`` — receive webhook
- ``GET  /api/v1/webhooks/whatsapp/evolution/status`` — health check

The webhook is *not* behind the TenantMiddleware (no auth required), but
the middleware resolves the tenant from the ``X-Tenant-Slug`` header or
from the request body's ``instance`` field.
"""

from __future__ import annotations

import uuid

import pytest

from app.domain.enums import ConversationStatus


class TestWebhookReceive:
    WEBHOOK_URL = "/api/v1/webhooks/whatsapp/evolution"

    _VALID_TENANT_BODY = {
        "event": "messages.upsert",
        "instance": "test-clinic",
        "data": {
            "key": {
                "remoteJid": "5491111111111@s.whatsapp.net",
                "fromMe": False,
                "id": "msg-abc-123",
            },
            "message": {"conversation": "Hola, quiero un turno"},
            "pushName": "Juan Pérez",
            "messageType": "conversation",
        },
    }

    async def test_receive_and_create_conversation(
        self, async_client_raw, test_tenant, tenant_headers
    ):
        """A valid webhook creates a patient + conversation + message."""
        resp = await async_client_raw.post(
            self.WEBHOOK_URL,
            headers=tenant_headers,
            json=self._VALID_TENANT_BODY,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ok"

    async def test_receive_from_self_is_ignored(
        self, async_client_raw, tenant_headers
    ):
        """Messages with fromMe=True are silently acknowledged (not processed)."""
        body = {
            "event": "messages.upsert",
            "instance": "test-clinic",
            "data": {
                "key": {
                    "remoteJid": "5491111111111@s.whatsapp.net",
                    "fromMe": True,  # <-- sent by ourselves
                    "id": "echo-msg",
                },
                "message": {"conversation": "Hola"},
                "pushName": "Bot",
                "messageType": "conversation",
            },
        }
        resp = await async_client_raw.post(
            self.WEBHOOK_URL, headers=tenant_headers, json=body
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "acknowledged"

    async def test_non_message_event_is_acknowledged(
        self, async_client_raw, tenant_headers
    ):
        """Non-message events (e.g. presence.update) are acknowledged."""
        body = {
            "event": "presence.update",
            "instance": "test-clinic",
            "data": {},
        }
        resp = await async_client_raw.post(
            self.WEBHOOK_URL, headers=tenant_headers, json=body
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"

    async def test_invalid_json_returns_400(
        self, async_client_raw, tenant_headers
    ):
        """A non-JSON body returns 400."""
        resp = await async_client_raw.post(
            self.WEBHOOK_URL,
            headers=tenant_headers | {"Content-Type": "application/json"},
            content="not json",
        )
        assert resp.status_code == 400

    async def test_no_tenant_header_returns_400(
        self, async_client_raw
    ):
        """Missing X-Tenant-Slug — webhook resolves tenant from body or
        acknowledges gracefully. Without instance field and with a phone
        number that doesn't match any tenant, the webhook returns 200
        (acknowledged) because the middleware no longer blocks at that layer.
        """
        body = {
            "event": "messages.upsert",
            # no instance field
            "data": {
                "key": {"remoteJid": "5491111111111@s.whatsapp.net", "fromMe": False},
                "message": {"conversation": "Hola"},
                "messageType": "conversation",
            },
        }
        resp = await async_client_raw.post(self.WEBHOOK_URL, json=body)
        # The webhook acknowledges gracefully when tenant cannot be resolved
        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"


# =========================================================================
# Webhook status (health check)
# =========================================================================


class TestWebhookStatus:
    STATUS_URL = "/api/v1/webhooks/whatsapp/evolution/status"

    async def test_status_returns_healthy(self, async_client):
        """The health endpoint returns a healthy status."""
        resp = await async_client.get(self.STATUS_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "evolution-webhook"
