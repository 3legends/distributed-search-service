"""
TenantMiddleware
----------------
Extracts the tenant identifier from the X-Tenant-ID header for every
incoming request and stows it in request.state.tenant_id.

Does NOT hit the database on every request — the API routes that need
to validate tenant existence call the tenant dependency explicitly.
"""
from __future__ import annotations

import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Health and docs endpoints are exempt from tenant enforcement
_EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/", "/api/v1/tenants"}
_TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID", "").strip()

        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Missing X-Tenant-ID header",
                    "detail": "All API requests must include an X-Tenant-ID header.",
                    "status": 400,
                },
            )

        if not _TENANT_ID_PATTERN.match(tenant_id):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid X-Tenant-ID",
                    "detail": "Tenant ID must be 1-64 alphanumeric characters, hyphens, or underscores.",
                    "status": 400,
                },
            )

        request.state.tenant_id = tenant_id
        return await call_next(request)