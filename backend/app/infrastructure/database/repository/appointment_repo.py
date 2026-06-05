from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AppointmentStatus
from app.infrastructure.database.models.appointment import Appointment


class AppointmentRepo:
    """Repository for Appointment model database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_appointments_by_patient(
        self,
        patient_id: str,
        status: AppointmentStatus | None = None,
    ) -> list[Appointment]:
        """Return all appointments for a patient, optionally filtered by status."""
        stmt = select(Appointment).where(
            Appointment.patient_id == uuid.UUID(patient_id),
        )
        if status is not None:
            stmt = stmt.where(Appointment.status == status)
        stmt = stmt.order_by(Appointment.start_time.desc())
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_upcoming_appointments(
        self,
        patient_id: str,
    ) -> list[Appointment]:
        """Return confirmed/pending appointments whose start time is in the future."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(Appointment)
            .where(
                Appointment.patient_id == uuid.UUID(patient_id),
                Appointment.start_time > now,
                Appointment.status.in_([
                    AppointmentStatus.confirmed,
                    AppointmentStatus.pending,
                ]),
            )
            .order_by(Appointment.start_time.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def create_appointment(
        self,
        tenant_id: str,
        patient_id: str,
        doctor_id: str,
        start_time: datetime,
        end_time: datetime,
        reason: str | None = None,
    ) -> Appointment:
        """Create a new appointment record with status ``confirmed``."""
        appointment = Appointment(
            tenant_id=uuid.UUID(tenant_id),
            patient_id=uuid.UUID(patient_id),
            doctor_id=uuid.UUID(doctor_id),
            start_time=start_time,
            end_time=end_time,
            reason=reason,
            status=AppointmentStatus.confirmed,
        )
        self._db.add(appointment)
        await self._db.flush()
        await self._db.refresh(appointment)
        return appointment

    async def update_appointment_status(
        self,
        appointment_id: str,
        status: AppointmentStatus,
    ) -> None:
        """Update the status of an appointment."""
        stmt = (
            update(Appointment)
            .where(Appointment.id == uuid.UUID(appointment_id))
            .values(status=status)
        )
        await self._db.execute(stmt)
        await self._db.flush()

    async def get_appointment_by_id(
        self,
        appointment_id: str,
    ) -> Appointment | None:
        """Return a single appointment by its ID, or ``None``."""  # noqa: D402
        stmt = select(Appointment).where(
            Appointment.id == uuid.UUID(appointment_id),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
