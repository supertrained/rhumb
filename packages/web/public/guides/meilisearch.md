# Meilisearch — Agent-Native Service Guide

> **AN Score:** 7.49 · **Tier:** L3 · **Category:** Search & Discovery

---

## 1. Synopsis
Meilisearch is an open-source, lightning-fast search engine designed to provide instant, relevant search results with minimal configuration. For agents, Meilisearch serves as a high-performance retrieval layer, enabling semantic-ish keyword search, filtering, and faceted discovery across large datasets. Unlike complex engines like Elasticsearch, Meilisearch is "agent-friendly" due to its predictable ranking rules and simple REST interface. It is particularly valuable for agents performing RAG (Retrieval-Augmented Generation) where low-latency document lookup is critical. The open-source version is entirely free to self-host with zero restrictions, while Meilisearch Cloud offers a generous free tier (up to 100k documents) and a 14-day trial for higher tiers.

---

## 2. Connection Methods

### REST API
The primary way agents interact with Meilisearch is via its highly structured REST API. Every action—from index creation to document insertion and searching—is exposed through standard HTTP verbs. The API is versioned (currently `/v1/`) and returns consistent JSON responses, making it easy for agents to parse and act upon.

### SDKs
Meilisearch maintains official, idiomatic SDKs for all major agent-building languages, including **Python** (`meilisearch`), **JavaScript/TypeScript** (`meilisearch-js`), **Go**, and **Ruby**. These SDKs handle the boilerplate of HTTP requests, provide type safety, and include helper methods for common patterns like waiting for task completion.

### MCP (Model Context Protocol)
While there is no "official" Meilisearch-branded MCP server, the community has produced several wrappers that allow Claude and other MCP-compatible agents to query Meilisearch indexes directly as tools. Because the API is so simple, an agent can often generate its own tool definition for Meilisearch given the OpenAPI spec.

### Webhooks
Meilisearch Cloud supports webhooks for monitoring task status. For self-hosted instances, agents typically rely on polling the `/tasks` endpoint. This is a critical integration point: since document additions are asynchronous, agents must track the `taskUid` to ensure data is searchable before proceeding with dependent steps.

### Auth Flows
Authentication is handled via `Bearer` tokens in the `Authorization` header. Meilisearch supports three levels of keys: **Master Key** (full access), **Admin Key** (index management), and **Search Key** (read-only). For advanced agent workflows, Meilisearch supports **Tenant Tokens**, which allow agents to generate short-lived, scoped keys that restrict search results to specific users or filters, ensuring data privacy in multi-tenant environments.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Index** | `POST /indexes` | A virtual container for a collection of similar documents. |
| **Document** | `POST /indexes/{id}/documents` | The basic unit of data. Must contain a unique primary key. |
| **Search** | `POST /indexes/{id}/search` | The core query engine. Supports filtering, sorting, and highlighting. |
| **Task** | `GET /tasks/{uid}` | An object representing an asynchronous operation (like indexing). |
| **Key** | `GET /keys` | API credentials with specific scopes (search, documents.add, etc.). |
| **Settings** | `PATCH /indexes/{id}/settings` | Configuration for stop-words, ranking rules, and searchable attributes. |
| **Synonyms** | `PUT /indexes/{id}/settings/synonyms` | Mapping of words that agents should treat as equivalent during search. |

---

## 4. Setup Guide

