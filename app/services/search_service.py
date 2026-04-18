"""
SearchService
-------------
Builds and executes Elasticsearch queries with:
  - Multi-match full-text search (title boosted 2x)
  - Fuzzy matching for typo tolerance
  - Result highlighting
  - Tag filtering
  - Redis result caching (cache-aside pattern)
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from elasticsearch import NotFoundError

from core.elasticsearch import ElasticsearchClient
from core.redis_client import RedisClient
from core.exceptions import SearchServiceError
from models.document import SearchHit, SearchResponse

logger = logging.getLogger(__name__)

# Cache TTL for search results (seconds)
_SEARCH_CACHE_TTL = 120


class SearchService:
    def __init__(self, es: ElasticsearchClient, redis: RedisClient) -> None:
        self._es    = es
        self._redis = redis

    async def search(
        self,
        tenant_id: str,
        query:     str,
        page:      int  = 1,
        size:      int  = 10,
        tags:      Optional[List[str]] = None,
        fuzzy:     bool = True,
    ) -> SearchResponse:
        cache_key = self._cache_key(tenant_id, query, page, size, tags)

        # -------- Cache-aside: try cache first --------
        cached = await self._redis.get_cache(cache_key)
        if cached:
            logger.debug("Cache HIT for key '%s'", cache_key)
            data = json.loads(cached)
            data["cached"] = True
            return SearchResponse(**data)

        # -------- Build ES query ----------------------
        start_ms = time.monotonic()
        es_query = self._build_query(query, tags=tags, fuzzy=fuzzy)
        from_    = (page - 1) * size

        try:
            resp = await self._es.client.search(
                index=self._es.index_name(tenant_id),
                body=es_query,
                from_=from_,
                size=size,
                _source=["id", "title", "content", "tags", "created_at"],
            )
        except NotFoundError:
            # Tenant index doesn't exist yet — return empty result set
            return SearchResponse(
                query=query,
                tenant_id=tenant_id,
                total=0,
                page=page,
                size=size,
                took_ms=0.0,
                cached=False,
                results=[],
            )
        except Exception as exc:
            logger.error("Elasticsearch search error: %s", exc)
            raise SearchServiceError(str(exc)) from exc

        took_ms = (time.monotonic() - start_ms) * 1000
        hits    = resp["hits"]["hits"]
        total   = resp["hits"]["total"]["value"]

        results = [self._map_hit(h) for h in hits]

        response = SearchResponse(
            query=query,
            tenant_id=tenant_id,
            total=total,
            page=page,
            size=size,
            took_ms=round(took_ms, 2),
            cached=False,
            results=results,
        )

        # -------- Populate cache ----------------------
        await self._redis.set_cache(
            cache_key,
            response.model_dump_json(),
            ttl=_SEARCH_CACHE_TTL,
        )

        return response

    # ---------------------------------------------------------------- private

    def _build_query(
        self,
        query: str,
        tags:  Optional[List[str]] = None,
        fuzzy: bool = True,
    ) -> Dict[str, Any]:
        """
        Multi-match query over title (boosted) and content.
        Optionally filtered by tags.
        Highlight matching terms in both fields.
        """
        must: List[Dict] = [
            {
                "multi_match": {
                    "query":    query,
                    "fields":   ["title^2", "content"],
                    "type":     "best_fields",
                    "fuzziness": "AUTO" if fuzzy else "0",
                    "operator": "or",
                }
            }
        ]

        es_query: Dict[str, Any] = {"query": {"bool": {"must": must}}}

        if tags:
            es_query["query"]["bool"]["filter"] = [
                {"terms": {"tags": tags}}
            ]

        es_query["highlight"] = {
            "fields": {
                "title":   {"number_of_fragments": 1, "fragment_size": 150},
                "content": {"number_of_fragments": 3, "fragment_size": 200},
            },
            "pre_tags":  ["<em>"],
            "post_tags": ["</em>"],
        }

        return es_query

    def _map_hit(self, hit: Dict[str, Any]) -> SearchHit:
        src        = hit["_source"]
        highlights = hit.get("highlight", {})

        # Use highlighted title snippet if available, else raw title
        title_display = (
            highlights["title"][0]
            if "title" in highlights
            else src.get("title", "")
        )

        # Build a readable content snippet from highlights or raw content
        content_snippets = highlights.get("content", [])
        content_snippet  = (
            " … ".join(content_snippets)
            if content_snippets
            else src.get("content", "")[:300]
        )

        return SearchHit(
            id=src["id"],
            title=title_display,
            content_snippet=content_snippet,
            score=hit["_score"],
            tags=src.get("tags", []),
            highlights=highlights,
            created_at=src.get("created_at"),
        )

    @staticmethod
    def _cache_key(
        tenant_id: str,
        query:     str,
        page:      int,
        size:      int,
        tags:      Optional[List[str]],
    ) -> str:
        raw  = f"{query}|{page}|{size}|{sorted(tags or [])}"
        h    = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"search:{tenant_id}:{h}"
