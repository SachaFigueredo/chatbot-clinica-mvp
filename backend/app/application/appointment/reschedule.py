from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AppointmentStatus
from app.domain.interfaces.calendar import CalendarProvider
from app.infrastructure.database.repository.appointment_repo import AppointmentRepo
from app.infrastructure.database.models.patient import Patient
from app.application.appointment.get_slots import GetAvailableSlots
from app.application.appointment.book import BookAppointment

logger = logging.getLogger(__name__)


class RescheduleAppointment:
    """Use case: reschedule an existing appointment to a new slot.

    Reuses ``GetAvailableSlots`` for availability (T8) and
    ``BookAppointment`` for the new slot (T8). After booking the new
    slot, cancels the old appointment.

    Steps:
    1. Validate old appointment exists and belongs to patient.
    2. Check the 2-hour window (RN3.1).
    3. Book the new slot first (reuses BookAppointment).
    4. Delete the old calendar event.
    5. Mark old appointment as ``rescheduled``.
    """

    def __init__(
        self,
        db: AsyncSession,
        calendar_provider: CalendarProvider,
    ) -> None:
        self._db = db
        self._calendar_provider = calendar_provider
        self._appointment_repo = AppointmentRepo(db)
        self._get_slots_service = GetAvailableSlots(db, calendar_provider)
        self._booking_service = BookAppointment(db, calendar_provider)

    async def execute(
        self,
        tenant_id: str,
        patient: Patient,
        old_appointment_id: str,
        doctor_id: str,
        slot_start: datetime,
        slot_end: datetime,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Reschedule: book new slot, then cancel old appointment.

        Raises:
            ValueError: If the old appointment does not exist, does not
                belong to the patient, or is within the 2-hour window.
            RuntimeError: If the new booking fails (calendar error, etc.).
        """
        # 1. Validate old appointment exists.
        old_appointment = await self._appointment_repo.get_appointment_by_id(
            old_appointment_id
        )
        if old_appointment is None:
            raise ValueError("Turno original no encontrado.")

        # 2. Validate it belongs to this patient.
        if str(old_appointment.patient_id) != str(patient.id):
            raise ValueError("El turno original no pertenece al paciente.")

        # 3. Enforce 2-hour window (RN3.1).
        now = datetime.now(timezone.utc)
        appointment_start = (
            old_appointment.start_time
            if old_appointment.start_time.tzinfo is not None
            else old_appointment.start_time.replace(tzinfo=timezone.utc)
        )

        if appointment_start - now < timedelta(hours=2):
            raise ValueError("Debe llamar a la clínica")

        # 4. Book the new slot first (this creates the calendar event + DB record).
        new_booking = await self._booking_service.execute(
            tenant_id=tenant_id,
            patient=patient,
            doctor_id=doctor_id,
            slot_start=slot_start,
            slot_end=slot_end,
            reason=reason,
        )

        # 5. Delete the old appointment's calendar event (RN3.4: free the slot).
        if old_appointment.google_event_id:
            old_doctor_id = (
                str(old_appointment.doctor_id) if old_appointment.doctor_id else None
            )
            await self._calendar_provider.delete_event(
                doctor_id=old_doctor_id,
                event_id=old_appointment.google_event_id,
            )

        # 6. Mark old appointment as rescheduled.
        cancelled_at = datetime.now(timezone.utc)
        old_appointment.status = AppointmentStatus.rescheduled
        old_appointment.cancelled_at = cancelled_at
        old_appointment.cancellation_reason = "rescheduled"
        self._db.add(old_appointment)
        await self._db.flush()

        return {
            "old_appointment_id": old_appointment_id,
            "new_appointment_id": new_booking["appointment_id"],
            "new_google_event_id": new_booking["google_event_id"],
            "status": "rescheduled",
        }


# ---------------------------------------------------------------------------
# Utility for reminder-originated rescheduling (T10)
# ---------------------------------------------------------------------------


async def handle_reschedule_from_reminder(
    db: AsyncSession,
    calendar_provider: CalendarProvider,
    appointment_id: str,
) -> str:
    """Initiate a reschedule triggered from a reminder response.

    Called by the reminder handler when a patient responds with the
    reschedule option from a reminder message. This is a placeholder —
    T10 will connect the full multi-turn reschedule flow from here.

    Returns a user-facing message inviting the patient to choose a new date.
    """
    logger.info(
        "Reschedule from reminder triggered for appointment %s",
        appointment_id,
    )
    # T10 will wire the full multi-turn dialog from here.
    # For now, return a message that keeps the conversation flowing.
    return (
        "Entiendo que querés reprogramar tu turno. "
        "Decime qué día te viene mejor y busco disponibilidad."
    )