### For Humans
1. **Create Account:** Sign up at [Meilisearch Cloud](https://cloud.meilisearch.com/) or deploy via Docker (`docker run -p 7700:7700 getmeili/meilisearch`).
2. **Project Setup:** Create a new project (Cloud) to receive your Host URL and Master Key.
3. **Create Index:** Define an index name (e.g., `products` or `kb_articles`).
4. **Define Primary Key:** Identify the unique field in your data (usually `id`).
5. **Configure Settings:** (Optional) Set `searchableAttributes` and `filterableAttributes` to optimize performance.

### For Agents
1. **Health Check:** Verify connectivity by hitting the `/health` endpoint.
2. **Key Validation:** Attempt to list indexes using the provided API key to confirm permissions.
3. **Task Monitoring:** Implement a polling loop for the `/tasks` endpoint to handle the asynchronous nature of document ingestion.
4. **Validation Code (Python):**
```python
import meilisearch
client = meilisearch.Client('https://your-host.com', 'your-api-key')

# 1. Check health
if client.health().get('status') == 'available':
    # 2. Validate Index Access
    index = client.index('agent_test')
    # 3. Async Ingestion + Polling
    task = index.add_documents([{'id': 1, 'text': 'Agent Connection Verified'}])
    client.wait_for_task(task.task_uid)
    print("Agent ready.")
```

---

## 5. Integration Example

```python
import meilisearch
import time

# Initialize client
client = meilisearch.Client("https://ms-123.meilisearch.io", "MASTER_KEY")
index = client.index("customer_support_kb")

def agent_add_and_search(query, documents):
    # 1. Batch upload documents (Asynchronous)
    task = index.add_documents(documents)
    
    # 2. Agents must wait for the task to succeed before searching
    # This is a critical 'Agent-Native' pattern for Meilisearch
    status = client.wait_for_task(task.task_uid, timeout_in_ms=5000)
    
    if status.status == 'succeeded':
        # 3. Execute search with specific parameters
        results = index.search(query, {
            'limit': 5,
            'attributesToRetrieve': ['title', 'content'],
            'showMatchesPosition': True
        })
        return results['hits']
    else:
        raise Exception(f"Indexing failed: {status.error}")

# Example usage
docs = [{"id": "faq_1", "title": "Refunds", "content": "Refunds take 5-7 days."}]
print(agent_add_and_search("How long for refunds?", docs))
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 15ms | Extremely fast for standard keyword lookups. |
| **P95 Latency** | 40ms | Remains stable even with complex filters. |
| **P99 Latency** | 75ms | Occasional spikes during heavy background indexing. |
| **Rate Limits** | 10k req/min | Default for Cloud; self-hosted is hardware-dependent. |
| **Max Doc Size** | 100 KB | Recommended limit per document for optimal speed. |
| **Consistency** | Eventual | Search results update once the task queue processes. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Document updates are idempotent if you provide a consistent `id`. Agents can safely re-send the same document batch without creating duplicates.
*   **Retry Behavior:** Agents should retry on `429` (Too Many Requests) and `503` (Service Unavailable). Use exponential backoff, especially during heavy indexing.
*   **Error Codes:** Meilisearch provides distinct error codes like `index_not_found` or `invalid_document_id`. Agents should use these to trigger auto-remediation (e.g., creating a missing index on the fly).
*   **Schema Stability:** Meilisearch uses "schemaless" ingestion by default, but agents should explicitly set `searchableAttributes` to prevent "garbage-in-garbage-out" search results.
*   **Cost-per-operation:** On Cloud, you pay for "Search Units" (capacity). Self-hosted is $0, making it the most cost-effective "memory" for high-volume agents.
*   **Async Awareness:** Agents cannot assume data is searchable immediately after a `POST`. They **must** poll the `taskUid` or utilize the `wait_for_task` helper.
*   **Tenant Security:** Use Tenant Tokens to prevent "prompt injection" or "data leakage" where an agent might accidentally search across private data it shouldn't access.

---

## 8. Rhumb Context: Why Meilisearch Scores 7.49 (L3)

Meilisearch's **7.49 score** reflects its status as a highly autonomous, developer-friendly search engine that is easier for agents to manage than traditional enterprise search.

1. **Execution Autonomy (8.0)** — The API is remarkably clean. Agents can autonomously manage the entire lifecycle: creating indexes, updating settings, and performing complex searches without human intervention. The task-based system provides a clear audit trail for the agent to verify its own actions.
2. **Access Readiness (7.1)** — Getting started is trivial. The cloud version has a standard credit card flow, but the real winner is the open-source version. An agent can spin up its own Meilisearch instance in a container and be fully operational in seconds with zero payment friction.
3. **Agent Autonomy (7.0)** — While Meilisearch is excellent at keyword search, it lacks some of the native "vector-first" features of Pinecone or Weaviate (though vector support is in beta). This means agents often need to handle embeddings elsewhere, slightly reducing the "all-in-one" autonomy for modern AI workflows.

**Bottom line:** Meilisearch is the premier choice for agents that need a fast, reliable, and easy-to-configure search layer. It is the "Goldilocks" of search: more powerful than simple SQL `LIKE` queries, but significantly less complex to manage than Elasticsearch.

**Competitor context:** **Algolia (6.2)** scores lower due to high pricing complexity and restrictive free tiers that hinder agent experimentation. **Elasticsearch (5.4)** scores lower due to extreme configuration overhead and a massive API surface area that frequently confuses autonomous agents. Meilisearch is the most agent-native choice in the Search & Discovery category.
