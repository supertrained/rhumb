# Elasticsearch — Agent-Native Service Guide

> **AN Score:** 6.25 · **Tier:** L3 · **Category:** Search & Discovery

---

## 1. Synopsis
Elasticsearch is a distributed, multitenant-capable full-text search and analytics engine. For agents, it serves as the primary "long-term memory" and retrieval layer, supporting both traditional keyword search and modern vector (kNN) search for Retrieval-Augmented Generation (RAG). Its ability to handle unstructured data at scale makes it essential for agents tasked with knowledge discovery, log analysis, or real-time monitoring. While the underlying engine is open-source, most agent operators use Elastic Cloud for managed stability. Elastic Cloud offers a 14-day free trial; thereafter, pricing is resource-based (compute/storage). For agents, the API provides deep control over scoring, filtering, and aggregations, allowing for highly nuanced data retrieval beyond simple vector similarity.

---

## 2. Connection Methods

### REST API
The primary interface for Elasticsearch is a comprehensive REST API. Agents interact with indices and documents via standard HTTP verbs (GET, POST, PUT, DELETE). The API is remarkably consistent, using JSON for both request bodies and responses. Most search operations are directed at the `/{index}/_search` endpoint.

### SDKs
Elastic maintains high-quality, official client libraries for all major agent-relevant languages. The Python (`elasticsearch`) and JavaScript (`@elastic/elasticsearch`) clients are the industry standards. These SDKs handle connection pooling, retries on 502/503/504 errors, and node sniffing (in self-managed clusters) automatically, which significantly reduces the boilerplate code required for agent resilience.

### Webhooks & Watcher
While Elasticsearch doesn't natively "push" via webhooks in the traditional SaaS sense, its "Watcher" feature (available in Platinum/Cloud tiers) allows agents to define "Watches" that trigger actions—including Webhooks—when specific query conditions are met (e.g., "alert me when error logs exceed 100 in 5 minutes").

### Auth Flows
Elasticsearch supports several authentication schemes. For agent-to-service integration, **API Keys** are the recommended approach. They can be scoped to specific indices and restricted to specific operations (e.g., read-only for a retrieval agent). Alternatively, Basic Auth (username/password) is supported but less secure for distributed agent fleets. In enterprise environments, agents can also authenticate via JWT or OpenID Connect.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Index Document** | `PUT /{index}/_doc/{id}` | Persists a JSON document. Use `PUT` with a specific ID for idempotency. |
| **Search** | `POST /{index}/_search` | Executes a query (match, filter, or kNN) to retrieve relevant documents. |
| **Bulk Ops** | `POST /_bulk` | Performs multiple index/delete actions in a single request to reduce overhead. |
| **Get Mapping** | `GET /{index}/_mapping` | Retrieves the schema definition; crucial for agents to understand data types. |
| **Delete Index** | `DELETE /{index}` | Removes an entire index and its data. High-risk operation for agents. |
| **kNN Search** | `POST /{index}/_search` | Performs vector-based similarity search (requires `dense_vector` field). |
| **Update** | `POST /{index}/_update/{id}` | Partially updates an existing document via script or doc merge. |

---

## 4. Setup Guide

