from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.patient import Patient


class PatientRepo:
    """Repository for Patient model database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_or_create_patient(
        self,
        tenant_id: str,
        phone_number: str,
        name: str | None = None,
    ) -> Patient:
        """Return an existing patient by tenant + phone, or create a new one."""
        existing = await self.get_patient_by_phone(tenant_id, phone_number)
        if existing is not None:
            return existing

        patient = Patient(
            tenant_id=uuid.UUID(tenant_id),
            phone_number=phone_number,
            name=name,
        )
        self._db.add(patient)
        await self._db.flush()
        await self._db.refresh(patient)
        return patient

    async def get_patient_by_phone(
        self,
        tenant_id: str,
        phone_number: str,
    ) -> Patient | None:
        """Look up a patient by tenant and phone number."""
        stmt = select(Patient).where(
            Patient.tenant_id == uuid.UUID(tenant_id),
            Patient.phone_number == phone_number,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_patient(
        self,
        patient_id: str,
        **kwargs: Any,
    ) -> None:
        """Update one or more fields on a patient record."""
        stmt = select(Patient).where(Patient.id == uuid.UUID(patient_id))
        result = await self._db.execute(stmt)
        patient = result.scalar_one_or_none()
        if patient is None:
            return
        for key, value in kwargs.items():
            setattr(patient, key, value)
        self._db.add(patient)
        await self._db.flush()
