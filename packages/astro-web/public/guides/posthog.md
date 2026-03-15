# PostHog — Agent-Native Service Guide

> **AN Score:** 6.91 · **Tier:** L3 · **Category:** Analytics & Product Intelligence

---

## 1. Synopsis
PostHog is an all-in-one, open-source product intelligence platform that combines product analytics, session replay, feature flags, and A/B testing into a single API surface. For autonomous agents, PostHog serves as both a "sensory memory" (recording user interactions and agent actions) and a "control plane" (using feature flags to toggle agent capabilities remotely). Unlike traditional analytics tools, PostHog’s API allows for deep querying of raw event data via HogQL, enabling agents to perform self-analysis or retrieve user context in real-time. It offers a generous free tier of 1 million events per month, making it an ideal low-friction starting point for agentic workflows that require persistent state tracking without the overhead of a dedicated database.

---

## 2. Connection Methods

### REST API
PostHog provides a comprehensive REST API divided into two main categories: the **Capture API** and the **Public API**. The Capture API (`https://us.i.posthog.com` or `https://eu.i.posthog.com`) is optimized for high-volume event ingestion and feature flag evaluation. The Public API (`/api/projects/{project_id}/...`) is used for management tasks, querying data, and administrative actions. Agents should use the Capture API for real-time telemetry and the Public API for analytical retrieval.

### SDKs
PostHog maintains high-quality, official SDKs for Python, JavaScript/TypeScript, Go, Ruby, and Java. The Python SDK (`posthog-python`) is particularly well-suited for agents, featuring built-in local evaluation for feature flags to reduce latency and an asynchronous internal queue for non-blocking event capture.

### Webhooks
PostHog supports outgoing webhooks that trigger when specific "Actions" are detected. This allows agents to be "woken up" by user behavior. For example, an agent can subscribe to a webhook triggered whenever a user completes a "Subscription Cancelled" event to initiate a retention dialogue.

### Auth Flows
PostHog uses two primary authentication mechanisms:
1.  **Project API Key (Write-only):** Used for capturing events and identifying users. Safe to embed in client-side agent code.
2.  **Personal API Key (Read/Write):** Used for querying data and managing resources. This must be kept secret and is required for the `/api/` endpoints. Authentication is handled via the `Authorization: Bearer <key>` header.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Capture** | `POST /batch/` | Ingests one or more events. Includes properties and timestamps. |
| **Identify** | `POST /capture/` | Links a distinct ID to a set of person properties (e.g., email, plan). |
| **Decide** | `POST /decide/` | Evaluates feature flags and experiments for a specific user. |
| **Query (HogQL)** | `POST /api/projects/{id}/query/` | Executes SQL-like queries against raw event data for analysis. |
| **Persons** | `GET /api/projects/{id}/persons/` | Retrieves the profile and properties of a specific user or agent. |
| **Feature Flags** | `GET /api/projects/{id}/feature_flags/` | Lists or updates the status of remote configuration toggles. |
| **Annotations** | `POST /api/projects/{id}/annotations/` | Adds a text note to a specific point in time on charts. |

---

## 4. Setup Guide

