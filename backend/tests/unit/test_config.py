"""Unit tests for the Settings config object.

Verifies new Mercado Pago and super admin config vars exist.
"""

from app.config import settings


class TestConfigMercadoPago:
    """Mercado Pago configuration vars."""

    def test_mp_access_token_exists(self):
        """Settings has mp_access_token (defaults to empty)."""
        assert hasattr(settings, "mp_access_token")
        assert settings.mp_access_token is None or isinstance(settings.mp_access_token, str)

    def test_mp_webhook_secret_exists(self):
        """Settings has mp_webhook_secret (defaults to empty)."""
        assert hasattr(settings, "mp_webhook_secret")
        assert settings.mp_webhook_secret is None or isinstance(settings.mp_webhook_secret, str)

    def test_mp_notification_url_exists(self):
        """Settings has mp_notification_url (defaults to empty)."""
        assert hasattr(settings, "mp_notification_url")
        assert settings.mp_notification_url is None or isinstance(settings.mp_notification_url, str)


class TestConfigSuperAdmin:
    """Super admin seed configuration vars."""

    def test_super_admin_email_exists(self):
        """Settings has super_admin_email (defaults to empty)."""
        assert hasattr(settings, "super_admin_email")
        assert settings.super_admin_email is None or isinstance(settings.super_admin_email, str)

    def test_super_admin_password_exists(self):
        """Settings has super_admin_password (defaults to empty)."""
        assert hasattr(settings, "super_admin_password")
        assert settings.super_admin_password is None or isinstance(settings.super_admin_password, str)
