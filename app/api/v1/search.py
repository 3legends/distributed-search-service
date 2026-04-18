"""
/api/v1/search
--------------
GET /search?q={query}&tenant={tenantId}[&page=1&size=10&tags=t1,t2&fuzzy=true]

The tenant can also be supplied via the X-Tenant-ID header (preferred) or
the ?tenant= query param (convenience for curl testing).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, status

from dependencies import (
    dep_tenant,
    dep_search_service,
    dep_rate_limiter,
)
from models.document import SearchResponse
from services.search_service import SearchService
from services.rate_limiter import RateLimiter
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Full-text search across tenant documents",
    description=(
        "Executes a multi-match, BM25-ranked full-text search against the "
        "tenant's Elasticsearch index. Results are highlighted and optionally "
        "served from the Redis cache."
    ),
)
async def search_documents(
    request:        Request,
    q:              str            = Query(..., min_length=1, description="Search query"),
    page:           int            = Query(1,  ge=1,  description="Page number (1-indexed)"),
    size:           int            = Query(10, ge=1,  le=100, description="Results per page"),
    tags:           Optional[str]  = Query(None, description="Comma-separated tag filter"),
    fuzzy:          bool           = Query(True, description="Enable fuzzy/typo matching"),
    # Tenant can come from query param too (header takes priority via middleware)
    tenant:         Optional[str]  = Query(None, description="Tenant ID (or use X-Tenant-ID header)"),
    search_service: SearchService  = Depends(dep_search_service),
    rate_limiter:   RateLimiter    = Depends(dep_rate_limiter),
) -> SearchResponse:
    # Header tenant (set by middleware) takes priority over query param
    tenant_id = getattr(request.state, "tenant_id", None) or tenant
    if not tenant_id:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="Tenant ID required: use X-Tenant-ID header or ?tenant= query param",
        )

    await rate_limiter.check(tenant_id)

    tag_list: Optional[List[str]] = (
        [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    )

    result = await search_service.search(
        tenant_id=tenant_id,
        query=q,
        page=page,
        size=size,
        tags=tag_list,
        fuzzy=fuzzy,
    )

    logger.info(
        "Search tenant='%s' q='%s' total=%d cached=%s took=%.1fms",
        tenant_id, q, result.total, result.cached, result.took_ms,
    )
    return result
