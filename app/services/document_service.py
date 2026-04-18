"""
DocumentService
---------------
Orchestrates document indexing and retrieval.
- Writes ground-truth metadata to PostgreSQL
- Indexes / removes documents in Elasticsearch
- Invalidates relevant cache entries on mutation
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy import update

from core.elasticsearch import ElasticsearchClient
from core.redis_client import RedisClient
from core.database import Database, DocumentMetaModel
from core.exceptions import DocumentNotFoundError, IndexingError, SearchServiceError
from models.document import DocumentCreate, DocumentResponse

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        es: ElasticsearchClient,
        redis: RedisClient,
        db: Database,
    ) -> None:
        self._es    = es
        self._redis = redis
        self._db    = db

    # ----------------------------------------------------------------- create

    async def create_document(
        self,
        tenant_id: str,
        payload: DocumentCreate,
    ) -> DocumentResponse:
        doc_id = str(uuid.uuid4())
        now    = datetime.now(timezone.utc)

        doc_body: Dict[str, Any] = {
            "id":         doc_id,
            "tenant_id":  tenant_id,
            "title":      payload.title,
            "content":    payload.content,
            "metadata":   payload.metadata,
            "tags":       payload.tags,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        # 1. Ensure tenant index exists
        await self._es.ensure_index(tenant_id)

        # 2. Index in Elasticsearch (primary search store)
        try:
            await self._es.client.index(
                index=self._es.index_name(tenant_id),
                id=doc_id,
                document=doc_body,
                refresh="wait_for",  # consistent reads in prototype; use "false" in prod
            )
        except Exception as exc:
            logger.error("ES indexing failed for doc '%s': %s", doc_id, exc)
            raise IndexingError(str(exc)) from exc

        # 3. Persist lightweight metadata to PostgreSQL
        async with self._db.get_session() as session:
            meta = DocumentMetaModel(
                id=doc_id,
                tenant_id=tenant_id,
                title=payload.title,
                tags=payload.tags,
                created_at=now,
                updated_at=now,
            )
            session.add(meta)
            await session.commit()

        # 4. Invalidate search cache for this tenant
        await self._invalidate_tenant_cache(tenant_id)

        logger.info("Document '%s' indexed for tenant '%s'", doc_id, tenant_id)
        return DocumentResponse(
            id=doc_id,
            tenant_id=tenant_id,
            title=payload.title,
            content=payload.content,
            metadata=payload.metadata,
            tags=payload.tags,
            created_at=now,
            updated_at=now,
        )

    # -------------------------------------------------------------------- get

    async def get_document(self, tenant_id: str, doc_id: str) -> DocumentResponse:
        try:
            resp = await self._es.client.get(
                index=self._es.index_name(tenant_id),
                id=doc_id,
            )
        except Exception as exc:
            if "NotFoundError" in type(exc).__name__ or getattr(exc, "status_code", 0) == 404:
                raise DocumentNotFoundError(doc_id)
            raise SearchServiceError(str(exc)) from exc

        src = resp["_source"]
        return DocumentResponse(
            id=src["id"],
            tenant_id=src["tenant_id"],
            title=src["title"],
            content=src["content"],
            metadata=src.get("metadata", {}),
            tags=src.get("tags", []),
            created_at=src["created_at"],
            updated_at=src["updated_at"],
        )

    # ----------------------------------------------------------------- delete

    async def delete_document(self, tenant_id: str, doc_id: str) -> None:
        # Verify ownership / existence via ES
        try:
            await self._es.client.delete(
                index=self._es.index_name(tenant_id),
                id=doc_id,
                refresh="wait_for",
            )
        except Exception as exc:
            if "NotFoundError" in type(exc).__name__ or getattr(exc, "status_code", 0) == 404:
                raise DocumentNotFoundError(doc_id)
            raise

        # Soft-delete in PostgreSQL for audit trail
        async with self._db.get_session() as session:
            await session.execute(
                update(DocumentMetaModel)
                .where(
                    DocumentMetaModel.id == doc_id,
                    DocumentMetaModel.tenant_id == tenant_id,
                )
                .values(is_deleted=True, updated_at=datetime.now(timezone.utc))
            )
            await session.commit()

        # Invalidate cache
        await self._invalidate_tenant_cache(tenant_id)
        await self._redis.delete_cache(f"doc:{tenant_id}:{doc_id}")

        logger.info("Document '%s' deleted for tenant '%s'", doc_id, tenant_id)

    # ---------------------------------------------------------------- helpers

    async def _invalidate_tenant_cache(self, tenant_id: str) -> None:
        """Bust all search caches for this tenant after a write."""
        await self._redis.delete_by_pattern(f"search:{tenant_id}:*")