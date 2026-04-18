"""
/api/v1/documents
-----------------
POST   /documents          – index a new document
GET    /documents/{doc_id} – retrieve a document by ID
DELETE /documents/{doc_id} – remove a document
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from dependencies import (
    dep_tenant,
    dep_document_service,
    dep_rate_limiter,
)
from models.document import DocumentCreate, DocumentResponse, DocumentIndexed
from services.document_service import DocumentService
from services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "",
    response_model=DocumentIndexed,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Index a new document",
    description=(
        "Indexes the document into the tenant's Elasticsearch index and "
        "persists lightweight metadata to PostgreSQL. Returns immediately with "
        "the generated document ID."
    ),
)
async def create_document(
    payload:          DocumentCreate,
    tenant_id:        str             = Depends(dep_tenant),
    doc_service:      DocumentService = Depends(dep_document_service),
    rate_limiter:     RateLimiter     = Depends(dep_rate_limiter),
) -> DocumentIndexed:
    await rate_limiter.check(tenant_id)
    doc = await doc_service.create_document(tenant_id=tenant_id, payload=payload)
    logger.info("Document '%s' created for tenant '%s'", doc.id, tenant_id)
    return DocumentIndexed(
        id=doc.id,
        tenant_id=doc.tenant_id,
        indexed=True,
        message="Document indexed successfully",
    )


@router.get(
    "/{doc_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a document by ID",
    description="Fetches the full document (including content) from Elasticsearch.",
)
async def get_document(
    doc_id:       str,
    tenant_id:    str             = Depends(dep_tenant),
    doc_service:  DocumentService = Depends(dep_document_service),
    rate_limiter: RateLimiter     = Depends(dep_rate_limiter),
) -> DocumentResponse:
    await rate_limiter.check(tenant_id)
    return await doc_service.get_document(tenant_id=tenant_id, doc_id=doc_id)


@router.delete(
    "/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a document",
    description=(
        "Removes the document from Elasticsearch and marks it as deleted in "
        "PostgreSQL (soft-delete for audit trail)."
    ),
)
async def delete_document(
    doc_id:       str,
    tenant_id:    str             = Depends(dep_tenant),
    doc_service:  DocumentService = Depends(dep_document_service),
    rate_limiter: RateLimiter     = Depends(dep_rate_limiter),
) -> Response:
    await rate_limiter.check(tenant_id)
    await doc_service.delete_document(tenant_id=tenant_id, doc_id=doc_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)