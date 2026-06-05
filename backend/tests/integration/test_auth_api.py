"""Integration tests for the Auth API endpoints.

Routes under test:
- ``POST /api/v1/auth/register``
- ``POST /api/v1/auth/login``
- ``POST /api/v1/auth/magic-link/request``
- ``POST /api/v1/auth/magic-link/verify``
"""

from __future__ import annotations

import pytest


# =========================================================================
# Register
# =========================================================================


class TestRegister:
    REGISTER_URL = "/api/v1/auth/register"

    async def test_register_success(self, async_client, test_tenant):
        """A valid registration returns a JWT and creates a user."""
        body = {
            "tenant_slug": test_tenant.slug,
            "email": "newuser@test.com",
            "password": "secure-pass-123",
            "name": "New User",
        }
        resp = await async_client.post(self.REGISTER_URL, json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "access_token" in data
        assert "user_id" in data
        assert "tenant_id" in data
        assert data["tenant_id"] == str(test_tenant.id)

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
