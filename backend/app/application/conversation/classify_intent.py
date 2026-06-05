from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.llm import LLMProvider, IntentResult
from app.infrastructure.llm.intent_classifier import IntentClassifier
from app.infrastructure.database.models.clinic_config import ClinicConfig
from app.infrastructure.database.models.tenant import Tenant

logger = logging.getLogger(__name__)


class ClassifyIntentService:
    """Application service that loads clinic context and classifies
    conversation intent using the LLM-based ``IntentClassifier``.

    This is the glue between the database layer (clinic config, tenant)
    and the intent classifier domain service.
    """

    def __init__(self, db: AsyncSession, llm_provider: LLMProvider) -> None:
        self._db = db
        self._classifier = IntentClassifier(llm_provider)

    async def classify(
        self,
        tenant_id: str,
        conversation_history: list[dict[str, str]],
        patient_message: str,
    ) -> IntentResult:
        """Load clinic context and classify the patient's message.

        Args:
            tenant_id: The tenant UUID string.
            conversation_history: Previous messages in the conversation
                (without the current message). Each entry has
                ``role`` (``"user" | "assistant"``) and ``content``.
            patient_message: The current message text from the patient.

        Returns:
            An ``IntentResult`` with the classified intent and response.
        """
        # --- 1. Load clinic context ---
        clinic_context = await self._build_clinic_context(tenant_id)

        # --- 2. Build the full history with current message ---
        full_history = list(conversation_history)
        full_history.append({"role": "user", "content": patient_message})

        # --- 3. Classify ---
        result = await self._classifier.classify(full_history, clinic_context)

        return result

    async def _build_clinic_context(
        self, tenant_id: str
    ) -> dict[str, Any]:
        """Load clinic configuration and tenant info for context building."""
        # Load tenant info.
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await self._db.execute(stmt)
        tenant = result.scalar_one_or_none()

        # Load clinic config.
        stmt = select(ClinicConfig).where(
            ClinicConfig.tenant_id == tenant_id
        )
        result = await self._db.execute(stmt)
        config = result.scalar_one_or_none()

        clinic_name = tenant.name if tenant else "la clínica"
        business_hours_display = "Consultar horarios de atención"

        if config:
            if config.business_hours:
                try:
                    hours = config.business_hours
                    lines = []
                    day_names = {
                        "monday": "Lunes",
                        "tuesday": "Martes",
                        "wednesday": "Miércoles",
                        "thursday": "Jueves",
                        "friday": "Viernes",
                        "saturday": "Sábado",
                        "sunday": "Domingo",
                    }
                    for eng_day, span_day in day_names.items():
                        day_hours = hours.get(eng_day, {})
                        if day_hours:
                            start = day_hours.get("start", "")
                            end = day_hours.get("end", "")
                            lines.append(f"{span_day}: {start} - {end}")
                    if lines:
                        business_hours_display = " | ".join(lines)
                except Exception:
                    business_hours_display = str(config.business_hours)

        return {
            "clinic_name": clinic_name,
            "address": config.address if config else "No especificada",
            "business_hours": business_hours_display,
            "phone": config.phone if config else "No especificado",
            "prices": "Consultar directamente con la clínica",
        }
