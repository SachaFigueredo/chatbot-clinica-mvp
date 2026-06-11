"""Integration tests for the SubscriptionGuard wired into protected routers.

Tests verify that:
- Expired trial + suspended status → 402 on protected routes (e.g., /dashboard)
- Active subscription → 200 on the same route
- Auth routes are exempt (no guard)
"""

from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio

from app.infrastructure.database.models.tenant import Tenant
from app.infrastructure.database.models.user import User
from app.domain.enums import TenantPlan, TenantStatus, UserRole
from app.domain.services.auth_service import AuthService


DASHBOARD_URL = "/api/v1/dashboard/stats"


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def trial_tenant_expired(db_session) -> Tenant:
    """Tenant with an expired trial and suspended status."""
    tenant = Tenant(
        name="Expired Trial",
        slug="expired-trial",
        phone_number="541111111120",
        status=TenantStatus.suspended,
        plan=TenantPlan.trial,
        trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def expired_trial_user(db_session, trial_tenant_expired) -> User:
    """User belonging to the expired trial tenant."""
    user = User(
        tenant_id=trial_tenant_expired.id,
        email="expired@test.com",
        password_hash=AuthService.hash_password("password"),
        name="Expired Trial User",
        role=UserRole.recepcionista,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
def expired_trial_token(expired_trial_user, trial_tenant_expired) -> str:
    return AuthService.create_access_token(
        str(expired_trial_user.id), str(trial_tenant_expired.id)
    )


class TestSubscriptionGuardWired:
    """SubscriptionGuard must be wired into non-exempt routers."""

    async def test_expired_trial_blocked_on_dashboard(
        self, async_client, expired_trial_token
    ):
        """Expired trial tenant gets 402 on a protected route."""
        resp = await async_client.get(
            DASHBOARD_URL,
            headers=_auth_headers(expired_trial_token),
        )
        assert resp.status_code == 402, (
            f"Expected 402, got {resp.status_code}: {resp.text}"
        )

    async def test_active_tenant_allowed_on_dashboard(
        self, async_client, auth_headers
    ):
        """Active basic tenant is allowed on the same route."""
        resp = await async_client.get(
            DASHBOARD_URL,
            headers=auth_headers,
        )
        # May return 200 with data, or 4xx for other reasons, but NOT 402
        assert resp.status_code != 402, resp.text

    async def test_auth_route_exempt(
        self, async_client, expired_trial_token
    ):
        """Auth routes are exempt from the guard — /auth/me should work."""
        resp = await async_client.get(
            "/api/v1/auth/me",
            headers=_auth_headers(expired_trial_token),
        )
        assert resp.status_code == 200, resp.text
