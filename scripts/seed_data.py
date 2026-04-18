#!/usr/bin/env python3
"""
seed_data.py
------------
Populates the search service with realistic sample documents across
two tenants so you can immediately test search queries.

Usage:
    python scripts/seed_data.py [--url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import List

import httpx

BASE_URL = "http://localhost:8000"

# Sample tenants
TENANTS = [
    {"id": "acme_corp",    "name": "Acme Corporation"},
    {"id": "globex_inc",   "name": "Globex Inc"},
]

# Sample documents per tenant
DOCUMENTS: dict[str, List[dict]] = {
    "acme_corp": [
        {
            "title":   "Introduction to Microservices Architecture",
            "content": (
                "Microservices architecture is an approach to developing a single application "
                "as a suite of small services, each running in its own process and communicating "
                "with lightweight mechanisms, often an HTTP resource API. These services are built "
                "around business capabilities and independently deployable by fully automated "
                "deployment machinery. There is a bare minimum of centralised management of these "
                "services, which may be written in different programming languages and use different "
                "data storage technologies."
            ),
            "tags":     ["microservices", "architecture", "distributed-systems"],
            "metadata": {"author": "Elon Musk", "category": "Engineering", "year": 2024},
        },
        {
            "title":   "CAP Theorem Explained",
            "content": (
                "The CAP theorem states that any distributed data store can only provide two of the "
                "following three guarantees: Consistency (every read receives the most recent write), "
                "Availability (every request receives a response, though not necessarily the most "
                "recent), and Partition tolerance (the system continues to operate despite an arbitrary "
                "number of messages being dropped or delayed by the network). In the presence of a "
                "network partition, one has to choose between consistency and availability."
            ),
            "tags":     ["cap-theorem", "distributed-systems", "database"],
            "metadata": {"author": "Eric Brewer", "category": "Theory"},
        },
        {
            "title":   "Redis as a Distributed Cache",
            "content": (
                "Redis is an in-memory data structure store used as a distributed, in-memory key-value "
                "database, cache and message broker. It supports data structures such as strings, hashes, "
                "lists, sets, sorted sets with range queries, bitmaps, hyperloglogs, geospatial indexes "
                "and streams. Redis has built-in replication, Lua scripting, LRU eviction, transactions "
                "and different levels of on-disk persistence."
            ),
            "tags":     ["redis", "cache", "performance"],
            "metadata": {"author": "Salvatore Sanfilippo", "category": "Infrastructure"},
        },
        {
            "title":   "Elasticsearch Full-Text Search Guide",
            "content": (
                "Elasticsearch is a distributed, RESTful search and analytics engine built on Apache "
                "Lucene. It allows you to store, search, and analyze big volumes of data quickly and "
                "in near real time. It is generally used as the underlying engine for applications "
                "that have complex search features and requirements. Elasticsearch provides relevance "
                "ranking using the BM25 algorithm and supports full-text search, structured queries, "
                "fuzzy matching, and aggregations."
            ),
            "tags":     ["elasticsearch", "search", "lucene"],
            "metadata": {"author": "Shay Banon", "category": "Search"},
        },
        {
            "title":   "Kubernetes Horizontal Pod Autoscaling",
            "content": (
                "Kubernetes Horizontal Pod Autoscaler automatically scales the number of Pods in a "
                "deployment or replica set based on observed CPU utilization or other custom metrics. "
                "This allows your application to handle increased load by adding more pod replicas and "
                "to save resources during low-traffic periods. The autoscaler periodically fetches "
                "metrics from the Metrics Server and computes the desired number of replicas."
            ),
            "tags":     ["kubernetes", "scaling", "devops", "cloud"],
            "metadata": {"category": "Operations"},
        },
    ],
    "globex_inc": [
        {
            "title":   "Event-Driven Architecture with Kafka",
            "content": (
                "Apache Kafka is an open-source distributed event streaming platform. It is used for "
                "high-performance data pipelines, streaming analytics, data integration, and "
                "mission-critical applications. Kafka stores events durably and reliably and allows "
                "consumers to replay messages. It is widely used in event-driven microservices "
                "architectures to decouple producers and consumers."
            ),
            "tags":     ["kafka", "event-driven", "streaming", "microservices"],
            "metadata": {"author": "Jay Kreps", "category": "Messaging"},
        },
        {
            "title":   "PostgreSQL Performance Tuning",
            "content": (
                "PostgreSQL query performance can be significantly improved through proper indexing, "
                "query planning, and configuration tuning. Key areas include B-tree index selection, "
                "partial indexes, covering indexes, EXPLAIN ANALYZE output interpretation, work_mem "
                "configuration, connection pooling with PgBouncer, and vacuum settings. Proper schema "
                "design with appropriate normalization levels also plays a major role in query performance."
            ),
            "tags":     ["postgresql", "database", "performance", "sql"],
            "metadata": {"category": "Database"},
        },
        {
            "title":   "Zero-Downtime Deployments with Blue-Green Strategy",
            "content": (
                "Blue-green deployment is a technique that reduces downtime and risk by running two "
                "identical production environments called Blue and Green. At any time, only one of the "
                "environments is live, with the live environment serving all production traffic. "
                "When deploying a new version, it is deployed to the idle environment. After testing, "
                "traffic is switched to the new version. This allows instant rollback by switching traffic back."
            ),
            "tags":     ["deployment", "blue-green", "devops", "zero-downtime"],
            "metadata": {"category": "Operations"},
        },
    ],
}


async def register_tenant(client: httpx.AsyncClient, tenant: dict) -> bool:
    response = await client.post("/api/v1/tenants", json=tenant)
    if response.status_code in (201, 409):  # 409 = already exists
        print(f"  ✓ Tenant '{tenant['id']}' ready")
        return True
    print(f"  ✗ Failed to register tenant '{tenant['id']}': {response.text}")
    return False


async def index_document(
    client: httpx.AsyncClient,
    tenant_id: str,
    doc: dict,
) -> bool:
    response = await client.post(
        "/api/v1/documents",
        json=doc,
        headers={"X-Tenant-ID": tenant_id},
    )
    if response.status_code == 202:
        doc_id = response.json().get("id", "?")
        print(f"  ✓ '{doc['title'][:50]}…' → {doc_id}")
        return True
    print(f"  ✗ Failed: {doc['title'][:50]} — {response.status_code}: {response.text}")
    return False


async def main(base_url: str) -> None:
    print(f"\n🌱 Seeding data to {base_url}\n")

    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        # Health check first
        resp = await client.get("/health")
        if resp.status_code not in (200, 503):
            print(f"✗ Service not reachable at {base_url}")
            sys.exit(1)

        # Register tenants
        print("── Registering tenants …")
        for tenant in TENANTS:
            await register_tenant(client, tenant)

        # Index documents
        total_ok = 0
        for tenant_id, docs in DOCUMENTS.items():
            print(f"\n── Indexing documents for tenant '{tenant_id}' …")
            for doc in docs:
                ok = await index_document(client, tenant_id, doc)
                if ok:
                    total_ok += 1

    print(f"\n✅ Done! {total_ok} documents indexed across {len(TENANTS)} tenants.")
    print("\nTry a search:")
    print(f"  curl '{base_url}/api/v1/search?q=distributed' -H 'X-Tenant-ID: acme_corp' | python3 -m json.tool")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=BASE_URL)
    args = parser.parse_args()
    asyncio.run(main(args.url))
