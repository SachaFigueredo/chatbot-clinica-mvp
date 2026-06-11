"""Unit tests for the SubscriptionGuard dependency logic.

Extracted as a pure function check_subscription_access() to avoid DB mocking.
"""

from datetime import datetime, timezone, timedelta

import pytest

from app.domain.enums import TenantPlan, TenantStatus
from app.api.deps import check_subscription_access


class TestCheckSubscriptionAccess:
    """Pure function that determines if a tenant has access to restricted routes."""

    def test_subscription_active_allowed(self):
        """Paying customer with active status is always allowed."""
        assert check_subscription_access(
            plan=TenantPlan.subscription,
            status=TenantStatus.active,
            trial_ends_at=None,
        ) is True

    def test_trial_active_allowed(self):
        """Trial tenant within trial period is allowed."""
        future = datetime.now(timezone.utc) + timedelta(days=3)
        assert check_subscription_access(
            plan=TenantPlan.trial,
            status=TenantStatus.active,
            trial_ends_at=future,
        ) is True

    def test_trial_expired_suspended_blocked(self):
        """Expired trial with suspended status is blocked."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        assert check_subscription_access(
            plan=TenantPlan.trial,
            status=TenantStatus.suspended,
            trial_ends_at=past,
        ) is False

    def test_trial_active_expired_allowed(self):
        """Even if trial is past, active status means allowed (subscription active)."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        assert check_subscription_access(
            plan=TenantPlan.trial,
            status=TenantStatus.active,
            trial_ends_at=past,
        ) is True

    def test_subscription_suspended_allowed(self):
        """Subscription tenant even if suspended is not blocked by this guard."""
        assert check_subscription_access(
            plan=TenantPlan.subscription,
            status=TenantStatus.suspended,
            trial_ends_at=None,
        ) is True

    def test_trial_expired_cancelled_blocked(self):
        """Cancelled tenant with expired trial is blocked."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        assert check_subscription_access(
            plan=TenantPlan.cancelled,
            status=TenantStatus.cancelled,
            trial_ends_at=past,
        ) is False

    def test_no_trial_ends_at_allowed(self):
        """When trial_ends_at is None (subscription tenants), always allowed."""
        assert check_subscription_access(
            plan=TenantPlan.subscription,
            status=TenantStatus.active,
            trial_ends_at=None,
        ) is True
