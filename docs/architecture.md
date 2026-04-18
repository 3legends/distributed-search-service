# Distributed Document Search Service — Architecture & Production Readiness

> **Author:** Aman Prakash (Software Engineer)
> **Version:** 1.0.0

---

## 1. System Architecture

### 1.1 High-Level Component Diagram

```
                              ┌─────────────────────────────────────────────────┐
                              │               Client (Browser / API)            │
                              └─────────────────────┬───────────────────────────┘
                                                     │ HTTPS
                                                     ▼
                              ┌─────────────────────────────────────────────────┐
                              │               Load Balancer / API Gateway       │
                              │         (rate limit, TLS termination, auth)     │
                              └─────────────────────┬───────────────────────────┘
                                                     │
                          ┌──────────────────────────▼──────────────────────────┐
                          │                  FastAPI Application                │
                          │                                                     │
                          │  ┌─────────────┐  ┌──────────────┐  ┌───────────┐   │
                          │  │  Tenant     │  │  Rate Limiter│  │ Request   │   │
                          │  │  Middleware │  │  Middleware  │  │ Logger    │   │ 
                          │  └──────┬──────┘  └──────┬───────┘  └─────┬─────┘   │
                          │         └─────────────────▼────────────────┘        │
                          │                    ┌────────────┐                   │
                          │                    │  API Layer │                   │
                          │                    │  v1 Routes │                   │
                          │                    └─────┬──────┘                   │
                          │          ┌───────────────┼─────────────────┐        │
                          │          ▼               ▼                 ▼        │
                          │   ┌─────────────┐ ┌──────────────┐ ┌───────────┐    │
                          │   │  Document   │ │    Search    │ │  Health   │    │
                          │   │  Service    │ │   Service    │ │  Service  │    │
                          │   └──────┬──────┘ └──────┬───────┘ └─────┬─────┘    │
                          └──────────┼───────────────┼───────────────┼─────────-┘
                                     │               │               │
               ┌─────────────────────▼───┐     ┌────▼───────┐  ┌────▼───────┐
               │     Elasticsearch 8.x   │     │   Redis    │  │ PostgreSQL │
               │  ┌────────┐ ┌─────────┐ │     │  ┌──────┐  │  │  ┌───────┐ │
               │  │docs_   │ │docs_    │ │     │  │Cache │  │  │  │Tenant │ │
               │  │acme_   │ │globex_  │ │     │  └──────┘  │  │  │Meta   │ │
               │  │corp    │ │inc      │ │     │  ┌──────┐  │  │  └───────┘ │
               │  └────────┘ └─────────┘ │     │  │ Rate │  │  │  ┌───────┐ │
               │   (per-tenant indices)  │     │  │Limit │  │  │  │Doc    │ │
               └─────────────────────────┘     │  └──────┘  │  │  │Meta   │ │
                                               └────────────┘  │  └───────┘ │
                                                               └────────────┘
```

### 1.2 Technology Choices & Rationale

| Component       | Choice           | Rationale                                                                    |
|-----------------|------------------|------------------------------------------------------------------------------|
| API Framework   | FastAPI          | Async-first, automatic OpenAPI docs, Pydantic validation, high performance   |
| Search Engine   | Elasticsearch 8  | Purpose-built for full-text search, BM25 ranking, horizontal sharding        |
| Cache           | Redis            | Sub-millisecond reads, atomic Lua scripts for rate limiting, TTL support      |
| Metadata DB     | PostgreSQL       | ACID transactions for tenant registry and audit trail, rich SQL queries       |
| Containerisation| Docker Compose   | Reproducible local dev; same images promote to Kubernetes in production       |

---

## 2. Data Flow Diagrams

### 2.1 Document Indexing Flow

```
Client
  │
  │  POST /api/v1/documents
  │  Header: X-Tenant-ID: acme_corp
  │  Body: { title, content, tags, metadata }
  ▼
TenantMiddleware
  │  Validate & extract tenant_id → request.state
  ▼
RateLimiter (Redis sliding window)
  │  Check requests/min quota for tenant
  ▼
DocumentService.create_document()
  │
  ├─ 1. Ensure ES index exists for tenant (docs_acme_corp)
  │       └─ Create index with mapping if absent
  │
  ├─ 2. Generate ULID → doc_id
  │
  ├─ 3. Index document in Elasticsearch
  │       └─ refresh=wait_for (prototype) / false (production)
  │
  ├─ 4. Write metadata row to PostgreSQL
  │       └─ id, tenant_id, title, tags, created_at
  │
  └─ 5. Invalidate tenant search cache
          └─ Redis DEL search:acme_corp:*

  └─ Return 202 { id, tenant_id, indexed: true }
```

