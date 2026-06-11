"""Unit tests for the trial expiry Celery task.

Tests the pure function that evaluates whether a tenant's trial has expired.
"""

from datetime import datetime, timezone, timedelta

import pytest

from app.domain.enums import TenantPlan, TenantStatus
from tasks.trial_expiry import is_trial_expired


class TestIsTrialExpired:
    """Pure function: is this tenant's trial expired?"""

    def test_active_trial_within_period_not_expired(self):
        """Active trial within the 7-day period is not expired."""
        future = datetime.now(timezone.utc) + timedelta(days=3)
        assert is_trial_expired(
            plan=TenantPlan.trial,
            status=TenantStatus.active,
            trial_ends_at=future,
        ) is False

    def test_active_trial_expired_is_expired(self):
        """Tenant with trial expired but still active should be caught."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        assert is_trial_expired(
            plan=TenantPlan.trial,
            status=TenantStatus.active,
            trial_ends_at=past,
        ) is True

    def test_subscription_active_not_expired(self):
        """Paying subscribers are not subject to trial expiry."""
        assert is_trial_expired(
            plan=TenantPlan.subscription,
            status=TenantStatus.active,
            trial_ends_at=None,
        ) is False

    def test_already_suspended_not_expired(self):
        """Already suspended tenants are not 'expired' — they're already handled."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        assert is_trial_expired(
            plan=TenantPlan.trial,
            status=TenantStatus.suspended,
            trial_ends_at=past,
        ) is False

    def test_no_trial_ends_at_returns_false(self):
        """Tenants without trial_ends_at set are not expired."""
        assert is_trial_expired(
            plan=TenantPlan.basic,
            status=TenantStatus.active,
            trial_ends_at=None,
        ) is False

    def test_trial_cancelled_not_expired(self):
        """Cancelled tenants are not subject to trial expiry."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        assert is_trial_expired(
            plan=TenantPlan.cancelled,
            status=TenantStatus.cancelled,
            trial_ends_at=past,
        ) is False
