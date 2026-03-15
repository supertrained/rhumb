# Calendly — Agent-Native Service Guide

> **AN Score:** 5.87 · **Tier:** L3 · **Category:** Scheduling & Calendar

---

## 1. Synopsis
Calendly is a scheduling automation platform that abstracts the complexity of timezone math, calendar conflict resolution, and buffer management. For agents, Calendly serves as a programmable interface for time-based coordination—allowing an agent to book meetings, retrieve availability, and manage event lifecycles without direct calendar access. It is particularly valuable for "AI Assistant" agents that handle inbound leads or internal coordination. The API is RESTful (v2) and highly structured. While there is a free tier for individuals (1 event type), programmatic use for agents typically requires a "Standard" or "Higher" plan to access advanced features like routing forms and multiple event types.

---

## 2. Connection Methods

### REST API
Calendly’s primary interface is its v2 REST API. It uses predictable, resource-oriented URLs and returns JSON-encoded responses. The API is versioned and follows standard HTTP semantics. Agents interact with it primarily through `GET` requests for discovery (finding event types) and `POST` requests for administrative actions or webhook management.

### SDKs
Calendly does not maintain a large suite of official language-specific SDKs. Most agent implementations use standard HTTP libraries (like `axios` in Node.js or `requests` in Python). There is a community-maintained Python wrapper (`calendly-v2`), but direct REST integration is recommended for agents to ensure full control over error handling and header management.

### Webhooks
Crucial for reactive agents. Calendly supports webhooks for events like `invitee.created` and `invitee.canceled`. This allows an agent to "wake up" when a meeting is booked, rather than polling for status. Webhooks include a `signature` header for HMAC verification, which agents should always validate to prevent spoofing.

### Auth Flows
*   **Personal Access Tokens (PAT):** Best for internal-use agents. Generated in the Calendly developer portal, these provide long-lived access to a single user's account.
*   **OAuth 2.0:** Required for agents that act on behalf of multiple third-party users. It follows the standard Authorization Code flow. Scopes are granular (e.g., `users:read`, `events:read`), which is excellent for agent security.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **User** | `GET /users/me` | Returns the unique URI and details for the authenticated user/agent. |
| **Event Type** | `GET /event_types` | The template for a meeting (e.g., "15 Minute Discovery"). Agents need the UUID to book. |
| **Scheduled Event** | `GET /scheduled_events` | A specific instance of a meeting on the calendar. |
| **Invitee** | `GET /scheduled_events/{uuid}/invitees` | Details about the person who booked the meeting (email, answers to questions). |
| **Availability** | `GET /user_availability_schedules` | Returns the set hours a user is available for booking via the API. |
| **Organization** | `GET /organizations/{uuid}` | The root container for team-based scheduling and resource management. |

---

## 4. Setup Guide

