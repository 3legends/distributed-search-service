import logging
from typing import Any

from elasticsearch import AsyncElasticsearch, NotFoundError, ConnectionError
from config import Settings

logger = logging.getLogger(__name__)

# Index mapping for documents — optimised for full-text search + faceting
DOCUMENT_MAPPING = {
    "mappings": {
        "properties": {
            "id":         {"type": "keyword"},
            "tenant_id":  {"type": "keyword"},
            "title":      {"type": "text", "analyzer": "standard",
                           "fields": {"keyword": {"type": "keyword"}}},
            "content":    {"type": "text", "analyzer": "standard"},
            "tags":       {"type": "keyword"},
            "metadata":   {"type": "object", "dynamic": True},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "standard": {
                    "type":      "standard",
                    "stopwords": "_english_",
                }
            }
        },
    },
}


class ElasticsearchClient:
    """Thin wrapper around AsyncElasticsearch with index-lifecycle helpers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncElasticsearch | None = None

    def _build_client(self) -> AsyncElasticsearch:
        return AsyncElasticsearch(
            self._settings.elasticsearch_url,
            retry_on_timeout=True,
            max_retries=3,
            request_timeout=30,
        )

    @property
    def client(self) -> AsyncElasticsearch:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def index_name(self, tenant_id: str) -> str:
        """Each tenant owns a dedicated index — true data isolation."""
        safe = tenant_id.lower().replace(" ", "_")
        return f"{self._settings.es_index_prefix}_{safe}"

    async def ensure_index(self, tenant_id: str) -> None:
        """Create the tenant's index if it doesn't exist yet."""
        name = self.index_name(tenant_id)
        try:
            exists = await self.client.indices.exists(index=name)
            if not exists:
                mapping = dict(DOCUMENT_MAPPING)
                mapping["settings"] = {
                    **DOCUMENT_MAPPING["settings"],
                    "number_of_shards":   self._settings.es_shards,
                    "number_of_replicas": self._settings.es_replicas,
                }
                await self.client.indices.create(index=name, body=mapping)
                logger.info("Created ES index '%s' for tenant '%s'", name, tenant_id)
        except Exception as exc:
            logger.error("Failed to ensure ES index for tenant '%s': %s", tenant_id, exc)
            raise

    async def ping(self) -> bool:
        try:
            return await self.client.ping()
        except ConnectionError:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None


# Module-level singleton — injected via FastAPI dependency
_es_client: ElasticsearchClient | None = None


def get_es_client() -> ElasticsearchClient:
    global _es_client
    if _es_client is None:
        raise RuntimeError("ElasticsearchClient not initialised")
    return _es_client


def init_es_client(settings: Settings) -> ElasticsearchClient:
    global _es_client
    _es_client = ElasticsearchClient(settings)
    return _es_client
