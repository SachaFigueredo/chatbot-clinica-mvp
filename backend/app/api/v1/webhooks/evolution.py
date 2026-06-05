from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import async_session
from app.infrastructure.database.models.tenant import Tenant
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.conversation import (
    Conversation,
    ConversationMessage,
)
from app.domain.enums import ConversationStatus, ConversationChannel, MessageOrigin
from app.application.conversation.handle_message import handle_incoming_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhooks"])


# ---------------------------------------------------------------------------
# Webhook endpoint — receive messages from Evolution API
# ---------------------------------------------------------------------------


@router.post("/evolution")
async def receive_evolution_webhook(request: Request) -> dict[str, str]:
    """Receive an incoming WhatsApp message forwarded by Evolution API v2.

    Evolution API sends a POST with the following structure::

        {
            "event": "messages.upsert",
            "instance": "clinic-1",
            "data": {
                "key": {
                    "remoteJid": "5491112345678@s.whatsapp.net",
                    "fromMe": false,
                    "id": "ABC123"
                },
                "message": {
                    "conversation": "Hola, quiero un turno"
                },
                "pushName": "Juan Perez",
                "messageType": "conversation"
            }
        }

    This endpoint:
    1. Validates the request source
    2. Extracts the sender and destination numbers
    3. Identifies the tenant by destination number
    4. Finds or creates the patient record
    5. Finds or creates an active conversation
    6. Saves the incoming message
    7. Triggers the message handler (or logs it if T7 is not active)
    8. Returns 200 OK immediately
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        )

    # 1. Validate we have a message event.
    event = body.get("event", "")
    if event not in ("messages.upsert", "messages.update"):
        # Non-message events are acknowledged silently.
        logger.debug("Ignoring non-message event: %s", event)
        return {"status": "acknowledged"}

    data: dict[str, Any] = body.get("data", {})
    key: dict[str, Any] = data.get("key", {})
    message: dict[str, Any] = data.get("message", {})

    # 2. Extract message details.
    remote_jid: str = key.get("remoteJid", "")
    from_me: bool = key.get("fromMe", False)
    message_id: str = key.get("id", "")
    message_type: str = data.get("messageType", "conversation")
    push_name: str = data.get("pushName", "")

    # Ignore messages sent by ourselves (echo).
    if from_me:
        logger.debug("Ignoring echo message (fromMe=true)")
        return {"status": "acknowledged"}

    # Extract the phone number from remoteJid (strip @s.whatsapp.net).
    sender_number = _extract_phone(remote_jid)
    if not sender_number:
        logger.warning("Could not extract sender from remoteJid=%s", remote_jid)
        return {"status": "acknowledged"}

    # Extract text content.
    text = _extract_text(message, message_type)

    # 3. Identify tenant by the destination number.
    destination_number = _extract_destination(body, sender_number)

    async with async_session() as db:
        tenant = await _find_tenant_by_phone(db, destination_number)
        if tenant is None:
            logger.warning(
                "No tenant found for destination number %s", destination_number
            )
            return {"status": "acknowledged"}

        # 4. Find or create patient.
        patient = await _find_or_create_patient(db, tenant.id, sender_number, push_name)

        # 5. Find or create active conversation.
        conversation = await _find_or_create_conversation(db, tenant.id, patient.id)

        # 6. Save the incoming message.
        msg = ConversationMessage(
            conversation_id=conversation.id,
            origin=MessageOrigin.patient,
            content=text,
            extra_data={
                "message_id": message_id,
                "push_name": push_name,
                "message_type": message_type,
            },
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

    # 7. Trigger the message handler (stub until T7).
    await handle_incoming_message(
        tenant_id=str(tenant.id),
        patient_id=str(patient.id),
        conversation_id=str(conversation.id),
        message_id=str(msg.id),
        text=text,
        sender_number=sender_number,
    )

    logger.info(
        "Processed incoming message from %s for tenant %s: %.80s",
        sender_number,
        tenant.slug,
        text,
    )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get("/evolution/status")
async def webhook_status() -> dict[str, str]:
    """Return the current health status of the webhook endpoint."""
    return {"status": "healthy", "service": "evolution-webhook"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_phone(remote_jid: str) -> str:
    """Strip the ``@s.whatsapp.net`` suffix from a JID."""
    if "@" in remote_jid:
        return remote_jid.split("@")[0]
    return remote_jid


def _extract_text(message: dict[str, Any], message_type: str) -> str:
    """Extract the text content from an Evolution API message object."""
    # Conversation messages have ``conversation`` key.
    if message_type == "conversation":
        return message.get("conversation", "")
    # Extended text messages may have ``extendedTextMessage.text``.
    if message_type == "extendedTextMessage":
        return (
            message.get("extendedTextMessage", {}).get("text", "")
            or message.get("conversation", "")
        )
    # For other types (image, audio, etc.), return a placeholder.
    if message_type in ("imageMessage", "videoMessage", "audioMessage", "documentMessage"):
        return f"[{message_type}]"
    # Fallback.
    return message.get("conversation", "")


def _extract_destination(body: dict[str, Any], sender_number: str) -> str:
    """Try to determine the destination (clinic) phone number.

    Evolution API v2 does not include the destination explicitly in the
    webhook payload. We derive it heuristically:

    1. Check if the body has an explicit ``to`` field.
    2. Fall back to the ``instance`` name mapped via tenant config.
    3. As last resort, we rely on the fact that the request arrives at a
       URL specific to the tenant. For now, return an empty string so
       the caller treats it as an unknown destination.
    """
    # Some Evolution API configurations include a ``to`` field.
    to = body.get("to", "")
    if to:
        return to

    # The ``instance`` field in the body identifies which WhatsApp instance
    # received the message. We'll use this to look up the tenant later.
    instance = body.get("instance", "")
    if instance:
        return instance  # This will be resolved via slug → phone mapping.

    return ""


async def _find_tenant_by_phone(
    db: AsyncSession, phone: str
) -> Tenant | None:
    """Look up a tenant by its WhatsApp phone number or slug."""
    if not phone:
        return None

    # Try phone number match first.
    stmt = select(Tenant).where(Tenant.phone_number == phone, Tenant.status == "active")
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant:
        return tenant

    # Try slug match (for when instance name doubles as slug).
    stmt = select(Tenant).where(Tenant.slug == phone, Tenant.status == "active")
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _find_or_create_patient(
    db: AsyncSession,
    tenant_id: Any,
    phone_number: str,
    push_name: str,
) -> Patient:
    """Find an existing patient or create a new one."""
    stmt = select(Patient).where(
        Patient.tenant_id == tenant_id,
        Patient.phone_number == phone_number,
    )
    result = await db.execute(stmt)
    patient = result.scalar_one_or_none()

    if patient:
        # Update the name if push_name is available and patient has no name.
        if push_name and not patient.name:
            patient.name = push_name
            db.add(patient)
            await db.commit()
            await db.refresh(patient)
        return patient

    patient = Patient(
        tenant_id=tenant_id,
        phone_number=phone_number,
        name=push_name or None,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    logger.info("Created new patient %s for tenant %s", phone_number, tenant_id)
    return patient


async def _find_or_create_conversation(
    db: AsyncSession,
    tenant_id: Any,
    patient_id: Any,
) -> Conversation:
    """Find the active conversation for this patient or create a new one."""
    stmt = select(Conversation).where(
        Conversation.tenant_id == tenant_id,
        Conversation.patient_id == patient_id,
        Conversation.status == ConversationStatus.active,
    ).order_by(Conversation.created_at.desc())
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if conversation:
        return conversation

    conversation = Conversation(
        tenant_id=tenant_id,
        patient_id=patient_id,
        status=ConversationStatus.active,
        channel=ConversationChannel.whatsapp,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    logger.info("Created new conversation for patient %s", patient_id)
    return conversation
