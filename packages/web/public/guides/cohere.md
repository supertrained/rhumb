# Cohere — Agent-Native Service Guide

> **AN Score:** 6.33 · **Tier:** L3 · **Category:** AI & Machine Learning

---

## 1. Synopsis
Cohere provides enterprise-grade large language models (LLMs) with a specific focus on Retrieval-Augmented Generation (RAG) and multilingual capabilities. For agents, Cohere is a high-utility inference provider because it offers more than just text generation; its specialized `Rerank` and `Embed` endpoints allow agents to build sophisticated information retrieval pipelines that outperform standard vector search. Cohere’s "Command" model family is optimized for tool-use and long-context reasoning. They offer a generous free trial tier (rate-limited) for developers, making it easy for agents to self-provision or validate connections without immediate financial commitment, though production workloads require a credit card for usage-based billing.

---

## 2. Connection Methods

### REST API
Cohere exposes a standard REST API at `https://api.cohere.com/v1`. The API is highly structured and follows predictable patterns across its generation, embedding, and classification endpoints. It supports both synchronous responses and server-sent events (SSE) for streaming text generation, which is critical for reducing perceived latency in agentic workflows.

### SDKs
Cohere maintains high-quality, official SDKs for Python, JavaScript/TypeScript, Go, and Java. The Python SDK (`pip install cohere`) is the most feature-complete and is frequently used in agent frameworks like LangChain and LlamaIndex. The SDKs include built-in support for request retries on 429 (Rate Limit) and 5xx (Server Error) responses, reducing the boilerplate code required for agent reliability.

### Webhooks
Cohere uses webhooks primarily for asynchronous tasks, such as notification when a custom model fine-tuning job has completed. This allows agents to initiate a training cycle and "sleep" or perform other tasks until the model is ready for deployment.

### Auth Flows
Authentication is handled via a simple Bearer Token passed in the `Authorization` header. Cohere provides two types of keys: **Trial Keys** (free, restricted rate limits, data may be used for training) and **Production Keys** (paid, higher limits, data privacy guarantees). Agents should be configured to check the key type to adjust their request pacing accordingly.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Chat** | `POST /v1/chat` | The primary interface for agents. Supports tool-use (function calling) and RAG. |
| **Rerank** | `POST /v1/rerank` | Re-orders a list of documents based on relevance to a query. Essential for agentic RAG. |
| **Embed** | `POST /v1/embed` | Converts text into vector embeddings for semantic search or memory storage. |
| **Classify** | `POST /v1/classify` | Categorizes text into predefined labels; useful for agent intent routing. |
| **Tokenize** | `POST /v1/tokenize` | Converts text into tokens to help agents manage context window limits. |
| **Tool Use** | `chat(tools=[...])` | Native support for agents to call external functions and process results. |

---

## 4. Setup Guide

