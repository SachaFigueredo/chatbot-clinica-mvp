"""Integration tests for the Conversations API endpoints.

Routes under test:
- ``GET  /api/v1/conversations`` — list conversations
- ``GET  /api/v1/conversations/{id}`` — get conversation detail
- ``POST /api/v1/conversations/{id}/take`` — take ownership
- ``POST /api/v1/conversations/{id}/reply`` — reply as human
- ``POST /api/v1/conversations/{id}/return-to-bot`` — return control to bot
"""

from __future__ import annotations

import pytest


# =========================================================================
# List conversations
# =========================================================================


class TestListConversations:
    LIST_URL = "/api/v1/conversations"

    async def test_list_empty(self, async_client, auth_headers):
        """No conversations returns an empty list."""
        resp = await async_client.get(self.LIST_URL, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    async def test_list_with_data(
        self, async_client, auth_headers, test_conversation, test_messages
    ):
        """Conversations with messages appear in the list."""
        resp = await async_client.get(self.LIST_URL, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == str(test_conversation.id)
        assert data[0]["status"] == "active"
        assert data[0]["patient_name"] == "Juan Pérez"
        # Last message preview
        assert data[0]["last_message"] is not None

    async def test_list_filter_by_status(
        self, async_client, auth_headers, test_conversation
    ):
        """Filtering by 'active' returns only active conversations."""
        resp = await async_client.get(
            self.LIST_URL,
            headers=auth_headers,
            params={"status": "active"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await async_client.get(
            self.LIST_URL,
            headers=auth_headers,
            params={"status": "escalated"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_unauthorized(self, async_client):
        """No auth header returns 401."""
        resp = await async_client.get(self.LIST_URL)
        assert resp.status_code == 401

    async def test_list_tenant_isolation(
        self, async_client, test_conversation, auth_headers_other
    ):
        """A user from tenant B cannot see tenant A's conversations."""
        resp = await async_client.get(self.LIST_URL, headers=auth_headers_other)
        assert resp.status_code == 200
        assert resp.json() == []


# =========================================================================
# Get conversation detail
# =========================================================================


class TestGetConversation:
    def _url(self, conv_id: str) -> str:
        return f"/api/v1/conversations/{conv_id}"

    async def test_get_detail(
        self, async_client, auth_headers, test_conversation, test_messages
    ):
        """Full conversation detail includes messages."""
        resp = await async_client.get(
            self._url(str(test_conversation.id)), headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == str(test_conversation.id)
        assert data["status"] == "active"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["origin"] == "patient"

    async def test_get_detail_not_found(
        self, async_client, auth_headers
    ):
        """Non-existent conversation returns 404."""
        resp = await async_client.get(
            self._url("00000000-0000-0000-0000-000000000000"),
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_get_detail_unauthorized(
        self, async_client, test_conversation
    ):
        """No auth returns 401."""
        resp = await async_client.get(self._url(str(test_conversation.id)))
        assert resp.status_code == 401


# =========================================================================
# Take conversation
# =========================================================================


class TestTakeConversation:
    def _url(self, conv_id: str) -> str:
        return f"/api/v1/conversations/{conv_id}/take"

    async def test_take_escalated(
        self, async_client, auth_headers, test_escalated_conversation
    ):
        """Taking an escalated conversation succeeds."""
        resp = await async_client.post(
            self._url(str(test_escalated_conversation.id)),
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True

    async def test_take_active_fails(
        self, async_client, auth_headers, test_conversation
    ):
        """Taking an active (not escalated) conversation returns 400."""
        resp = await async_client.post(
            self._url(str(test_conversation.id)),
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text

    async def test_take_already_taken(
        self, async_client, auth_headers, test_taken_conversation
    ):
        """Taking a conversation already taken by someone else returns 409."""
        resp = await async_client.post(
            self._url(str(test_taken_conversation.id)),
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text


# =========================================================================
# Reply to conversation
# =========================================================================


class TestReply:
    def _url(self, conv_id: str) -> str:
        return f"/api/v1/conversations/{conv_id}/reply"

    async def test_reply_taken_conversation(
        self, async_client, auth_headers, test_taken_conversation, mocker
    ):
        """Replying to a taken conversation sends via WhatsApp and returns success."""
        # Mock the Evolution API send_text to avoid real HTTP calls
        mocker.patch(
            "app.infrastructure.whatsapp.evolution.EvolutionAPIProvider.send_text",
            return_value=None,
        )

        resp = await async_client.post(
            self._url(str(test_taken_conversation.id)),
            headers=auth_headers,
            json={"message": "Gracias por esperar, ¿cómo puedo ayudarte?"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True

    async def test_reply_not_taken_fails(
        self, async_client, auth_headers, test_escalated_conversation
    ):
        """Replying to an escalated but not-taken conversation returns 403."""
        resp = await async_client.post(
            self._url(str(test_escalated_conversation.id)),
            headers=auth_headers,
            json={"message": "Hola!"},
        )
        assert resp.status_code == 403, resp.text

    async def test_reply_active_fails(
        self, async_client, auth_headers, test_conversation
    ):
        """Replying to an active (bot-controlled) conversation returns 400."""
        resp = await async_client.post(
            self._url(str(test_conversation.id)),
            headers=auth_headers,
            json={"message": "Hola!"},
        )
        assert resp.status_code == 400, resp.text

    async def test_reply_empty_message(
        self, async_client, auth_headers, test_taken_conversation
    ):
        """An empty reply message returns 400."""
        resp = await async_client.post(
            self._url(str(test_taken_conversation.id)),
            headers=auth_headers,
            json={"message": "   "},
        )
        assert resp.status_code == 400, resp.text


# =========================================================================
# Return to bot
# =========================================================================


class TestReturnToBot:
    def _url(self, conv_id: str) -> str:
        return f"/api/v1/conversations/{conv_id}/return-to-bot"

    async def test_return_to_bot_success(
        self, async_client, auth_headers, test_taken_conversation
    ):
        """Returning a taken conversation back to the bot succeeds."""
        resp = await async_client.post(
            self._url(str(test_taken_conversation.id)),
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert "devuelto" in data["message"].lower()

    async def test_return_to_bot_active_fails(
        self, async_client, auth_headers, test_conversation
    ):
        """Returning an active (not escalated) conversation returns 400."""
        resp = await async_client.post(
            self._url(str(test_conversation.id)),
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text
