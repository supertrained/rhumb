# Typesense — Agent-Native Service Guide

> **AN Score:** 7.11 · **Tier:** L3 · **Category:** Search & Discovery

---

## 1. Synopsis
Typesense is a high-performance, open-source search engine designed for sub-millisecond "search-as-you-type" experiences. For agents, it serves as a reliable retrieval layer for both structured data and unstructured text (via vector search). Unlike heavier alternatives, Typesense is operationally lean and prioritizes developer experience with a "batteries-included" approach to typo tolerance and ranking. Agents benefit from its predictable REST API, strict schema validation, and high-concurrency performance. Typesense Cloud offers a free tier (0.5GB RAM cluster) for prototyping, while production usage is based on cluster memory/CPU hourly rates. It is an ideal RAG (Retrieval-Augmented Generation) backend for agents requiring low-latency knowledge retrieval.

---

## 2. Connection Methods

### REST API
The primary interface for Typesense is a RESTful API communicating over HTTP/2. It uses JSON for all request and response bodies. The API is designed for high-frequency querying, with dedicated endpoints for individual document operations and bulk imports.

### SDKs
Official, production-ready SDKs are available for:
*   **Python:** `typesense` (pip)
*   **JavaScript/TypeScript:** `typesense` (npm)
*   **Go:** `typesense-go`
*   **Ruby:** `typesense`
*   **PHP:** `typesense-php`

These SDKs are recommended for agents as they include built-in cluster failover logic and connection pooling, which are critical for maintaining autonomy during network blips.

### MCP (Model Context Protocol)
Typesense can be integrated into MCP hosts via community-built search connectors. This allows agents to treat a Typesense collection as a tool-accessible database for semantic search without writing custom indexing logic.

### Auth Flows
Typesense uses API Key authentication.
*   **Admin API Key:** Full access to create/delete collections and manage keys.
*   **Search-Only API Key:** Restricted to search operations (safe for client-side or scoped agent tools).
*   **Scoped API Keys:** Allows agents to generate time-limited or parameter-restricted keys (e.g., restricting an agent to a specific `tenant_id` within a shared collection).

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Collection** | `POST /collections` | Defines the schema (fields, types, indexing options). |
| **Document** | `POST /collections/{name}/documents` | Indexes a single record for search. |
| **Search** | `GET /collections/{name}/documents/search` | Executes a query with typo tolerance, filtering, and sorting. |
| **Multi-Search** | `POST /multi_search` | Executes multiple search queries across different collections in one RTT. |
| **Upsert** | `POST /collections/{name}/documents/import?action=upsert` | Efficiently updates or creates documents in bulk. |
| **Vector Search** | `GET ...&vector_query=...` | Performs nearest-neighbor search for embeddings (RAG-native). |
| **Health** | `GET /health` | Returns the status of the node and cluster consensus. |

---

## 4. Setup Guide

