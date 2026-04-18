"""
test_health.py
--------------
Tests for GET /health
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHealthCheck:
    async def test_health_returns_200_when_all_ok(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_response_schema(self, client: AsyncClient):
        response = await client.get("/health")
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "dependencies" in data

    async def test_health_dependencies_present(self, client: AsyncClient):
        response = await client.get("/health")
        deps = response.json()["dependencies"]
        assert "elasticsearch" in deps
        assert "redis" in deps
        assert "postgres" in deps

    async def test_health_dependency_structure(self, client: AsyncClient):
        response = await client.get("/health")
        deps = response.json()["dependencies"]
        for name, dep in deps.items():
            assert "status" in dep,     f"Missing 'status' in {name}"
            assert "latency_ms" in dep, f"Missing 'latency_ms' in {name}"

    async def test_health_returns_503_when_es_down(
        self, client: AsyncClient, mock_es_wrapper
    ):
        original = mock_es_wrapper.ping
        mock_es_wrapper.ping = AsyncMock(return_value=False)
        try:
            response = await client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["dependencies"]["elasticsearch"]["status"] == "down"
        finally:
            mock_es_wrapper.ping = original

    async def test_health_returns_503_when_redis_down(
        self, client: AsyncClient, mock_redis
    ):
        original = mock_redis.ping
        mock_redis.ping = AsyncMock(return_value=False)
        try:
            response = await client.get("/health")
            assert response.status_code == 503
        finally:
            mock_redis.ping = original

    async def test_health_no_tenant_header_required(self, client: AsyncClient):
        """Health endpoint must work without X-Tenant-ID."""
        response = await client.get("/health", headers={})  # no tenant header
        # Should not be 400
        assert response.status_code in (200, 503)

    async def test_health_includes_version(self, client: AsyncClient):
        response = await client.get("/health")
        data = response.json()
        assert data["version"] == "1.0.0"
