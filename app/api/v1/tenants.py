"""
/api/v1/tenants
---------------
POST /tenants       – register a new tenant
GET  /tenants       – list all tenants
GET  /tenants/{id}  – get a single tenant
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from core.database import Database, TenantModel
from core.elasticsearch import ElasticsearchClient
from dependencies import dep_db, dep_es
from models.document import TenantCreate, TenantResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new tenant",
)
async def create_tenant(
    payload: TenantCreate,
    db:      Database            = Depends(dep_db),
    es:      ElasticsearchClient = Depends(dep_es),
) -> TenantResponse:
    async with db.get_session() as session:
        # Check for duplicates
        existing = await session.get(TenantModel, payload.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tenant '{payload.id}' already exists.",
            )

        tenant = TenantModel(
            id=payload.id,
            name=payload.name,
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)

    # Pre-create the ES index so the first document write is instant
    await es.ensure_index(payload.id)
    logger.info("Tenant '%s' registered", payload.id)
    return TenantResponse.model_validate(tenant)


@router.get(
    "",
    response_model=List[TenantResponse],
    summary="List all tenants",
)
async def list_tenants(
    db: Database = Depends(dep_db),
) -> List[TenantResponse]:
    async with db.get_session() as session:
        result = await session.execute(
            select(TenantModel).where(TenantModel.is_active == True)  # noqa: E712
        )
        tenants = result.scalars().all()
    return [TenantResponse.model_validate(t) for t in tenants]


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Get a tenant by ID",
)
async def get_tenant(
    tenant_id: str,
    db:        Database = Depends(dep_db),
) -> TenantResponse:
    async with db.get_session() as session:
        tenant = await session.get(TenantModel, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found.",
        )
    return TenantResponse.model_validate(tenant)
