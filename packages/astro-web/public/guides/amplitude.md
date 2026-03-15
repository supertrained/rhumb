# Amplitude — Agent-Native Service Guide

> **AN Score:** 5.66 · **Tier:** L3 · **Category:** Analytics & Product Intelligence

---

## 1. Synopsis
Amplitude is a premier product intelligence platform that allows agents to track user behavior, perform cohort analysis, and derive actionable insights from event data. For autonomous agents, Amplitude acts as a sophisticated sensory system and feedback loop. Rather than just logging "what" happened, agents can query Amplitude to understand "why" certain behaviors occur, identifying high-value user cohorts or detecting anomalies in feature adoption. This makes it indispensable for agents tasked with product optimization, personalized marketing, or automated growth experiments. Amplitude offers a generous free "Starter" tier (up to 50,000 monthly tracked users), while advanced governance and higher volume require paid plans.

---

## 2. Connection Methods

### REST API
Amplitude provides several specialized APIs. The **HTTP V2 API** is the primary endpoint for event ingestion, optimized for high-volume, low-latency writes. For data retrieval, the **Dashboard REST API** and **Export API** allow agents to query computed metrics, retrieve cohort definitions, and download raw event data in bulk.

### SDKs
Amplitude maintains high-quality, agent-ready SDKs for major environments. For backend agent logic, the **Python SDK** (`amplitude-analytics`) and **Node.js SDK** (`@amplitude/analytics-node`) are the standard. These SDKs handle local queuing, batching, and basic retry logic out of the box, which reduces the boilerplate required for reliable event logging.

### Webhooks
Amplitude supports outbound webhooks (primarily in Enterprise tiers) to notify agents when specific thresholds are met or when users enter/exit defined cohorts. This enables event-driven agent architectures where an agent "wakes up" to perform an action (like sending a personalized email) the moment a user behavior triggers a predefined rule.

### Auth Flows
Authentication varies by endpoint. Ingestion requires only an `api_key` passed in the JSON payload. Management and Query APIs require **Basic Authentication**, using the `api_key` as the username and the `secret_key` as the password. Agents must store these as environment variables; project-level scoping is the primary method for isolating agent access.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Event** | `/2/httpapi` | A single point-in-time action (e.g., "File Uploaded") with associated properties. |
| **Identify** | `/identify` | Updates or sets properties for a specific user (e.g., "Plan Type: Pro"). |
| **Cohort** | `/api/3/cohorts` | A group of users defined by shared characteristics or behaviors over time. |
| **User Look-up** | `/api/2/usersearch` | Retrieves the full event history and property set for a specific user ID. |
| **Export** | `/api/2/export` | Downloads raw event data for a specific time range in JSON format. |
| **Annotation** | `/api/2/annotations` | Programmatically marks events on charts (e.g., "Agent Version 2.0 Deployed"). |

---

## 4. Setup Guide

