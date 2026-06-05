"""Unit tests for appointment use cases (Book, Cancel, Reschedule).

Tests cover:
- ``BookAppointment`` — calendar event creation, DB persistence
- ``CancelAppointment`` — validation, 2-hour rule, calendar deletion
- ``RescheduleAppointment`` — booking new slot, cancelling old one
- ``GetAvailableSlots`` — duration from config, calendar delegation
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.application.appointment.book import BookAppointment
from app.application.appointment.cancel import CancelAppointment
from app.application.appointment.reschedule import RescheduleAppointment
from app.application.appointment.get_slots import GetAvailableSlots
from app.domain.enums import AppointmentStatus
from app.infrastructure.database.repository.appointment_repo import AppointmentRepo


# =========================================================================
# BookAppointment
# =========================================================================


class TestBookAppointment:
    async def test_execute_creates_appointment(
        self, db_session, mock_calendar_provider, test_tenant, test_patient
    ):
        """Booking creates a DB record and returns expected fields."""
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        slot_start = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        slot_end = slot_start + timedelta(minutes=20)

        service = BookAppointment(
            db=db_session, calendar_provider=mock_calendar_provider
        )
        result = await service.execute(
            tenant_id=str(test_tenant.id),
            patient=test_patient,
            doctor_id="00000000-0000-0000-0000-000000000001",
            slot_start=slot_start,
            slot_end=slot_end,
            reason="Consulta general",
        )

        assert result["appointment_id"] is not None
        assert result["google_event_id"] == "google-event-id-123"
        assert result["status"] == "confirmed"
        assert result["start_time"] == slot_start

        # Verify it was persisted
        repo = AppointmentRepo(db_session)
        persisted = await repo.get_appointment_by_id(result["appointment_id"])
        assert persisted is not None
        assert str(persisted.patient_id) == str(test_patient.id)

    async def test_calendar_retry_on_failure(
        self, db_session, mock_calendar_provider, test_tenant, test_patient
    ):
        """If the first calendar call fails, a retry is attempted."""
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        slot_start = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        slot_end = slot_start + timedelta(minutes=20)

        # Fail first, succeed second
        mock_calendar_provider.create_event.side_effect = [
            ConnectionError("first attempt failed"),
            "google-event-id-retry",
        ]

        service = BookAppointment(
            db=db_session, calendar_provider=mock_calendar_provider
        )
        result = await service.execute(
            tenant_id=str(test_tenant.id),
            patient=test_patient,
            doctor_id="00000000-0000-0000-0000-000000000001",
            slot_start=slot_start,
            slot_end=slot_end,
        )
        assert result["google_event_id"] == "google-event-id-retry"
        # Should have been called twice
        assert mock_calendar_provider.create_event.await_count == 2

    async def test_calendar_all_attempts_fail(
        self, db_session, mock_calendar_provider, test_tenant, test_patient
    ):
        """If all calendar attempts fail, a RuntimeError is raised."""
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        slot_start = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        slot_end = slot_start + timedelta(minutes=20)

        mock_calendar_provider.create_event.side_effect = RuntimeError("calendar down")

        service = BookAppointment(
            db=db_session, calendar_provider=mock_calendar_provider
        )
        with pytest.raises(RuntimeError, match="Failed to create calendar event"):
            await service.execute(
                tenant_id=str(test_tenant.id),
                patient=test_patient,
                doctor_id="00000000-0000-0000-0000-000000000001",
                slot_start=slot_start,
                slot_end=slot_end,
            )


# =========================================================================
# CancelAppointment
# =========================================================================


class TestCancelAppointment:
    async def test_cancel_success(
        self, db_session, mock_calendar_provider, test_appointment, test_patient
    ):
        """A valid cancellation (outside 2h window) succeeds."""
        service = CancelAppointment(
            db=db_session, calendar_provider=mock_calendar_provider
        )
        result = await service.execute(
            tenant_id=str(test_appointment.tenant_id),
            patient_id=str(test_patient.id),
            appointment_id=str(test_appointment.id),
            reason="patient_request",
        )

        assert result["status"] == "cancelled_by_patient"
        assert result["cancellation_reason"] == "patient_request"

        # Verify calendar delete was called
        mock_calendar_provider.delete_event.assert_awaited_once()

    async def test_cancel_appointment_not_found(
        self, db_session, mock_calendar_provider, test_patient
    ):
        """Cancelling a non-existent appointment raises ValueError."""
        service = CancelAppointment(
            db=db_session, calendar_provider=mock_calendar_provider
        )
        with pytest.raises(ValueError, match="Turno no encontrado"):
            await service.execute(
                tenant_id="x",
                patient_id=str(test_patient.id),
                appointment_id="00000000-0000-0000-0000-000000000000",
            )

    async def test_cancel_wrong_patient(
        self, db_session, mock_calendar_provider, test_appointment
    ):
        """Cancelling another patient's appointment raises ValueError."""
        service = CancelAppointment(
            db=db_session, calendar_provider=mock_calendar_provider
        )
        other_patient_id = "00000000-0000-0000-0000-000000099999"
        with pytest.raises(ValueError, match="no pertenece al paciente"):
            await service.execute(
                tenant_id=str(test_appointment.tenant_id),
                patient_id=other_patient_id,
                appointment_id=str(test_appointment.id),
            )

    async def test_cancel_within_2h_window(
        self, db_session, mock_calendar_provider, test_tenant, test_patient
    ):
        """Appointments within 2h cannot be cancelled."""
        # Create an appointment starting in 30 minutes
        soon = datetime.now(timezone.utc) + timedelta(minutes=30)
        repo = AppointmentRepo(db_session)
        appointment = await repo.create_appointment(
            tenant_id=str(test_tenant.id),
            patient_id=str(test_patient.id),
            doctor_id="00000000-0000-0000-0000-000000000001",
            start_time=soon,
            end_time=soon + timedelta(minutes=20),
        )

        service = CancelAppointment(
            db=db_session, calendar_provider=mock_calendar_provider
        )
        with pytest.raises(ValueError, match="Debe llamar"):
            await service.execute(
                tenant_id=str(test_tenant.id),
                patient_id=str(test_patient.id),
                appointment_id=str(appointment.id),
            )


