"""
main.py
-------
FastAPI application entry-point.

Responsibilities:
  - Application factory with lifespan context manager
  - Infrastructure initialisation (ES, Redis, PostgreSQL)
  - Global exception handlers (map domain errors → HTTP responses)
  - Middleware registration (tenant extraction, request logging)
  - Router mounting
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from core.elasticsearch import init_es_client
from core.redis_client import init_redis_client
from core.database import init_database
from core.exceptions import (
    AppError,
    RateLimitExceededError,
    DocumentNotFoundError,
    TenantNotFoundError,
)
from middleware.tenant import TenantMiddleware
from api.v1.router import api_router
from api.v1.health import router as health_router

# ------------------------------------------------------------------- logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)
settings = get_settings()


# ------------------------------------------------------------------ lifespan

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup → yield → shutdown."""
    logger.info("Starting up %s v%s …", settings.app_name, settings.app_version)

    # Initialise infrastructure clients
    es    = init_es_client(settings)
    redis = init_redis_client(settings)
    db    = init_database(settings)

    await redis.connect()
    await db.connect()

    # Warm up ES connection
    if await es.ping():
        logger.info("Elasticsearch connected ✓")
    else:
        logger.warning("Elasticsearch not reachable on startup — will retry per request")

    logger.info("Application ready ✓")
    yield

    # Shutdown — release resources
    logger.info("Shutting down …")
    await es.close()
    await redis.close()
    await db.close()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------- app factory

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Distributed document search service with multi-tenancy, "
            "full-text search, Redis caching, and per-tenant rate limiting."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS (open in dev; tighten in prod via env var)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Tenant extraction middleware
    app.add_middleware(TenantMiddleware)

    # ── Request timing middleware
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        elapsed = (time.monotonic() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed:.2f}"
        return response

    # ── Exception handlers
    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(request: Request, exc: RateLimitExceededError):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(exc.retry_after)},
            content={
                "error":  "Rate limit exceeded",
                "detail": exc.message,
                "status": 429,
            },
        )

    @app.exception_handler(DocumentNotFoundError)
    async def not_found_handler(request: Request, exc: DocumentNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Not found", "detail": exc.message, "status": 404},
        )

    @app.exception_handler(TenantNotFoundError)
    async def tenant_not_found_handler(request: Request, exc: TenantNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Not found", "detail": exc.message, "status": 404},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "Application error", "detail": exc.message, "status": exc.status_code},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal server error", "detail": str(exc), "status": 500},
        )

    # ── Routes
    app.include_router(health_router)           # GET /health  (no tenant needed)
    app.include_router(api_router)              # /api/v1/...

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs":    "/docs",
            "health":  "/health",
        }

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info",
    )
