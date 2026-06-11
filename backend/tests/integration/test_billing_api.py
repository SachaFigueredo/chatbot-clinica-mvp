"""Integration tests for the Billing API endpoints.

Routes under test:
- ``POST /api/v1/billing/checkout`` — create MP preapproval
- ``GET /api/v1/billing/status`` — current billing status
- ``POST /api/v1/billing/cancel`` — cancel subscription

Privacy: all endpoints require authentication (any tenant user).
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.infrastructure.database.models.tenant import Tenant
from app.infrastructure.database.models.user import User
from app.domain.enums import TenantPlan, TenantStatus, UserRole
from app.domain.services.auth_service import AuthService


CHECKOUT_URL = "/api/v1/billing/checkout"
STATUS_URL = "/api/v1/billing/status"
CANCEL_URL = "/api/v1/billing/cancel"


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def subscription_tenant(db_session) -> Tenant:
    """Tenant with an active subscription (plan=subscription)."""
    tenant = Tenant(
        name="Subscribed Clinic",
        slug="subscribed-clinic",
        phone_number="541111111130",
        status=TenantStatus.active,
        plan=TenantPlan.subscription,
        trial_ends_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def subscription_user(db_session, subscription_tenant) -> User:
    """User belonging to the subscription tenant."""
    user = User(
        tenant_id=subscription_tenant.id,
        email="subscribed@test.com",
        password_hash=AuthService.hash_password("password"),
        name="Subscribed User",
        role=UserRole.recepcionista,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
def subscription_token(subscription_user, subscription_tenant) -> str:
    return AuthService.create_access_token(
        str(subscription_user.id), str(subscription_tenant.id)
    )


# ---------------------------------------------------------------------------
# POST /billing/checkout
# ---------------------------------------------------------------------------


class TestBillingCheckout:
    """POST /api/v1/billing/checkout — create MP preapproval."""

    async def test_checkout_with_active_subscription_returns_409(
        self, async_client, subscription_token
    ):
        """Task 6.4: A tenant with active subscription gets 409 Conflict."""
        resp = await async_client.post(
            CHECKOUT_URL,
            headers=_auth_headers(subscription_token),
        )
        assert resp.status_code == 409, (
            f"Expected 409 for active sub, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# GET /billing/status
# ---------------------------------------------------------------------------


class TestBillingStatus:
    """GET /api/v1/billing/status — current billing info."""

    async def test_status_returns_plan_and_trial_info(
        self, async_client, auth_headers, test_tenant
    ):
        """A trial tenant sees plan, status, and trial days remaining."""
        resp = await async_client.get(
            STATUS_URL,
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "plan" in data
        assert "status" in data
        assert "days_remaining" in data
        assert data["plan"] == (test_tenant.plan.value if hasattr(test_tenant.plan, "value") else test_tenant.plan)


# ---------------------------------------------------------------------------
# POST /billing/cancel
# ---------------------------------------------------------------------------


class TestBillingCancel:
    """POST /api/v1/billing/cancel — cancel subscription."""

    async def test_cancel_sets_cancelled_status(
        self, async_client, auth_headers, test_tenant, db_session
    ):
        """Cancelling sets plan=cancelled and status=suspended."""
        resp = await async_client.post(
            CANCEL_URL,
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "cancelled"

        # Verify DB state
        await db_session.refresh(test_tenant)
        assert test_tenant.plan == TenantPlan.cancelled
        assert test_tenant.status == TenantStatus.suspended
