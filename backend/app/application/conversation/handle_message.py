from __future__ import annotations

import logging
import re
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.domain.enums import MessageOrigin
from app.domain.interfaces.llm import IntentResult
from app.infrastructure.database.session import async_session
from app.infrastructure.database.models.conversation import (
    Conversation,
    ConversationMessage,
)
from app.infrastructure.database.models.clinic_config import ClinicConfig
from app.infrastructure.database.models.tenant import Tenant
from app.infrastructure.database.models.doctor import Doctor
# Repositories used indirectly via booking services (AppointmentRepo, PatientRepo)
from app.infrastructure.llm.openai_client import OpenAIClient
from app.application.conversation.classify_intent import ClassifyIntentService
from app.application.conversation.escalate import escalate_conversation
from app.application.faq.answer import search_faqs, generate_faq_response
from app.application.appointment.get_slots import GetAvailableSlots
from app.application.appointment.book import BookAppointment
from app.application.appointment.cancel import CancelAppointment, handle_cancel_from_reminder
from app.application.appointment.reschedule import RescheduleAppointment, handle_reschedule_from_reminder
from app.infrastructure.calendar.google import GoogleCalendarProvider
from app.infrastructure.whatsapp.evolution import EvolutionAPIProvider
from app.infrastructure.database.repository.appointment_repo import AppointmentRepo
from app.infrastructure.database.models.appointment import Appointment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting (in-memory)
# ---------------------------------------------------------------------------

MAX_MESSAGES_PER_MINUTE = 20
WINDOW_SECONDS = 60

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
"""Maps ``sender_number`` to a list of timestamps of recent messages."""


def _check_rate_limit(sender_number: str) -> bool:
    """Check if the sender has exceeded the rate limit.

    Returns ``True`` if the message is allowed, ``False`` if rate-limited.
    """
    now = time.monotonic()
    window_start = now - WINDOW_SECONDS

    timestamps = _rate_limit_store[sender_number]
    # Prune old entries.
    _rate_limit_store[sender_number] = [
        t for t in timestamps if t > window_start
    ]

    if len(_rate_limit_store[sender_number]) >= MAX_MESSAGES_PER_MINUTE:
        logger.warning(
            "Rate limit exceeded for %s (%d msgs in %ds)",
            sender_number,
            len(_rate_limit_store[sender_number]),
            WINDOW_SECONDS,
        )
        return False

    _rate_limit_store[sender_number].append(now)
    return True


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


async def handle_incoming_message(
    tenant_id: str,
    patient_id: str,
    conversation_id: str,
    message_id: str,
    text: str,
    sender_number: str,
) -> None:
    """Process an incoming WhatsApp message through the AI orchestrator.

    This is the entry point called by the webhook after saving the
    incoming message. It:

    1. Checks rate limit.
    2. Loads tenant info, clinic context, and conversation history.
    3. Classifies the intent using GPT-4o-mini.
    4. Routes to the appropriate handler (agendar, faq, humano, etc.).
    5. Saves the bot's response to the database.
    6. Sends the response via Evolution API.
    7. Handles escalation when needed.

    Args:
        tenant_id: Tenant UUID string.
        patient_id: Patient UUID string.
        conversation_id: Conversation UUID string.
        message_id: The saved incoming message UUID string.
        text: The plain-text content of the patient's message.
        sender_number: The patient's phone number (without ``@s.whatsapp.net``).
    """
    # --- 1. Rate limit check ---
    if not _check_rate_limit(sender_number):
        logger.info("Message from %s dropped due to rate limiting", sender_number)
        return

    # --- 2. Load context ---
    async with async_session() as db:
        try:
            # Load tenant for slug (used by EvolutionAPIProvider) and name.
            stmt_tenant = select(Tenant).where(Tenant.id == tenant_id)
            result = await db.execute(stmt_tenant)
            tenant = result.scalar_one_or_none()
            if tenant is None:
                logger.error("Tenant %s not found, cannot process message", tenant_id)
                return

            # Load clinic config for context.
            stmt_config = select(ClinicConfig).where(
                ClinicConfig.tenant_id == tenant_id
            )
            result = await db.execute(stmt_config)
            clinic_config = result.scalar_one_or_none()

            # Load conversation (needed for booking state management).
            stmt_conv = select(Conversation).where(Conversation.id == conversation_id)
            result_conv = await db.execute(stmt_conv)
            conversation = result_conv.scalar_one_or_none()

            # Load conversation history, EXCLUDING the current message.
            history_without_current = await _load_history_excluding(
                db, conversation_id, message_id
            )

            # --- 3a. Check for active multi-turn state ---
            # If the patient is in the middle of a cancel, reschedule, or
            # booking flow, skip intent classification and route directly
            # to the appropriate multi-turn handler.
            cancel_step = None
            reschedule_step = None
            booking_step = None
            if conversation and conversation.extra_data:
                cancel_step = conversation.extra_data.get("cancel_step")
                reschedule_step = conversation.extra_data.get("reschedule_step")
                booking_step = conversation.extra_data.get("booking_step")

            if cancel_step:
                bot_message = await _handle_cancelar_multiturn(
                    db=db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    patient_id=patient_id,
                    sender_number=sender_number,
                    tenant_name=tenant.name or "la clínica",
                    clinic_config=clinic_config,
                    conversation=conversation,
                    patient_message=text,
                )
                result_intent = "cancelar"
                result_confidence = 1.0
                is_emergency = False
            elif reschedule_step:
                bot_message = await _handle_reprogramar_multiturn(
                    db=db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    patient_id=patient_id,
                    sender_number=sender_number,
                    tenant_name=tenant.name or "la clínica",
                    clinic_config=clinic_config,
                    conversation=conversation,
                    patient_message=text,
                )
                result_intent = "reprogramar"
                result_confidence = 1.0
                is_emergency = False
            elif booking_step:
                bot_message = await _handle_booking_multiturn(
                    db=db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    patient_id=patient_id,
                    sender_number=sender_number,
                    tenant_name=tenant.name or "la clínica",
                    clinic_config=clinic_config,
                    conversation=conversation,
                    patient_message=text,
                )
                result_intent = "agendar"
                result_confidence = 1.0
                is_emergency = False
            else:
                # --- 3b. Check for reminder reply (F4) ---
                # When a patient responds to a reminder message, we handle it
                # directly BEFORE intent classification to avoid LLM latency
                # and ensure deterministic routing.
                reminder_bot_message = None
                if conversation:
                    reminder_bot_message = await _handle_reminder_reply(
                        db=db,
                        conversation_id=conversation_id,
                        patient_id=patient_id,
                        tenant_id=tenant_id,
                        patient_message=text,
                        sender_number=sender_number,
                        tenant_slug=tenant.slug,
                    )

                if reminder_bot_message:
                    bot_message = reminder_bot_message
                    result_intent = "reminder_reply"
                    result_confidence = 1.0
                    is_emergency = False
                else:
                    # --- 3c. Classify intent (normal flow) ---
                    llm_provider = OpenAIClient(
                        api_key=settings.openai_api_key or "",
                        model="gpt-4o-mini",
                    )
                    classifier = ClassifyIntentService(db, llm_provider)
                    result = await classifier.classify(
                        tenant_id=tenant_id,
                        conversation_history=history_without_current,
                        patient_message=text,
                    )
                    result_intent = result.intent
                    result_confidence = result.confidence
                    is_emergency = result.is_emergency

                    # --- 4. Route to handler ---
                    bot_message = await _route_intent(
                        db=db,
                        llm_provider=llm_provider,
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        patient_id=patient_id,
                        sender_number=sender_number,
                        tenant_name=tenant.name or "la clínica",
                        tenant_slug=tenant.slug,
                        clinic_config=clinic_config,
                        result=result,
                        patient_message=text,
                    )

            # --- 5. Save bot response & update patient message intent ---
            await _save_responses(
                db=db,
                conversation_id=conversation_id,
                message_id=message_id,
                bot_message=bot_message,
                intent=result_intent,
                confidence=result_confidence,
                is_emergency=is_emergency,
            )

            # --- 6. Send response via Evolution API ---
            if bot_message:
                await _send_whatsapp_response(
                    tenant_slug=tenant.slug,
                    to=sender_number,
                    text=bot_message,
                )

        except Exception:
            logger.exception(
                "Unhandled error processing message for tenant %s: %.80s",
                tenant_id,
                text,
            )


# ---------------------------------------------------------------------------
# Intent routing
# ---------------------------------------------------------------------------


async def _route_intent(
    db: Any,
    llm_provider: OpenAIClient,
    tenant_id: str,
    conversation_id: str,
    patient_id: str,
    sender_number: str,
    tenant_name: str,
    tenant_slug: str,
    clinic_config: Any,
    result: IntentResult,
    patient_message: str,
) -> str:
    """Route the classified intent to the appropriate handler.

    Returns the bot response text to send to the patient.
    """
    # Emergency overrides any other intent.
    if result.is_emergency:
        return await _handle_emergency(
            db=db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            clinic_config=clinic_config,
            patient_message=patient_message,
        )

    # Route by intent.
    intent_handlers = {
        "saludo": _handle_saludo,
        "agendar": _handle_booking_multiturn,
        "consultar_turno": _handle_consultar_turno,
        "reprogramar": _handle_reprogramar_multiturn,
        "cancelar": _handle_cancelar_multiturn,
        "faq": _handle_faq,
        "humano": _handle_humano,
        "desconocido": _handle_desconocido,
    }

    handler = intent_handlers.get(result.intent, _handle_desconocido)

    bot_message = await handler(
        db=db,
        llm_provider=llm_provider,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        patient_id=patient_id,
        sender_number=sender_number,
        tenant_name=tenant_name,
        clinic_config=clinic_config,
        result=result,
        patient_message=patient_message,
    )

    return bot_message


