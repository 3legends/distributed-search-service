from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Application
    app_name: str = "Distributed Document Search Service"
    app_version: str = "1.0.0"
    debug: bool = False

    # Elasticsearch
    elasticsearch_url: str = "http://elasticsearch:9200"
    es_index_prefix: str = "docs"
    es_shards: int = 1
    es_replicas: int = 0

    # Redis
    redis_url: str = "redis://redis:6379/0"
    cache_ttl_seconds: int = 300  # 5 minutes

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:password@postgres:5432/searchdb"

    # Rate Limiting (per tenant)
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # Search
    max_search_results: int = 100
    default_search_results: int = 10


@lru_cache()
def get_settings() -> Settings:
    return Settings()
