"""
test_search.py
--------------
Tests for GET /api/v1/search
"""
from __future__ import annotations

import json
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestSearch:
    async def test_search_returns_200(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=distributed")
        assert response.status_code == 200

    async def test_search_returns_expected_schema(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=distributed")
        data = response.json()
        for field in ("query", "tenant_id", "total", "page", "size", "took_ms", "cached", "results"):
            assert field in data, f"Missing field: {field}"

    async def test_search_query_reflected_in_response(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=hello+world")
        data = response.json()
        assert data["query"] == "hello world"

    async def test_search_tenant_reflected_in_response(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=test")
        data = response.json()
        assert data["tenant_id"] == "test_tenant"

    async def test_search_pagination_defaults(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=test")
        data = response.json()
        assert data["page"] == 1
        assert data["size"] == 10

    async def test_search_custom_pagination(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=test&page=2&size=5")
        data = response.json()
        assert data["page"] == 2
        assert data["size"] == 5

    async def test_search_empty_query_returns_422(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=")
        assert response.status_code == 422

    async def test_search_missing_query_returns_422(self, client: AsyncClient):
        response = await client.get("/api/v1/search")
        assert response.status_code == 422

    async def test_search_size_exceeds_max_returns_422(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=test&size=101")
        assert response.status_code == 422

    async def test_search_missing_tenant_returns_400(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/search?q=test",
            headers={"X-Tenant-ID": ""},
        )
        assert response.status_code == 400

    async def test_search_results_structure(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=test")
        data = response.json()
        if data["results"]:
            hit = data["results"][0]
            for field in ("id", "title", "content_snippet", "score"):
                assert field in hit, f"Missing hit field: {field}"

    async def test_search_cache_hit(self, client: AsyncClient, mock_redis):
        """Second call should return cached=True."""
        cached_response = {
            "query":     "cached",
            "tenant_id": "test_tenant",
            "total":     1,
            "page":      1,
            "size":      10,
            "took_ms":   5.0,
            "cached":    True,
            "results":   [],
        }
        mock_redis.get_cache.return_value = json.dumps(cached_response)

        response = await client.get("/api/v1/search?q=cached")
        data = response.json()
        assert data["cached"] is True

        # Reset to default cache-miss behaviour
        mock_redis.get_cache.return_value = None

    async def test_search_with_tag_filter(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=test&tags=distributed,systems")
        assert response.status_code == 200

    async def test_search_fuzzy_disabled(self, client: AsyncClient):
        response = await client.get("/api/v1/search?q=test&fuzzy=false")
        assert response.status_code == 200


@pytest.mark.asyncio
class TestRateLimiting:
    async def test_rate_limit_exceeded_returns_429(self, client: AsyncClient, mock_redis):
        from unittest.mock import AsyncMock
        original = mock_redis.sliding_window_check
        mock_redis.sliding_window_check = AsyncMock(return_value=(False, 30))
        try:
            response = await client.get("/api/v1/search?q=test")
            assert response.status_code == 429
            assert "Retry-After" in response.headers
        finally:
            mock_redis.sliding_window_check = original
