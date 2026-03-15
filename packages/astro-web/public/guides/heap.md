# Heap — Agent-Native Service Guide

> **AN Score:** 5.14 · **Tier:** L2 · **Category:** Analytics & Product Intelligence

---

## 1. Synopsis
Heap is a product analytics platform that distinguishes itself through "autocapture," recording every user interaction without manual event tagging. For agents, Heap provides a high-fidelity audit trail of their own actions and the user responses they trigger. While primarily a frontend-focused tool, its Server-Side Track API allows agents to log discrete events, identify users, and update properties programmatically. This makes it ideal for agents that need to quantify their business impact or monitor user engagement with agent-driven features. Heap offers a functional free tier for up to 10k monthly sessions, though advanced data export and governance features require transitioning to sales-led plans, which creates friction for autonomous scaling.

---

## 2. Connection Methods

### REST API
The primary interface for agents is the Heap Server-Side API. It consists of three main endpoints for data ingestion: `/api/track`, `/api/identify`, and `/api/add_user_properties`. These are standard REST endpoints accepting JSON payloads via POST requests. Unlike frontend autocapture, these require explicit event naming and property mapping.

### SDKs
Heap maintains an official Node.js SDK (`@heap/node-sdk`) which wraps the Server-Side API. For agents built in Python or other languages, the REST API is the preferred path as third-party library support is inconsistent. The Node SDK handles batching and retries, making it the most robust choice for high-volume agent logging.

### Webhooks
Heap does not offer standard outbound webhooks for real-time event triggers (e.g., "trigger agent when a user clicks X"). Instead, it uses "Data Out" integrations to sync data to S3, BigQuery, or Redshift. This makes Heap a "write-heavy" service for agents; agents report to Heap, but rarely receive real-time signals back from it.

### Auth Flows
Authentication is straightforward but lacks fine-grained scoping. Agents require an `app_id` (public identifier) and a `secret` (private API key). These are passed in the JSON body of the request. There is no support for OAuth2 or short-lived tokens, meaning agents must be provisioned with long-lived secrets stored in secure environment variables.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Track Event** | `POST /api/track` | Records a specific action taken by a user or the agent itself. |
| **Identify** | `POST /api/identify` | Maps a Heap-generated `user_id` to a custom `identity` (e.g., email). |
| **User Properties** | `POST /api/add_user_properties` | Attaches metadata (e.g., "plan: premium") to a specific user profile. |
| **Live View** | Web UI Only | Real-time stream of incoming events, used for agent debugging. |
| **Data Out** | Integration Sync | Periodic export of captured data to cloud data warehouses. |
| **Labeling** | Web UI Only | The process of defining "events" from raw captured data. |

---

## 4. Setup Guide