### For Humans
1.  **Sign Up:** Create an account at [Typesense Cloud](https://cloud.typesense.org).
2.  **Spin up Cluster:** Select a region and cluster size (Free Tier available).
3.  **Generate API Keys:** Copy the `nodes`, `api_key`, and `connection_timeout` from the dashboard.
4.  **Define Schema:** Create your first Collection by defining field names and types (e.g., `string`, `int32`, `float[]` for vectors).
5.  **Import Data:** Use the JSONL import tool or API to populate the collection.

### For Agents
1.  **Initialize Client:** Instantiate the SDK using the provided cluster nodes and API key.
2.  **Connection Probe:** Execute a `health` check to ensure the cluster is reachable.
3.  **Schema Verification:** Query the `/collections/{name}` endpoint to verify the expected fields exist before attempting writes.
4.  **Validate Keys:** Attempt a low-cost search with `q=*` to confirm the API key has the necessary permissions.

```python
import typesense

client = typesense.Client({
  'nodes': [{'host': 'xxx.typesense.net', 'port': '443', 'protocol': 'https'}],
  'api_key': 'agent-api-key',
  'connection_timeout_seconds': 2
})

# Connection Validation
try:
    is_healthy = client.health.retrieve()['ok']
    print(f"Agent Connection Verified: {is_healthy}")
except Exception as e:
    print(f"Connection Failed: {e}")
```

---

## 5. Integration Example

```python
import typesense

client = typesense.Client({
    'nodes': [{'host': 'xyz.typesense.net', 'port': '443', 'protocol': 'https'}],
    'api_key': 'YOUR_API_KEY',
    'connection_timeout_seconds': 5
})

# Agent-driven search with filtering
search_parameters = {
    'q': 'autonomous agents',
    'query_by': 'title,description',
    'filter_by': 'category:=[research, whitepaper]',
    'sort_by': 'relevance:desc',
    'per_page': 5
}

# Execute search
results = client.collections['knowledge_base'].documents.search(search_parameters)

# Extract and process hits
for hit in results['hits']:
    doc_id = hit['document']['id']
    score = hit['text_match']
    print(f"Found Doc {doc_id} with score {score}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 18ms | Measured for standard text search queries. |
| **P95 Latency** | 48ms | Increases with complex filtering or large result sets. |
| **P99 Latency** | 85ms | Usually occurs during cluster leader re-election or heavy bulk imports. |
| **Rate Limits** | Variable | Based on cluster size; Typesense Cloud scales with CPU/RAM. |
| **Concurrency** | High | Multi-threaded engine; handles thousands of concurrent queries. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Use the `import` endpoint with `action=upsert`. This allows agents to safely retry indexing tasks without creating duplicate documents.
*   **Retry Behavior:** Official SDKs automatically retry on 5xx errors and connection timeouts across different nodes in the cluster. Agents should set `connection_timeout_seconds` to at least 5s for cross-region calls.
*   **Error Codes:**
    *   `400`: Schema mismatch or invalid query syntax (Agent action: Fix prompt/logic).
    *   `404`: Collection missing (Agent action: Trigger collection creation).
    *   `409`: Version conflict on document update (Agent action: Re-fetch and merge).
*   **Schema Stability:** Typesense supports `auto` field detection, but for agents, explicit schemas are safer to prevent "type-drift" where an agent accidentally changes a field from `int` to `string`.
*   **Cost-per-operation:** Extremely low. Since it's cluster-based, there is no "per-query" fee, making it ideal for agents that need to perform high-frequency lookups without escalating costs.
*   **Vector Readiness:** Native support for `float[]` fields and HNSW indexing makes it a top-tier choice for agents managing their own RAG memory.
*   **Self-Healing:** In a cluster setup, if the leader node fails, the SDKs handle the transition to a new node transparently to the agent's logic.

---

## 8. Rhumb Context: Why Typesense Scores 7.11 (L3)

Typesense’s **7.11 score** reflects a highly accessible, developer-centric search engine that balances performance with operational simplicity:

1. **Execution Autonomy (7.7)** — Typesense provides exceptionally clear error messages and a predictable REST interface. The bulk `upsert` capability is a standout for agents, allowing for idempotent data synchronization. Its strict schema enforcement (when enabled) acts as a guardrail, ensuring agents don't corrupt the index with malformed data.

2. **Access Readiness (6.6)** — The availability of a free tier on Typesense Cloud allows for immediate agent validation. However, the score is slightly tempered by the need to provision a cluster (even a small one), which introduces a few minutes of latency between "account creation" and "ready for API calls," compared to purely serverless search APIs.

3. **Agent Autonomy (6.67)** — The service excels in search-only scenarios, but agent-driven management of synonyms, curations, and complex schemas requires more orchestration. The lack of built-in compliance audit logs in the standard cloud offering means agents in highly regulated environments may require additional governance wrappers.

**Bottom line:** Typesense is the "L3 Ready" choice for agents that need a dedicated, high-performance search and retrieval layer. It is significantly more agent-friendly than legacy search engines due to its modern API design and predictable performance profile.

**Competitor context:** **Algolia (6.8)** offers faster initial setup but becomes cost-prohibitive for high-volume agent indexing. **Elasticsearch (5.4)** provides more features but suffers from a massive API surface area that frequently confuses LLM-based agents. Typesense hits the "Goldilocks" zone for agent-native search.