### 2.2 Search Flow (Cache-Aside Pattern)

```
Client
  │
  │  GET /api/v1/search?q=elasticsearch&page=1&size=10
  │  Header: X-Tenant-ID: acme_corp
  ▼
TenantMiddleware → RateLimiter
  ▼
SearchService.search()
  │
  ├─ 1. Generate cache key:
  │       sha256("elasticsearch|1|10|[]")[:16]
  │       → "search:acme_corp:a3f9c2b1..."
  │
  ├─ 2. Redis GET cache key
  │       ├─ HIT  → Return cached result (cached=true), done ✓
  │       └─ MISS → continue
  │
  ├─ 3. Build ES multi-match query
  │       { multi_match: { query: "elasticsearch",
  │                        fields: ["title^2","content"],
  │                        fuzziness: "AUTO" } }
  │
  ├─ 4. Execute ES search on index docs_acme_corp
  │
  ├─ 5. Map hits to SearchHit objects (with highlights)
  │
  ├─ 6. Redis SET cache key = JSON result, TTL=120s
  │
  └─ 7. Return SearchResponse { total, results, took_ms, cached=false }
```

---

## 3. Storage Strategy

### Elasticsearch — Primary Search Store
- **Per-tenant indices** (`docs_{tenant_id}`): true data isolation, no cross-tenant query leakage
- **Mapping**: `title` (text + keyword), `content` (text), `tags` (keyword), `metadata` (dynamic object)
- **Analyzer**: standard English with stopwords for title/content
- **Sharding**: 1 shard per index in prototype; scale to 3–5 per index as volume grows

### Redis — Cache + Rate Limiter
- **Search cache**: key `search:{tenant_id}:{query_hash}`, TTL 120s
- **Rate limiter**: sorted sets with timestamps as members (sliding window)
- **Invalidation**: all `search:{tenant_id}:*` keys flushed on any document write for that tenant

### PostgreSQL — Metadata + Audit
- **Tenants table**: registry of known tenants, `is_active` flag
- **document_meta table**: lightweight shadow of every document — `id`, `tenant_id`, `title`, `tags`, `is_deleted`, timestamps
- **Purpose**: SQL-level audit queries, tenant ownership verification, and compliance hard-delete guarantees
- **Trade-off**: dual-write introduces a consistency window; ES is the read-path ground truth

---

## 4. API Design

### Endpoints

| Method | Path                      | Auth              | Description                        |
|--------|---------------------------|-------------------|------------------------------------|
| GET    | /health                   | None              | Liveness + dependency status       |
| POST   | /api/v1/tenants           | None (admin only) | Register a new tenant              |
| GET    | /api/v1/tenants           | None (admin only) | List all tenants                   |
| POST   | /api/v1/documents         | X-Tenant-ID       | Index a new document               |
| GET    | /api/v1/documents/{id}    | X-Tenant-ID       | Retrieve full document             |
| DELETE | /api/v1/documents/{id}    | X-Tenant-ID       | Remove a document                  |
| GET    | /api/v1/search            | X-Tenant-ID       | Full-text search with pagination   |

### Request / Response Contract Examples

**POST /api/v1/documents**
```json
// Request
{
  "title":    "Elasticsearch Best Practices",
  "content":  "Use index aliases for zero-downtime re-indexing...",
  "tags":     ["elasticsearch", "performance"],
  "metadata": {"author": "Jane", "year": 2024}
}

// Response 202
{
  "id":        "01HQ123ABC...",
  "tenant_id": "acme_corp",
  "indexed":   true,
  "message":   "Document indexed successfully"
}
```

