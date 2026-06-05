from abc import ABC, abstractmethod


class MessagingProvider(ABC):
    """Abstract port for messaging (WhatsApp) integration.

    Implementations provide message sending capabilities against a
    messaging gateway such as Evolution API or Twilio.
    """

    @abstractmethod
    async def send_text(self, to: str, text: str) -> str:
        """Send a plain text message to *to* and return the message ID."""
        ...

    @abstractmethod
    async def send_template(
        self, to: str, template_name: str, params: list[str]
    ) -> str:
        """Send a template message to *to* and return the message ID."""
        ...

    @abstractmethod
    async def get_instance_status(self) -> dict:
        """Return the current connection status of the messaging instance."""
        ...
