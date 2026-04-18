"""
RateLimiter
-----------
Per-tenant sliding-window rate limiter backed by Redis.
Fail-open: if Redis is unavailable the request is allowed through.
"""
from __future__ import annotations

import logging

from config import Settings
from core.redis_client import RedisClient
from core.exceptions import RateLimitExceededError

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis: RedisClient, settings: Settings) -> None:
        self._redis    = redis
        self._settings = settings

    async def check(self, tenant_id: str) -> None:
        """
        Raises RateLimitExceededError if the tenant has exhausted their quota.
        """
        allowed, retry_after = await self._redis.sliding_window_check(
            tenant_id=tenant_id,
            limit=self._settings.rate_limit_requests,
            window_seconds=self._settings.rate_limit_window_seconds,
        )
        if not allowed:
            logger.warning(
                "Rate limit hit for tenant '%s'. Retry-after: %ds",
                tenant_id, retry_after,
            )
            raise RateLimitExceededError(tenant_id, retry_after)