### For Humans
1. Sign up for an account at [Elastic Cloud](https://cloud.elastic.co/).
2. Create a new "Elasticsearch" deployment in your preferred cloud provider and region.
3. Save the provided `elastic` user password immediately (it is only shown once).
4. Navigate to **Management > Stack Management > API Keys** in Kibana.
5. Generate a "Restrictive" API key with permissions limited to the indices the agent will use.
6. Copy the **Cloud ID** and the **API Key** for your agent's environment variables.

### For Agents
1. **Discover Endpoint:** If not using Cloud ID, the agent should verify the base URL is reachable via a `GET /` request.
2. **Validate Auth:** Execute a `GET /_authenticate` call to ensure the API key is valid and check current privileges.
3. **Check Index Readiness:** Attempt a `HEAD /{index}` to see if the target index exists.
4. **Verify Schema:** Call `GET /{index}/_mapping` to ensure the document structure matches the agent's internal model.

```python
# Connection Validation Snippet
from elasticsearch import Elasticsearch

client = Elasticsearch(cloud_id="my-cloud-id", api_key="my-api-key")
if client.ping():
    print("Connected to Elasticsearch")
    auth_info = client.security.authenticate()
    print(f"Authenticated as: {auth_info['username']}")
```

---

## 5. Integration Example

```python
from elasticsearch import Elasticsearch

# Initialize the client
es = Elasticsearch(
    cloud_id="deployment-name:dXMtY2VudHJhbDEuZ2NwLmNsb3VkLmVzLmlv...",
    api_key="V3p6S0JKMEJmS3p..."
)

def agent_search(query_text, vector_query=None):
    # Hybrid search: combining BM25 (text) and kNN (vector)
    search_query = {
        "query": {
            "match": { "content": query_text }
        },
        "knn": {
            "field": "content_vector",
            "query_vector": vector_query,
            "k": 5,
            "num_candidates": 50
        } if vector_query else None,
        "size": 3
    }
    
    # Remove None values for knn if not provided
    search_query = {k: v for k, v in search_query.items() if v is not None}
    
    try:
        response = es.search(index="knowledge-base", body=search_query)
        return [hit["_source"] for hit in response["hits"]["hits"]]
    except Exception as e:
        # Agent decision: Log and retry or escalate based on error type
        print(f"Search failed: {e}")
        return []

# Example usage
results = agent_search("How do I reset my password?")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 45ms | Standard keyword search on indexed fields. |
| **P95 Latency** | 120ms | Complex aggregations or high-dimensional kNN search. |
| **P99 Latency** | 220ms | Large bulk requests or cold-start queries on large indices. |
| **Rate Limits** | Variable | Based on cluster size (CPU/RAM) in Elastic Cloud. |
| **Concurrency** | High | Distributed nature allows for massive parallel search requests. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Use `PUT /{index}/_doc/{id}` for document creation. If the agent retries an operation with the same ID, Elasticsearch will overwrite the existing document rather than creating a duplicate, ensuring state consistency.
*   **Retry Behavior:** Agents should implement exponential backoff specifically for `429 (Too Many Requests)` and `503 (Service Unavailable)`. The official Python client handles these automatically if configured with `retry_on_timeout=True`.
*   **Error Codes:** A `404` on a search means the *index* is missing, not that results are empty. A `400` usually indicates a mapping conflict (e.g., trying to put a string into an integer field). Agents should be programmed to check mappings before bulk indexing.
*   **Schema Stability:** Use "Dynamic Mapping" with caution. For agents, it is safer to define explicit mappings to prevent "mapping explosions" where too many unique fields degrade performance.
*   **Cost-per-operation:** Unlike Pinecone or Algolia, Elasticsearch is generally priced by the hour based on the underlying hardware. Agents can perform unlimited queries within the capacity of the provisioned nodes, making it cost-efficient for high-frequency search tasks.
*   **Refresh Interval:** By default, documents are searchable 1 second after indexing (`refresh_interval`). If an agent needs "read-your-own-write" consistency, it must use the `?refresh=wait_for` parameter.

---

## 8. Rhumb Context: Why Elasticsearch Scores 6.25 (L3)

Elasticsearch's **6.25 score** reflects its status as a robust, enterprise-grade engine that requires more "human-in-the-loop" configuration compared to pure serverless offerings:

1. **Execution Autonomy (6.8)** — The API is incredibly expressive. Agents can perform complex filtering, weighting, and vector math in a single call. The `_bulk` API is a gold standard for efficient state synchronization. However, the complexity of the Query DSL means agents can easily craft "expensive" queries that timeout or impact cluster health.

2. **Access Readiness (5.6)** — This is the primary drag on the score. Unlike "agent-first" services where you get a key and go, Elasticsearch usually requires provisioning a cluster (even in the cloud), setting up VPCs or IP allowlists, and managing index mappings. The 14-day trial is helpful, but the lack of a permanent "Free Tier" for small agent experiments creates friction.

3. **Agent Autonomy (6.33)** — Governance is a major strength (Score: 8). The RBAC system is granular, allowing agents to be restricted to specific documents or even specific fields within a document. This makes it safe to deploy agents in multi-tenant environments. The latency profile (P50: 45ms) is excellent for real-time agent reasoning loops.

**Bottom line:** Elasticsearch is the "heavy lifter" for agents requiring deep search capabilities and high-volume data processing. It is less "plug-and-play" than Pinecone but offers significantly more power for agents that need to combine structured metadata filtering with unstructured text and vector search.

**Competitor context:** **Pinecone (7.2)** scores higher for simplicity and "serverless" ease of use but lacks Elasticsearch's rich aggregation and full-text capabilities. **Algolia (6.9)** offers better out-of-the-box search relevance for humans but is significantly more expensive at the scale typical of agentic log processing or RAG.
