"""
conftest.py
-----------
Shared pytest fixtures.
All infrastructure (ES, Redis, Postgres) is mocked so tests run
without any Docker containers — fast, hermetic, CI-friendly.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ---- patch infrastructure before importing the app ----
# These patches prevent the lifespan from trying to connect to real services.

MOCK_DOC = {
    "id":         "01HQ1111111111111111111111",
    "tenant_id":  "test_tenant",
    "title":      "Test Document",
    "content":    "This is a test document with searchable content.",
    "metadata":   {"author": "Elon"},
    "tags":       ["test", "demo"],
    "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
    "updated_at": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
}


@pytest.fixture(scope="session")
def mock_es_client():
    client = MagicMock()
    client.ping = AsyncMock(return_value=True)
    client.index = AsyncMock(return_value={"result": "created"})
    client.get   = AsyncMock(return_value={"_source": MOCK_DOC})
    client.delete = AsyncMock(return_value={"result": "deleted"})
    client.search = AsyncMock(return_value={
        "hits": {
            "total": {"value": 1},
            "hits": [{
                "_id":     MOCK_DOC["id"],
                "_score":  1.5,
                "_source": MOCK_DOC,
                "highlight": {
                    "content": ["This is a <em>test</em> document"],
                },
            }],
        }
    })
    client.indices = MagicMock()
    client.indices.exists = AsyncMock(return_value=True)
    client.indices.create = AsyncMock(return_value={"acknowledged": True})
    return client


@pytest.fixture(scope="session")
def mock_es_wrapper(mock_es_client):
    wrapper = MagicMock()
    wrapper.client = mock_es_client
    wrapper.ping   = AsyncMock(return_value=True)
    wrapper.index_name  = lambda tid: f"docs_{tid}"
    wrapper.ensure_index = AsyncMock()
    return wrapper


@pytest.fixture(scope="session")
def mock_redis():
    r = MagicMock()
    r.ping            = AsyncMock(return_value=True)
    r.get_cache       = AsyncMock(return_value=None)  # cache miss by default
    r.set_cache       = AsyncMock()
    r.delete_cache    = AsyncMock()
    r.delete_by_pattern = AsyncMock(return_value=1)
    r.sliding_window_check = AsyncMock(return_value=(True, 0))  # always allowed
    return r


@pytest.fixture(scope="session")
def mock_db():
    db = MagicMock()
    db.ping = AsyncMock(return_value=True)

    # Mock session context manager
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__  = AsyncMock(return_value=False)
    session.add    = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    db.get_session = MagicMock(return_value=session)
    return db


@pytest_asyncio.fixture(scope="session")
async def app(mock_es_wrapper, mock_redis, mock_db):
    """Return a FastAPI app instance with all infra mocked."""
    import core.elasticsearch as es_module
    import core.redis_client as redis_module
    import core.database as db_module

    es_module._es_client    = mock_es_wrapper
    redis_module._redis_client = mock_redis
    db_module._database     = mock_db

    # Import app AFTER patching the singletons
    from main import create_app
    _app = create_app()

    # Manually trigger the startup without real connections
    yield _app


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Tenant-ID": "test_tenant"},
    ) as c:
        yield c


@pytest.fixture
def tenant_id() -> str:
    return "test_tenant"


@pytest.fixture
def sample_document() -> dict:
    return {
        "title":    "Introduction to Distributed Systems",
        "content":  "Distributed systems require careful thought about consistency, availability, and partition tolerance.",
        "tags":     ["distributed", "systems", "cap-theorem"],
        "metadata": {"author": "Elon", "year": 2024},
    }
