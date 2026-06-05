from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ConversationStatus
from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def escalate_conversation(
    db: AsyncSession,
    conversation_id: str,
    tenant_id: str,
    reason: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Escalate a conversation to human handling.

    Sets the conversation status to ``escalated``, records the escalation
    timestamp, and creates an audit log entry.

    Args:
        db: Database session.
        conversation_id: The conversation UUID string to escalate.
        tenant_id: The tenant UUID string.
        reason: Why the conversation is being escalated
                (e.g. ``emergency``, ``low_confidence``, ``patient_request``,
                 ``max_unknown_retries``).
        details: Optional extra data to store in the audit log
                 (e.g. last intent, confidence, message text).

    Returns:
        Dict with escalation info:
        ``{"conversation_id": ..., "status": "escalated", "reason": ...}``
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if conversation is None:
        logger.warning(
            "Cannot escalate: conversation %s not found", conversation_id
        )
        return {
            "conversation_id": conversation_id,
            "status": "not_found",
            "reason": reason,
        }

    if conversation.status == ConversationStatus.escalated:
        logger.info(
            "Conversation %s already escalated, skipping", conversation_id
        )
        return {
            "conversation_id": conversation_id,
            "status": "already_escalated",
            "reason": reason,
        }

    # Mark as escalated.
    conversation.status = ConversationStatus.escalated
    conversation.escalated_at = datetime.now(timezone.utc)
    db.add(conversation)

    # Create audit log entry.
    audit_entry = AuditLog(
        tenant_id=tenant_id,
        action="conversation.escalated",
        entity_type="conversation",
        entity_id=conversation_id,
        details={
            "reason": reason,
            **(details or {}),
        },
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(conversation)

    logger.info(
        "Conversation %s escalated. Reason: %s",
        conversation_id,
        reason,
    )

    return {
        "conversation_id": conversation_id,
        "status": "escalated",
        "reason": reason,
        "escalated_at": conversation.escalated_at.isoformat()
        if conversation.escalated_at
        else None,
    }
