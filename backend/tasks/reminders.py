"""Celery periodic tasks for automatic appointment reminders (F4).

Sends two reminders per appointment:
  - Reminder 1: 24 hours before the appointment.
  - Reminder 2: 6 hours before the appointment (only if the patient did not
    confirm Reminder 1).

Both tasks run every 30 minutes via Celery Beat.  A 1-hour lookup window
ensures no appointment is missed.  Flag columns on ``Appointment`` prevent
duplicate sends.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from celery import shared_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.enums import AppointmentStatus
from app.infrastructure.database.models.appointment import Appointment
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.clinic_config import ClinicConfig
from app.infrastructure.database.models.doctor import Doctor
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.tenant import Tenant
from app.infrastructure.database.models.tenant_settings import TenantSettings
from app.infrastructure.whatsapp.evolution import EvolutionAPIProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sync engine for Celery workers
# ---------------------------------------------------------------------------
# The FastAPI app uses an async engine (asyncpg).  Celery tasks run
# synchronously in a worker process, so we create a separate sync engine
# with psycopg2 for background task use.
# ---------------------------------------------------------------------------

_SYNC_DATABASE_URL = settings.database_url.replace("+asyncpg", "+psycopg2")
_sync_engine = create_engine(_SYNC_DATABASE_URL)


def _get_sync_session() -> Session:
    """Return a new synchronous SQLAlchemy session for Celery tasks."""
    return Session(_sync_engine)


# ---------------------------------------------------------------------------
# Constants (spec F4 / RN4)
# ---------------------------------------------------------------------------

REMINDER_1_HOURS_BEFORE = 24       # RN4.1
REMINDER_2_HOURS_BEFORE = 6        # RN4.2
LOOKUP_WINDOW_MINUTES = 30          # ±30 min around the target → 1h window
NO_REMINDER_HOUR_START = 22         # RN4.3: no reminders between 22:00 …
NO_REMINDER_HOUR_END = 8            # … and 8:00

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@shared_task(name="tasks.reminders.send_reminder_1")
def send_reminder_1() -> None:
    """Send first reminder for appointments exactly 24h before start time.

    Runs every 30 minutes via Celery Beat.  Queries appointments where
    ``start_time`` is within a 1-hour window around ``now + 24h``, status
    is ``confirmed``, and ``reminder_1_sent`` is ``False``.
    """
    logger.info("[reminder_1] Starting task run")
    now = datetime.now(timezone.utc)

    target_delta = timedelta(hours=REMINDER_1_HOURS_BEFORE)
    window = timedelta(minutes=LOOKUP_WINDOW_MINUTES)

    window_start = now + target_delta - window
    window_end = now + target_delta + window

    session = _get_sync_session()
    try:
        stmt = (
            select(Appointment)
            .where(
                Appointment.status == AppointmentStatus.confirmed,
                Appointment.start_time >= window_start,
                Appointment.start_time <= window_end,
                Appointment.reminder_1_sent.is_(False),
            )
            .execution_options(stream_results=False)
        )
        appointments = list(session.execute(stmt).scalars().all())
        logger.info("[reminder_1] Found %d appointments to process", len(appointments))

        for appointment in appointments:
            try:
                _process_reminder_1(session, appointment)
            except Exception:
                logger.exception(
                    "[reminder_1] Failed for appointment %s", appointment.id,
                )
                session.rollback()

        session.commit()
        logger.info("[reminder_1] Task completed successfully")

    except Exception:
        logger.exception("[reminder_1] Unhandled error")
        session.rollback()
        raise
    finally:
        session.close()


@shared_task(name="tasks.reminders.send_reminder_2")
def send_reminder_2() -> None:
    """Send second reminder for appointments exactly 6h before start time.

    Only sent if the patient did NOT confirm Reminder 1
    (``reminder_confirmed = False``).  If the patient has not responded
    after this reminder, the appointment is marked as ``unconfirmed``.
    """
    logger.info("[reminder_2] Starting task run")
    now = datetime.now(timezone.utc)

    target_delta = timedelta(hours=REMINDER_2_HOURS_BEFORE)
    window = timedelta(minutes=LOOKUP_WINDOW_MINUTES)

    window_start = now + target_delta - window
    window_end = now + target_delta + window

    session = _get_sync_session()
    try:
        stmt = (
            select(Appointment)
            .where(
                Appointment.status == AppointmentStatus.confirmed,
                Appointment.start_time >= window_start,
                Appointment.start_time <= window_end,
                Appointment.reminder_1_sent.is_(True),
                Appointment.reminder_confirmed.is_(False),
                Appointment.reminder_2_sent.is_(False),
            )
            .execution_options(stream_results=False)
        )
        appointments = list(session.execute(stmt).scalars().all())
        logger.info("[reminder_2] Found %d appointments to process", len(appointments))

        for appointment in appointments:
            try:
                _process_reminder_2(session, appointment)
            except Exception:
                logger.exception(
                    "[reminder_2] Failed for appointment %s", appointment.id,
                )
                session.rollback()

        session.commit()
        logger.info("[reminder_2] Task completed successfully")

    except Exception:
        logger.exception("[reminder_2] Unhandled error")
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Processing helpers
# ---------------------------------------------------------------------------


def _process_reminder_1(session: Session, appointment: Appointment) -> None:
    """Send first reminder for a single appointment."""
    patient = session.get(Patient, appointment.patient_id)
    if patient is None:
        logger.warning(
            "[reminder_1] Patient %s not found, skipping", appointment.patient_id,
        )
        return

    if not patient.reminders_opt_in:
        logger.info(
            "[reminder_1] Patient %s opted out of reminders, skipping",
            patient.id,
        )
        return

    # Night check
    tenant_settings = _get_tenant_settings(session, appointment.tenant_id)
    if not _should_send_now(tenant_settings):
        logger.info(
            "[reminder_1] Nighttime window, will retry for appointment %s",
            appointment.id,
        )
        return

    # Build and send message
    message = _build_reminder_message(
        session=session,
        appointment=appointment,
        patient=patient,
        is_second=False,
    )

    tenant = session.get(Tenant, appointment.tenant_id)
    if tenant is None:
        logger.warning(
            "[reminder_1] Tenant %s not found, skipping", appointment.tenant_id,
        )
        return

    _send_whatsapp_sync(
        instance_name=tenant.slug,
        to=patient.phone_number,
        text=message,
    )

    # Mark sent
    appointment.reminder_1_sent = True
    session.add(appointment)

    # Audit log
    _log_audit(session, appointment, "reminder_1_sent")

    logger.info(
        "[reminder_1] Sent to appointment %s (patient %s, phone %s)",
        appointment.id, patient.id, patient.phone_number,
    )


def _process_reminder_2(session: Session, appointment: Appointment) -> None:
    """Send second reminder for a single appointment."""
    patient = session.get(Patient, appointment.patient_id)
    if patient is None:
        logger.warning(
            "[reminder_2] Patient %s not found, skipping", appointment.patient_id,
        )
        return

    if not patient.reminders_opt_in:
        logger.info(
            "[reminder_2] Patient %s opted out of reminders, skipping",
            patient.id,
        )
        return

    # Night check
    tenant_settings = _get_tenant_settings(session, appointment.tenant_id)
    if not _should_send_now(tenant_settings):
        logger.info(
            "[reminder_2] Nighttime window, will retry for appointment %s",
            appointment.id,
        )
        return

    # Build and send message
    message = _build_reminder_message(
        session=session,
        appointment=appointment,
        patient=patient,
        is_second=True,
    )

    tenant = session.get(Tenant, appointment.tenant_id)
    if tenant is None:
        logger.warning(
            "[reminder_2] Tenant %s not found, skipping", appointment.tenant_id,
        )
        return

    _send_whatsapp_sync(
        instance_name=tenant.slug,
        to=patient.phone_number,
        text=message,
    )

    # Mark sent
    appointment.reminder_2_sent = True
    session.add(appointment)

    # If no confirmation after second reminder → mark as unconfirmed
    # (the appointment stays in DB, but the panel will show this status)
    if not appointment.reminder_confirmed:
        appointment.status = AppointmentStatus.unconfirmed
        session.add(appointment)

    # Audit log
    _log_audit(session, appointment, "reminder_2_sent")

    logger.info(
        "[reminder_2] Sent to appointment %s (patient %s, phone %s)",
        appointment.id, patient.id, patient.phone_number,
    )


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------


def _build_reminder_message(
    session: Session,
    appointment: Appointment,
    patient: Patient,
    is_second: bool,
) -> str:
    """Build the WhatsApp reminder message per spec F4.

    Format::

        📅 *Recordatorio de turno*
        Hola [nombre], te recordamos que tenés turno mañana [fecha] a las
        [hora] con [médico] en [dirección].
        Respondé:
        ✅ *Confirmar*
        🔄 *Reprogramar*
        ❌ *Cancelar*
    """
    # Resolve doctor name
    doctor_name = "Médico"
    if appointment.doctor_id:
        doctor = session.get(Doctor, appointment.doctor_id)
        if doctor:
            doctor_name = doctor.name

    # Resolve clinic address
    clinic_config = _get_clinic_config(session, appointment.tenant_id)
    address = clinic_config.address if clinic_config and clinic_config.address else ""

    # Format date/time in Argentina timezone
    tz = ZoneInfo("America/Argentina/Buenos_Aires")
    start_local = appointment.start_time.astimezone(tz)

    date_str = _format_date_es(start_local)
    time_str = start_local.strftime("%H:%M")

    greeting = "Hola" if patient.name else "Hola"
    name_part = f" {patient.name}" if patient.name else ""

    header = "📅 *Recordatorio de turno*"
    if is_second:
        header = "📅 *Segundo recordatorio*"

    body_lines = [
        header,
        "",
        f"{greeting}{name_part}, te recordamos que tenés turno mañana "
        f"{date_str} a las {time_str} con {doctor_name}.",
    ]

    if address:
        body_lines.append(f"📍 {address}")

    body_lines.extend([
        "",
        "Respondé:",
        "✅ *Confirmar* — voy a asistir",
        "🔄 *Reprogramar* — quiero cambiar la fecha",
        "❌ *Cancelar* — no voy a poder ir",
    ])

    return "\n".join(body_lines)


# ---------------------------------------------------------------------------
# Nighttime check
# ---------------------------------------------------------------------------


def _should_send_now(tenant_settings: TenantSettings | None) -> bool:
    """Check if current time is outside the no-reminder window (RN4.3).

    Default window: 22:00 – 8:00 (no reminders during nighttime).
    Uses the tenant's configured timezone if available.
    """
    tz_name = "America/Argentina/Buenos_Aires"
    if tenant_settings and getattr(tenant_settings, "timezone", None):
        tz_name = tenant_settings.timezone

    now = datetime.now(ZoneInfo(tz_name))
    current_hour = now.hour

    # Window wraps past midnight (e.g., 22:00 → 8:00).
    if NO_REMINDER_HOUR_START > NO_REMINDER_HOUR_END:
        # Example: 22:00 – 8:00 → true if hour is 22, 23, 0, 1, …, 7
        if current_hour >= NO_REMINDER_HOUR_START or current_hour < NO_REMINDER_HOUR_END:
            return False
    else:
        # Non-wrapping window (e.g., 0:00 – 6:00).
        if NO_REMINDER_HOUR_START <= current_hour < NO_REMINDER_HOUR_END:
            return False

    return True


# ---------------------------------------------------------------------------
# WhatsApp sending (async → sync bridge)
# ---------------------------------------------------------------------------


def _send_whatsapp_sync(instance_name: str, to: str, text: str) -> None:
    """Send a WhatsApp message synchronously inside a Celery task.

    ``EvolutionAPIProvider.send_text`` is async (uses ``httpx.AsyncClient``),
    so we bridge with ``asyncio.run()`` for the Celery worker context.
    """
    async def _send() -> None:
        provider = EvolutionAPIProvider(instance_name=instance_name)
        await provider.send_text(to=to, text=text)

    asyncio.run(_send())


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_tenant_settings(
    session: Session,
    tenant_id,
) -> TenantSettings | None:
    """Load ``TenantSettings`` for the given tenant."""
    stmt = select(TenantSettings).where(
        TenantSettings.tenant_id == tenant_id,
    )
    return session.execute(stmt).scalar_one_or_none()


def _get_clinic_config(
    session: Session,
    tenant_id,
) -> ClinicConfig | None:
    """Load ``ClinicConfig`` for the given tenant."""
    stmt = select(ClinicConfig).where(
        ClinicConfig.tenant_id == tenant_id,
    )
    return session.execute(stmt).scalar_one_or_none()


def _log_audit(
    session: Session,
    appointment: Appointment,
    action: str,
) -> None:
    """Create an audit log entry for a reminder event."""
    audit = AuditLog(
        tenant_id=appointment.tenant_id,
        action=action,
        entity_type="appointment",
        entity_id=str(appointment.id),
        details={
            "patient_id": str(appointment.patient_id),
            "appointment_time": appointment.start_time.isoformat(),
        },
    )
    session.add(audit)


# ---------------------------------------------------------------------------
# Date formatting (Spanish)
# ---------------------------------------------------------------------------


def _format_date_es(dt: datetime) -> str:
    """Format a datetime in Spanish, e.g. ``"lunes 15 de junio"``."""
    day_names = {
        0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
        4: "viernes", 5: "sábado", 6: "domingo",
    }
    month_names = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
        7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre",
        11: "noviembre", 12: "diciembre",
    }
    weekday = day_names[dt.weekday()]
    month = month_names[dt.month]
    return f"{weekday} {dt.day} de {month}"