# ---------------------------------------------------------------------------
# Intent handlers
# ---------------------------------------------------------------------------


async def _handle_saludo(
    db: Any,
    llm_provider: OpenAIClient,
    tenant_id: str,
    conversation_id: str,
    patient_id: str,
    sender_number: str,
    tenant_name: str,
    clinic_config: Any,
    result: IntentResult,
    patient_message: str,
) -> str:
    """Handle a greeting — return a welcome message."""
    if clinic_config and clinic_config.welcome_message:
        welcome = clinic_config.welcome_message
        welcome = welcome.replace("{clinic_name}", tenant_name)
        return welcome
    return (
        f"¡Hola! Soy el asistente virtual de {tenant_name}. "
        "¿En qué puedo ayudarte?"
    )


# ---------------------------------------------------------------------------
# Consultar turno handler (one-shot)
# ---------------------------------------------------------------------------


async def _handle_consultar_turno(
    db: Any,
    llm_provider: OpenAIClient,
    tenant_id: str,
    conversation_id: str,
    patient_id: str,
    sender_number: str,
    tenant_name: str,
    clinic_config: Any,
    result: IntentResult,
    patient_message: str,
) -> str:
    """Handle ``consultar_turno`` — show the patient's upcoming appointments."""
    appointments_data = await _get_patient_appointments_for_display(db, patient_id)

    if not appointments_data:
        return (
            "No tenés turnos agendados. "
            "Si querés sacar un turno, decime."
        )

    if len(appointments_data) == 1:
        apt = appointments_data[0]
        return (
            f"Tenés un turno agendado:\n\n"
            f"📅 {_format_date_es(apt['date'])} a las {apt['time']}\n"
            f"👨‍⚕️ {apt['doctor_name']}\n\n"
            "¿Necesitás algo más?"
        )

    lines = ["Tenés estos turnos agendados:\n"]
    for i, apt in enumerate(appointments_data, 1):
        lines.append(
            f"{i}. {_format_date_es(apt['date'])} a las {apt['time']} "
            f"con {apt['doctor_name']}"
        )
    lines.append("")
    lines.append("¿Necesitás algo más?")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cancelar multi-turn handler (F3)
# ---------------------------------------------------------------------------


async def _handle_cancelar_multiturn(
    db: Any,
    llm_provider: OpenAIClient | None = None,
    tenant_id: str = "",
    conversation_id: str = "",
    patient_id: str = "",
    sender_number: str = "",
    tenant_name: str = "",
    clinic_config: Any = None,
    result: IntentResult | None = None,
    patient_message: str = "",
    conversation: Conversation | None = None,
) -> str:
    """Handle the multi-turn cancel dialog.

    State machine stored in ``conversation.extra_data["cancel_step"]``::

        None (first call) → shows upcoming appointments
            → ``awaiting_appointment_selection`` if multiple
            → ``awaiting_confirmation`` if single
        ``awaiting_appointment_selection`` → parse choice → ``awaiting_confirmation``
        ``awaiting_confirmation`` → confirm → execute CancelAppointment
    """
    # Guard: we need the conversation object.
    if conversation is None:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result_c = await db.execute(stmt)
        conversation = result_c.scalar_one_or_none()
        if conversation is None:
            return "Lo siento, hubo un error al procesar tu solicitud."

    cancel_state = conversation.extra_data or {}
    step = cancel_state.get("cancel_step")

    if step is None:
        # First entry: show upcoming appointments.
        return await _cancel_step_list_appointments(
            db, tenant_id, conversation, patient_id
        )
    elif step == "awaiting_appointment_selection":
        return await _cancel_step_select_appointment(
            db, conversation, patient_message
        )
    elif step == "awaiting_confirmation":
        return await _cancel_step_confirm(
            db, tenant_id, patient_id, conversation, patient_message, tenant_name
        )
    else:
        # Unknown step — reset.
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return await _cancel_step_list_appointments(
            db, tenant_id, conversation, patient_id
        )


async def _cancel_step_list_appointments(
    db: Any,
    tenant_id: str,
    conversation: Conversation,
    patient_id: str,
) -> str:
    """Show upcoming appointments for the cancel flow."""
    appointments_data = await _get_patient_appointments_for_display(db, patient_id)

    if not appointments_data:
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return (
            "No tenés turnos agendados para cancelar. "
            "Si querés sacar un turno nuevo, decime."
        )

    if len(appointments_data) == 1:
        # Single appointment — go directly to confirmation.
        apt = appointments_data[0]
        conversation.extra_data = {
            "cancel_step": "awaiting_confirmation",
            "cancel_appointment_id": apt["id"],
            "cancel_doctor_name": apt["doctor_name"],
            "cancel_date": apt["date"].isoformat(),
            "cancel_time": apt["time"],
        }
        db.add(conversation)
        await db.flush()

        return (
            f"Veo que tenés un turno agendado:\n\n"
            f"📅 {_format_date_es(apt['date'])} a las {apt['time']}\n"
            f"👨‍⚕️ {apt['doctor_name']}\n\n"
            "¿Confirmás que querés cancelarlo?\n\n"
            'Respondé "Sí" para cancelar, o "No" para mantenerlo.'
        )

    # Multiple appointments — list them.
    cancel_appointments = []
    for i, apt in enumerate(appointments_data, 1):
        cancel_appointments.append({
            "index": i,
            "id": apt["id"],
            "doctor_name": apt["doctor_name"],
            "date": apt["date"].isoformat(),
            "time": apt["time"],
        })

    conversation.extra_data = {
        "cancel_step": "awaiting_appointment_selection",
        "cancel_appointments": cancel_appointments,
    }
    db.add(conversation)
    await db.flush()

    lines = ["Tenés estos turnos agendados. ¿Cuál querés cancelar?\n"]
    for apt in cancel_appointments:
        parsed_date = date.fromisoformat(apt["date"])
        lines.append(
            f"{apt['index']}. {_format_date_es(parsed_date)} "
            f"a las {apt['time']} con {apt['doctor_name']}"
        )
    lines.append("")
    lines.append('Podés decir "el 1", "el 2", etc.')
    return "\n".join(lines)


async def _cancel_step_select_appointment(
    db: Any,
    conversation: Conversation,
    patient_message: str,
) -> str:
    """Parse the patient's appointment selection."""
    cancel_state = conversation.extra_data or {}
    cancel_appointments = cancel_state.get("cancel_appointments", [])

    if not cancel_appointments:
        # Corrupted state — reset.
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return "Lo siento, hubo un error. Por favor, decime de nuevo que querés cancelar un turno."

    # Try to match by index.
    selected = _match_appointment_selection(patient_message, cancel_appointments)

    if selected is None:
        # Show list again.
        lines = ["Disculpá, no entendí cuál turno querés cancelar.\n"]
        for apt in cancel_appointments:
            parsed_date = date.fromisoformat(apt["date"])
            lines.append(
                f"{apt['index']}. {_format_date_es(parsed_date)} "
                f"a las {apt['time']} con {apt['doctor_name']}"
            )
        lines.append("")
        lines.append('Podés decir "el 1", "el 2", etc.')
        return "\n".join(lines)

    # Store selection and ask for confirmation.
    parsed_date = date.fromisoformat(selected["date"])
    conversation.extra_data = {
        "cancel_step": "awaiting_confirmation",
        "cancel_appointment_id": selected["id"],
        "cancel_doctor_name": selected["doctor_name"],
        "cancel_date": selected["date"],
        "cancel_time": selected["time"],
    }
    db.add(conversation)
    await db.flush()

    return (
        f"Querés cancelar este turno:\n\n"
        f"📅 {_format_date_es(parsed_date)} a las {selected['time']}\n"
        f"👨‍⚕️ {selected['doctor_name']}\n\n"
        "¿Confirmás que querés cancelarlo?\n\n"
        'Respondé "Sí" para cancelar, o "No" para mantenerlo.'
    )


