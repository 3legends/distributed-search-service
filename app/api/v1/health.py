"""
/health
-------
GET /health – liveness + dependency readiness probe

Returns HTTP 200 when all dependencies are healthy.
Returns HTTP 503 when any dependency is down.
Designed to be consumed by container orchestrators (k8s, ECS).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from core.elasticsearch import get_es_client
from core.redis_client import get_redis_client
from core.database import get_database
from models.document import DependencyStatus, HealthResponse
from config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])
settings = get_settings()


async def _check_elasticsearch() -> DependencyStatus:
    start = time.monotonic()
    try:
        ok = await get_es_client().ping()
        latency = (time.monotonic() - start) * 1000
        return DependencyStatus(
            status="ok" if ok else "down",
            latency_ms=round(latency, 2),
        )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return DependencyStatus(status="down", latency_ms=round(latency, 2), detail=str(exc))


async def _check_redis() -> DependencyStatus:
    start = time.monotonic()
    try:
        ok = await get_redis_client().ping()
        latency = (time.monotonic() - start) * 1000
        return DependencyStatus(
            status="ok" if ok else "down",
            latency_ms=round(latency, 2),
        )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return DependencyStatus(status="down", latency_ms=round(latency, 2), detail=str(exc))


async def _check_postgres() -> DependencyStatus:
    start = time.monotonic()
    try:
        ok = await get_database().ping()
        latency = (time.monotonic() - start) * 1000
        return DependencyStatus(
            status="ok" if ok else "down",
            latency_ms=round(latency, 2),
        )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return DependencyStatus(status="down", latency_ms=round(latency, 2), detail=str(exc))


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description=(
        "Returns the liveness status of the service and each dependency "
        "(Elasticsearch, Redis, PostgreSQL). All checks run concurrently."
    ),
)
async def health_check() -> JSONResponse:
    es_status, redis_status, pg_status = await asyncio.gather(
        _check_elasticsearch(),
        _check_redis(),
        _check_postgres(),
    )

    deps: Dict[str, DependencyStatus] = {
        "elasticsearch": es_status,
        "redis":         redis_status,
        "postgres":      pg_status,
    }

    all_ok      = all(d.status == "ok" for d in deps.values())
    any_down    = any(d.status == "down" for d in deps.values())
    overall     = "healthy" if all_ok else ("unhealthy" if any_down else "degraded")
    http_status = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    response = HealthResponse(
        status=overall,
        version=settings.app_version,
        dependencies=deps,
    )

    logger.info("Health check: %s", overall)
    return JSONResponse(content=response.model_dump(), status_code=http_status)
