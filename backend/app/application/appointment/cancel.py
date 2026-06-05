from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AppointmentStatus
from app.domain.interfaces.calendar import CalendarProvider
from app.infrastructure.database.repository.appointment_repo import AppointmentRepo

logger = logging.getLogger(__name__)


class CancelAppointment:
    """Use case: cancel an existing appointment.

    Validates the appointment exists, belongs to the patient, and is more
    than 2 hours away. Deletes the calendar event and updates the DB record.

    Steps:
    1. Validate appointment exists and belongs to patient.
    2. Check the 2-hour window (RN3.1: only cancel with >2h before).
    3. Delete the Google Calendar event.
    4. Update appointment status to ``cancelled_by_patient``.
    5. Set ``cancelled_at`` and ``cancellation_reason``.
    """

    def __init__(
        self,
        db: AsyncSession,
        calendar_provider: CalendarProvider,
    ) -> None:
        self._db = db
        self._calendar_provider = calendar_provider
        self._appointment_repo = AppointmentRepo(db)

    async def execute(
        self,
        tenant_id: str,
        patient_id: str,
        appointment_id: str,
        reason: str | None = "patient_request",
    ) -> dict[str, Any]:
        """Cancel the appointment and return updated details.

        Raises:
            ValueError: If the appointment does not exist, does not belong
                to the patient, or is within the 2-hour window.
        """
        # 1. Validate appointment exists.
        appointment = await self._appointment_repo.get_appointment_by_id(appointment_id)
        if appointment is None:
            raise ValueError("Turno no encontrado.")

        # 2. Validate it belongs to this patient.
        if str(appointment.patient_id) != patient_id:
            raise ValueError("El turno no pertenece al paciente.")

        # 3. Enforce 2-hour window (RN3.1).
        now = datetime.now(timezone.utc)
        appointment_start = (
            appointment.start_time
            if appointment.start_time.tzinfo is not None
            else appointment.start_time.replace(tzinfo=timezone.utc)
        )

        if appointment_start - now < timedelta(hours=2):
            # RN3.2: within 2h — must call the clinic.
            raise ValueError(
                "Debe llamar a la clínica"
            )

        # 4. Delete the Google Calendar event (RN3.4: free the slot).
        if appointment.google_event_id:
            doctor_id = str(appointment.doctor_id) if appointment.doctor_id else None
            await self._calendar_provider.delete_event(
                doctor_id=doctor_id,
                event_id=appointment.google_event_id,
            )

        # 5. Update the appointment record.
        cancelled_at = datetime.now(timezone.utc)
        appointment.status = AppointmentStatus.cancelled_by_patient
        appointment.cancelled_at = cancelled_at
        appointment.cancellation_reason = reason
        self._db.add(appointment)
        await self._db.flush()
        await self._db.refresh(appointment)

        return {
            "appointment_id": str(appointment.id),
            "status": str(appointment.status),
            "cancelled_at": cancelled_at,
            "cancellation_reason": reason,
            "doctor_id": str(appointment.doctor_id) if appointment.doctor_id else None,
        }


# ---------------------------------------------------------------------------
# Utility for reminder-originated cancellations (T10)
# ---------------------------------------------------------------------------


async def handle_cancel_from_reminder(
    db: AsyncSession,
    calendar_provider: CalendarProvider,
    appointment_id: str,
) -> str:
    """Cancel an appointment triggered from a reminder response (T10).

    Called by the reminder handler when a patient responds with the cancel
    option from a reminder message. Returns a user-facing confirmation or
    error message.
    """
    try:
        repo = AppointmentRepo(db)
        appointment = await repo.get_appointment_by_id(appointment_id)
        if appointment is None:
            return "Lo siento, no encontré el turno."

        patient_id = str(appointment.patient_id)
        tenant_id = str(appointment.tenant_id)

        service = CancelAppointment(db=db, calendar_provider=calendar_provider)
        await service.execute(
            tenant_id=tenant_id,
            patient_id=patient_id,
            appointment_id=appointment_id,
            reason="reminder_cancellation",
        )
        return "Tu turno fue cancelado."
    except ValueError as exc:
        return str(exc)
    except Exception:
        logger.exception("Failed to cancel appointment %s from reminder", appointment_id)
        return (
            "Lo siento, hubo un error al cancelar el turno. "
            "Por favor, comunicate con la clínica."
        )