### For Humans
1. Sign up for a Heap account at [heapanalytics.com](https://heapanalytics.com).
2. Create a new "Project" for your agent environment.
3. Navigate to **Settings > Projects** to find your `app_id`.
4. Navigate to **Settings > API Tokens** to generate a private `secret`.
5. (Optional) Install the web snippet if the agent interacts with a web frontend.

### For Agents
1. **Store Credentials:** Securely inject `HEAP_APP_ID` and `HEAP_SECRET` into the agent's environment.
2. **Initialize Connection:** Ensure the agent can reach `heapanalytics.com` on port 443.
3. **Validate Auth:** Execute a test `track` call to the API.
4. **Verify Ingestion:** Check the "Live View" in the Heap dashboard to confirm the event was received and parsed correctly.

```python
import requests

def validate_heap_connection(app_id, secret):
    payload = {
        "app_id": app_id,
        "identity": "agent-connection-test",
        "event": "Agent Validation Run",
        "properties": {"status": "success"}
    }
    # Note: Heap Server-side API uses the same endpoint for track/identify logic
    response = requests.post("https://heapanalytics.com/api/track", json=payload)
    return response.status_code == 200
```

---

## 5. Integration Example

This example demonstrates an agent logging a completed task using the Python `requests` library.

```python
import requests
import os

def log_agent_action(user_email, action_name, task_id):
    url = "https://heapanalytics.com/api/track"
    
    # Heap requires app_id in the body for server-side calls
    payload = {
        "app_id": os.getenv("HEAP_APP_ID"),
        "identity": user_email,
        "event": f"Agent {action_name}",
        "properties": {
            "task_id": task_id,
            "agent_version": "2.1.0",
            "execution_environment": "production"
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        print(f"Successfully logged {action_name} to Heap.")
    except requests.exceptions.RequestException as e:
        # Agents should handle analytics failures gracefully 
        # to avoid blocking core logic
        print(f"Heap logging failed: {e}")

# Usage
log_agent_action("user@example.com", "Data Extraction", "task_8821")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Latency P50** | 200ms | Standard for single-event tracking. |
| **Latency P95** | 470ms | Occasional spikes during peak ingestion hours. |
| **Latency P99** | 800ms | Significant tail latency; agents should use async calls. |
| **Rate Limit** | 30 requests/sec | Per IP/App ID. Check docs for current enterprise limits. |
| **Max Payload** | 256 KB | Maximum size for a single track request. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Heap does not support idempotency keys. Retrying a failed `track` call will result in duplicate events if the original request actually reached the server. Agents should prioritize "at-most-once" delivery for analytics unless financial accuracy is required.
*   **Retry Behavior:** Implement exponential backoff for `429 Too Many Requests`. For `5xx` errors, agents should attempt a maximum of 3 retries before suppressing the error to prevent workflow interruption.
*   **Error Codes:** A `400 Bad Request` usually indicates malformed JSON or a missing `app_id`. A `403 Forbidden` indicates an invalid secret. Agents should log these as configuration errors rather than transient network issues.
*   **Schema Stability:** Heap is schema-less on ingestion. You can send any property key-value pair. This is highly agent-friendly as it allows agents to evolve their metadata without breaking the integration.
*   **Cost-per-operation:** The free tier is generous (10k sessions), but "sessions" are defined by user activity. For pure server-side agents, costs are generally low until moving to the Growth tier, which requires human negotiation.
*   **Identity Resolution:** Agents must be careful with the `identity` field. If an agent identifies a user incorrectly, it can merge two distinct user profiles in Heap, which is difficult to undo programmatically.

---

## 8. Rhumb Context: Why Heap Scores 5.14 (L2)

Heap’s **5.14 score** reflects a service that is highly reliable for data ingestion but lacks the "loop-closing" capabilities required for high-autonomy agents:

1. **Execution Autonomy (6.1)** — The Server-Side API is simple and predictable. The schema-less nature of the ingestion API allows agents to append new metadata fields autonomously without human intervention to "update the database schema." However, the lack of a robust Query API for agents to *retrieve* and *reason* about their own performance data limits them to being "write-only" participants.

2. **Access Readiness (4.1)** — This is Heap's weakest dimension. While the free tier exists, the transition to paid tiers is gated by "Schedule a Demo" sales cycles. Agents cannot autonomously upgrade their own infrastructure or handle usage spikes by programmatically increasing their quota. The lack of self-serve billing for mid-tier usage is a significant barrier to agent-native scaling.

3. **Agent Autonomy (5.0)** — Heap is excellent for "Observability" (letting humans see what agents do), but poor for "Agency" (letting agents see what they've done to improve). Without a real-time webhook system or an easy-to-use REST-based query engine, agents cannot use Heap as a feedback loop to adjust their behavior in real-time.

**Bottom line:** Heap is a tier-1 choice for agents that need to report status and impact to human stakeholders with minimal setup. However, for agents that need to query their own analytics to make autonomous decisions, it is currently outclassed by more "open" platforms.

**Competitor context:** **PostHog (7.2)** scores significantly higher due to its open-source nature, self-serve transparent pricing, and built-in feature flags that agents can toggle. **Mixpanel (6.8)** also outscores Heap for agents due to its more mature Query API, which allows agents to programmatically analyze trends.
