from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.calendar import CalendarProvider
from app.infrastructure.database.repository.appointment_repo import AppointmentRepo
from app.infrastructure.database.models.patient import Patient


class BookAppointment:
    """Use case: book an appointment and create the corresponding calendar event.

    Steps:
    1. Create the event in Google Calendar (retry once on failure).
    2. Persist the appointment record in the local database.
    3. Store the Google Calendar event ID on the appointment record.
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
        patient: Patient,
        doctor_id: str,
        slot_start: datetime,
        slot_end: datetime,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Execute the booking and return appointment details."""
        # 1. Create event in Google Calendar.
        google_event_id = await self._create_calendar_event(
            doctor_id=doctor_id,
            patient=patient,
            slot_start=slot_start,
            slot_end=slot_end,
            reason=reason,
        )

        # 2. Create the appointment record.
        appointment = await self._appointment_repo.create_appointment(
            tenant_id=tenant_id,
            patient_id=str(patient.id),
            doctor_id=doctor_id,
            start_time=slot_start,
            end_time=slot_end,
            reason=reason,
        )

        # 3. Link the Google Calendar event ID.
        appointment.google_event_id = google_event_id
        self._db.add(appointment)
        await self._db.flush()
        await self._db.refresh(appointment)

        return {
            "appointment_id": str(appointment.id),
            "google_event_id": google_event_id,
            "start_time": slot_start,
            "end_time": slot_end,
            "status": str(appointment.status),
        }

    async def _create_calendar_event(
        self,
        doctor_id: str,
        patient: Patient,
        slot_start: datetime,
        slot_end: datetime,
        reason: str | None,
    ) -> str:
        """Create a calendar event with a single retry on failure."""
        max_retries = 2
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                event_id = await self._calendar_provider.create_event(
                    doctor_id=doctor_id,
                    patient_name=patient.name or "Paciente",
                    patient_phone=patient.phone_number,
                    reason=reason,
                    start_time=slot_start,
                    end_time=slot_end,
                )
                return event_id
            except Exception as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    continue
                raise RuntimeError(
                    f"Failed to create calendar event after {max_retries} attempts: {exc}"
                ) from last_error

        # Should not be reached, but satisfy the return type.
        raise RuntimeError(
            f"Failed to create calendar event after {max_retries} attempts"
        ) from last_error
