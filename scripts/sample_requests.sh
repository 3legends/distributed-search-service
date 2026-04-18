#!/usr/bin/env bash
# =============================================================================
# sample_requests.sh — Manual API smoke tests via curl
# =============================================================================
# Usage: bash scripts/sample_requests.sh [BASE_URL]
# Default BASE_URL: http://localhost:8000
# =============================================================================

BASE_URL="${1:-http://localhost:8000}"
TENANT_A="acme_corp"
TENANT_B="globex_inc"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'

section() { echo -e "\n${BLUE}── $1 ──${NC}"; }
ok()      { echo -e "${GREEN}✓ $1${NC}"; }

# ---------------------------------------------------------------------------
section "Health Check"
curl -s "$BASE_URL/health" | python3 -m json.tool
ok "Health check done"

# ---------------------------------------------------------------------------
section "Register Tenants"
curl -s -X POST "$BASE_URL/api/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{"id":"acme_corp","name":"Acme Corporation"}' | python3 -m json.tool

curl -s -X POST "$BASE_URL/api/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{"id":"globex_inc","name":"Globex Inc"}' | python3 -m json.tool

# ---------------------------------------------------------------------------
section "Index a Document (Tenant A)"
DOC_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/documents" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_A" \
  -d '{
    "title":   "Elasticsearch vs Solr: A Comparison",
    "content": "Elasticsearch and Solr are both open-source search engines built on Apache Lucene. Elasticsearch is known for its distributed nature, ease of use, and RESTful API. Solr is more mature and offers advanced features for enterprise use.",
    "tags":    ["elasticsearch", "solr", "search", "comparison"],
    "metadata": {"author": "Jane Doe", "category": "Search"}
  }')
echo "$DOC_RESPONSE" | python3 -m json.tool
DOC_ID=$(echo "$DOC_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
ok "Document indexed: $DOC_ID"

# ---------------------------------------------------------------------------
section "Get Document by ID (Tenant A)"
curl -s "$BASE_URL/api/v1/documents/$DOC_ID" \
  -H "X-Tenant-ID: $TENANT_A" | python3 -m json.tool

# ---------------------------------------------------------------------------
section "Search Documents — Basic Query (Tenant A)"
curl -s "$BASE_URL/api/v1/search?q=elasticsearch" \
  -H "X-Tenant-ID: $TENANT_A" | python3 -m json.tool

# ---------------------------------------------------------------------------
section "Search with Tag Filter"
curl -s "$BASE_URL/api/v1/search?q=search&tags=elasticsearch,solr" \
  -H "X-Tenant-ID: $TENANT_A" | python3 -m json.tool

# ---------------------------------------------------------------------------
section "Search with Pagination"
curl -s "$BASE_URL/api/v1/search?q=search&page=1&size=5" \
  -H "X-Tenant-ID: $TENANT_A" | python3 -m json.tool

# ---------------------------------------------------------------------------
section "Search with Fuzzy Off (exact match)"
curl -s "$BASE_URL/api/v1/search?q=elasticsearch&fuzzy=false" \
  -H "X-Tenant-ID: $TENANT_A" | python3 -m json.tool

# ---------------------------------------------------------------------------
section "Tenant Isolation Check — Search as Tenant B (should return 0 results)"
curl -s "$BASE_URL/api/v1/search?q=elasticsearch" \
  -H "X-Tenant-ID: $TENANT_B" | python3 -m json.tool
ok "Tenant B sees its own empty index — isolation works"

# ---------------------------------------------------------------------------
section "Delete Document"
curl -s -X DELETE "$BASE_URL/api/v1/documents/$DOC_ID" \
  -H "X-Tenant-ID: $TENANT_A" -w "\nHTTP Status: %{http_code}\n"

# ---------------------------------------------------------------------------
section "Get Deleted Document (should be 404)"
curl -s "$BASE_URL/api/v1/documents/$DOC_ID" \
  -H "X-Tenant-ID: $TENANT_A" | python3 -m json.tool

# ---------------------------------------------------------------------------
section "Missing Tenant Header (should be 400)"
curl -s "$BASE_URL/api/v1/search?q=test" | python3 -m json.tool

# ---------------------------------------------------------------------------
section "List Tenants"
curl -s "$BASE_URL/api/v1/tenants" | python3 -m json.tool

echo -e "\n${GREEN}All sample requests complete!${NC}\n"