async def _cancel_step_confirm(
    db: Any,
    tenant_id: str,
    patient_id: str,
    conversation: Conversation,
    patient_message: str,
    tenant_name: str,
) -> str:
    """Handle confirmation for the cancel flow."""
    cancel_state = conversation.extra_data or {}
    appointment_id = cancel_state.get("cancel_appointment_id")
    doctor_name = cancel_state.get("cancel_doctor_name", "el médico")
    date_str = cancel_state.get("cancel_date")
    time_str = cancel_state.get("cancel_time")

    text_lower = patient_message.strip().lower()
    cancel_words = {"no", "cancelar", "cancelá", "no quiero", "para", "dejá"}
    confirm_words = {"sí", "si", "confirmar", "confirmo", "dale", "ok", "okay", "de acuerdo", "si, cancelar"}

    if any(word in text_lower for word in cancel_words) and not any(word in text_lower for word in confirm_words):
        # Patient changed their mind.
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return "No hay problema. Si necesitás algo más, decime."

    if not any(word in text_lower for word in confirm_words):
        # Unclear response — ask again.
        return (
            "Disculpá, no entendí. ¿Confirmamos la cancelación?\n\n"
            'Respondé "Sí" para cancelar el turno, o "No" para mantenerlo.'
        )

    # --- Execute cancellation ---
    try:
        calendar_provider = GoogleCalendarProvider(tenant_id=tenant_id, db=db)
        cancel_service = CancelAppointment(db=db, calendar_provider=calendar_provider)
        result = await cancel_service.execute(
            tenant_id=tenant_id,
            patient_id=patient_id,
            appointment_id=appointment_id,
            reason="patient_request",
        )

        # Clear cancel state.
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()

        logger.info(
            "Appointment cancelled: id=%s reason=%s patient=%s",
            appointment_id, "patient_request", patient_id,
        )

        parsed_date = date.fromisoformat(date_str) if date_str else date.today()
        return (
            f"✅ Turno cancelado.\n\n"
            f"{_format_date_es(parsed_date)} a las {time_str}\n"
            f"👨‍⚕️ {doctor_name}\n\n"
            "Tu turno fue cancelado. El horario queda disponible para otro paciente.\n"
            "Si querés agendar un turno nuevo, decime."
        )

    except ValueError as exc:
        error_msg = str(exc)
        if "Debe llamar a la clínica" in error_msg:
            # RN3.2: close to appointment time.
            conversation.extra_data = {}
            db.add(conversation)
            await db.flush()
            return (
                "⚠️ Como tu turno es en menos de 2 horas, "
                "no puedo cancelarlo automáticamente. "
                "Por favor, llamá a la clínica para cancelarlo."
            )
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return f"Lo siento, no se pudo cancelar el turno: {error_msg}"

    except (RuntimeError, ConnectionError) as exc:
        logger.error("Cancel failed for appointment %s: %s", appointment_id, exc)
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return (
            "Lo siento, hubo un error al cancelar el turno. "
            "El sistema está temporalmente fuera de servicio. "
            "Por favor, comunicate con la clínica."
        )


# ---------------------------------------------------------------------------
# Reprogramar multi-turn handler (F3)
# ---------------------------------------------------------------------------


async def _handle_reprogramar_multiturn(
    db: Any,
    llm_provider: OpenAIClient | None = None,
    tenant_id: str = "",
    conversation_id: str = "",
    patient_id: str = "",
    sender_number: str = "",
    tenant_name: str = "",
    clinic_config: Any = None,
    result: IntentResult | None = None,
    patient_message: str = "",
    conversation: Conversation | None = None,
) -> str:
    """Handle the multi-turn reschedule dialog.

    State machine stored in ``conversation.extra_data["reschedule_step"]``::

        None → list appointments (``awaiting_appointment_selection``)
        ``awaiting_appointment_selection`` → parse choice → ``awaiting_date``
        ``awaiting_date`` → parse date, fetch slots → ``awaiting_slot``
        ``awaiting_slot`` → parse slot → ``awaiting_confirmation``
        ``awaiting_confirmation`` → confirm → execute RescheduleAppointment

    Reuses ``GetAvailableSlots`` and ``BookAppointment`` from T8.
    """
    # Guard: we need the conversation object.
    if conversation is None:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result_c = await db.execute(stmt)
        conversation = result_c.scalar_one_or_none()
        if conversation is None:
            return "Lo siento, hubo un error al procesar tu solicitud."

    reschedule_state = conversation.extra_data or {}
    step = reschedule_state.get("reschedule_step")

    if step is None:
        # First entry: show upcoming appointments.
        return await _reschedule_step_list_appointments(
            db, tenant_id, conversation, patient_id
        )
    elif step == "awaiting_appointment_selection":
        return await _reschedule_step_select_appointment(
            db, conversation, patient_message
        )
    elif step == "awaiting_date":
        return await _reschedule_step_date(
            db, tenant_id, conversation, patient_message, clinic_config
        )
    elif step == "awaiting_slot":
        return await _reschedule_step_slot(
            db, conversation, patient_message, tenant_name
        )
    elif step == "awaiting_confirmation":
        return await _reschedule_step_confirm(
            db, tenant_id, patient_id, conversation, patient_message, tenant_name
        )
    else:
        # Unknown step — reset.
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return await _reschedule_step_list_appointments(
            db, tenant_id, conversation, patient_id
        )


async def _reschedule_step_list_appointments(
    db: Any,
    tenant_id: str,
    conversation: Conversation,
    patient_id: str,
) -> str:
    """Show upcoming appointments for the reschedule flow."""
    appointments_data = await _get_patient_appointments_for_display(db, patient_id)

    if not appointments_data:
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return (
            "No tenés turnos agendados para reprogramar. "
            "Si querés sacar un turno nuevo, decime."
        )

    if len(appointments_data) == 1:
        # Single appointment — go directly to date selection.
        apt = appointments_data[0]
        conversation.extra_data = {
            "reschedule_step": "awaiting_date",
            "reschedule_appointment_id": apt["id"],
            "reschedule_doctor_id": apt["doctor_id"],
            "reschedule_doctor_name": apt["doctor_name"],
            "reschedule_date": apt["date"].isoformat(),
            "reschedule_time": apt["time"],
        }
        db.add(conversation)
        await db.flush()

        return (
            f"Querés reprogramar este turno:\n\n"
            f"📅 {_format_date_es(apt['date'])} a las {apt['time']}\n"
            f"👨‍⚕️ {apt['doctor_name']}\n\n"
            "¿Para qué día querés el nuevo turno?\n\n"
            "Podés decirme:\n"
            '• "Hoy"\n'
            '• "Mañana"\n'
            '• "El lunes"\n'
            '• "15 de junio"'
        )

    # Multiple appointments — list them.
    reschedule_appointments = []
    for i, apt in enumerate(appointments_data, 1):
        reschedule_appointments.append({
            "index": i,
            "id": apt["id"],
            "doctor_id": apt["doctor_id"],
            "doctor_name": apt["doctor_name"],
            "date": apt["date"].isoformat(),
            "time": apt["time"],
        })

    conversation.extra_data = {
        "reschedule_step": "awaiting_appointment_selection",
        "reschedule_appointments": reschedule_appointments,
    }
    db.add(conversation)
    await db.flush()

    lines = ["Tenés estos turnos agendados. ¿Cuál querés reprogramar?\n"]
    for apt in reschedule_appointments:
        parsed_date = date.fromisoformat(apt["date"])
        lines.append(
            f"{apt['index']}. {_format_date_es(parsed_date)} "
            f"a las {apt['time']} con {apt['doctor_name']}"
        )
    lines.append("")
    lines.append('Podés decir "el 1", "el 2", etc.')
    return "\n".join(lines)


async def _reschedule_step_select_appointment(
    db: Any,
    conversation: Conversation,
    patient_message: str,
) -> str:
    """Parse the patient's appointment selection for reschedule."""
    reschedule_state = conversation.extra_data or {}
    reschedule_appointments = reschedule_state.get("reschedule_appointments", [])

    if not reschedule_appointments:
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return "Lo siento, hubo un error. Por favor, decime de nuevo que querés reprogramar un turno."

    selected = _match_appointment_selection(patient_message, reschedule_appointments)

    if selected is None:
        lines = ["Disculpá, no entendí cuál turno querés reprogramar.\n"]
        for apt in reschedule_appointments:
            parsed_date = date.fromisoformat(apt["date"])
            lines.append(
                f"{apt['index']}. {_format_date_es(parsed_date)} "
                f"a las {apt['time']} con {apt['doctor_name']}"
            )
        lines.append("")
        lines.append('Podés decir "el 1", "el 2", etc.')
        return "\n".join(lines)

    # Store and ask for new date.
    conversation.extra_data = {
        "reschedule_step": "awaiting_date",
        "reschedule_appointment_id": selected["id"],
        "reschedule_doctor_id": selected["doctor_id"],
        "reschedule_doctor_name": selected["doctor_name"],
        "reschedule_date": selected["date"],
        "reschedule_time": selected["time"],
    }
    db.add(conversation)
    await db.flush()

    parsed_date = date.fromisoformat(selected["date"])
    return (
        f"Querés reprogramar este turno:\n\n"
        f"📅 {_format_date_es(parsed_date)} a las {selected['time']}\n"
        f"👨‍⚕️ {selected['doctor_name']}\n\n"
        "¿Para qué día querés el nuevo turno?\n\n"
        "Podés decirme:\n"
        '• "Hoy"\n'
        '• "Mañana"\n'
        '• "El lunes"\n'
        '• "15 de junio"'
    )


