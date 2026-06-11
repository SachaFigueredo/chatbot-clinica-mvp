"""Unit tests for the CurrentSuperAdmin dependency.

Tests the get_current_super_admin function logic directly.
"""

import pytest
from fastapi import HTTPException

from app.domain.enums import UserRole
from app.api.deps import get_current_super_admin


class FakeUser:
    """Minimal fake user for testing the dependency."""
    def __init__(self, role: UserRole):
        self.role = role


class TestCurrentSuperAdmin:
    """CurrentSuperAdmin allows only super_admin users."""

    async def test_super_admin_allowed(self):
        """A user with role=super_admin passes through."""
        user = FakeUser(role=UserRole.super_admin)
        result = await get_current_super_admin(user)
        assert result is user

    async def test_admin_denied(self):
        """A user with role=admin gets 403."""
        user = FakeUser(role=UserRole.admin)
        with pytest.raises(HTTPException) as exc:
            await get_current_super_admin(user)
        assert exc.value.status_code == 403

    async def test_recepcionista_denied(self):
        """A user with role=recepcionista gets 403."""
        user = FakeUser(role=UserRole.recepcionista)
        with pytest.raises(HTTPException) as exc:
            await get_current_super_admin(user)
        assert exc.value.status_code == 403
