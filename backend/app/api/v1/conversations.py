from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.domain.enums import ConversationStatus, MessageOrigin
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.conversation import (
    Conversation,
    ConversationMessage,
)
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.tenant import Tenant
from app.infrastructure.database.models.user import User
from app.infrastructure.whatsapp.evolution import EvolutionAPIProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConversationListItem(BaseModel):
    id: str
    patient_id: str
    patient_name: str | None
    patient_phone: str
    status: str
    channel: str
    last_message: str | None
    last_message_at: datetime | None
    escalated_to_name: str | None
    created_at: datetime
    updated_at: datetime


class MessageItem(BaseModel):
    id: str
    origin: str
    content: str
    intent: str | None
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    patient_id: str
    patient_name: str | None
    patient_phone: str
    status: str
    channel: str
    escalated_to_name: str | None
    escalated_at: datetime | None
    resolved_at: datetime | None
    messages: list[MessageItem]
    created_at: datetime
    updated_at: datetime


class ConversationTakeResponse(BaseModel):
    success: bool
    message: str


class ReplyRequest(BaseModel):
    message: str


class ReplyResponse(BaseModel):
    success: bool
    message: str


class ReturnToBotResponse(BaseModel):
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_conversation_or_404(
    db: Any,
    conversation_id: str,
    tenant_id: str,
) -> Conversation:
    """Get a conversation scoped to the tenant, or raise 404."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format",
        )

    stmt = select(Conversation).where(
        Conversation.id == conv_uuid,
        Conversation.tenant_id == uuid.UUID(tenant_id),
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


def _status_value(status: ConversationStatus | str) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _channel_value(status: Any) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _origin_value(status: Any) -> str:
    return status.value if hasattr(status, "value") else str(status)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ConversationListItem])
async def list_conversations(
    db: SessionDep,
    user: CurrentUser,
    status_filter: str | None = Query(
        None, alias="status", description="Filter by status: active, escalated, resolved, archived"
    ),
    channel: str | None = Query(
        None, description="Filter by channel: whatsapp, web"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List conversations for the current tenant.

    Returns conversations ordered by ``updated_at`` descending, with the
    latest message preview included.  Optionally filter by ``status``
    and/or ``channel``.
    """
    tenant_uuid = uuid.UUID(str(user.tenant_id))

    # -- Build query conditions --
    conditions = [Conversation.tenant_id == tenant_uuid]

    if status_filter:
        conditions.append(Conversation.status == status_filter)
    if channel:
        conditions.append(Conversation.channel == channel)

    # Correlated subquery for the latest message content per conversation.
    latest_msg = (
        select(ConversationMessage.content)
        .where(ConversationMessage.conversation_id == Conversation.id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )

    # Correlated subquery for the latest message timestamp per conversation.
    latest_msg_at = (
        select(ConversationMessage.created_at)
        .where(ConversationMessage.conversation_id == Conversation.id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )

    stmt = (
        select(
            Conversation,
            Patient,
            latest_msg,
            latest_msg_at,
        )
        .join(Patient, Conversation.patient_id == Patient.id)
        .where(*conditions)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    # Batch-load taken-by user names.
    escalated_user_ids = [
        str(row.Conversation.escalated_to)
        for row in rows
        if row.Conversation.escalated_to is not None
    ]
    user_names: dict[str, str] = {}
    if escalated_user_ids:
        user_uuids = [uuid.UUID(uid) for uid in set(escalated_user_ids)]
        stmt_users = select(User).where(User.id.in_(user_uuids))
        result_users = await db.execute(stmt_users)
        for u in result_users.scalars().all():
            user_names[str(u.id)] = u.name or u.email

    items: list[ConversationListItem] = []
    for row in rows:
        conv: Conversation = row.Conversation
        patient: Patient = row.Patient
        items.append(
            ConversationListItem(
                id=str(conv.id),
                patient_id=str(patient.id),
                patient_name=patient.name,
                patient_phone=patient.phone_number,
                status=_status_value(conv.status),
                channel=_channel_value(conv.channel),
                last_message=row[2],  # latest_msg subquery result
                last_message_at=row[3],  # latest_msg_at subquery result
                escalated_to_name=(
                    user_names.get(str(conv.escalated_to))
                    if conv.escalated_to
                    else None
                ),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
        )

    return items


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    db: SessionDep,
    user: CurrentUser,
):
    """Get full conversation detail with message history (last 50 messages).

    Includes patient info, escalation state, and all messages ordered
    ascending (oldest first, up to 50 total).
    """
    tenant_uuid = uuid.UUID(str(user.tenant_id))
    conv = await _get_conversation_or_404(db, conversation_id, str(user.tenant_id))

    # Load patient info.
    stmt_patient = select(Patient).where(Patient.id == conv.patient_id)
    result = await db.execute(stmt_patient)
    patient = result.scalar_one_or_none()

    # Load last 50 messages (order DESC then reverse to get ASC).
    stmt_msgs = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conv.id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt_msgs)
    messages = list(reversed(result.scalars().all()))

    # Resolve escalated_to user name.
    escalated_to_name: str | None = None
    if conv.escalated_to:
        stmt_user = select(User).where(User.id == conv.escalated_to)
        result = await db.execute(stmt_user)
        u = result.scalar_one_or_none()
        if u:
            escalated_to_name = u.name or u.email

    return ConversationDetail(
        id=str(conv.id),
        patient_id=str(patient.id) if patient else "",
        patient_name=patient.name if patient else None,
        patient_phone=patient.phone_number if patient else "",
        status=_status_value(conv.status),
        channel=_channel_value(conv.channel),
        escalated_to_name=escalated_to_name,
        escalated_at=conv.escalated_at,
        resolved_at=conv.resolved_at,
        messages=[
            MessageItem(
                id=str(m.id),
                origin=_origin_value(m.origin),
                content=m.content,
                intent=m.intent,
                created_at=m.created_at,
            )
            for m in messages
        ],
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.post("/{conversation_id}/take", response_model=ConversationTakeResponse)
async def take_conversation(
    conversation_id: str,
    db: SessionDep,
    user: CurrentUser,
):
    """Take ownership of an escalated conversation.

    Only works for conversations with ``status = escalated`` that have not
    already been taken by another user.  Sets ``escalated_to`` to the
    current user.
    """
    conv = await _get_conversation_or_404(db, conversation_id, str(user.tenant_id))

    if conv.status != ConversationStatus.escalated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "La conversación no está derivada. "
                "Solo se pueden tomar conversaciones derivadas."
            ),
        )

    if conv.escalated_to is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La conversación ya fue tomada por otro usuario.",
        )

    # Set ownership.
    conv.escalated_to = user.id
    db.add(conv)

    # Audit log.
    audit_entry = AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="conversation.taken",
        entity_type="conversation",
        entity_id=conversation_id,
        details={"taken_by": str(user.id)},
    )
    db.add(audit_entry)

    await db.commit()

    logger.info(
        "Conversation %s taken by user %s (tenant %s)",
        conversation_id, user.id, user.tenant_id,
    )

    return ConversationTakeResponse(
        success=True,
        message="Conversación tomada con éxito. Ahora podés responder al paciente.",
    )