async def _reschedule_step_date(
    db: Any,
    tenant_id: str,
    conversation: Conversation,
    patient_message: str,
    clinic_config: Any,
) -> str:
    """Parse the new date and fetch available slots for reschedule."""
    reschedule_state = conversation.extra_data or {}
    doctor_id = reschedule_state.get("reschedule_doctor_id")
    doctor_name = reschedule_state.get("reschedule_doctor_name", "el médico")

    parsed_date = _parse_date(patient_message)

    if parsed_date is None:
        return (
            "Disculpá, no entendí la fecha. Podés decirme:\n"
            '• "Hoy"\n'
            '• "Mañana"\n'
            '• "El lunes"\n'
            '• "15 de junio"\n'
            '• O "15/06"'
        )

    today = date.today()
    if parsed_date < today:
        return "La fecha que me diste ya pasó. ¿Podés elegir un día a partir de hoy?"

    # Fetch available slots.
    try:
        calendar_provider = GoogleCalendarProvider(tenant_id=tenant_id, db=db)
        slot_service = GetAvailableSlots(db=db, calendar_provider=calendar_provider)
        slots = await slot_service.execute(
            tenant_id=tenant_id,
            doctor_id=doctor_id,
            day=parsed_date,
        )
    except ConnectionError as exc:
        logger.error("Calendar provider error during reschedule: %s", exc)
        return (
            "Por el momento no puedo consultar la disponibilidad. "
            "El sistema de turnos está temporalmente fuera de servicio. "
            "Por favor, comunicate con la clínica para reprogramar."
        )

    if not slots:
        # No slots — offer to check another date.
        conversation.extra_data = {
            **reschedule_state,
            "reschedule_step": "awaiting_date",
        }
        db.add(conversation)
        await db.flush()

        # Try next few days.
        alt_dates = await _find_next_available_dates(
            db=db, tenant_id=tenant_id, doctor_id=doctor_id,
            start_date=parsed_date + timedelta(days=1), max_days=7,
            slot_service=slot_service,
        )

        if alt_dates:
            lines = [
                f"No tengo turnos disponibles para {_format_date_es(parsed_date)}.",
                f"Próximas fechas con disponibilidad:",
            ]
            for d in alt_dates:
                lines.append(f"• {_format_date_es(d)}")
            lines.append("")
            lines.append("¿Te gusta alguna de esas fechas?")
            return "\n".join(lines)

        return (
            f"No tengo turnos disponibles para {_format_date_es(parsed_date)} "
            "ni para los próximos 7 días. ¿Querés que te avisemos si se "
            "libera alguno? Por ahora, te sugiero llamar a la clínica."
        )

    # Format slots for display.
    slot_options = []
    for idx, slot in enumerate(slots, 1):
        start_local = slot.start_time.astimezone()
        time_str = start_local.strftime("%H:%M")
        slot_options.append({
            "index": idx,
            "time": time_str,
            "start": slot.start_time.isoformat(),
            "end": slot.end_time.isoformat(),
        })

    max_slots = 8
    display_slots = slot_options[:max_slots]

    lines = [f"Turnos disponibles para {_format_date_es(parsed_date)} con {doctor_name}:"]
    for opt in display_slots:
        lines.append(f"{opt['index']}. {opt['time']}")
    lines.append("")
    lines.append("¿Qué horario te queda mejor?")
    lines.append('(Podés decir "el 1", "el 2", o la hora directamente)')

    conversation.extra_data = {
        **reschedule_state,
        "reschedule_step": "awaiting_slot",
        "reschedule_new_date": parsed_date.isoformat(),
        "reschedule_slots": slot_options,
    }
    db.add(conversation)
    await db.flush()

    return "\n".join(lines)


async def _reschedule_step_slot(
    db: Any,
    conversation: Conversation,
    patient_message: str,
    tenant_name: str,
) -> str:
    """Parse slot selection and advance to confirmation step."""
    reschedule_state = conversation.extra_data or {}
    slots_data = reschedule_state.get("reschedule_slots", [])
    doctor_name = reschedule_state.get("reschedule_doctor_name", "el médico")
    date_str = reschedule_state.get("reschedule_new_date")

    selected_slot = _match_slot(patient_message, slots_data)
    if selected_slot is None:
        lines = ["Disculpá, no entendí qué horario elegiste. Opciones disponibles:"]
        for opt in slots_data[:8]:
            lines.append(f"{opt['index']}. {opt['time']}")
        lines.append("")
        lines.append("¿Cuál te queda mejor?")
        lines.append('(Podés decir "el 1", "el 2", o la hora)')
        return "\n".join(lines)

    # Store selection and advance to confirmation step.
    parsed_date = date.fromisoformat(date_str) if date_str else date.today()
    conversation.extra_data = {
        **reschedule_state,
        "reschedule_selected_slot": selected_slot,
        "reschedule_step": "awaiting_confirmation",
    }
    db.add(conversation)
    await db.flush()

    return (
        f"Perfecto, confirmame los nuevos datos:\n\n"
        f"🏥 {tenant_name}\n"
        f"👨‍⚕️ {doctor_name}\n"
        f"📅 {_format_date_es(parsed_date)} a las {selected_slot['time']}\n\n"
        "¿Querés agregar un motivo de consulta? (opcional)\n"
        "O respondé:\n"
        '• "Sí, confirmar" — para reprogramarlo\n'
        '• "No" o "cancelar" — para cancelar'
    )


async def _reschedule_step_confirm(
    db: Any,
    tenant_id: str,
    patient_id: str,
    conversation: Conversation,
    patient_message: str,
    tenant_name: str,
) -> str:
    """Handle confirmation for the reschedule flow and execute."""
    reschedule_state = conversation.extra_data or {}
    appointment_id = reschedule_state.get("reschedule_appointment_id")
    doctor_id = reschedule_state.get("reschedule_doctor_id")
    doctor_name = reschedule_state.get("reschedule_doctor_name", "el médico")
    date_str = reschedule_state.get("reschedule_new_date") or reschedule_state.get("reschedule_date")
    slots_data = reschedule_state.get("reschedule_slots", [])
    selected_slot = reschedule_state.get("reschedule_selected_slot")

    # If slot not selected yet, parse the patient's choice.
    if selected_slot is None:
        selected_slot = _match_slot(patient_message, slots_data)
        if selected_slot is None:
            lines = ["Disculpá, no entendí qué horario elegiste. Opciones disponibles:"]
            for opt in slots_data[:8]:
                lines.append(f"{opt['index']}. {opt['time']}")
            lines.append("")
            lines.append("¿Cuál te queda mejor?")
            return "\n".join(lines)

        # Store and ask confirmation.
        conversation.extra_data = {
            **reschedule_state,
            "reschedule_selected_slot": selected_slot,
            "reschedule_step": "awaiting_confirmation",
        }
        db.add(conversation)
        await db.flush()

        parsed_date = date.fromisoformat(date_str) if date_str else date.today()
        return (
            f"Perfecto, confirmame los nuevos datos:\n\n"
            f"🏥 {tenant_name}\n"
            f"👨‍⚕️ {doctor_name}\n"
            f"📅 {_format_date_es(parsed_date)} a las {selected_slot['time']}\n\n"
            "¿Querés agregar un motivo de consulta? (opcional)\n"
            "O respondé:\n"
            '• "Sí, confirmar" — para reprogramarlo\n'
            '• "No" o "cancelar" — para cancelar'
        )

    # Parse confirmation.
    text_lower = patient_message.strip().lower()
    cancel_words = {"no", "cancelar", "cancelá", "no quiero", "para", "dejá"}
    confirm_words = {"sí", "si", "confirmar", "confirmo", "dale", "ok", "okay", "de acuerdo"}

    if any(word in text_lower for word in cancel_words) and not any(word in text_lower for word in confirm_words):
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return "No hay problema. Si querés reprogramar más tarde, decime."

    has_reason = not any(
        word == text_lower or text_lower.startswith(word)
        for word in list(confirm_words) + list(cancel_words)
    )

    if not has_reason and not any(word in text_lower for word in confirm_words):
        return (
            "Disculpá, no entendí. ¿Confirmamos la reprogramación?\n\n"
            'Respondé "Sí, confirmar" para reprogramar, '
            'o "No" para cancelar.'
        )

    reason_text = patient_message if has_reason else None

    # --- Execute reschedule ---
    try:
        # Parse dates.
        start_dt = datetime.fromisoformat(selected_slot["start"])
        end_dt = datetime.fromisoformat(selected_slot["end"])

        # Get patient record.
        from app.infrastructure.database.models.patient import Patient as PatientModel
        stmt_p = select(PatientModel).where(
            PatientModel.id == uuid.UUID(patient_id)
        )
        res_p = await db.execute(stmt_p)
        patient = res_p.scalar_one_or_none()

        if patient is None:
            return "Lo siento, hubo un error al identificar tus datos. Por favor, comunicate con la clínica."

        # Execute reschedule.
        calendar_provider = GoogleCalendarProvider(tenant_id=tenant_id, db=db)
        reschedule_service = RescheduleAppointment(
            db=db, calendar_provider=calendar_provider
        )
        result = await reschedule_service.execute(
            tenant_id=tenant_id,
            patient=patient,
            old_appointment_id=appointment_id,
            doctor_id=doctor_id,
            slot_start=start_dt,
            slot_end=end_dt,
            reason=reason_text,
        )

        # Clear reschedule state.
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()

        logger.info(
            "Appointment rescheduled: old=%s new=%s patient=%s",
            appointment_id, result["new_appointment_id"], patient_id,
        )

        parsed_date = date.fromisoformat(date_str) if date_str else start_dt.date()
        return (
            f"✅ ¡Turno reprogramado con éxito!\n\n"
            f"📍 Turno ANTERIOR cancelado.\n"
            f"🆕 Nuevo turno:\n"
            f"🏥 {tenant_name}\n"
            f"👨‍⚕️ {doctor_name}\n"
            f"📅 {_format_date_es(parsed_date)} a las {selected_slot['time']}\n\n"
            "Te voy a enviar un recordatorio 24 horas antes.\n"
            "Si necesitas cancelar o reprogramar de nuevo, solo decime."
        )

    except ValueError as exc:
        error_msg = str(exc)
        if "Debe llamar a la clínica" in error_msg:
            conversation.extra_data = {}
            db.add(conversation)
            await db.flush()
            return (
                "⚠️ Como tu turno original es en menos de 2 horas, "
                "no puedo reprogramarlo automáticamente. "
                "Por favor, llamá a la clínica para reprogramarlo."
            )
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return f"Lo siento, no se pudo reprogramar el turno: {error_msg}"

    except (RuntimeError, ConnectionError) as exc:
        logger.error("Reschedule failed for appointment %s: %s", appointment_id, exc)
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return (
            "Lo siento, hubo un error al reprogramar tu turno. "
            "El sistema está temporalmente fuera de servicio. "
            "Por favor, comunicate con la clínica."
        )


