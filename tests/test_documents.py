"""
test_documents.py
-----------------
Tests for POST /api/v1/documents, GET /api/v1/documents/{id},
and DELETE /api/v1/documents/{id}.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestCreateDocument:
    async def test_create_returns_202(self, client: AsyncClient, sample_document: dict):
        response = await client.post("/api/v1/documents", json=sample_document)
        assert response.status_code == 202, response.text

    async def test_create_returns_document_id(self, client: AsyncClient, sample_document: dict):
        response = await client.post("/api/v1/documents", json=sample_document)
        data = response.json()
        assert "id" in data
        assert data["indexed"] is True
        assert data["tenant_id"] == "test_tenant"

    async def test_create_missing_title_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/documents",
            json={"content": "Some content"},
        )
        assert response.status_code == 422

    async def test_create_missing_content_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/documents",
            json={"title": "Some title"},
        )
        assert response.status_code == 422

    async def test_create_missing_tenant_returns_400(self, client: AsyncClient, sample_document: dict):
        response = await client.post(
            "/api/v1/documents",
            json=sample_document,
            headers={"X-Tenant-ID": ""},  # override fixture header
        )
        assert response.status_code == 400

    async def test_create_too_many_tags_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/documents",
            json={
                "title":   "X",
                "content": "Y",
                "tags":    [f"tag{i}" for i in range(51)],
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestGetDocument:
    async def test_get_existing_document_returns_200(self, client: AsyncClient):
        response = await client.get("/api/v1/documents/01HQ1111111111111111111111")
        assert response.status_code == 200

    async def test_get_returns_expected_fields(self, client: AsyncClient):
        response = await client.get("/api/v1/documents/01HQ1111111111111111111111")
        data = response.json()
        for field in ("id", "tenant_id", "title", "content", "tags", "metadata", "created_at", "updated_at"):
            assert field in data, f"Missing field: {field}"

    async def test_get_nonexistent_document_returns_404(
        self, client: AsyncClient, mock_es_wrapper
    ):
        from unittest.mock import AsyncMock

        class FakeNotFoundError(Exception):
            status_code = 404
            __name__ = "NotFoundError"

        original = mock_es_wrapper.client.get
        mock_es_wrapper.client.get = AsyncMock(side_effect=type(
            "NotFoundError", (Exception,), {"status_code": 404}
        )())
        try:
            response = await client.get("/api/v1/documents/does_not_exist")
            assert response.status_code == 404
        finally:
            mock_es_wrapper.client.get = original


@pytest.mark.asyncio
class TestDeleteDocument:
    async def test_delete_existing_document_returns_204(self, client: AsyncClient):
        response = await client.delete("/api/v1/documents/01HQ1111111111111111111111")
        assert response.status_code == 204

    async def test_delete_response_has_no_body(self, client: AsyncClient):
        response = await client.delete("/api/v1/documents/01HQ1111111111111111111111")
        assert response.content == b""

    async def test_delete_missing_tenant_returns_400(self, client: AsyncClient):
        response = await client.delete(
            "/api/v1/documents/01HQ1111111111111111111111",
            headers={"X-Tenant-ID": ""},
        )
        assert response.status_code == 400