### For Humans
1.  Sign up at [PostHog.com](https://posthog.com) and create a new Project.
2.  Navigate to **Project Settings** to find your **Project API Key** (for ingestion).
3.  Go to **Personal Settings > Access Tokens** to generate a **Personal API Key** (for querying).
4.  Identify your **Project ID** from the URL (e.g., `https://us.posthog.com/project/12345`).
5.  Define any Feature Flags you want your agent to check.
6.  (Optional) Enable Session Recording if the agent interacts with a web frontend.

### For Agents
1.  **Store Credentials:** Ensure `POSTHOG_API_KEY` (Personal) and `POSTHOG_PROJECT_ID` are in the environment.
2.  **Initialize Client:** Instantiate the SDK with the correct host (US vs EU).
3.  **Validate Connection:** Execute a simple query to verify the Personal API Key.
4.  **Check Capabilities:** Query the `/decide` endpoint to see which flags are active for the agent's current context.

```python
import os
from posthog import Posthog

ph = Posthog(os.getenv("POSTHOG_PROJECT_API_KEY"), host='https://us.i.posthog.com')

# Validation check
if ph.feature_enabled("agent-active-mode", "agent_001"):
    ph.capture("agent_001", "agent_initialized", {"version": "1.0.4"})
```

---

## 5. Integration Example

This example demonstrates an agent checking a feature flag to decide on a course of action and then capturing the result.

```python
import os
from posthog import Posthog

# Initialize with Project API Key for capture
posthog = Posthog(
    os.getenv("POSTHOG_API_KEY"), 
    host="https://us.i.posthog.com"
)

def agent_task(user_id):
    # 1. Remote Steering: Check if the 'advanced-reasoning' flag is on for this user
    is_advanced = posthog.get_feature_flag("advanced-reasoning", user_id)
    
    # 2. Execute logic based on flag
    model = "gpt-4o" if is_advanced else "gpt-3.5-turbo"
    
    try:
        # Simulate agent work
        result = f"Processed using {model}"
        
        # 3. Telemetry: Capture the event with metadata
        posthog.capture(
            distinct_id=user_id,
            event="agent_task_completed",
            properties={
                "model_used": model,
                "success": True,
                "latency_ms": 150
            }
        )
        return result
    except Exception as e:
        posthog.capture(user_id, "agent_task_failed", {"error": str(e)})
        raise e

# Ensure events are flushed before exit
posthog.flush()
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 110ms | Capture API is highly optimized. |
| **P95 Latency** | 250ms | Queries (HogQL) may take longer depending on dataset size. |
| **P99 Latency** | 420ms | Occurs during peak ingestion or complex aggregations. |
| **Rate Limits** | 240 req/min | Default for Public API; Capture API is much higher. |
| **Idempotency** | Supported | Use `uuid` property in capture calls to prevent duplicates. |
| **Data Consistency** | Eventual | Capture to Query lag is typically < 30 seconds. |

---

## 7. Agent-Native Notes

*   **Idempotency via UUIDs:** To ensure retry safety, agents should generate a version 4 UUID for every event and pass it as the `uuid` field. PostHog will deduplicate events with the same UUID within a 24-hour window.
*   **Retry Behavior:** The official SDKs implement exponential backoff for 5xx errors and network timeouts. Agents should wrap `capture` calls in non-blocking threads to avoid stalling on network hiccups.
*   **Error Handling:** A `429 Too Many Requests` response should trigger an immediate "cool down" in the agent's ingestion loop. A `401 Unauthorized` usually indicates an expired Personal API Key.
*   **Schema Stability:** PostHog is schema-less for event properties. While this provides flexibility, agents must be disciplined in property naming to avoid polluting the global namespace.
*   **Cost Management:** The 1M free event tier is generous, but agents generating high-frequency telemetry (e.g., every thought in a chain) can burn through this quickly. Use `sampling_rate` in SDKs for high-volume agents.
*   **Local Evaluation:** For performance-critical agents, use "Local Evaluation" for feature flags. This fetches flag definitions once and evaluates them locally, reducing latency from ~110ms to <1ms.
*   **HogQL Power:** Agents can use the `/query` endpoint to perform complex self-corrections. For example, "Find the last 5 times I failed this task for this user" can be expressed in a single SQL-like query.

---

## 8. Rhumb Context: Why PostHog Scores 6.91 (L3)

PostHog’s **6.91 score** reflects its position as a highly capable but slightly complex "memory and control" layer for agents:

1.  **Execution Autonomy (7.4)** — The introduction of HogQL is a game-changer for agents. It allows them to programmatically query their own history without needing a separate database. The ability to evaluate feature flags locally (Local Evaluation) gives agents the ability to change behavior instantly without network round-trips, a key requirement for high-autonomy systems.

2.  **Access Readiness (6.2)** — This is the lowest sub-score due to the "Project ID" friction. Unlike some modern APIs where a token is enough, PostHog often requires a Project ID, a Project API Key, and a Personal API Key depending on the action. This creates a slightly higher configuration burden for agents during the initial handshake phase.

3.  **Agent Autonomy (7.33)** — PostHog excels here because it isn't just a "sink" for data; it's a "source" of truth. Feature flags and Experiments allow human operators to "steer" agents without redeploying code. The webhook system allows agents to remain dormant until specific user conditions are met, preserving compute resources.

**Bottom line:** PostHog is the best-in-class choice for agents that need a combination of event logging, user profiling, and remote configuration. Its open-source nature and generous free tier make it more "agent-friendly" than enterprise-heavy alternatives.

**Competitor context:** **Mixpanel (6.1)** and **Amplitude (5.9)** score lower primarily due to more restrictive free tiers and less developer-centric API documentation. They lack the built-in feature flagging and session replay integration that makes PostHog a cohesive "operating system" for agent data.