# ---------------------------------------------------------------------------
# Reminder reply handler (F4)
# ---------------------------------------------------------------------------
# When a patient responds to an automatic reminder, we intercept the message
# BEFORE intent classification and route directly to the appropriate action:
# confirm, cancel, or reschedule.  If the response doesn't match any
# reminder keyword, we fall through to normal intent classification.
# ---------------------------------------------------------------------------


async def _handle_reminder_reply(
    db: Any,
    conversation_id: str,
    patient_id: str,
    tenant_id: str,
    patient_message: str,
    sender_number: str,
    tenant_slug: str,
) -> str | None:
    """Check if this message is a reply to a reminder and handle it.

    Steps:
    1. Check if the most recent bot message in the conversation was a
       reminder (within the last 24 hours).
    2. Parse the patient's message for confirm / cancel / reschedule
       keywords.
    3. If matched, execute the action and return a response string.
    4. If not matched, return ``None`` — the caller falls through to
       normal intent classification.

    Returns:
        A bot response string if handled, or ``None`` to continue.
    """
    # 1. Check for recent reminder message from bot.
    has_recent_reminder = await _conversation_has_recent_reminder(
        db, conversation_id,
    )
    if not has_recent_reminder:
        return None

    # 2. Parse patient intent from message text.
    text_lower = patient_message.strip().lower()

    # --- Emoji first (most explicit signals) ---
    has_confirm_emoji = "✅" in patient_message
    has_cancel_emoji = "❌" in patient_message
    has_reschedule_emoji = "🔄" in patient_message

    # --- Keyword sets ---
    # (Order matters: confirm is checked first to avoid "sí" matching cancel)
    confirm_kw = {"confirmar", "confirmo", "sí voy", "si voy", "voy a ir",
                  "voy a asistir", "asistiré", "sí", "si", "ok", "dale"}
    cancel_kw = {"cancelar", "cancelá", "no voy", "no puedo", "no quiero",
                 "no puedo ir", "no pienso ir"}
    reschedule_kw = {"reprogramar", "cambiar", "reagendar", "repreguntar"}

    # Check multi-word phrases (word-boundary matching done via `in`).
    has_confirm_word = any(kw in text_lower for kw in confirm_kw)
    has_cancel_word = any(kw in text_lower for kw in cancel_kw)
    has_reschedule_word = any(kw in text_lower for kw in reschedule_kw)

    # 3. Route to action.
    # Confirm takes priority over reschedule if both match (unlikely).
    if has_confirm_emoji or (has_confirm_word and not has_cancel_word and not has_reschedule_word):
        return await _handle_reminder_confirm(
            db, patient_id, tenant_id, sender_number, tenant_slug,
        )

    if has_cancel_emoji or has_cancel_word:
        return await _handle_reminder_cancel(
            db, patient_id, tenant_id, sender_number, tenant_slug,
        )

    if has_reschedule_emoji or has_reschedule_word:
        return await _handle_reminder_reschedule(
            db, patient_id, tenant_id, sender_number, tenant_slug,
        )

    # 4. No match — fall through to intent classification.
    return None


