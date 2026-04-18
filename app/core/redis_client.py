import logging
from typing import Any

import redis.asyncio as aioredis
from config import Settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client with helpers for cache and rate limiting."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: aioredis.ConnectionPool | None = None
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._pool = aioredis.ConnectionPool.from_url(
            self._settings.redis_url,
            max_connections=20,
            decode_responses=True,
        )
        self._client = aioredis.Redis(connection_pool=self._pool)
        logger.info("Redis connection pool initialised")

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("RedisClient not connected — call connect() first")
        return self._client

    async def ping(self) -> bool:
        try:
            return await self.client.ping()
        except Exception:
            return False

    # ------------------------------------------------------------------ cache

    async def get_cache(self, key: str) -> str | None:
        try:
            return await self.client.get(key)
        except Exception as exc:
            logger.warning("Cache GET failed for key '%s': %s", key, exc)
            return None

    async def set_cache(self, key: str, value: str, ttl: int | None = None) -> None:
        try:
            await self.client.setex(key, ttl or self._settings.cache_ttl_seconds, value)
        except Exception as exc:
            logger.warning("Cache SET failed for key '%s': %s", key, exc)

    async def delete_cache(self, key: str) -> None:
        try:
            await self.client.delete(key)
        except Exception as exc:
            logger.warning("Cache DELETE failed for key '%s': %s", key, exc)

    async def delete_by_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Use sparingly in prod."""
        try:
            keys = await self.client.keys(pattern)
            if keys:
                return await self.client.delete(*keys)
            return 0
        except Exception as exc:
            logger.warning("Cache pattern-delete failed for '%s': %s", pattern, exc)
            return 0

    # ---------------------------------------------------------- rate limiting

    async def sliding_window_check(
        self,
        tenant_id: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """
        Sliding window rate limiter.

        Returns (allowed: bool, retry_after_seconds: int).
        Uses a sorted set where each member is a timestamp.
        """
        key = f"rl:{tenant_id}"
        import time
        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = self.client.pipeline()
            # Remove expired entries
            pipe.zremrangebyscore(key, "-inf", window_start)
            # Count requests in window
            pipe.zcard(key)
            # Add current request
            pipe.zadd(key, {str(now): now})
            # Set expiry so the key auto-cleans
            pipe.expire(key, window_seconds + 1)
            results = await pipe.execute()

            current_count = results[1]
            if current_count >= limit:
                # Oldest entry tells us when the window will open again
                oldest = await self.client.zrange(key, 0, 0, withscores=True)
                retry_after = 1
                if oldest:
                    retry_after = max(1, int(window_seconds - (now - oldest[0][1])))
                return False, retry_after

            return True, 0
        except Exception as exc:
            logger.warning("Rate limiter error for tenant '%s': %s", tenant_id, exc)
            return True, 0  # fail-open so a Redis blip doesn't kill the API

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pool:
            await self._pool.aclose()
            self._pool = None


_redis_client: RedisClient | None = None


def get_redis_client() -> RedisClient:
    global _redis_client
    if _redis_client is None:
        raise RuntimeError("RedisClient not initialised")
    return _redis_client


def init_redis_client(settings: Settings) -> RedisClient:
    global _redis_client
    _redis_client = RedisClient(settings)
    return _redis_client
