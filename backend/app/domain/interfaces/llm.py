from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentResult:
    """Result of classifying a user's intent from a conversation message."""

    intent: str
    """One of: agendar, consultar_turno, reprogramar, cancelar, faq, humano, saludo, desconocido."""

    confidence: float
    """Confidence score from 0.0 to 1.0."""

    message: str
    """The bot's response message to send to the patient."""

    params: dict[str, Any] = field(default_factory=dict)
    """Extracted parameters such as dates, doctor names, etc."""

    is_emergency: bool = False
    """Whether the message was flagged as an emergency / medical query."""


class LLMProvider(ABC):
    """Abstract port for Large Language Model interactions.

    Implementations wrap an external LLM service (OpenAI, Anthropic, etc.)
    and provide chat completion capabilities.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
    ) -> str:
        """Send a chat completion request and return the response text.

        Args:
            messages: Conversation history in OpenAI format
                      ``[{"role": "system"|"user"|"assistant", "content": "..."}]``.
            temperature: Sampling temperature (default 0.1 for consistent output).

        Returns:
            The model's response text.

        Raises:
            ConnectionError: If the LLM service is unavailable.
            TimeoutError: If the request exceeds the timeout.
        """
        ...