async def _conversation_has_recent_reminder(
    db: Any,
    conversation_id: str,
    max_age_hours: int = 24,
) -> bool:
    """Check if the most recent bot message was a reminder within *max_age*.

    Looks at the latest ``origin = bot`` message and checks whether its
    content contains reminder keywords and is less than *max_age_hours* old.
    """
    stmt = (
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.origin == MessageOrigin.bot,
        )
        .order_by(ConversationMessage.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    last_bot_msg = result.scalar_one_or_none()

    if last_bot_msg is None:
        return False

    # Check age.
    now = datetime.now(timezone.utc)
    msg_time = last_bot_msg.created_at
    if msg_time.tzinfo is None:
        msg_time = msg_time.replace(tzinfo=timezone.utc)

    if now - msg_time > timedelta(hours=max_age_hours):
        return False

    # Check for reminder keywords.
    reminder_keywords = [
        "recordatorio de turno", "recordatorio",
        "segundo recordatorio",
    ]
    content_lower = last_bot_msg.content.lower()
    return any(kw in content_lower for kw in reminder_keywords)


async def _handle_reminder_confirm(
    db: Any,
    patient_id: str,
    tenant_id: str,
    sender_number: str,
    tenant_slug: str,
) -> str:
    """Handle a confirmation reply to a reminder.

    Finds the upcoming appointment with a pending (sent-but-unconfirmed)
    reminder and marks ``reminder_confirmed = True``.
    """
    appointment = await _find_reminder_appointment(db, patient_id, tenant_id)
    if appointment is None:
        return (
            "Gracias por confirmar. 😊 "
            "No encontré un turno pendiente de confirmación, "
            "pero si necesitás algo más, decime."
        )

    # Mark as confirmed.
    appointment.reminder_confirmed = True
    db.add(appointment)
    await db.flush()

    logger.info(
        "Reminder confirmed for appointment %s (patient %s)",
        appointment.id, patient_id,
    )

    return (
        "✅ *Confirmación recibida*\n\n"
        "Gracias por confirmar. Te esperamos."
    )


async def _handle_reminder_cancel(
    db: Any,
    patient_id: str,
    tenant_id: str,
    sender_number: str,
    tenant_slug: str,
) -> str:
    """Handle a cancel reply to a reminder.

    Finds the appointment with a pending reminder and cancels it via
    the ``handle_cancel_from_reminder`` utility.
    """
    appointment = await _find_reminder_appointment(db, patient_id, tenant_id)
    if appointment is None:
        return (
            "Gracias por avisar. 😊 "
            "No encontré un turno pendiente de confirmación. "
            "¿Querés consultar tus turnos?"
        )

    calendar_provider = GoogleCalendarProvider(tenant_id=tenant_id, db=db)
    result = await handle_cancel_from_reminder(
        db=db,
        calendar_provider=calendar_provider,
        appointment_id=str(appointment.id),
    )

    logger.info(
        "Reminder-originated cancellation for appointment %s: %s",
        appointment.id, result,
    )

    return result


async def _handle_reminder_reschedule(
    db: Any,
    patient_id: str,
    tenant_id: str,
    sender_number: str,
    tenant_slug: str,
) -> str:
    """Handle a reschedule reply to a reminder.

    Finds the appointment with a pending reminder and initiates the
    reschedule flow via ``handle_reschedule_from_reminder``.
    """
    appointment = await _find_reminder_appointment(db, patient_id, tenant_id)
    if appointment is None:
        return (
            "Gracias por avisar. 😊 "
            "No encontré un turno pendiente de reprogramación. "
            "¿Querés consultar tus turnos?"
        )

    calendar_provider = GoogleCalendarProvider(tenant_id=tenant_id, db=db)
    result = await handle_reschedule_from_reminder(
        db=db,
        calendar_provider=calendar_provider,
        appointment_id=str(appointment.id),
    )

    logger.info(
        "Reminder-originated reschedule for appointment %s: %s",
        appointment.id, result,
    )

    return result


async def _find_reminder_appointment(
    db: Any,
    patient_id: str,
    tenant_id: str,
) -> Appointment | None:
    """Find the nearest upcoming appointment for this patient that has a
    sent-but-unconfirmed reminder.

    This is the appointment the patient is most likely responding to when
    they reply to a reminder message.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(Appointment)
        .where(
            Appointment.patient_id == uuid.UUID(patient_id),
            Appointment.tenant_id == uuid.UUID(tenant_id),
            Appointment.status == AppointmentStatus.confirmed,
            Appointment.start_time > now,
            Appointment.reminder_1_sent.is_(True),
            Appointment.reminder_confirmed.is_(False),
        )
        .order_by(Appointment.start_time.asc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Shared helpers for cancel/reschedule flows
# ---------------------------------------------------------------------------


async def _get_patient_appointments_for_display(
    db: Any,
    patient_id: str,
) -> list[dict]:
    """Fetch upcoming confirmed/pending appointments with doctor names.

    Returns a list of dicts ordered by start time (earliest first).
    """
    repo = AppointmentRepo(db)
    appointments = await repo.get_upcoming_appointments(patient_id)

    result: list[dict] = []
    for apt in appointments:
        doctor_name = "Médico"
        doctor_id = str(apt.doctor_id) if apt.doctor_id else None
        if doctor_id:
            stmt = select(Doctor).where(Doctor.id == uuid.UUID(doctor_id))
            res = await db.execute(stmt)
            doctor = res.scalar_one_or_none()
            if doctor:
                doctor_name = doctor.name

        start = apt.start_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        result.append({
            "id": str(apt.id),
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "start_time": start,
            "date": start.date(),
            "time": start.strftime("%H:%M"),
            "reason": apt.reason,
        })

    return result


def _match_appointment_selection(
    text: str,
    appointments: list[dict],
) -> dict | None:
    """Match an appointment selection from the patient's message.

    Supports index-based selection (``"el 1"``, ``"1"``, ``"el 2"``).
    """
    text_lower = text.lower().strip()

    m = re.search(r'(?:el\s+)?(\d+)', text_lower)
    if m:
        idx = int(m.group(1)) - 1
        for apt in appointments:
            if apt["index"] == idx + 1:
                return apt

    return None


# ---------------------------------------------------------------------------
# Booking multi-turn handler (T8 — Agendar Turnos)
# ---------------------------------------------------------------------------


async def _handle_booking_multiturn(
    db: Any,
    llm_provider: OpenAIClient | None = None,
    tenant_id: str = "",
    conversation_id: str = "",
    patient_id: str = "",
    sender_number: str = "",
    tenant_name: str = "",
    clinic_config: Any = None,
    result: IntentResult | None = None,
    patient_message: str = "",
    conversation: Conversation | None = None,
) -> str:
    """Handle the multi-turn booking dialog for ``agendar`` intent.

    Called either from intent routing (first turn) or from the main flow's
    booking-state check (subsequent turns).  Uses
    ``conversation.extra_data["booking_step"]`` to track progress.

    State machine::

        None              → "awaiting_doctor"   — ask which doctor
        "awaiting_doctor"  → "awaiting_date"     — ask which date
        "awaiting_date"    → "awaiting_slot"     — show slots, ask which time
        "awaiting_slot"    → "awaiting_confirmation" — show summary, ask confirm
        "awaiting_confirmation" → {}             — book it, success message
    """
    # Guard: we need the conversation object.
    if conversation is None:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result_c = await db.execute(stmt)
        conversation = result_c.scalar_one_or_none()
        if conversation is None:
            return "Lo siento, hubo un error al procesar tu solicitud."

    booking_state = conversation.extra_data or {}
    step = booking_state.get("booking_step")

    # Decide what to do based on current step.
    if step is None or step == "awaiting_doctor":
        return await _booking_step_doctor(db, tenant_id, conversation, tenant_name)
    elif step == "awaiting_date":
        return await _booking_step_date(
            db, tenant_id, conversation, clinic_config, patient_message, tenant_name
        )
    elif step == "awaiting_slot":
        return await _booking_step_slot(
            db, tenant_id, conversation, patient_message, tenant_name, clinic_config
        )
    elif step == "awaiting_confirmation":
        return await _booking_step_confirm(
            db, tenant_id, patient_id, conversation, patient_message, tenant_name
        )
    else:
        # Unknown step — reset.
        return await _booking_step_doctor(db, tenant_id, conversation, tenant_name)


async def _booking_step_doctor(
    db: Any,
    tenant_id: str,
    conversation: Conversation,
    tenant_name: str,
) -> str:
    """Ask the patient which doctor they want to see."""
    # Fetch active doctors for this tenant.
    stmt = (
        select(Doctor)
        .where(
            Doctor.tenant_id == uuid.UUID(tenant_id),
            Doctor.is_active.is_(True),
        )
        .order_by(Doctor.name)
    )
    result = await db.execute(stmt)
    doctors = list(result.scalars().all())

    if not doctors:
        # No doctors configured — this is an edge case.
        return (
            f"Gracias por tu interés, {tenant_name} no tiene médicos "
            "configurados aún. Por favor, comunicate con la clínica "
            "para más información."
        )

    # Store doctor list in booking state for later matching.
    doctor_list = [{"id": str(d.id), "name": d.name, "specialty": d.specialty} for d in doctors]

    if len(doctors) == 1:
        # Only one doctor — skip asking, go directly to date.
        conversation.extra_data = {
            "booking_step": "awaiting_date",
            "doctor_id": str(doctors[0].id),
            "doctor_name": doctors[0].name,
            "doctors": doctor_list,
        }
        db.add(conversation)
        await db.flush()

        return (
            f"Perfecto, voy a agendarte un turno con {doctors[0].name}. "
            "¿Para qué día querés el turno?\n\n"
            "Podés decirme, por ejemplo:\n"
            "• \"Hoy\"\n"
            "• \"Mañana\"\n"
            "• \"El lunes\"\n"
            "• \"15 de junio\""
        )

    # Multiple doctors — list them.
    conversation.extra_data = {
        "booking_step": "awaiting_doctor",
        "doctors": doctor_list,
    }
    db.add(conversation)
    await db.flush()

    lines = ["Tenemos estos profesionales disponibles:"]
    for idx, d in enumerate(doctors, 1):
        lines.append(f"{idx}. {d.name} ({d.specialty})")
    lines.append("")
    lines.append("¿Con qué profesional querés agendarte?")
    lines.append('(Podés decir "el 1", "el Dr. Garcia", o "cualquiera")')

    return "\n".join(lines)


async def _booking_step_date(
    db: Any,
    tenant_id: str,
    conversation: Conversation,
    clinic_config: Any,
    patient_message: str,
    tenant_name: str,
) -> str:
    """Parse the patient's doctor selection, then ask for date."""
    booking_state = conversation.extra_data or {}
    doctors = booking_state.get("doctors", [])
    doctor_id = booking_state.get("doctor_id")

    # If doctor_id is already set (single-doctor clinic), skip parsing.
    if doctor_id is None:
        matched = _match_doctor(patient_message, doctors)
        if matched is None:
            # Show list again.
            lines = ["Disculpá, no entendí qué profesional elegiste.\n"]
            lines.append("Podés decir:")
            for idx, d in enumerate(doctors, 1):
                lines.append(f"• \"el {idx}\" para {d['name']}")
            lines.append('• "cualquiera" para el primero disponible')
            return "\n".join(lines)

        doctor_id = matched["id"]
        doctor_name = matched["name"]
    else:
        doctor_name = booking_state.get("doctor_name", "")

    # Now ask for date.
    conversation.extra_data = {
        "booking_step": "awaiting_date",
        "doctor_id": doctor_id,
        "doctor_name": doctor_name,
        "doctors": doctors,
    }
    db.add(conversation)
    await db.flush()

    return (
        f"¿Para qué día querés el turno con {doctor_name}?\n\n"
        "Podés decirme:\n"
        '• "Hoy"\n'
        '• "Mañana"\n'
        '• "El lunes"\n'
        '• "15 de junio"\n'
        '• O una fecha como "15/06"'
    )


async def _booking_step_slot(
    db: Any,
    tenant_id: str,
    conversation: Conversation,
    patient_message: str,
    tenant_name: str,
    clinic_config: Any,
) -> str:
    """Parse date, fetch slots, present options."""
    booking_state = conversation.extra_data or {}
    doctor_id = booking_state.get("doctor_id")
    doctor_name = booking_state.get("doctor_name", "el médico")

    # Try to parse the date.
    parsed_date = _parse_date(patient_message)

    # If we already have a stored date from a previous attempt, use it.
    stored_date_str = booking_state.get("date")
    if parsed_date is None and stored_date_str:
        # Patient is selecting a slot for an already-chosen date.
        parsed_date = date.fromisoformat(stored_date_str)

    if parsed_date is None:
        return (
            "Disculpá, no entendí la fecha. Podés decirme:\n"
            '• "Hoy"\n'
            '• "Mañana"\n'
            '• "El lunes"\n'
            '• "15 de junio"\n'
            '• O "15/06"'
        )

    today = date.today()
    if parsed_date < today:
        return "La fecha que me diste ya pasó. ¿Podés elegir un día a partir de hoy?"

    # Fetch available slots from Google Calendar.
    try:
        calendar_provider = GoogleCalendarProvider(tenant_id=tenant_id, db=db)
        slot_service = GetAvailableSlots(db=db, calendar_provider=calendar_provider)
        slots = await slot_service.execute(
            tenant_id=tenant_id,
            doctor_id=doctor_id,
            day=parsed_date,
        )
    except ConnectionError as exc:
        logger.error("Calendar provider error: %s", exc)
        return (
            "Por el momento no puedo consultar la disponibilidad. "
            "El sistema de turnos está temporalmente fuera de servicio. "
            "Por favor, comunicate con la clínica para agendarte."
        )

    if not slots:
        # No slots — offer to check another date.
        conversation.extra_data = {
            **booking_state,
            "booking_step": "awaiting_date",
            "date": parsed_date.isoformat(),
        }
        db.add(conversation)
        await db.flush()

        # Try next few days.
        alt_dates = await _find_next_available_dates(
            db=db, tenant_id=tenant_id, doctor_id=doctor_id,
            start_date=parsed_date + timedelta(days=1), max_days=7,
            slot_service=slot_service,
        )

        if alt_dates:
            lines = [
                f"No tengo turnos disponibles para {_format_date_es(parsed_date)}.",
                f"Próximas fechas con disponibilidad:",
            ]
            for d in alt_dates:
                lines.append(f"• {_format_date_es(d)}")
            lines.append("")
            lines.append("¿Te gusta alguna de esas fechas?")
            return "\n".join(lines)

        return (
            f"No tengo turnos disponibles para {_format_date_es(parsed_date)} "
            "ni para los próximos 7 días. ¿Querés que te avisemos si se "
            "libera alguno? Por ahora, te sugiero llamar a la clínica."
        )

    # Format slots for display.
    slot_options = []
    for idx, slot in enumerate(slots, 1):
        start_local = slot.start_time.astimezone()
        time_str = start_local.strftime("%H:%M")
        slot_options.append({
            "index": idx,
            "time": time_str,
            "start": slot.start_time.isoformat(),
            "end": slot.end_time.isoformat(),
        })

    max_slots = 8  # Don't show too many at once.
    display_slots = slot_options[:max_slots]

    lines = [f"Turnos disponibles para {_format_date_es(parsed_date)} con {doctor_name}:"]
    for opt in display_slots:
        lines.append(f"{opt['index']}. {opt['time']}")
    lines.append("")
    lines.append("¿Qué horario te queda mejor?")
    lines.append('(Podés decir "el 1", "el 2", o la hora directamente)')

    conversation.extra_data = {
        **booking_state,
        "booking_step": "awaiting_slot",
        "date": parsed_date.isoformat(),
        "slots": slot_options,
        "doctor_id": doctor_id,
        "doctor_name": doctor_name,
    }
    db.add(conversation)
    await db.flush()

    return "\n".join(lines)


async def _booking_step_confirm(
    db: Any,
    tenant_id: str,
    patient_id: str,
    conversation: Conversation,
    patient_message: str,
    tenant_name: str,
) -> str:
    """Parse slot selection, ask for confirmation, or execute booking."""
    booking_state = conversation.extra_data or {}
    doctor_id = booking_state.get("doctor_id")
    doctor_name = booking_state.get("doctor_name", "el médico")
    date_str = booking_state.get("date")
    slots_data = booking_state.get("slots", [])
    selected_slot = booking_state.get("selected_slot")

    # If slot not selected yet, parse the patient's choice.
    if selected_slot is None:
        selected_slot = _match_slot(patient_message, slots_data)
        if selected_slot is None:
            # Show options again.
            lines = [f"Disculpá, no entendí qué horario elegiste. Opciones disponibles:"]
            for opt in slots_data[:8]:
                lines.append(f"{opt['index']}. {opt['time']}")
            lines.append("")
            lines.append("¿Cuál te queda mejor?")
            return "\n".join(lines)

        # Store selected slot and ask for confirmation.
        conversation.extra_data = {
            **booking_state,
            "selected_slot": selected_slot,
            "booking_step": "awaiting_confirmation",
        }
        db.add(conversation)
        await db.flush()

        parsed_date = date.fromisoformat(date_str) if date_str else date.today()
        return (
            f"Perfecto, confirmame los datos:\n\n"
            f"🏥 {tenant_name}\n"
            f"👨‍⚕️ {doctor_name}\n"
            f"📅 {_format_date_es(parsed_date)} a las {selected_slot['time']}\n\n"
            "¿Querés agregar un motivo de consulta? (opcional)\n"
            "O respondé:\n"
            '• "Sí, confirmar" — para agendarlo\n'
            '• "No" o "cancelar" — para cancelar\n'
            '• El motivo directamente'
        )

    # We're waiting for confirmation or a reason.
    cancel_words = {"no", "cancelar", "cancelá", "no quiero", "para", "cancelación"}
    confirm_words = {"sí", "si", "confirmar", "confirmo", "dale", "ok", "okay", "de acuerdo"}

    text_lower = patient_message.strip().lower()

    if any(word in text_lower for word in cancel_words):
        # Cancel the booking flow.
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return "No hay problema. Si querés agendar un turno más tarde, decime."

    # Check if they want to add a reason or just confirm.
    has_reason = not any(
        word == text_lower or text_lower.startswith(word)
        for word in list(confirm_words) + list(cancel_words)
    )

    if not has_reason and not any(
        word in text_lower for word in confirm_words
    ):
        # Patient said something unclear — ask again.
        return (
            "Disculpá, no entendí. ¿Confirmamos el turno?\n\n"
            'Respondé "Sí, confirmar" para agendarlo, '
            'o "No" para cancelar.'
        )

    reason_text = patient_message if has_reason else None

    # --- Execute the booking ---
    try:
        # Parse dates.
        start_dt = datetime.fromisoformat(selected_slot["start"])
        end_dt = datetime.fromisoformat(selected_slot["end"])

        # Get patient record by patient_id (UUID passed from orchestrator).
        from app.infrastructure.database.models.patient import Patient as PatientModel
        stmt_p = select(PatientModel).where(
            PatientModel.id == uuid.UUID(patient_id)
        )
        res_p = await db.execute(stmt_p)
        patient = res_p.scalar_one_or_none()

        if patient is None:
            return "Lo siento, hubo un error al identificar tus datos. Por favor, comunicate con la clínica."

        # Book it.
        calendar_provider = GoogleCalendarProvider(tenant_id=tenant_id, db=db)
        booking_service = BookAppointment(db=db, calendar_provider=calendar_provider)
        result = await booking_service.execute(
            tenant_id=tenant_id,
            patient=patient,
            doctor_id=doctor_id,
            slot_start=start_dt,
            slot_end=end_dt,
            reason=reason_text,
        )

        # Clear booking state.
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()

        logger.info(
            "Appointment booked: id=%s google_event_id=%s patient=%s doctor=%s",
            result["appointment_id"], result["google_event_id"],
            patient_id, doctor_id,
        )

        parsed_date = date.fromisoformat(date_str) if date_str else start_dt.date()
        return (
            f"✅ ¡Turno confirmado!\n\n"
            f"🏥 {tenant_name}\n"
            f"👨‍⚕️ {doctor_name}\n"
            f"📅 {_format_date_es(parsed_date)} a las {selected_slot['time']}\n\n"
            "Te voy a enviar un recordatorio 24 horas antes.\n"
            "Si necesitas cancelar o reprogramar, solo decime."
        )

    except (RuntimeError, ConnectionError) as exc:
        logger.error("Booking failed for patient %s: %s", patient_id, exc)
        conversation.extra_data = {}
        db.add(conversation)
        await db.flush()
        return (
            "Lo siento, hubo un error al agendar tu turno. "
            "El sistema está temporalmente fuera de servicio. "
            "Por favor, comunicate con la clínica para agendarte."
        )


# ---------------------------------------------------------------------------
# Booking helper functions
# ---------------------------------------------------------------------------


def _match_doctor(text: str, doctors: list[dict]) -> dict | None:
    """Try to match a doctor from the patient's message.

    Supports:
    - Index: ``"el 1"``, ``"el 2"``
    - Name: ``"Dr. Garcia"``, ``"el doctor Garcia"``, ``"Garcia"``
    - Any: ``"cualquiera"``, ``"el primero"``
    """
    text_lower = text.lower().strip()

    # "cualquiera", "el primero", "cualquier"
    if any(word in text_lower for word in ["cualquiera", "primero", "primera", "cualquier"]):
        return doctors[0] if doctors else None

    # Index: "el 1", "el 2", "1", "2"
    m = re.search(r'(?:el\s+)?(\d+)', text_lower)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(doctors):
            return doctors[idx]

    # Name matching: remove common prefixes.
    clean = re.sub(r'(?:el\s+)?(?:doctor|dr\.?|dra\.?|doctora)\s+', '', text_lower).strip()

    for doc in doctors:
        doc_name_lower = doc["name"].lower()
        # Check if the cleaned text contains the doctor's name or vice versa.
        if clean and (clean in doc_name_lower or doc_name_lower in clean):
            return doc

    # Try matching against full name parts.
    for doc in doctors:
        parts = doc["name"].lower().split()
        for part in parts:
            if len(part) > 2 and part in text_lower:
                return doc

    return None


def _parse_date(text: str) -> date | None:
    """Parse a Spanish date expression and return a ``date``, or ``None``."""
    text_lower = text.lower().strip()
    today = date.today()

    # "hoy"
    if text_lower in ("hoy", "ahora", "ya"):
        return today

    # "mañana"
    if text_lower in ("mañana", "manana"):
        return today + timedelta(days=1)

    # "pasado mañana"
    if text_lower in ("pasado mañana", "pasado manana", "pasado"):
        return today + timedelta(days=2)

    # Day-of-week: "el lunes", "lunes", "el martes"...
    day_names = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
    }
    m = re.search(
        r'(?:el\s+)?(lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)',
        text_lower,
    )
    if m:
        target_weekday = day_names[m.group(1)]
        days_ahead = target_weekday - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead)

    # "15 de junio", "15/06", "15-06", "15/6"
    # Try DD/MM or DD-MM format first.
    m = re.search(r'(\d{1,2})\s*[/\-]\s*(\d{1,2})(?:\s*[/\-]\s*(\d{2,4}))?', text_lower)
    if m:
        day_num = int(m.group(1))
        month_num = int(m.group(2))
        year_str = m.group(3)
        year = int(year_str) if year_str else today.year
        if 1 <= day_num <= 31 and 1 <= month_num <= 12:
            try:
                parsed = date(year, month_num, day_num)
                if parsed < today:
                    parsed = date(year + 1, month_num, day_num)
                return parsed
            except ValueError:
                pass

    # "15 de junio" style.
    month_names = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
        "diciembre": 12,
    }
    m = re.search(
        r'(\d{1,2})\s*de\s*([a-záéíóúñ]+)',
        text_lower,
    )
    if m:
        day_num = int(m.group(1))
        month_str = m.group(2)
        month_num = month_names.get(month_str)
        if month_num and 1 <= day_num <= 31:
            year = today.year
            try:
                parsed = date(year, month_num, day_num)
                if parsed < today:
                    parsed = date(year + 1, month_num, day_num)
                return parsed
            except ValueError:
                pass

    return None