# =========================================================================
# RescheduleAppointment
# =========================================================================


class TestRescheduleAppointment:
    async def test_reschedule_success(
        self, db_session, mock_calendar_provider, test_appointment, test_patient
    ):
        """A reschedule books a new slot and marks the old one as rescheduled."""
        tomorrow = datetime.now(timezone.utc) + timedelta(days=2)
        new_start = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
        new_end = new_start + timedelta(minutes=20)

        service = RescheduleAppointment(
            db=db_session, calendar_provider=mock_calendar_provider
        )
        result = await service.execute(
            tenant_id=str(test_appointment.tenant_id),
            patient=test_patient,
            old_appointment_id=str(test_appointment.id),
            doctor_id="00000000-0000-0000-0000-000000000001",
            slot_start=new_start,
            slot_end=new_end,
        )

        assert result["status"] == "rescheduled"
        assert result["new_appointment_id"] is not None
        assert result["old_appointment_id"] == str(test_appointment.id)

        # Old appointment should now be rescheduled
        repo = AppointmentRepo(db_session)
        old = await repo.get_appointment_by_id(str(test_appointment.id))
        assert old is not None
        assert old.status == AppointmentStatus.rescheduled

    async def test_reschedule_old_not_found(
        self, db_session, mock_calendar_provider, test_patient
    ):
        """Rescheduling a non-existent appointment raises ValueError."""
        service = RescheduleAppointment(
            db=db_session, calendar_provider=mock_calendar_provider
        )
        tomorrow = datetime.now(timezone.utc) + timedelta(days=2)
        new_start = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
        new_end = new_start + timedelta(minutes=20)

        with pytest.raises(ValueError, match="Turno original no encontrado"):
            await service.execute(
                tenant_id="x",
                patient=test_patient,
                old_appointment_id="00000000-0000-0000-0000-000000000000",
                doctor_id="00000000-0000-0000-0000-000000000001",
                slot_start=new_start,
                slot_end=new_end,
            )


# =========================================================================
# GetAvailableSlots
# =========================================================================


class TestGetAvailableSlots:
    async def test_delegates_to_calendar_provider(
        self, db_session, mock_calendar_provider
    ):
        """GetAvailableSlots reads duration from config and delegates."""
        from datetime import date

        # No clinic config → fallback to 20 min
        service = GetAvailableSlots(
            db=db_session, calendar_provider=mock_calendar_provider
        )
        slots = await service.execute(
            tenant_id="00000000-0000-0000-0000-000000000001",
            doctor_id=None,
            day=date.today(),
        )

        mock_calendar_provider.get_available_slots.assert_awaited_once_with(
            doctor_id=None, day=date.today(), duration_minutes=20
        )
