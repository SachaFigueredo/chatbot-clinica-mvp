from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.calendar import CalendarProvider, AvailableSlot
from app.infrastructure.database.models.clinic_config import ClinicConfig


class GetAvailableSlots:
    """Use case: retrieve available appointment slots for a doctor on a given date.

    Reads the clinic's configured appointment duration and delegates to
    the calendar provider for the actual slot calculation.
    """

    def __init__(
        self,
        db: AsyncSession,
        calendar_provider: CalendarProvider,
    ) -> None:
        self._db = db
        self._calendar_provider = calendar_provider

    async def execute(
        self,
        tenant_id: str,
        doctor_id: str | None,
        day: date,
    ) -> list[AvailableSlot]:
        """Return free slots for *doctor_id* on *day*.

        Falls back to a 20-minute duration if no ``ClinicConfig`` exists
        for the tenant.
        """
        stmt = select(ClinicConfig).where(ClinicConfig.tenant_id == tenant_id)
        result = await self._db.execute(stmt)
        config = result.scalar_one_or_none()
        duration_minutes = config.appointment_duration_minutes if config else 20

        slots = await self._calendar_provider.get_available_slots(
            doctor_id=doctor_id,
            day=day,
            duration_minutes=duration_minutes,
        )

        return slots