### For Humans
1. Create an account at [dashboard.cohere.com](https://dashboard.cohere.com/).
2. Navigate to the "API Keys" section in the sidebar.
3. Copy your default "Trial Key" for initial development.
4. (Optional) Add a payment method under "Billing" to generate a "Production Key."
5. Explore the "Playground" to test model prompts and tool-use configurations.
6. Review the "Usage" dashboard to monitor token consumption and costs.

### For Agents
1. **Environment Provisioning:** Ensure the `COHERE_API_KEY` is available in the environment.
2. **SDK Initialization:** Instantiate the client (e.g., `co = cohere.Client(api_key)`).
3. **Connection Validation:** Perform a low-cost "heartbeat" call using the `tokenize` endpoint.
4. **Capability Discovery:** Query the model list to ensure the agent has access to the required model (e.g., `command-r-plus`).

```python
import cohere
import os

co = cohere.ClientV2(os.environ["COHERE_API_KEY"])
try:
    # Validate connection with a simple token count
    response = co.tokenize(text="connection_test", model="command-r")
    print("Connection Verified")
except Exception as e:
    print(f"Connection Failed: {e}")
```

---

## 5. Integration Example

This example demonstrates an agent using Cohere's `chat` V2 API with a tool-calling pattern, which is the standard for autonomous service interaction.

```python
import cohere

co = cohere.ClientV2("YOUR_API_KEY")

# Define a tool the agent can use
tools = [{
    "type": "function",
    "function": {
        "name": "query_database",
        "description": "Queries the internal DB for user info",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"}
            },
            "required": ["user_id"]
        }
    }
}]

# Agent execution loop
response = co.chat(
    model="command-r-plus",
    messages=[{"role": "user", "content": "Find info for user_id 'u_123'"}],
    tools=tools
)

# Check if the agent wants to call a tool
if response.message.tool_calls:
    for call in response.message.tool_calls:
        print(f"Agent requesting tool: {call.function.name} with {call.function.arguments}")
        # Logic to execute the local function would go here
else:
    print(f"Agent response: {response.message.content[0].text}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Latency P50** | 400ms | Fast for small prompts and Embed/Rerank calls. |
| **Latency P95** | 1100ms | Typical for medium-length generation or high-traffic periods. |
| **Latency P99** | 2200ms | Outlier latency usually associated with maximum context generation. |
| **Rate Limits** | 10-5000 RPM | Varies significantly between Trial (low) and Production (high) tiers. |
| **Context Window** | 128k Tokens | Available on Command R and Command R+ models. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Cohere does not natively support idempotency keys for chat completion. Agents must implement their own deduplication logic or handle duplicate generations if a retry occurs mid-stream.
*   **Retry Behavior:** The official Python/JS SDKs default to 3 retries with exponential backoff for 429 and 5xx errors. Agents should rely on this rather than wrapping calls in custom loops.
*   **Error Codes:** 
    *   `429`: Rate limit exceeded. Agent should back off or switch to a fallback provider.
    *   `400`: Often indicates context window overflow. Agent should truncate the prompt.
    *   `401`: Invalid API key. Agent should halt and escalate to the operator.
*   **Schema Stability:** Cohere is highly disciplined with API versioning (currently v1/v2). Breaking changes are rare and communicated through clear header-based versioning.
*   **Cost-per-operation:** Command R is significantly cheaper than Command R+, making it the "workhorse" for agentic sub-tasks, while R+ should be reserved for complex reasoning.
*   **RAG Optimization:** The `Rerank` primitive is a unique advantage; agents can retrieve 100 documents via cheap vector search and use `Rerank` to select the top 5 for the prompt, drastically improving accuracy.
*   **Tool-Use Native:** Unlike some models that "hack" tool use via prompting, Command models are fine-tuned specifically for the tool-calling JSON schema, leading to fewer parsing errors.

---

## 8. Rhumb Context: Why Cohere Scores 6.33 (L3)

Cohere’s **6.33 score** reflects its position as a reliable, enterprise-ready inference provider that lacks some of the broader ecosystem autonomy seen in OpenAI or Anthropic:

1. **Execution Autonomy (7.0)** — Cohere’s tool-calling and RAG-specific features (like the Rerank API) provide agents with high-quality primitives for autonomous decision-making. The models are stable and the structured output is reliable. However, the lack of native idempotency headers prevents it from reaching an 8.0+.

2. **Access Readiness (5.7)** — While the free trial tier is excellent for testing, the transition to production requires manual credit card entry. There is currently no programmatic way for an agent to "buy its own credits" or manage its billing lifecycle, which is a common friction point for fully autonomous agents.

3. **Agent Autonomy (6.0)** — Cohere scores well on governance (SOC 2 Type II) and has basic team management. The SDKs handle retries well, but the overall ecosystem for "agent-to-agent" discovery or MCP (Model Context Protocol) support is less mature than competitors, requiring more manual integration work from the operator.

**Bottom line:** Cohere is the premier choice for agents that prioritize RAG performance and enterprise data privacy. Its specialized endpoints make it more than just a chatbot, serving as a functional "brain" for complex information retrieval systems.

**Competitor context:** OpenAI (7.9) and Anthropic (8.1) score higher due to more mature ecosystem integrations (like MCP) and slightly more robust autonomous billing/scaling features. However, Cohere often outperforms both in specific multilingual and RAG-heavy use cases.
