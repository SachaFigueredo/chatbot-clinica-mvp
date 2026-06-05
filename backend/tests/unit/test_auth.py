"""Unit tests for the ``AuthService`` domain service.

Tests cover:
- Password hashing and verification
- Access token creation and decoding
- Magic link token creation and verification
- Token expiry and invalid signatures
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import settings
from app.domain.services.auth_service import AuthService


class TestPasswordHashing:
    def test_hash_and_verify(self):
        """A hashed password can be verified with the original."""
        pw = "secure-password-123"
        hashed = AuthService.hash_password(pw)
        assert hashed != pw
        assert AuthService.verify_password(pw, hashed) is True

    def test_wrong_password_fails(self):
        """A wrong password does not verify."""
        hashed = AuthService.hash_password("correct-pw")
        assert AuthService.verify_password("wrong-pw", hashed) is False

    def test_hash_is_different_each_time(self):
        """Each call to hash_password produces a different bcrypt salt."""
        pw = "password"
        h1 = AuthService.hash_password(pw)
        h2 = AuthService.hash_password(pw)
        assert h1 != h2


class TestAccessToken:
    def test_create_and_decode(self):
        """A token created by AuthService can be decoded."""
        token = AuthService.create_access_token("user-1", "tenant-1")
        payload = AuthService.decode_access_token(token)
        assert payload["sub"] == "user-1"
        assert payload["tenant_id"] == "tenant-1"

    def test_decode_invalid_signature(self):
        """A token with a bad signature raises jwt.PyJWTError."""
        bad_token = jwt.encode(
            {"sub": "x", "tenant_id": "y"},
            "wrong-secret",
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(jwt.PyJWTError):
            AuthService.decode_access_token(bad_token)

    def test_decode_expired_token(self):
        """An expired token raises jwt.ExpiredSignatureError (which is a PyJWTError)."""
        now = datetime.now(timezone.utc)
        expired_payload = {
            "sub": "user-1",
            "tenant_id": "tenant-1",
            "iat": now - timedelta(hours=48),
            "exp": now - timedelta(hours=24),
        }
        expired = jwt.encode(
            expired_payload,
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(jwt.PyJWTError):
            AuthService.decode_access_token(expired)

    def test_malformed_token(self):
        """A completely invalid string raises jwt.PyJWTError."""
        with pytest.raises(jwt.PyJWTError):
            AuthService.decode_access_token("not-a-jwt-token")


class TestMagicLinkToken:
    def test_create_and_verify(self):
        """A magic link token can be created and verified."""
        token = AuthService.create_magic_link_token("user@test.com", "tenant-1")
        payload = AuthService.verify_magic_link_token(token)
        assert payload is not None
        assert payload["email"] == "user@test.com"
        assert payload["tenant_id"] == "tenant-1"
        assert payload["purpose"] == "magic_link"

    def test_verify_wrong_purpose(self):
        """A regular JWT should not pass as a magic link token (wrong purpose)."""
        token = AuthService.create_access_token("user-1", "tenant-1")
        payload = AuthService.verify_magic_link_token(token)
        assert payload is None  # purpose check fails

    def test_verify_expired(self):
        """An expired magic link returns None."""
        now = datetime.now(timezone.utc)
        payload = {
            "email": "user@test.com",
            "tenant_id": "tenant-1",
            "purpose": "magic_link",
            "iat": now - timedelta(hours=1),
            "exp": now - timedelta(minutes=30),
        }
        expired = jwt.encode(
            payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
        )
        result = AuthService.verify_magic_link_token(expired)
        assert result is None

    def test_verify_invalid_token(self):
        """A garbage string returns None."""
        assert AuthService.verify_magic_link_token("garbage") is None
