"""Integration tests for the FAQ API endpoints.

Routes under test:
- ``GET    /api/v1/faqs/faqs`` — list FAQs (with search & category filters)
- ``POST   /api/v1/faqs/faqs`` — create a FAQ
- ``PUT    /api/v1/faqs/faqs/{id}`` — update a FAQ
- ``DELETE /api/v1/faqs/faqs/{id}`` — soft-delete a FAQ
"""

from __future__ import annotations

import pytest


class TestListFAQs:
    LIST_URL = "/api/v1/faqs/faqs"

    async def test_list_empty(self, async_client, auth_headers):
        """No FAQs returns an empty list."""
        resp = await async_client.get(self.LIST_URL, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    async def test_list_with_data(
        self, async_client, auth_headers, test_faqs
    ):
        """Active FAQs are returned, sorted by sort_order."""
        resp = await async_client.get(self.LIST_URL, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # 3 active FAQs (the 4th is inactive)
        assert len(data) == 3
        # Sorted by sort_order → 1, 2, 3
        assert data[0]["sort_order"] == 1
        assert data[1]["sort_order"] == 2
        assert data[2]["sort_order"] == 3

    async def test_list_filter_by_category(
        self, async_client, auth_headers, test_faqs
    ):
        """?category=horarios returns only FAQs in that category."""
        resp = await async_client.get(
            self.LIST_URL,
            headers=auth_headers,
            params={"category": "horarios"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        for faq in data:
            assert faq["category"] == "horarios"

    async def test_list_search(
        self, async_client, auth_headers, test_faqs
    ):
        """?search=obras returns FAQs matching the query."""
        resp = await async_client.get(
            self.LIST_URL,
            headers=auth_headers,
            params={"search": "obras"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert "obras" in data[0]["question"].lower()

    async def test_list_tenant_isolation(
        self, async_client, test_faqs, auth_headers_other
    ):
        """A user from another tenant sees no FAQs."""
        resp = await async_client.get(self.LIST_URL, headers=auth_headers_other)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_unauthorized(self, async_client):
        """No auth returns 401."""
        resp = await async_client.get(self.LIST_URL)
        assert resp.status_code == 401


class TestCreateFAQ:
    CREATE_URL = "/api/v1/faqs/faqs"

    async def test_create_success(self, async_client, auth_headers):
        """A valid FAQ creation returns 201 with the new FAQ."""
        body = {
            "question": "¿Nuevo horario?",
            "answer": "Atendemos de 9 a 17hs.",
            "category": "horarios",
            "sort_order": 10,
        }
        resp = await async_client.post(
            self.CREATE_URL, headers=auth_headers, json=body
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["question"] == body["question"]
        assert data["answer"] == body["answer"]
        assert data["category"] == body["category"]
        assert data["is_active"] is True
        assert "id" in data

    async def test_create_unauthorized(self, async_client):
        """No auth returns 401."""
        resp = await async_client.post(
            self.CREATE_URL, json={"question": "?", "answer": "!"}
        )
        assert resp.status_code == 401


class TestUpdateFAQ:
    async def test_update_success(
        self, async_client, auth_headers, test_faqs
    ):
        """Updating a FAQ changes the fields."""
        faq_id = str(test_faqs[0].id)
        body = {"question": "¿Horarios actualizados?", "answer": "8 a 20hs."}
        resp = await async_client.put(
            f"/api/v1/faqs/faqs/{faq_id}",
            headers=auth_headers,
            json=body,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["question"] == "¿Horarios actualizados?"
        assert data["answer"] == "8 a 20hs."

    async def test_update_not_found(self, async_client, auth_headers):
        """Updating a non-existent FAQ returns 404."""
        body = {"question": "?"}
        resp = await async_client.put(
            "/api/v1/faqs/faqs/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
            json=body,
        )
        assert resp.status_code == 404

    async def test_update_other_tenant(
        self, async_client, test_faqs, auth_headers_other
    ):
        """A user from another tenant cannot update this FAQ."""
        faq_id = str(test_faqs[0].id)
        body = {"question": "Hacked?"}
        resp = await async_client.put(
            f"/api/v1/faqs/faqs/{faq_id}",
            headers=auth_headers_other,
            json=body,
        )
        assert resp.status_code == 404  # not found (scoped)


class TestDeleteFAQ:
    async def test_delete_soft_delete(
        self, async_client, auth_headers, test_faqs
    ):
        """Deleting a FAQ soft-sets is_active=False."""
        faq_id = str(test_faqs[0].id)
        resp = await async_client.delete(
            f"/api/v1/faqs/faqs/{faq_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204, resp.text

        # Verify it's no longer listed
        list_resp = await async_client.get(
            "/api/v1/faqs/faqs", headers=auth_headers
        )
        faq_ids = [f["id"] for f in list_resp.json()]
        assert faq_id not in faq_ids

    async def test_delete_not_found(self, async_client, auth_headers):
        """Deleting a non-existent FAQ returns 404."""
        resp = await async_client.delete(
            "/api/v1/faqs/faqs/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404
