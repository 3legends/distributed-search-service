"""
dependencies.py
---------------
FastAPI dependency functions — injected into route handlers.
All infrastructure clients are resolved from module-level singletons
that are initialised in main.py's lifespan handler.
"""
from __future__ import annotations

from fastapi import Depends, Request

from config import Settings, get_settings
from core.elasticsearch import ElasticsearchClient, get_es_client
from core.redis_client import RedisClient, get_redis_client
from core.database import Database, get_database
from services.document_service import DocumentService
from services.search_service import SearchService
from services.rate_limiter import RateLimiter


# ---------------------------------------------------------------- primitives

def dep_settings() -> Settings:
    return get_settings()


def dep_es() -> ElasticsearchClient:
    return get_es_client()


def dep_redis() -> RedisClient:
    return get_redis_client()


def dep_db() -> Database:
    return get_database()


# ----------------------------------------------------------------- services

def dep_document_service(
    es:    ElasticsearchClient = Depends(dep_es),
    redis: RedisClient         = Depends(dep_redis),
    db:    Database            = Depends(dep_db),
) -> DocumentService:
    return DocumentService(es=es, redis=redis, db=db)


def dep_search_service(
    es:    ElasticsearchClient = Depends(dep_es),
    redis: RedisClient         = Depends(dep_redis),
) -> SearchService:
    return SearchService(es=es, redis=redis)


def dep_rate_limiter(
    redis:    RedisClient = Depends(dep_redis),
    settings: Settings    = Depends(dep_settings),
) -> RateLimiter:
    return RateLimiter(redis=redis, settings=settings)


# ------------------------------------------------------------------ tenant

def dep_tenant(request: Request) -> str:
    """Pull the tenant_id stowed by TenantMiddleware."""
    return request.state.tenant_id