**GET /api/v1/search?q=elasticsearch&page=1&size=5**
```json
{
  "query":     "elasticsearch",
  "tenant_id": "acme_corp",
  "total":     42,
  "page":      1,
  "size":      5,
  "took_ms":   18.4,
  "cached":    false,
  "results": [
    {
      "id":              "01HQ123ABC...",
      "title":           "<em>Elasticsearch</em> Best Practices",
      "content_snippet": "Use index aliases for zero-downtime <em>re-indexing</em>...",
      "score":           2.34,
      "tags":            ["elasticsearch", "performance"],
      "highlights":      { "title": ["<em>Elasticsearch</em>..."], "content": ["..."] },
      "created_at":      "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

## 5. Multi-Tenancy Approach

**Strategy**: Index-per-tenant isolation

Each tenant's documents live in their own dedicated Elasticsearch index (`docs_{tenant_id}`). This means:

- **Security**: It is architecturally impossible to return another tenant's documents — each query runs against a single tenant-owned index
- **Performance**: Index-level query isolation; one tenant's heavy query does not block another's
- **Operational flexibility**: Different retention policies, index settings, or shard counts per tenant
- **Scalability limit**: ES recommends < 1,000 indices per cluster. For 10,000+ tenants, migrate to a shared index with `tenant_id` field + document-level security (DLS) in Elasticsearch's X-Pack

**Tenant enforcement** layers:
1. `TenantMiddleware` validates and extracts `X-Tenant-ID` from every request
2. `ElasticsearchClient.index_name(tenant_id)` scopes every ES operation
3. PostgreSQL rows are always filtered by `tenant_id`

---

## 6. Caching Strategy

| Layer          | Implementation        | TTL       | Invalidation                        |
|----------------|-----------------------|-----------|-------------------------------------|
| Search results | Redis (cache-aside)   | 120s      | Write to tenant → flush all tenant search keys |
| Document GET   | (Add Redis get-by-ID) | 60s       | On delete                           |
| Rate limit     | Redis sorted sets     | Window+1s | Rolling expiry                      |

The cache is **best-effort** — failures are swallowed and the request falls through to ES. A Redis outage degrades performance but never breaks correctness.

---

## 7. Consistency Model and Trade-offs

The system is **eventually consistent** with a short consistency window:

- `refresh=wait_for` in the prototype ensures indexed documents appear in the next search (1s max). In production, use `refresh=false` and accept ~1s lag for throughput.
- The Redis cache introduces a 120-second staleness window for search results. Documents deleted during this window may still appear in cached results.
- PostgreSQL metadata and Elasticsearch are written in sequence (not a distributed transaction). A failure between steps leaves the systems temporarily inconsistent — a background reconciler job would clean this up in production.

**Chosen position**: AP (Available + Partition-tolerant) per CAP theorem. We sacrifice strict consistency for availability and latency.

---

## 8. Message Queue Usage (Async Indexing)

In the prototype, indexing is synchronous within the request. The architecture is designed to evolve:

```
Indexing Pipeline (production target):
  API → Kafka/SQS → Indexing Worker → Elasticsearch
                  ↘ PostgreSQL

Benefits:
  - API returns instantly (fire-and-forget)
  - Indexing retries on ES failure without user impact
  - Bulk indexing can be batched for throughput
  - Decoupled scaling of API vs. indexing workers
```

The `DocumentService` is already structured to support this — move the ES + PG write from the API thread into a Celery worker task with minimal refactoring.

---

## 9. Production Readiness Analysis

### 9.1 Scalability — Handling 100x Growth

**Current**: 10M docs, 1,000 req/s
**Target**:  1B docs, 100,000 req/s

| Dimension         | Strategy                                                                 |
|-------------------|--------------------------------------------------------------------------|
| Search throughput | Horizontal ES nodes; each index distributes across shards                |
| API throughput    | Scale app containers behind a load balancer (stateless — trivially horizontal) |
| Indexing pipeline | Switch to async Kafka pipeline with parallel indexing workers            |
| Cache             | Redis Cluster for horizontal cache scaling                               |
| Tenant count      | Migrate from index-per-tenant to shared index + DLS for 10,000+ tenants |
| Read replicas     | Add ES replica shards; read from replicas, write to primary              |

### 9.2 Resilience

| Concern            | Strategy                                                                |
|--------------------|-------------------------------------------------------------------------|
| ES unavailable     | Circuit breaker (e.g. tenacity/pybreaker) around ES client; degrade to cache-only reads |
| Redis unavailable  | Cache miss → ES directly; rate limiter fails open                       |
| Postgres down      | Reads still work (ES is the read path); writes degrade gracefully       |
| Retry strategy     | Exponential backoff with jitter on transient 5xx errors                 |
| Bulkhead isolation | Separate thread/connection pools per dependency; one blowout doesn't cascade |
| Failover           | ES multi-zone cluster; Redis Sentinel or Redis Cluster; PG primary-replica with auto-failover |

### 9.3 Security

| Area                 | Implementation                                                          |
|----------------------|-------------------------------------------------------------------------|
| Authentication       | JWT Bearer tokens validated at API Gateway layer (or FastAPI dependency)|
| Multi-tenant isolation | Index-per-tenant; `tenant_id` enforced in every operation             |
| Transport encryption | TLS everywhere (HTTPS ingress, ES + Redis in-transit via TLS)          |
| Secrets management   | HashiCorp Vault or AWS Secrets Manager for DB/ES credentials           |
| Input validation     | Pydantic models reject malformed input before it reaches service layer  |
| Rate limiting        | Per-tenant sliding window prevents abuse and noisy-neighbour problems   |
| Encryption at rest   | ES disk encryption; RDS/ElastiCache encryption at rest enabled          |

### 9.4 Observability

```
Metrics (Prometheus / Grafana):
  - Request latency (p50, p95, p99) per tenant and endpoint
  - Cache hit/miss rate
  - ES query latency distribution
  - Rate-limit rejection rate per tenant
  - Document indexing throughput and lag

