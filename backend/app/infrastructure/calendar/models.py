# DTOs re-exported from domain interfaces.
# The canonical definition lives in domain/interfaces/calendar.py
# so that the port contract is self-contained.
#
# Infrastructure-specific DTOs (API request/response bodies) should
# be placed here as they grow beyond simple re-exports.

from app.domain.interfaces.calendar import AvailableSlot, ConnectionStatus  # noqa: F401