### For Humans
1.  Log in to the [Calendly Developer Portal](https://developer.calendly.com/).
2.  Navigate to **API Keys** and generate a new Personal Access Token.
3.  Store the token in a secure secret manager (e.g., `.env` or Vault).
4.  Create at least one "Event Type" in the Calendly dashboard (e.g., "AI Consultation").
5.  Set your "Availability" hours in the dashboard to ensure the API has slots to report.

### For Agents
1.  **Identity Discovery:** Call `GET https://api.calendly.com/users/me` to retrieve your `current_organization` URI.
2.  **Resource Discovery:** Call `GET https://api.calendly.com/event_types?user={user_uri}` to map human-readable names to API UUIDs.
3.  **Validation:** Verify the agent has the `events:write` scope if it needs to cancel or reschedule events.
4.  **Connection Test:** 
```python
import requests
headers = {"Authorization": "Bearer <TOKEN>"}
res = requests.get("https://api.calendly.com/users/me", headers=headers)
assert res.status_code == 200, "Calendly Connection Failed"
```

---

## 5. Integration Example

```python
import requests

class CalendlyAgent:
    def __init__(self, api_token):
        self.base_url = "https://api.calendly.com"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

    def get_active_event_types(self):
        # First, get the user URI
        user_info = requests.get(f"{self.base_url}/users/me", headers=self.headers).json()
        user_uri = user_info['resource']['uri']
        
        # Then, list event types for that user
        params = {"user": user_uri, "active": "true"}
        response = requests.get(f"{self.base_url}/event_types", headers=self.headers, params=params)
        
        if response.status_code == 200:
            return response.json().get('collection', [])
        return []

    def cancel_event(self, event_uuid, reason="Canceled by AI Agent"):
        url = f"{self.base_url}/scheduled_events/{event_uuid}/cancellation"
        payload = {"reason": reason}
        return requests.post(url, headers=self.headers, json=payload)

# Usage
agent = CalendlyAgent("your_pat_here")
events = agent.get_active_event_types()
print(f"Agent found {len(events)} booking templates.")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 140ms | Fast enough for real-time chat agent interactions. |
| **P95 Latency** | 320ms | Occasional spikes during complex availability lookups. |
| **P99 Latency** | 540ms | Usually occurs during heavy organization-wide queries. |
| **Rate Limit** | 30 req/min | Relatively strict; agents should cache `event_types`. |
| **Sync Speed** | Near-instant | Webhooks trigger within <2s of a human booking. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Calendly does **not** support a standard `Idempotency-Key` header for event creation (booking is usually done via a hosted UI). For administrative actions like cancellations, agents must implement "check-before-act" patterns to avoid double-processing.
*   **Retry Behavior:** Implement exponential backoff for `429 Too Many Requests`. Calendly's limits are burst-sensitive.
*   **Error Codes:** A `403 Forbidden` often means the PAT is valid but lacks the scope for a specific organization resource. Agents should escalate this as a "Permissions Error" rather than a "Connection Error."
*   **Schema Stability:** The v2 API is stable, but the `resource` objects are deeply nested. Agents should use robust JSON pathing to avoid `KeyError` exceptions.
*   **Cost-per-operation:** Effectively $0 beyond the flat SaaS subscription, but the low rate limit (30 RPM) imposes a "throughput cost" that requires agents to use efficient batching or caching.
*   **Discovery Requirement:** Agents cannot "guess" event IDs. They must perform a discovery crawl of `event_types` at startup to map slugs to URIs.
*   **Timezone Handling:** The API returns all timestamps in UTC (ISO 8601). Agents must be explicitly programmed to convert these to the user's local timezone before presenting options in chat.

---

## 8. Rhumb Context: Why Calendly Scores 5.87 (L3)

Calendly's **5.87 score** reflects a service that is highly reliable but remains "human-first" in its design, requiring some shim logic for autonomous agents:

1.  **Execution Autonomy (6.8)** — The API provides high-level abstractions. Agents don't have to manage calendar "busy" blocks; they just query "Event Types." This high score is due to the service handling the "hard parts" of scheduling (conflicts, buffers) automatically. However, the lack of a direct "Create Event" API (most booking happens via their frontend) limits full agent autonomy in booking.

2.  **Access Readiness (4.9)** — This is the primary drag on the score. Setting up OAuth for multi-tenant agents is cumbersome, and there is no official "Sandbox" environment for testing. Agents must test against live accounts, which carries the risk of sending real emails to real users during development.

3.  **Agent Autonomy (5.67)** — While the webhook system is robust, the discovery process is heavy. An agent cannot simply "act"—it must first fetch the user, then fetch the organization, then fetch the event types. This multi-step bootstrapping makes it harder for zero-config agents to deploy.

**Bottom line:** Calendly is the most stable and feature-rich scheduling service for agents, but it requires a "Discovery" phase at runtime. It is best suited for L3 agents that have a persistent state and can cache resource URIs.

**Competitor context:** **Acuity Scheduling (5.2)** offers a more direct "Create Appointment" API but has a significantly more fragmented data model. **Cronofy (6.4)** scores higher for purely programmatic agents due to its "Calendar-as-Infrastructure" approach, but it lacks Calendly's user-friendly workflow automation.
