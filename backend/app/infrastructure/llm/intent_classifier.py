from __future__ import annotations

import json
import logging
from typing import Any

from app.domain.interfaces.llm import LLMProvider, IntentResult
from app.infrastructure.llm.prompts import EMERGENCY_KEYWORDS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD = 0.7
MAX_UNKNOWN_COUNT = 2

VALID_INTENTS = frozenset({
    "agendar",
    "consultar_turno",
    "reprogramar",
    "cancelar",
    "faq",
    "humano",
    "saludo",
    "desconocido",
})


class IntentClassifier:
    """Classifies user intent from conversation messages using an LLM.

    Wraps an ``LLMProvider`` to build the classification prompt, parse
    the response, apply confidence thresholds, detect emergencies, and
    track repeated unknown intents.

    Usage::

        classifier = IntentClassifier(llm_provider)
        result = await classifier.classify(history, clinic_context)
    """

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def classify(
        self,
        conversation_history: list[dict[str, str]],
        clinic_context: dict[str, Any],
    ) -> IntentResult:
        """Classify the latest user message in a conversation.

        Steps:
        1. Build the system prompt with clinic context.
        2. Prepend conversation history.
        3. Call LLM and parse JSON response.
        4. Validate intent is one of the known types.
        5. Apply confidence threshold (``< 0.7`` → ``desconocido``).
        6. Detect emergency keywords / LLM emergency flag.
        7. Return an ``IntentResult``.

        Args:
            conversation_history: Messages in
                ``[{"role": "user"|"assistant", "content": "..."}]`` format.
                The **last** message MUST be the patient's current message.
            clinic_context: Dict with clinic info keys
                (``clinic_name``, ``address``, etc.).

        Returns:
            An ``IntentResult`` with the classified intent and response.
        """
        # --- 1. Build classification messages ---
        messages = self._build_messages(conversation_history, clinic_context)

        # --- 2. Call LLM ---
        try:
            raw = await self._llm.chat(messages)
        except (ConnectionError, TimeoutError) as exc:
            logger.error("LLM call failed during classification: %s", exc)
            return IntentResult(
                intent="desconocido",
                confidence=0.0,
                message="Disculpá, tengo un problema técnico. "
                        "Por favor, intentá de nuevo en un momento.",
            )

        # --- 3. Parse JSON response ---
        parsed = self._parse_response(raw)

        # --- 4. Validate intent ---
        intent = parsed.get("intent", "desconocido")
        if intent not in VALID_INTENTS:
            logger.warning(
                "LLM returned unknown intent '%s', falling back to desconocido",
                intent,
            )
            intent = "desconocido"

        confidence = float(parsed.get("confidence", 0.0))
        message = parsed.get("message", "")
        params = parsed.get("params", {})

        # --- 5. Apply confidence threshold ---
        if confidence < CONFIDENCE_THRESHOLD:
            logger.info(
                "Low confidence %.2f for intent '%s', falling back to desconocido",
                confidence,
                intent,
            )
            intent = "desconocido"
            message = "Disculpá, no entendí bien tu mensaje. ¿Podrías reformularlo?"
            confidence = min(confidence, 0.69)  # Keep actual low confidence

        # --- 6. Detect emergency ---
        is_emergency = self._detect_emergency(
            conversation_history, intent, params, message
        )

        # --- 7. Track unknown count from conversation history ---
        if intent == "desconocido":
            unknown_count = self._count_consecutive_unknown(conversation_history)
            if unknown_count >= MAX_UNKNOWN_COUNT:
                return IntentResult(
                    intent="humano",
                    confidence=confidence,
                    message="Ya intenté varias veces pero no logro entender tu "
                            "consulta. Te paso con recepción así te pueden ayudar mejor.",
                    params=params,
                    is_emergency=is_emergency,
                )

        return IntentResult(
            intent=intent,
            confidence=confidence,
            message=message,
            params=params,
            is_emergency=is_emergency,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        conversation_history: list[dict[str, str]],
        clinic_context: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Build the messages array combining system prompt + history."""
        system_prompt = self._render_system_prompt(clinic_context)
        return [
            {"role": "system", "content": system_prompt},
            *conversation_history,
        ]

    def _render_system_prompt(self, ctx: dict[str, Any]) -> str:
        from app.infrastructure.llm.prompts import SYSTEM_PROMPT_TEMPLATE

        return SYSTEM_PROMPT_TEMPLATE.format(
            clinic_name=ctx.get("clinic_name", "la clínica"),
            address=ctx.get("address", "No especificada"),
            business_hours=ctx.get("business_hours", "No especificados"),
            phone=ctx.get("phone", "No especificado"),
            prices=ctx.get("prices", "No especificados"),
        )

    def _parse_response(self, raw: str) -> dict[str, Any]:
        """Parse the LLM JSON response with fallback."""
        # Try to extract JSON if wrapped in markdown fences.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Extract JSON from code fence.
            lines = cleaned.splitlines()
            start = 0
            for i, line in enumerate(lines):
                if line.startswith("```"):
                    start = i + 1
                    break
            cleaned = "\n".join(
                line for line in lines[start:] if not line.startswith("```")
            )

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        logger.warning(
            "Failed to parse LLM response as JSON: %.200s", raw
        )
        return {
            "intent": "desconocido",
            "confidence": 0.0,
            "message": "Disculpá, no entendí tu mensaje. ¿Podrías reformularlo?",
            "params": {},
        }

    def _detect_emergency(
        self,
        conversation_history: list[dict[str, str]],
        intent: str,
        params: dict[str, Any],
        message: str,
    ) -> bool:
        """Check if the message indicates an emergency or medical query.

        Detection strategies:
        1. LLM returned intent ``emergencia`` (non-standard, explicit flag).
        2. Last user message contains emergency keywords.
        """
        # Check if LLM explicitly flagged it (via params or message content).
        if params.get("is_emergency") or params.get("emergency"):
            return True
        if intent == "emergencia":
            return True

        # Check last user message for emergency keywords.
        if conversation_history:
            last_msg = conversation_history[-1]
            if last_msg.get("role") == "user":
                user_text = last_msg.get("content", "").lower()
                return self._has_emergency_keywords(user_text)

        return False

    def _has_emergency_keywords(self, text: str) -> bool:
        """Check if text contains any emergency keywords."""
        text_lower = text.lower()
        for keyword in EMERGENCY_KEYWORDS:
            if keyword in text_lower:
                logger.info("Emergency keyword detected: '%s'", keyword)
                return True
        return False

    def _count_consecutive_unknown(
        self, conversation_history: list[dict[str, str]]
    ) -> int:
        """Count how many consecutive user messages were classified as
        ``desconocido`` (or had very low confidence) by checking the
        assistant responses stored in history.

        Since the history contains bot responses too, we look at every
        pair of user → assistant messages. If the assistant marked the
        intent as unknown, we count it.
        """
        count = 0
        for msg in reversed(conversation_history):
            if msg.get("role") == "assistant":
                # Check if the assistant response contains a low-confidence
                # classification. We look for the "no entendí" pattern or
                # similar phrasing.
                content = msg.get("content", "")
                if "no entendí" in content.lower() or "reformular" in content.lower():
                    count += 1
                else:
                    break
            elif msg.get("role") == "user":
                continue
        return min(count, MAX_UNKNOWN_COUNT + 1)
