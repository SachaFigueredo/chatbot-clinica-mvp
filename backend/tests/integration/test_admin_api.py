"""Integration tests for the Super Admin API endpoints.

Routes under test:
- ``GET /api/v1/admin/tenants`` — list tenants with filters
- ``POST /api/v1/admin/tenants/{id}/suspend`` — suspend a tenant
- ``POST /api/v1/admin/tenants/{id}/activate`` — activate a tenant
- ``POST /api/v1/admin/tenants/{id}/mark-paid`` — manual payment override

Privacy: all endpoints require super_admin role.
"""

from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio

from app.infrastructure.database.models.tenant import Tenant
from app.infrastructure.database.models.user import User
from app.domain.enums import TenantPlan, TenantStatus, UserRole
from app.domain.services.auth_service import AuthService

TENANTS_LIST_URL = "/api/v1/admin/tenants"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def super_admin_user(db_session, test_tenant) -> User:
    """Create a super admin user for testing."""
    user = User(
        tenant_id=test_tenant.id,
        email="superadmin@test.com",
        password_hash=AuthService.hash_password("super-password"),
        name="Super Admin",
        role=UserRole.super_admin,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
def super_admin_token(super_admin_user, test_tenant) -> str:
    return AuthService.create_access_token(
        str(super_admin_user.id), str(test_tenant.id)
    )


@pytest_asyncio.fixture
def super_admin_headers(super_admin_token, test_tenant) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {super_admin_token}",
        "X-Tenant-Slug": test_tenant.slug,
    }


@pytest_asyncio.fixture
async def suspended_tenant(db_session) -> Tenant:
    """A suspended tenant for testing admin actions."""
    tenant = Tenant(
        name="Suspended Clinic",
        slug="suspended-clinic",
        phone_number="541111111140",
        status=TenantStatus.suspended,
        plan=TenantPlan.trial,
        trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# GET /admin/tenants
# ---------------------------------------------------------------------------


class TestAdminTenantsList:
    """GET /api/v1/admin/tenants — list with optional filters."""

    async def test_non_super_admin_gets_403(
        self, async_client, auth_headers
    ):
        """Task 6.6: A non-super_admin user gets 403."""
        resp = await async_client.get(
            TENANTS_LIST_URL,
            headers=auth_headers,
        )
        assert resp.status_code == 403, (
            f"Expected 403, got {resp.status_code}: {resp.text}"
        )

    async def test_super_admin_lists_tenants(
        self, async_client, super_admin_headers
    ):
        """Super admin can list all tenants."""
        resp = await async_client.get(
            TENANTS_LIST_URL,
            headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "id" in data[0]
        assert "name" in data[0]
        assert "plan" in data[0]
        assert "status" in data[0]


# ---------------------------------------------------------------------------
# POST /admin/tenants/{id}/suspend
# ---------------------------------------------------------------------------


class TestAdminSuspend:
    """POST /api/v1/admin/tenants/{id}/suspend."""

    async def test_suspend_tenant(
        self, async_client, super_admin_headers, test_tenant, db_session
    ):
        """Super admin can suspend an active tenant."""
        url = f"{TENANTS_LIST_URL}/{test_tenant.id}/suspend"
        resp = await async_client.post(url, headers=super_admin_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "suspended"

        await db_session.refresh(test_tenant)
        assert test_tenant.status == TenantStatus.suspended
        assert test_tenant.suspended_at is not None


# ---------------------------------------------------------------------------
# POST /admin/tenants/{id}/activate
# ---------------------------------------------------------------------------


class TestAdminActivate:
    """POST /api/v1/admin/tenants/{id}/activate."""

    async def test_activate_tenant(
        self, async_client, super_admin_headers, suspended_tenant, db_session
    ):
        """Super admin can activate a suspended tenant with trial extension."""
        url = f"{TENANTS_LIST_URL}/{suspended_tenant.id}/activate"
        resp = await async_client.post(
            url,
            headers=super_admin_headers,
            json={},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "active"
        assert data["trial_ends_at"] is not None

        await db_session.refresh(suspended_tenant)
        assert suspended_tenant.status == TenantStatus.active


# ---------------------------------------------------------------------------
# POST /admin/tenants/{id}/mark-paid
# ---------------------------------------------------------------------------


class TestAdminMarkPaid:
    """POST /api/v1/admin/tenants/{id}/mark-paid."""

    async def test_mark_paid_updates_plan_and_status(
        self, async_client, super_admin_headers, suspended_tenant, db_session
    ):
        """Super admin can manually mark a tenant as paid."""
        url = f"{TENANTS_LIST_URL}/{suspended_tenant.id}/mark-paid"
        resp = await async_client.post(
            url,
            headers=super_admin_headers,
            json={},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["plan"] == "subscription"
        assert data["status"] == "active"

        await db_session.refresh(suspended_tenant)
        assert suspended_tenant.plan == TenantPlan.subscription
        assert suspended_tenant.status == TenantStatus.active
