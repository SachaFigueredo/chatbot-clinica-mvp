"""Unit tests for domain enums.

Tests cover the enum values used across the application.
New billing/enum values are tested here.
"""

from app.domain.enums import TenantPlan, TenantStatus, UserRole


class TestTenantPlan:
    """TenantPlan defines the subscription tier for a tenant."""

    def test_existing_values_preserved(self):
        """Original plan values still exist after extension."""
        assert TenantPlan.basic is not None
        assert TenantPlan.professional is not None
        assert TenantPlan.premium is not None

    def test_trial_value_added(self):
        """TenantPlan now includes trial for new registrations."""
        assert TenantPlan.trial == "trial"

    def test_subscription_value_added(self):
        """TenantPlan now includes subscription for paying tenants."""
        assert TenantPlan.subscription == "subscription"

    def test_cancelled_value_added(self):
        """TenantPlan now includes cancelled for former subscribers."""
        assert TenantPlan.cancelled == "cancelled"


class TestUserRole:
    """UserRole defines the permission level for a user."""

    def test_existing_values_preserved(self):
        """Original role values still exist after extension."""
        assert UserRole.admin is not None
        assert UserRole.recepcionista is not None

    def test_super_admin_value_added(self):
        """UserRole now includes super_admin for SaaS owner."""
        assert UserRole.super_admin == "super_admin"


class TestTenantStatus:
    """TenantStatus — unchanged. This proves we didn't break existing enums."""

    def test_values_preserved(self):
        assert TenantStatus.active == "active"
        assert TenantStatus.suspended == "suspended"
        assert TenantStatus.cancelled == "cancelled"