def _match_slot(text: str, slots: list[dict]) -> dict | None:
    """Match a slot selection from the patient's message."""
    text_lower = text.lower().strip()

    # Index: "el 1", "1"
    m = re.search(r'(?:el\s+)?(\d+)', text_lower)
    if m:
        idx = int(m.group(1)) - 1
        for slot in slots:
            if slot["index"] == idx + 1:
                return slot

    # Time match: try to find an HH:MM pattern.
    m = re.search(r'(\d{1,2})[:.](\d{2})', text_lower)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        target = f"{hour:02d}:{minute:02d}"
        for slot in slots:
            if slot["time"] == target:
                return slot

    # Try "las 10", "a las 10" etc.
    m = re.search(r'(?:a\s+)?(?:las\s+)?(\d{1,2})(?:\s*horas?)?', text_lower)
    if m:
        hour = int(m.group(1))
        target = f"{hour:02d}:00"
        for slot in slots:
            if slot["time"] == target:
                return slot
        # Try :30 as well.
        target_half = f"{hour:02d}:30"
        for slot in slots:
            if slot["time"] == target_half:
                return slot

    return None


def _format_date_es(d: date) -> str:
    """Format a date in Spanish, e.g. ``"lunes 15 de junio"``."""
    day_names = {
        0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
        4: "viernes", 5: "sábado", 6: "domingo",
    }
    month_names = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
        7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre",
        11: "noviembre", 12: "diciembre",
    }
    weekday = day_names[d.weekday()]
    month = month_names[d.month]
    return f"{weekday} {d.day} de {month}"


