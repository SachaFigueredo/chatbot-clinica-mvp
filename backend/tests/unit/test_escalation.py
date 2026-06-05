"""Unit tests for the ``escalate_conversation`` domain function.

Tests cover:
- Escalating an active conversation
- Escalating an already-escalated conversation (idempotent safe-guard)
- Escalating a non-existent conversation
- Audit log creation on escalation
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.application.conversation.escalate import escalate_conversation
from app.domain.enums import ConversationStatus
from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.audit_log import AuditLog


class TestEscalateConversation:
    async def test_escalate_active_conversation(
        self, db_session, test_conversation, test_tenant
    ):
        """An active conversation becomes 'escalated' with timestamp."""
        result = await escalate_conversation(
            db=db_session,
            conversation_id=str(test_conversation.id),
            tenant_id=str(test_tenant.id),
            reason="patient_request",
            details={"last_intent": "humano", "msg_preview": "Quiero hablar con alguien"},
        )

        assert result["conversation_id"] == str(test_conversation.id)
        assert result["status"] == "escalated"
        assert result["reason"] == "patient_request"
        assert result["escalated_at"] is not None

        # Verify DB was updated
        conv = await db_session.get(Conversation, test_conversation.id)
        assert conv is not None
        assert conv.status == ConversationStatus.escalated
        assert conv.escalated_at is not None

    async def test_escalate_already_escalated(
        self, db_session, test_escalated_conversation, test_tenant
    ):
        """Escalating an already-escalated conversation returns 'already_escalated'."""
        result = await escalate_conversation(
            db=db_session,
            conversation_id=str(test_escalated_conversation.id),
            tenant_id=str(test_tenant.id),
            reason="patient_request",
        )

        assert result["status"] == "already_escalated"

    async def test_escalate_non_existent(self, db_session):
        """Escalating a non-existent conversation returns 'not_found'."""
        result = await escalate_conversation(
            db=db_session,
            conversation_id="00000000-0000-0000-0000-000000000000",
            tenant_id="00000000-0000-0000-0000-000000000000",
            reason="test",
        )

        assert result["status"] == "not_found"

    async def test_escalate_creates_audit_log(
        self, db_session, test_conversation, test_tenant
    ):
        """An audit log entry is created on successful escalation."""
        await escalate_conversation(
            db=db_session,
            conversation_id=str(test_conversation.id),
            tenant_id=str(test_tenant.id),
            reason="low_confidence",
            details={"confidence": 0.3},
        )

        # Query the audit log
        stmt = (
            select(AuditLog)
            .where(AuditLog.entity_id == str(test_conversation.id))
            .where(AuditLog.action == "conversation.escalated")
        )
        result = await db_session.execute(stmt)
        log = result.scalar_one_or_none()

        assert log is not None
        assert log.action == "conversation.escalated"
        assert log.entity_type == "conversation"
        assert log.details["reason"] == "low_confidence"
        assert log.details["confidence"] == 0.3
