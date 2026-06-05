"""Unit tests for the IntentClassifier domain service.

Tests cover:
- Classification flow (happy path)
- Low-confidence fallback (threshold < 0.7)
- Unknown intent fallback
- Consecutive unknown → escalate to human
- Emergency keyword detection
- LLM failure (ConnectionError / TimeoutError)
- JSON parsing (raw, markdown-fenced, malformed)
"""

from __future__ import annotations

import pytest

from app.infrastructure.llm.intent_classifier import (
    IntentClassifier,
    CONFIDENCE_THRESHOLD,
    MAX_UNKNOWN_COUNT,
)
from app.domain.interfaces.llm import IntentResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CLINIC_CONTEXT = {
    "clinic_name": "Clínica Test",
    "address": "Av. Siempre Viva 123",
    "business_hours": "Lunes a viernes de 8 a 18h",
    "phone": "541112345678",
    "prices": "Consultar directamente con la clínica",
}

_HISTORY_BASIC = [
    {"role": "user", "content": "Hola"},
    {"role": "assistant", "content": "¡Hola! ¿En qué puedo ayudarte?"},
]


def _make_classifier(mock_llm) -> IntentClassifier:
    """Shortcut to instantiate a classifier with a given mock provider."""
    return IntentClassifier(mock_llm)


def _history_with_unknown(count: int) -> list[dict[str, str]]:
    """Build a conversation history with *count* consecutive unknown intents."""
    history: list[dict[str, str]] = []
    for i in range(count):
        history.append({"role": "user", "content": f"blah blah {i}"})
        history.append(
            {"role": "assistant", "content": "Disculpá, no entendí bien tu mensaje."}
        )
    # Append the current user message
    history.append({"role": "user", "content": "más blah"})
    return history


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_classify_saludo(self, mock_llm_provider):
        """A valid LLM response with high confidence returns the parsed intent."""
        classifier = _make_classifier(mock_llm_provider)
        result = await classifier.classify(_HISTORY_BASIC, _CLINIC_CONTEXT)

        assert result.intent == "saludo"
        assert result.confidence == 0.95
        assert "ayudarte" in result.message
        assert not result.is_emergency

    async def test_classify_appointment(self, mock_llm_provider):
        """A booking intent is correctly parsed."""
        mock_llm_provider.chat.return_value = (
            '{"intent": "agendar", "confidence": 0.92, '
            '"message": "Claro, voy a buscar disponibilidad.", '
            '"params": {"doctor": "Dr. García"}}'
        )
        classifier = _make_classifier(mock_llm_provider)
        result = await classifier.classify(_HISTORY_BASIC, _CLINIC_CONTEXT)

        assert result.intent == "agendar"
        assert result.confidence > 0.9
        assert result.params.get("doctor") == "Dr. García"

    async def test_intent_is_validated(self, mock_llm_provider):
        """An unknown intent string is mapped to ``desconocido``."""
        mock_llm_provider.chat.return_value = (
            '{"intent": "invalid_intent_xyz", "confidence": 0.9, "message": "?"}'
        )
        classifier = _make_classifier(mock_llm_provider)
        result = await classifier.classify(_HISTORY_BASIC, _CLINIC_CONTEXT)
        assert result.intent == "desconocido"


# ---------------------------------------------------------------------------
# Confidence threshold
# ---------------------------------------------------------------------------


class TestConfidenceThreshold:
    async def test_below_threshold_falls_to_unknown(self, mock_llm_provider):
        """Confidence below 0.7 is treated as ``desconocido``."""
        mock_llm_provider.chat.return_value = (
            '{"intent": "saludo", "confidence": 0.45, "message": "Hola!"}'
        )
        classifier = _make_classifier(mock_llm_provider)
        result = await classifier.classify(_HISTORY_BASIC, _CLINIC_CONTEXT)
        assert result.intent == "desconocido"
        assert result.confidence <= 0.69  # clamped


# ---------------------------------------------------------------------------
# Consecutive unknown → human
# ---------------------------------------------------------------------------


