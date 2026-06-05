from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IncomingMessage:
    """A message received from WhatsApp via the Evolution API webhook."""

    from_number: str
    to_number: str
    text: str
    message_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class WhatsAppInstance:
    """Represents a connected WhatsApp instance on Evolution API."""

    instance_name: str
    connection_status: str
    phone_number: str
