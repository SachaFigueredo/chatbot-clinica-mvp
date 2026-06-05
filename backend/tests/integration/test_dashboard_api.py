"""Integration tests for the Dashboard API endpoint.

Routes under test:
- ``GET /api/v1/dashboard/stats`` — aggregate dashboard statistics
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from app.domain.enums import (
    AppointmentStatus,
    ConversationStatus,
    ConversationChannel,
)
from app.infrastructure.database.models.appointment import Appointment
from app.infrastructure.database.models.conversation import Conversation


class TestDashboardStats:
    STATS_URL = "/api/v1/dashboard/stats"

    async def test_stats_empty(
        self, async_client, auth_headers
    ):
        """With no data, all stats are zero."""
        resp = await async_client.get(self.STATS_URL, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["appointments_today"] == 0
        assert data["pending_confirmations"] == 0
        assert data["active_conversations"] == 0
        assert data["escalated_conversations"] == 0
        assert data["no_show_rate"] == 0.0

    async def test_stats_with_data(
        self, async_client, auth_headers, db_session, test_tenant
    ):
        """Stats reflect the actual counts in the database."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # --- Create test appointments ---
        apt1 = Appointment(
            tenant_id=test_tenant.id,
            patient_id=test_tenant.id,  # not a real patient FK, but we just need counts
            start_time=today_start + timedelta(hours=10),
            end_time=today_start + timedelta(hours=10, minutes=20),
            status=AppointmentStatus.confirmed,
        )
        apt2 = Appointment(
            tenant_id=test_tenant.id,
            patient_id=test_tenant.id,
            start_time=today_start + timedelta(hours=11),
            end_time=today_start + timedelta(hours=11, minutes=20),
            status=AppointmentStatus.pending,
        )
        db_session.add_all([apt1, apt2])

        # --- Create conversations ---
        conv1 = Conversation(
            tenant_id=test_tenant.id,
            patient_id=test_tenant.id,
            status=ConversationStatus.active,
            channel=ConversationChannel.whatsapp,
        )
        conv2 = Conversation(
            tenant_id=test_tenant.id,
            patient_id=test_tenant.id,
            status=ConversationStatus.escalated,
            channel=ConversationChannel.whatsapp,
        )
        db_session.add_all([conv1, conv2])
        await db_session.commit()

        # --- Fetch stats ---
        resp = await async_client.get(self.STATS_URL, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["appointments_today"] == 2
        assert data["pending_confirmations"] == 1
        assert data["active_conversations"] == 1
        assert data["escalated_conversations"] == 1
        assert data["no_show_rate"] == 0.0  # no no-show or attended this month

    async def test_stats_tenant_isolation(
        self, async_client, db_session, test_tenant, test_tenant_2, auth_headers_other
    ):
        """A user from tenant B sees only tenant B's stats."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Appointment for tenant A
        apt_a = Appointment(
            tenant_id=test_tenant.id,
            patient_id=test_tenant.id,
            start_time=today_start + timedelta(hours=10),
            end_time=today_start + timedelta(hours=10, minutes=20),
            status=AppointmentStatus.confirmed,
        )
        # Appointment for tenant B
        apt_b = Appointment(
            tenant_id=test_tenant_2.id,
            patient_id=test_tenant_2.id,
            start_time=today_start + timedelta(hours=10),
            end_time=today_start + timedelta(hours=10, minutes=20),
            status=AppointmentStatus.confirmed,
        )
        db_session.add_all([apt_a, apt_b])
        await db_session.commit()

        # Tenant B sees 1 appointment today, not 2
        resp = await async_client.get(self.STATS_URL, headers=auth_headers_other)
        assert resp.status_code == 200
        assert resp.json()["appointments_today"] == 1

    async def test_stats_unauthorized(self, async_client):
        """No auth returns 401."""
        resp = await async_client.get(self.STATS_URL)
        assert resp.status_code == 401
