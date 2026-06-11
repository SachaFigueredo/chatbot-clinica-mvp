"""Unit tests for the Tenant model definition.

Tests verify the ORM columns exist and have the expected types.
New billing/subscription fields are tested here.
"""

from datetime import datetime, timezone

import pytest

from app.domain.enums import TenantPlan, TenantStatus
from app.infrastructure.database.models.tenant import Tenant


class TestTenantModelFields:
    """Tenant model fields — both existing and new."""

    def test_existing_fields_preserved(self):
        """Original fields still exist after extension."""
        t = Tenant(
            name="Test",
            slug="test",
            phone_number="541111111111",
            status=TenantStatus.active,
            plan=TenantPlan.basic,
        )
        assert t.name == "Test"
        assert t.slug == "test"
        assert t.phone_number == "541111111111"
        assert t.status == TenantStatus.active
        assert t.plan == TenantPlan.basic

    def test_trial_ends_at_field_exists(self):
        """Tenant model has trial_ends_at DateTime column."""
        now = datetime.now(timezone.utc)
        t = Tenant(
            name="Trial",
            slug="trial-test",
            phone_number="541111111112",
            status=TenantStatus.active,
            plan=TenantPlan.trial,
            trial_ends_at=now,
        )
        assert t.trial_ends_at == now

    def test_mercadopago_customer_id_field_exists(self):
        """Tenant model has mercadopago_customer_id String column."""
        t = Tenant(
            name="MP Customer",
            slug="mp-customer",
            phone_number="541111111113",
            status=TenantStatus.active,
            plan=TenantPlan.subscription,
            mercadopago_customer_id="cust_123",
        )
        assert t.mercadopago_customer_id == "cust_123"

    def test_mercadopago_subscription_id_field_exists(self):
        """Tenant model has mercadopago_subscription_id String column."""
        t = Tenant(
            name="MP Sub",
            slug="mp-sub",
            phone_number="541111111114",
            status=TenantStatus.active,
            plan=TenantPlan.subscription,
            mercadopago_subscription_id="sub_456",
        )
        assert t.mercadopago_subscription_id == "sub_456"

    def test_suspended_at_field_exists(self):
        """Tenant model has suspended_at DateTime column."""
        now = datetime.now(timezone.utc)
        t = Tenant(
            name="Suspended",
            slug="suspended-test",
            phone_number="541111111115",
            status=TenantStatus.suspended,
            plan=TenantPlan.trial,
            suspended_at=now,
        )
        assert t.suspended_at == now
