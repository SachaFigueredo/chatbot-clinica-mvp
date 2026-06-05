from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from openai import AsyncOpenAI
from openai import (
    APIError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)

from app.domain.interfaces.llm import LLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.1
TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 1  # Retry once on 5xx


class OpenAIClient(LLMProvider):
    """OpenAI API adapter implementing LLMProvider.

    Wraps the ``openai`` Python SDK v1+ (async client) to provide chat
    completion capabilities with error handling, retries, and timeouts.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            timeout=TIMEOUT_SECONDS,
            max_retries=0,  # We handle retries ourselves
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        """Send a chat completion request with retry-on-5xx logic.

        Args:
            messages: OpenAI-format message list.
            temperature: Sampling temperature.

        Returns:
            The model's response string.

        Raises:
            ConnectionError: If the service is unavailable after retries.
            TimeoutError: If the request exceeds the timeout.
        """
        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 2):  # initial + MAX_RETRIES
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                )
                content = response.choices[0].message.content or ""
                return content

            except RateLimitError as exc:
                logger.warning(
                    "OpenAI rate limited (attempt %d/%d): %s",
                    attempt,
                    MAX_RETRIES + 1,
                    exc,
                )
                last_exception = exc
                if attempt <= MAX_RETRIES:
                    await asyncio.sleep(2.0 * attempt)
                    continue
                raise ConnectionError(
                    "Rate limit exceeded. Please try again later."
                ) from exc

            except APITimeoutError as exc:
                logger.warning(
                    "OpenAI timeout (attempt %d/%d)",
                    attempt,
                    MAX_RETRIES + 1,
                )
                last_exception = exc
                if attempt <= MAX_RETRIES:
                    continue
                raise TimeoutError(
                    "LLM request timed out after retries."
                ) from exc

            except InternalServerError as exc:
                logger.warning(
                    "OpenAI 5xx error (attempt %d/%d): %s",
                    attempt,
                    MAX_RETRIES + 1,
                    exc,
                )
                last_exception = exc
                if attempt <= MAX_RETRIES:
                    await asyncio.sleep(1.0 * attempt)
                    continue
                raise ConnectionError(
                    "LLM service temporarily unavailable."
                ) from exc

            except APIError as exc:
                logger.error("OpenAI API error: %s", exc)
                last_exception = exc
                if attempt <= MAX_RETRIES and (
                    getattr(exc, "status_code", 0) or 0
                ) >= 500:
                    await asyncio.sleep(1.0 * attempt)
                    continue
                raise ConnectionError(
                    f"LLM API error: {exc}"
                ) from exc

        # Should not reach here, but satisfy the return type.
        raise ConnectionError(
            f"LLM request failed after {MAX_RETRIES + 1} attempts."
        ) from last_exception

    async def classify_intent(
        self,
        conversation_history: list[dict[str, str]],
        clinic_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Convenience method: build messages array and call chat for intent
        classification, returning the parsed JSON response.

        This can be used directly or via IntentClassifier for additional
        logic (confidence thresholds, emergency detection, etc.).

        Returns:
            Parsed JSON dict with keys ``intent``, ``confidence``,
            ``message``, ``params``.
        """
        messages = self._build_classification_messages(
            conversation_history, clinic_context
        )
        raw = await self.chat(messages)

        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Failed to parse LLM response as JSON: %.200s", raw
            )
            return {
                "intent": "desconocido",
                "confidence": 0.0,
                "message": "Disculpá, no entendí tu mensaje. ¿Podrías reformularlo?",
                "params": {},
            }

        return parsed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_classification_messages(
        self,
        conversation_history: list[dict[str, str]],
        clinic_context: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Build the messages array for intent classification.

        System prompt is constructed from clinic context; conversation
        history is appended as user/assistant turns.
        """
        system_prompt = self._render_system_prompt(clinic_context)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(conversation_history)
        return messages

    def _render_system_prompt(
        self, ctx: dict[str, Any]
    ) -> str:
        """Render the system prompt template with clinic context data."""
        from app.infrastructure.llm.prompts import SYSTEM_PROMPT_TEMPLATE

        clinic_name = ctx.get("clinic_name", "la clínica")
        address = ctx.get("address", "No especificada")
        business_hours = ctx.get("business_hours", "No especificados")
        phone = ctx.get("phone", "No especificado")
        prices = ctx.get("prices", "No especificados")

        return SYSTEM_PROMPT_TEMPLATE.format(
            clinic_name=clinic_name,
            address=address,
            business_hours=business_hours,
            phone=phone,
            prices=prices,
        )
