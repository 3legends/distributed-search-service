import logging
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, JSON, Index, event
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, AsyncEngine, async_sessionmaker, create_async_engine
)
from sqlalchemy.orm import DeclarativeBase
from config import Settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class TenantModel(Base):
    """Registry of known tenants."""
    __tablename__ = "tenants"

    id         = Column(String(64),  primary_key=True)
    name       = Column(String(256), nullable=False)
    is_active  = Column(Boolean,     default=True, nullable=False)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_tenants_id", "id"),
    )


class DocumentMetaModel(Base):
    """
    Lightweight metadata table.
    Ground truth lives in Elasticsearch; this table enables
    SQL-level audit queries, tenant ownership checks, and hard deletes.
    """
    __tablename__ = "document_meta"

    id         = Column(String(64),  primary_key=True)
    tenant_id  = Column(String(64),  nullable=False, index=True)
    title      = Column(String(512), nullable=False)
    tags       = Column(JSON,        default=list)
    is_deleted = Column(Boolean,     default=False, nullable=False)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_docmeta_tenant_id", "tenant_id"),
        Index("ix_docmeta_created_at", "created_at"),
    )


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker | None = None

    async def connect(self) -> None:
        self._engine = create_async_engine(
            self._settings.database_url,
            echo=self._settings.debug,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL connected and schema ensured")

    def get_session(self) -> AsyncSession:
        if self._session_factory is None:
            raise RuntimeError("Database not connected — call connect() first")
        return self._session_factory()

    async def ping(self) -> bool:
        try:
            async with self._engine.connect() as conn:
                from sqlalchemy import text
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
            self._engine = None


_database: Database | None = None


def get_database() -> Database:
    global _database
    if _database is None:
        raise RuntimeError("Database not initialised")
    return _database


def init_database(settings: Settings) -> Database:
    global _database
    _database = Database(settings)
    return _database