class TestConsecutiveUnknown:
    async def test_max_unknown_triggers_human(self, mock_llm_provider):
        """After MAX_UNKNOWN_COUNT consecutive unknowns, intent becomes ``humano``."""
        mock_llm_provider.chat.return_value = (
            '{"intent": "desconocido", "confidence": 0.3, "message": "no entendí"}'
        )
        classifier = _make_classifier(mock_llm_provider)
        history = _history_with_unknown(MAX_UNKNOWN_COUNT + 1)

        result = await classifier.classify(history, _CLINIC_CONTEXT)

        assert result.intent == "humano"
        assert "recepción" in result.message.lower()

    async def test_below_max_stays_unknown(self, mock_llm_provider):
        """Under the limit, unknown stays unknown."""
        mock_llm_provider.chat.return_value = (
            '{"intent": "desconocido", "confidence": 0.3, "message": "no entendí"}'
        )
        classifier = _make_classifier(mock_llm_provider)
        history = _history_with_unknown(MAX_UNKNOWN_COUNT - 1)

        result = await classifier.classify(history, _CLINIC_CONTEXT)
        assert result.intent == "desconocido"


# ---------------------------------------------------------------------------
# Emergency detection
# ---------------------------------------------------------------------------


class TestEmergency:
    async def test_emergency_keyword_detected(self, mock_llm_provider):
        """A user message with emergency keywords is flagged."""
        mock_llm_provider.chat.return_value = (
            '{"intent": "faq", "confidence": 0.85, "message": "..."}'
        )
        classifier = _make_classifier(mock_llm_provider)
        history = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola!"},
            {"role": "user", "content": "Me duele mucho el pecho, es una emergencia"},
        ]

        result = await classifier.classify(history, _CLINIC_CONTEXT)
        assert result.is_emergency is True

    async def test_no_false_positive_for_normal_message(self, mock_llm_provider):
        """Normal messages do NOT trigger emergency flag."""
        classifier = _make_classifier(mock_llm_provider)
        result = await classifier.classify(_HISTORY_BASIC, _CLINIC_CONTEXT)
        assert result.is_emergency is False


# ---------------------------------------------------------------------------
# LLM failures
# ---------------------------------------------------------------------------


class TestLLMFailure:
    async def test_connection_error(self, mock_llm_provider):
        """A ConnectionError from the LLM returns a graceful fallback."""
        mock_llm_provider.chat.side_effect = ConnectionError("API down")
        classifier = _make_classifier(mock_llm_provider)
        result = await classifier.classify(_HISTORY_BASIC, _CLINIC_CONTEXT)

        assert result.intent == "desconocido"
        assert result.confidence == 0.0
        assert "técnico" in result.message.lower()

    async def test_timeout_error(self, mock_llm_provider):
        """A TimeoutError from the LLM returns a graceful fallback."""
        mock_llm_provider.chat.side_effect = TimeoutError("timed out")
        classifier = _make_classifier(mock_llm_provider)
        result = await classifier.classify(_HISTORY_BASIC, _CLINIC_CONTEXT)

        assert result.intent == "desconocido"
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


class TestJSONParsing:
    async def test_plain_json(self, mock_llm_provider):
        """A plain JSON response (no fences) is parsed correctly."""
        mock_llm_provider.chat.return_value = (
            '{"intent": "faq", "confidence": 0.88, "message": "Claro!"}'
        )
        classifier = _make_classifier(mock_llm_provider)
        result = await classifier.classify(_HISTORY_BASIC, _CLINIC_CONTEXT)
        assert result.intent == "faq"

    async def test_markdown_fenced_json(self, mock_llm_provider):
        """JSON wrapped in ``` fences is extracted."""
        mock_llm_provider.chat.return_value = (
            '```json\n{"intent": "cancelar", "confidence": 0.91, '
            '"message": "Claro, voy a cancelar el turno."}\n```'
        )
        classifier = _make_classifier(mock_llm_provider)
        result = await classifier.classify(_HISTORY_BASIC, _CLINIC_CONTEXT)
        assert result.intent == "cancelar"

    async def test_malformed_json(self, mock_llm_provider):
        """Malformed JSON falls back to ``desconocido``."""
        mock_llm_provider.chat.return_value = "this is not json at all"
        classifier = _make_classifier(mock_llm_provider)
        result = await classifier.classify(_HISTORY_BASIC, _CLINIC_CONTEXT)
        assert result.intent == "desconocido"