@router.post("/{conversation_id}/reply", response_model=ReplyResponse)
async def reply_as_human(
    conversation_id: str,
    body: ReplyRequest,
    db: SessionDep,
    user: CurrentUser,
):
    """Reply to a patient in an escalated conversation.

    The message is sent via WhatsApp using the tenant's Evolution API
    instance and saved to the conversation history as ``origin = human``.

    The conversation must be ``escalated`` AND ``taken_by`` the current user.
    """
    conv = await _get_conversation_or_404(db, conversation_id, str(user.tenant_id))

    if conv.status != ConversationStatus.escalated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "La conversación no está derivada. "
                "Solo se puede responder en conversaciones derivadas."
            ),
        )

    if conv.escalated_to != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "No tomaste esta conversación. "
                "Usá el endpoint /take primero."
            ),
        )

    if not body.message or not body.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El mensaje no puede estar vacío.",
        )

    # Load patient info (needed for phone number).
    stmt_patient = select(Patient).where(Patient.id == conv.patient_id)
    result = await db.execute(stmt_patient)
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paciente no encontrado.",
        )

    # Load tenant slug (needed for Evolution API instance name).
    stmt_tenant = select(Tenant).where(Tenant.id == uuid.UUID(str(user.tenant_id)))
    result = await db.execute(stmt_tenant)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant no encontrado.",
        )

    # Send via WhatsApp FIRST (fail-fast before DB writes).
    try:
        provider = EvolutionAPIProvider(instance_name=tenant.slug)
        await provider.send_text(to=patient.phone_number, text=body.message)
    except Exception as exc:
        logger.error(
            "Failed to send human reply to %s via Evolution API: %s",
            patient.phone_number,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al enviar el mensaje por WhatsApp: {exc}",
        )

    # Save human message to conversation history.
    human_msg = ConversationMessage(
        conversation_id=conv.id,
        origin=MessageOrigin.human,
        content=body.message,
    )
    db.add(human_msg)

    # Audit log.
    audit_entry = AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="conversation.human_reply",
        entity_type="conversation_message",
        entity_id=conversation_id,
        details={
            "message_preview": body.message[:200],
        },
    )
    db.add(audit_entry)

    await db.commit()

    logger.info(
        "Human reply sent to conversation %s by user %s",
        conversation_id,
        user.id,
    )

    return ReplyResponse(
        success=True,
        message="Mensaje enviado al paciente correctamente.",
    )


@router.post("/{conversation_id}/return-to-bot", response_model=ReturnToBotResponse)
async def return_to_bot(
    conversation_id: str,
    db: SessionDep,
    user: CurrentUser,
):
    """Return control of a conversation back to the bot.

    Sets the conversation status back to ``active``, clears escalation
    info (``escalated_to``, ``escalated_at``), and saves a system-style
    message indicating the bot is back in control.
    """
    conv = await _get_conversation_or_404(db, conversation_id, str(user.tenant_id))

    if conv.status != ConversationStatus.escalated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "La conversación no está derivada. "
                "Solo se pueden devolver al bot conversaciones derivadas."
            ),
        )

    # Reset to active.
    conv.status = ConversationStatus.active
    conv.escalated_to = None
    conv.escalated_at = None
    db.add(conv)

    # Save a system message indicating the return.
    system_msg = ConversationMessage(
        conversation_id=conv.id,
        origin=MessageOrigin.human,
        content="El recepcionista devolvió el control al bot",
    )
    db.add(system_msg)

    # Audit log.
    audit_entry = AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="conversation.returned_to_bot",
        entity_type="conversation",
        entity_id=conversation_id,
        details={"returned_by": str(user.id)},
    )
    db.add(audit_entry)

    await db.commit()

    logger.info(
        "Conversation %s returned to bot by user %s",
        conversation_id,
        user.id,
    )

    return ReturnToBotResponse(
        success=True,
        message="Control devuelto al bot. El bot volverá a responder los mensajes del paciente.",
    )
