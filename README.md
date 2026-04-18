# Distributed Document Search Service

A production-grade prototype of a distributed document search service with multi-tenancy, full-text search, Redis caching, and per-tenant rate limiting.

---

## Quick Start

### Prerequisites
- Docker ≥ 24 and Docker Compose ≥ 2
- Python 3.11+ (for running tests / seed script locally)

### 1. Start all services

```bash
cp .env.example .env
make up          # or: docker-compose up -d --build
```

Wait ~30 seconds for Elasticsearch to initialise, then verify:

```bash
curl http://localhost:8000/health | python3 -m json.tool
```

Expected output:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "dependencies": {
    "elasticsearch": { "status": "ok", "latency_ms": 4.2 },
    "redis":         { "status": "ok", "latency_ms": 0.8 },
    "postgres":      { "status": "ok", "latency_ms": 2.1 }
  }
}
```

### 2. Explore the API docs

Open **http://localhost:8000/docs** in your browser — fully interactive Swagger UI.

### 3. Seed sample data

```bash
make seed        # or: python3 scripts/seed_data.py
```

This registers two tenants (`acme_corp`, `globex_inc`) and indexes 8 sample documents.

### 4. Run a search

```bash
curl "http://localhost:8000/api/v1/search?q=distributed" \
  -H "X-Tenant-ID: acme_corp" | python3 -m json.tool
```

### 5. Run smoke tests

```bash
make smoke       # or: bash scripts/sample_requests.sh
```

---

## Running Tests (no Docker needed)

```bash
cd app
pip install -r requirements.txt
PYTHONPATH=. pytest ../tests -v
```

All tests use mocked infrastructure — no external services required.

---

## Project Structure

```
distributed-search-service/
├── docker-compose.yml          # Wires app + ES + Redis + Postgres
├── Makefile                    # Dev shortcuts
├── .env.example                # Environment variable reference
│
├── app/                        # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── main.py                 # App factory, lifespan, exception handlers
│   ├── config.py               # Pydantic settings (env-var driven)
│   ├── dependencies.py         # FastAPI DI wiring
│   │
│   ├── core/                   # Infrastructure clients
│   │   ├── elasticsearch.py    # Async ES client, per-tenant index management
│   │   ├── redis_client.py     # Async Redis (cache + sliding-window RL)
│   │   ├── database.py         # SQLAlchemy async + schema
│   │   └── exceptions.py       # Domain exception hierarchy
│   │
│   ├── models/
│   │   └── document.py         # All Pydantic request/response schemas
│   │
│   ├── services/               # Business logic layer
│   │   ├── document_service.py # Document CRUD (ES + Postgres + cache)
│   │   ├── search_service.py   # ES query builder, cache-aside
│   │   └── rate_limiter.py     # Per-tenant quota enforcement
│   │
│   ├── middleware/
│   │   └── tenant.py           # X-Tenant-ID extraction + validation
│   │
│   └── api/v1/                 # HTTP layer (thin, no business logic)
│       ├── router.py
│       ├── documents.py        # POST/GET/DELETE /documents
│       ├── search.py           # GET /search
│       ├── tenants.py          # POST/GET /tenants
│       └── health.py           # GET /health
│
├── tests/
│   ├── conftest.py             # Shared fixtures (all infra mocked)
│   ├── test_documents.py
│   ├── test_search.py
│   └── test_health.py
│
├── scripts/
│   ├── seed_data.py            # Populate sample documents
│   └── sample_requests.sh     # Manual smoke tests (curl)
│
└── docs/
    └── architecture.md         # Architecture + Production Readiness doc
```

---

## API Reference

All endpoints (except `/health` and `/api/v1/tenants`) require the `X-Tenant-ID` header.

### Health
```
GET /health
```

### Tenants
```
POST /api/v1/tenants          { "id": "my_company", "name": "My Company" }
GET  /api/v1/tenants
GET  /api/v1/tenants/{id}
```

### Documents
```
POST   /api/v1/documents        Index a document
GET    /api/v1/documents/{id}   Retrieve a document
DELETE /api/v1/documents/{id}   Remove a document
```

### Search
```
GET /api/v1/search?q={query}[&page=1&size=10&tags=a,b&fuzzy=true]
```

| Param   | Default | Description                           |
|---------|---------|---------------------------------------|
| `q`     | —       | Search query (required)               |
| `page`  | 1       | Page number                           |
| `size`  | 10      | Results per page (max 100)            |
| `tags`  | —       | Comma-separated tag filter            |
| `fuzzy` | true    | Enable fuzzy/typo matching            |

---

## Environment Variables

| Variable                   | Default                                              | Description                    |
|----------------------------|------------------------------------------------------|--------------------------------|
| `ELASTICSEARCH_URL`        | `http://elasticsearch:9200`                          | ES connection string           |
| `REDIS_URL`                | `redis://redis:6379/0`                               | Redis connection string        |
| `DATABASE_URL`             | `postgresql+asyncpg://postgres:password@postgres:5432/searchdb` | PG connection string |
| `CACHE_TTL_SECONDS`        | `300`                                                | Search result cache TTL        |
| `RATE_LIMIT_REQUESTS`      | `100`                                                | Requests per window per tenant |
| `RATE_LIMIT_WINDOW_SECONDS`| `60`                                                 | Rate limit window in seconds   |
| `DEBUG`                    | `false`                                              | Enable debug logging           |

---

## Architecture Highlights

- **Per-tenant ES indices** — true data isolation; `docs_acme_corp` and `docs_globex_inc` are physically separate
- **Cache-aside pattern** — search results cached in Redis for 120s; invalidated on document write
- **Sliding-window rate limiter** — Redis sorted set per tenant; fails open on Redis unavailability
- **Layered architecture** — `API → Services → Core clients`; each layer has a single responsibility
- **Async everywhere** — FastAPI + asyncpg + elasticsearch-py async + redis-py async; zero blocking I/O
- **Graceful degradation** — Redis down → bypass cache; ES down → circuit break + error response

See [`docs/architecture.md`](docs/architecture.md) for full architecture, production readiness analysis, and deployment strategy.
