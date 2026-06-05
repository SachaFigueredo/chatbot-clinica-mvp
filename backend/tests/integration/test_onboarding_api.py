"""Integration tests for the Onboarding API endpoints.

Routes under test:
- ``GET  /api/v1/onboarding/status`` — current onboarding state
- ``PUT  /api/v1/onboarding/step`` — mark a step as completed
- ``GET  /api/v1/onboarding/faq-templates`` — return FAQ templates
"""

from __future__ import annotations

import pytest


class TestOnboardingStatus:
    STATUS_URL = "/api/v1/onboarding/status"

    async def test_status_default(
        self, async_client, auth_headers
    ):
        """Without any onboarding data, returns default state (step 1, all incomplete)."""
        resp = await async_client.get(self.STATUS_URL, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["completed"] is False
        assert data["current_step"] == 1
        assert len(data["steps"]) == 5
        for step in data["steps"]:
            assert step["completed"] is False

    async def test_status_after_step(
        self, async_client, auth_headers
    ):
        """After marking step 1 complete, current_step advances."""
        # Mark step 1
        await async_client.put(
            "/api/v1/onboarding/step",
            headers=auth_headers,
            json={"step_id": 1},
        )
        resp = await async_client.get(self.STATUS_URL, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is False
        assert data["current_step"] == 2
        assert data["steps"][0]["completed"] is True
        assert data["steps"][1]["completed"] is False

    async def test_status_all_completed(
        self, async_client, auth_headers
    ):
        """After completing all 5 steps, onboarding is completed."""
        for step_id in range(1, 6):
            resp = await async_client.put(
                "/api/v1/onboarding/step",
                headers=auth_headers,
                json={"step_id": step_id},
            )
            assert resp.status_code == 200, resp.text

        resp = await async_client.get(self.STATUS_URL, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is True
        assert data["current_step"] == 5

    async def test_status_unauthorized(self, async_client):
        """No auth returns 401."""
        resp = await async_client.get(self.STATUS_URL)
        assert resp.status_code == 401


class TestMarkStep:
    STEP_URL = "/api/v1/onboarding/step"

    async def test_mark_step_success(
        self, async_client, auth_headers
    ):
        """Marking a valid step returns the updated status."""
        resp = await async_client.put(
            self.STEP_URL,
            headers=auth_headers,
            json={"step_id": 1},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["steps"][0]["completed"] is True
        assert data["current_step"] == 2

    async def test_mark_step_out_of_range(
        self, async_client, auth_headers
    ):
        """Step ID outside 1..5 returns 400."""
        resp = await async_client.put(
            self.STEP_URL,
            headers=auth_headers,
            json={"step_id": 99},
        )
        assert resp.status_code == 400

    async def test_mark_step_twice_is_idempotent(
        self, async_client, auth_headers
    ):
        """Marking the same step twice does not change state."""
        await async_client.put(
            self.STEP_URL, headers=auth_headers, json={"step_id": 1}
        )
        resp = await async_client.put(
            self.STEP_URL, headers=auth_headers, json={"step_id": 1}
        )
        assert resp.status_code == 200
        data = resp.json()
        completed_ids = [s["id"] for s in data["steps"] if s["completed"]]
        assert completed_ids == [1]  # not duplicated


class TestFAQTemplate:
    TEMPLATES_URL = "/api/v1/onboarding/faq-templates"

    async def test_templates_returned(self, async_client):
        """The FAQ templates endpoint returns predefined templates."""
        resp = await async_client.get(self.TEMPLATES_URL)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "templates" in data
        assert len(data["templates"]) == 7  # We have 7 templates defined
        first = data["templates"][0]
        assert "question" in first
        assert "answer" in first
        assert "category" in first

    async def test_templates_no_auth_required(self, async_client):
        """The FAQ templates endpoint is public (no auth needed)."""
        resp = await async_client.get(self.TEMPLATES_URL)
        assert resp.status_code == 200