async def _find_next_available_dates(
    db: Any,
    tenant_id: str,
    doctor_id: str | None,
    start_date: date,
    max_days: int = 7,
    slot_service: GetAvailableSlots | None = None,
) -> list[date]:
    """Scan up to *max_days* looking for dates that have at least one slot."""
    if slot_service is None:
        calendar_provider = GoogleCalendarProvider(tenant_id=tenant_id, db=db)
        slot_service = GetAvailableSlots(db=db, calendar_provider=calendar_provider)

    available: list[date] = []
    for i in range(max_days):
        check_date = start_date + timedelta(days=i)
        try:
            slots = await slot_service.execute(
                tenant_id=tenant_id,
                doctor_id=doctor_id,
                day=check_date,
            )
            if slots:
                available.append(check_date)
        except Exception:
            logger.exception("Error checking availability for %s", check_date)
            continue

        if len(available) >= 3:
            break

    return available


async def _handle_faq(
    db: Any,
    llm_provider: OpenAIClient,
    tenant_id: str,
    conversation_id: str,
    patient_id: str,
    sender_number: str,
    tenant_name: str,
    clinic_config: Any,
    result: IntentResult,
    patient_message: str,
) -> str:
    """Handle an FAQ by searching the knowledge base and generating a response."""
    faqs = await search_faqs(db, tenant_id, patient_message)

    if not faqs:
        return (
            "Disculpá, no tengo información sobre eso. "
            "¿Querés que te comunique con recepción para que te ayuden?"
        )

    response = await generate_faq_response(
        llm_provider=llm_provider,
        faq_results=faqs,
        question=patient_message,
        clinic_name=tenant_name,
    )

    if response:
        return response

    # Fallback: return the first FAQ answer directly.
    return faqs[0]["answer"]


async def _handle_humano(
    db: Any,
    llm_provider: OpenAIClient,
    tenant_id: str,
    conversation_id: str,
    patient_id: str,
    sender_number: str,
    tenant_name: str,
    clinic_config: Any,
    result: IntentResult,
    patient_message: str,
) -> str:
    """Handle a request to speak to a human — escalate immediately."""
    await escalate_conversation(
        db=db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        reason="patient_request",
        details={
            "intent": "humano",
            "patient_message": patient_message,
        },
    )

    return (
        "Te paso con recepción así te pueden ayudar mejor. "
        "Un momento por favor."
    )


async def _handle_desconocido(
    db: Any,
    llm_provider: OpenAIClient,
    tenant_id: str,
    conversation_id: str,
    patient_id: str,
    sender_number: str,
    tenant_name: str,
    clinic_config: Any,
    result: IntentResult,
    patient_message: str,
) -> str:
    """Handle an unknown intent — ask to rephrase or escalate if repeated."""
    # If the classifier determined it's time to escalate (after too many
    # unknown attempts), the result.intent will already be "humano".
    if result.intent == "humano":
        await escalate_conversation(
            db=db,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            reason="max_unknown_retries",
            details={
                "intent": "desconocido",
                "patient_message": patient_message,
                "confidence": result.confidence,
            },
        )

    return result.message or (
        "Disculpá, no entendí tu mensaje. ¿Podrías reformularlo?"
    )


async def _handle_emergency(
    db: Any,
    tenant_id: str,
    conversation_id: str,
    clinic_config: Any,
    patient_message: str,
) -> str:
    """Handle an emergency detection — escalate and return emergency message."""
    await escalate_conversation(
        db=db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        reason="emergency_detected",
        details={
            "patient_message": patient_message,
        },
    )

    emergency_phone = (
        clinic_config.emergency_phone
        if clinic_config and clinic_config.emergency_phone
        else None
    )

    if emergency_phone:
        return (
            f"⚠️ Si es una emergencia, por favor llamá al "
            f"{emergency_phone} inmediatamente.\n\n"
            "Te paso con recepción así te pueden ayudar mejor. "
            "Un momento por favor."
        )

    return (
        "⚠️ Si es una emergencia, por favor llamá al servicio de "
        "emergencias local (107) inmediatamente.\n\n"
        "Te paso con recepción así te pueden ayudar mejor. "
        "Un momento por favor."
    )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _load_history_excluding(
    db: Any,
    conversation_id: str,
    exclude_message_id: str,
    limit: int = 10,
) -> list[dict[str, str]]:
    """Load the last N messages from a conversation, excluding a given message.

    This ensures the current patient message is not included in the
    conversation history passed to the classifier (since it will be
    appended separately).
    """
    stmt = (
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.id != exclude_message_id,
        )
        .order_by(ConversationMessage.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()
    messages = list(reversed(messages))

    history: list[dict[str, str]] = []
    for msg in messages:
        if msg.origin == MessageOrigin.patient:
            history.append({"role": "user", "content": msg.content})
        elif msg.origin == MessageOrigin.bot:
            history.append({"role": "assistant", "content": msg.content})
    return history


async def _save_responses(
    db: Any,
    conversation_id: str,
    message_id: str,
    bot_message: str,
    intent: str,
    confidence: float,
    is_emergency: bool,
) -> None:
    """Update the patient message with intent data and save the bot response."""
    # Update the patient's message with the classified intent.
    stmt = select(ConversationMessage).where(
        ConversationMessage.id == message_id
    )
    result = await db.execute(stmt)
    patient_msg = result.scalar_one_or_none()
    if patient_msg:
        patient_msg.intent = intent
        metadata = patient_msg.extra_data or {}
        metadata.update(
            {
                "confidence": confidence,
                "is_emergency": is_emergency,
            }
        )
        patient_msg.extra_data = metadata
        db.add(patient_msg)

    # Save the bot response message.
    if bot_message:
        bot_response = ConversationMessage(
            conversation_id=conversation_id,
            origin=MessageOrigin.bot,
            content=bot_message,
            intent=intent,
            extra_data={
                "confidence": confidence,
                "is_emergency": is_emergency,
            },
        )
        db.add(bot_response)

    await db.commit()


async def _send_whatsapp_response(
    tenant_slug: str,
    to: str,
    text: str,
) -> None:
    """Send a WhatsApp message using the Evolution API provider."""
    try:
        provider = EvolutionAPIProvider(instance_name=tenant_slug)
        await provider.send_text(to=to, text=text)
        logger.info(
            "Sent WhatsApp response to %s via instance %s (%.80s)",
            to,
            tenant_slug,
            text,
        )
    except Exception as exc:
        logger.error(
            "Failed to send WhatsApp response to %s: %s",
            to,
            exc,
        )
