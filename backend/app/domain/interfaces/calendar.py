from abc import ABC, abstractmethod
from datetime import datetime, date


class AvailableSlot:
    """A free time slot returned by the calendar provider."""

    def __init__(self, start_time: datetime, end_time: datetime) -> None:
        self.start_time = start_time
        self.end_time = end_time


class ConnectionStatus:
    """Status of a doctor's calendar connection."""

    def __init__(
        self,
        connected: bool,
        calendar_email: str | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        self.connected = connected
        self.calendar_email = calendar_email
        self.expires_at = expires_at


class CalendarProvider(ABC):
    """Abstract port for calendar integration.

    Implementations provide OAuth 2.0 connection, availability lookup,
    event creation, and event deletion against a remote calendar service.
    """

    @abstractmethod
    async def get_auth_url(self, doctor_id: str | None = None) -> str:
        """Return the Google OAuth 2.0 consent-page URL for the given doctor."""
        ...

    @abstractmethod
    async def handle_callback(self, code: str, doctor_id: str | None = None) -> None:
        """Exchange the OAuth authorization code for tokens and persist them."""
        ...

    @abstractmethod
    async def get_available_slots(
        self,
        doctor_id: str | None,
        day: date,
        duration_minutes: int,
    ) -> list[AvailableSlot]:
        """Return free slots for a given date respecting business hours and existing events."""
        ...

    @abstractmethod
    async def create_event(
        self,
        doctor_id: str | None,
        patient_name: str,
        patient_phone: str,
        reason: str | None,
        start_time: datetime,
        end_time: datetime,
    ) -> str:
        """Create a calendar event and return its event ID."""
        ...

    @abstractmethod
    async def delete_event(self, doctor_id: str | None, event_id: str) -> None:
        """Delete a calendar event by its ID."""
        ...

    @abstractmethod
    async def get_connection_status(self, doctor_id: str | None) -> ConnectionStatus:
        """Return the current connection status for the given doctor."""
        ...

    @abstractmethod
    async def disconnect(self, doctor_id: str | None) -> None:
        """Remove stored tokens and disconnect the calendar."""
        ...