Logging (Structured JSON → ELK / CloudWatch):
  - Every request: method, path, tenant_id, status_code, duration_ms
  - ES errors with query bodies (sanitised)
  - Cache events (hit/miss/invalidation)

Distributed Tracing (OpenTelemetry → Jaeger / Tempo):
  - Trace: API → Service → ES + Redis + PG spans
  - Pinpoint where latency spikes occur in the call graph

Alerting:
  - p99 > 500ms for any tenant → PagerDuty
  - Error rate > 1% → alert
  - ES cluster health Yellow/Red → critical alert
```

### 9.5 Performance Optimisation

- **ES index aliases**: allow live re-indexing without downtime (create new index, re-index data, flip alias)
- **Query optimisation**: profile slow queries with ES `_profile` API; add `filter` context for non-scoring clauses
- **Bulk indexing**: use ES `_bulk` API for batch document ingestion (10–100x throughput gain)
- **Connection pooling**: ES client maintains persistent HTTP/2 connections; PG uses asyncpg pool
- **Field data cache**: for aggregation-heavy queries, pre-warm ES fielddata cache
- **Denormalisation**: store computed fields (word count, language) at index time to avoid runtime computation

### 9.6 Deployment Strategy

```
Blue-Green Deployment:
  ┌──────────────────────┐     ┌──────────────────────┐
  │   Blue (v1.0.0)      │     │   Green (v1.1.0)      │
  │   Production Live    │     │   Staging / Idle      │
  └──────────┬───────────┘     └───────────┬───────────┘
             │                              │
             └──────────┬───────────────────┘
                        │
                Load Balancer
                  (flip traffic)

Steps:
  1. Deploy v1.1.0 to Green environment
  2. Run smoke tests + integration tests on Green
  3. Shift 5% traffic to Green (canary)
  4. Monitor error rates and latency for 10 minutes
  5. If healthy → shift 100% to Green (atomic DNS/LB flip)
  6. Keep Blue alive for 15 minutes → instant rollback if needed
  7. Decommission Blue after confidence period
```

**Zero-downtime ES schema changes**: Use index aliases + re-index pattern. Never change a live index mapping.

### 9.7 SLA: Achieving 99.95% Availability

99.95% = 4.38 hours of allowed downtime per year (~26 minutes/month).

| Strategy                          | Contribution                          |
|-----------------------------------|---------------------------------------|
| Multi-AZ ES cluster (3 nodes)     | Survives 1 AZ failure                 |
| Redis Sentinel / Cluster          | Automatic failover in < 30s           |
| PG Multi-AZ (RDS)                 | Synchronous standby, < 60s failover   |
| Blue-green deploys                | Zero-downtime releases                |
| Circuit breakers per dependency   | Prevents cascading failures           |
| Auto-scaling app tier             | Absorbs traffic spikes                |
| Health check + automatic restart  | Container-level self-healing          |
| Global CDN for static responses   | Edge caching reduces origin load      |

---

## 10. AI Tool Disclosure

This project was designed and implemented with the assistance of an AI coding assistant (Claude, Anthropic). All architectural decisions, trade-off analysis, and code structure were authored by the engineer; the AI was used as a high-velocity pair programmer to accelerate implementation of boilerplate, test scaffolding, and documentation formatting. All generated code was reviewed and validated against the requirements.

---

## 11. Assumptions & Known Limitations (Prototype)

1. **Security**: The tenant header is trusted without JWT validation — in production, an API Gateway would authenticate and inject the tenant claim
2. **Consistency**: `refresh=wait_for` is used in ES writes for prototype correctness; in production this would be `false` for throughput
3. **Indexing pipeline**: Synchronous in-request indexing; a Kafka/Celery pipeline is documented but not implemented
4. **Index-per-tenant**: Practical up to ~1,000 tenants; beyond that, migrate to shared index with DLS
5. **Tests**: Mocked infrastructure — integration tests against real ES/Redis would be added in CI