### For Humans
1. Sign up for an account at [amplitude.com](https://amplitude.com).
2. Create a new "Project" specifically for your agent's environment.
3. Navigate to **Settings > Projects > [Project Name]**.
4. Copy the **API Key** and **Secret Key**.
5. (Optional) Define a "Plan" in Amplitude Data to enforce schema validation on incoming agent events.
6. Configure Team RBAC to ensure the agent's key has the minimum necessary permissions.

### For Agents
1. **Initialize SDK:** Install the package (e.g., `pip install amplitude-analytics`).
2. **Configure Credentials:** Load the `api_key` from a secure vault.
3. **Validate Connection:** Send a "Heartbeat" event to verify the key is active.
4. **Verify Schema:** (If using Data Planning) Send a test event with all required properties to ensure no 400 errors occur due to schema violations.

```python
from amplitude import Amplitude, BaseEvent

client = Amplitude("YOUR_API_KEY")
# Validation check
response = client.track(BaseEvent(event_type="agent_connection_test", user_id="agent_01"))
# Success is indicated by a 200 OK response from the ingestion endpoint
```

---

## 5. Integration Example

This example demonstrates an agent tracking a specific action with metadata and an `insert_id` for idempotency.

```python
import uuid
from amplitude import Amplitude, BaseEvent

# Initialize the client
amp_client = Amplitude(api_key="am_api_key_12345")

def log_agent_action(user_id, action_name, metadata):
    """
    Logs an autonomous action to Amplitude with idempotency.
    """
    event = BaseEvent(
        event_type=action_name,
        user_id=user_id,
        event_properties=metadata,
        # insert_id prevents duplicate billing/metrics if the agent retries
        insert_id=str(uuid.uuid4()), 
        app_version="2.1.0-beta"
    )
    
    # Async-style tracking (SDK handles batching)
    try:
        response = amp_client.track(event)
        return response
    except Exception as e:
        # Agent decision: Log locally and retry on next tick
        print(f"Amplitude logging failed: {e}")
        return None

# Usage
log_agent_action("user_99", "automated_upsell_offered", {"discount": 20, "model": "gpt-4o"})
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 175ms | Standard for HTTP V2 ingestion endpoint. |
| **P95 Latency** | 400ms | Occurs during peak global traffic or large batch processing. |
| **P99 Latency** | 680ms | Rare; usually indicates network congestion or complex query processing. |
| **Rate Limits** | 100 req/sec | Default for most ingestion; query limits vary by plan. |
| **Data Freshness** | < 30 seconds | Time from ingestion to availability in Query APIs. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Always provide an `insert_id` for every event. If the agent retries a request due to a timeout, Amplitude uses this ID to prevent duplicate data points.
*   **Retry Behavior:** Agents should implement exponential backoff for `429` (Rate Limit) and `5xx` (Server Error) codes. The Python/Node SDKs handle some of this, but it must be verified in the agent's error-handling loop.
*   **Error Codes → Agent Decisions:**
    *   `400`: Invalid Schema. Agent should stop sending this event type and alert a human to update the data contract.
    *   `413`: Payload Too Large. Agent must reduce batch size.
    *   `429`: Throttled. Agent should enter "buffer mode" and slow down ingestion.
*   **Schema Stability:** Amplitude is "schema-on-read" by default, but using **Amplitude Data** allows for "schema-on-write." Agents benefit from strict validation to ensure their downstream analysis isn't corrupted by malformed data.
*   **Cost-per-operation:** Ingestion is cheap (Starter tier is free); however, the **Export API** can be expensive in terms of processing time and potential egress costs on high-volume projects.
*   **Contextual Awareness:** Use the `Identify` API to store agent-specific state (e.g., `last_interaction_timestamp`) directly on the user profile so the agent doesn't need a separate database for basic user state.

---

## 8. Rhumb Context: Why Amplitude Scores 5.66 (L3)

Amplitude's **5.66 score** reflects a powerful but complex service that requires significant configuration before an agent can operate with full autonomy:

1. **Execution Autonomy (6.6)** — The ingestion API is exceptionally robust and predictable. The inclusion of `insert_id` for idempotency is a top-tier feature for agent reliability. However, the Query APIs are significantly more complex, often requiring the agent to understand Amplitude's proprietary query syntax or handle large JSON exports, which lowers the score compared to simpler CRUD services.

2. **Access Readiness (4.6)** — This is the primary friction point. While there is a free tier, getting started requires navigating a heavy UI designed for human product managers. API keys are project-specific, and there is no "single-click" OAuth flow for third-party agents to request access to a user's analytics without manual key copying.

3. **Agent Autonomy (5.67)** — Amplitude provides great "sensory" data, but "acting" on that data requires the agent to bridge the gap between analytics and action. While webhooks exist, they are often locked behind higher enterprise tiers, meaning most L3 agents will be forced to poll the Query API, which is less efficient than a push-based architecture.

**Bottom line:** Amplitude is the best-in-class choice for agents that need to perform "Product Intelligence" and behavioral analysis. It is a "Ready" (L3) service because while the API is rock-solid, the administrative overhead and lack of easy agent-onboarding flows prevent it from reaching L4.

**Competitor context:** **Mixpanel (6.12)** scores slightly higher due to a more developer-friendly Query API (JQL/Argo). **PostHog (7.05)** scores significantly higher for agents because it is open-source, offers easier self-hosting, and includes built-in feature flags and session replays in a more unified API surface.
