"""Integration tests for the Auth API endpoints.

Routes under test:
- ``POST /api/v1/auth/register``
- ``POST /api/v1/auth/login``
- ``POST /api/v1/auth/magic-link/request``
- ``POST /api/v1/auth/magic-link/verify``
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

import pytest

from sqlalchemy import select

from app.infrastructure.database.models.tenant import Tenant
from app.domain.enums import TenantPlan


# =========================================================================
# Register
# =========================================================================


class TestRegister:
    REGISTER_URL = "/api/v1/auth/register"

    async def test_register_success(self, async_client):
        """A valid registration creates tenant+user and returns a JWT."""
        body = {
            "email": "newuser@test.com",
            "password": "secure-pass-123",
            "name": "New User",
            "clinic_name": "Test Clinic",
        }
        resp = await async_client.post(self.REGISTER_URL, json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "newuser@test.com"
        assert data["user"]["name"] == "New User"
        assert data["user"]["role"] == "admin"
        assert data["user"]["tenant_id"] is not None

    async def test_register_with_tenant_slug(
        self, async_client, test_tenant, db_session
    ):
        """Registering with an existing tenant_slug adds a recepcionista.

        The existing tenant's plan is NOT changed to trial.
        """
        original_plan = test_tenant.plan

        body = {
            "tenant_slug": test_tenant.slug,
            "email": "staff@test.com",
            "password": "secure-pass-123",
            "name": "Staff User",
        }
        resp = await async_client.post(self.REGISTER_URL, json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["user"]["role"] == "recepcionista"
        assert str(data["user"]["tenant_id"]) == str(test_tenant.id)

        # Verify existing tenant's plan is unchanged
        result = await db_session.execute(
            select(Tenant).where(Tenant.id == test_tenant.id)
        )
        tenant = result.scalar_one()
        assert tenant.plan == original_plan, (
            f"Existing tenant plan changed from {original_plan} to {tenant.plan}"
        )

    async def test_register_duplicate_email(
        self, async_client, test_tenant, test_user
    ):
        """A duplicate email within the same tenant returns 409."""
        body = {
            "tenant_slug": test_tenant.slug,
            "email": test_user.email,
            "password": "another-pass",
            "name": "Duplicate User",
        }
        resp = await async_client.post(self.REGISTER_URL, json=body)
        assert resp.status_code == 409, resp.text

    async def test_register_tenant_not_found(self, async_client):
        """Registering for a non-existent tenant returns 404."""
        body = {
            "tenant_slug": "non-existent-slug",
            "email": "test@test.com",
            "password": "pass",
            "name": "Test",
        }
        resp = await async_client.post(self.REGISTER_URL, json=body)
        assert resp.status_code == 404, resp.text

    async def test_register_creates_trial_tenant(self, async_client, db_session):
        """New tenant registration creates a trial tenant with trial_ends_at=now+7d."""
        from datetime import timezone as tz_mod

        body = {
            "email": "trial@test.com",
            "password": "secure-pass-123",
            "name": "Trial User",
            "clinic_name": "Trial Clinic",
        }
        resp = await async_client.post(self.REGISTER_URL, json=body)
        assert resp.status_code == 200, resp.text

        # Extract the created tenant_id from the response
        tenant_id = resp.json()["user"]["tenant_id"]

        # Fetch the tenant from DB
        result = await db_session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        assert tenant is not None

        # Must be trial plan
        assert tenant.plan == TenantPlan.trial, f"Expected trial, got {tenant.plan}"

        # Must have trial_ends_at set ~7 days from now
        assert tenant.trial_ends_at is not None
        now = datetime.now(tz_mod.utc)
        # SQLite may return naive datetime; make comparison robust
        trial_end = tenant.trial_ends_at
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=tz_mod.utc)
        expected_lower = now + timedelta(days=6, hours=23)
        expected_upper = now + timedelta(days=7, hours=1)
        assert expected_lower <= trial_end <= expected_upper, (
            f"trial_ends_at {trial_end} not within 7d±1h of {now}"
        )

        # Must be active
        assert tenant.status == "active"


# =========================================================================
# Login
# =========================================================================


class TestLogin:
    LOGIN_URL = "/api/v1/auth/login"

    async def test_login_success(self, async_client, test_user):
        """Valid credentials return a JWT and user/tenant IDs."""
        body = {"email": test_user.email, "password": "test-password"}
        resp = await async_client.post(self.LOGIN_URL, json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "access_token" in data
        assert data["user_id"] == str(test_user.id)
        assert data["tenant_id"] == str(test_user.tenant_id)

    async def test_login_wrong_password(self, async_client, test_user):
        """Wrong password returns 401."""
        body = {"email": test_user.email, "password": "wrong-password"}
        resp = await async_client.post(self.LOGIN_URL, json=body)
        assert resp.status_code == 401, resp.text

    async def test_login_user_not_found(self, async_client):
        """Non-existent email returns 401."""
        body = {"email": "nobody@nowhere.com", "password": "pass"}
        resp = await async_client.post(self.LOGIN_URL, json=body)
        assert resp.status_code == 401, resp.text


# =========================================================================
# Magic Link — Request
# =========================================================================


class TestMagicLinkRequest:
    REQUEST_URL = "/api/v1/auth/magic-link/request"

    async def test_magic_link_request_success(
        self, async_client, test_tenant, test_user
    ):
        """A valid magic link request returns a token."""
        body = {
            "email": test_user.email,
            "tenant_slug": test_tenant.slug,
        }
        resp = await async_client.post(self.REQUEST_URL, json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "token" in data
        assert data["token"]  # non-empty

    async def test_magic_link_request_tenant_not_found(
        self, async_client, test_user
    ):
        """A non-existent tenant slug returns 404."""
        body = {
            "email": test_user.email,
            "tenant_slug": "no-such-tenant",
        }
        resp = await async_client.post(self.REQUEST_URL, json=body)
        assert resp.status_code == 404, resp.text

    async def test_magic_link_request_user_not_found(
        self, async_client, test_tenant
    ):
        """A non-existent user returns 404."""
        body = {
            "email": "nobody@test.com",
            "tenant_slug": test_tenant.slug,
        }
        resp = await async_client.post(self.REQUEST_URL, json=body)
        assert resp.status_code == 404, resp.text


# =========================================================================
# Magic Link — Verify
# =========================================================================


class TestMagicLinkVerify:
    VERIFY_URL = "/api/v1/auth/magic-link/verify"

    async def test_magic_link_verify_success(
        self, async_client, test_tenant, test_user
    ):
        """A valid magic link token exchanges for a JWT."""
        from app.domain.services.auth_service import AuthService

        token = AuthService.create_magic_link_token(
            test_user.email, str(test_tenant.id)
        )
        body = {"token": token}
        resp = await async_client.post(self.VERIFY_URL, json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "access_token" in data
        assert data["user_id"] == str(test_user.id)

    async def test_magic_link_verify_invalid_token(self, async_client):
        """An invalid/expired token returns 401."""
        body = {"token": "invalid-token-value"}
        resp = await async_client.post(self.VERIFY_URL, json=body)
        assert resp.status_code == 401, resp.text
