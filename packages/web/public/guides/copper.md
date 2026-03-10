# Copper — Agent-Native Service Guide

> **AN Score:** 4.66 · **Tier:** L2 · **Category:** CRM & Sales

---

## 1. Synopsis
Copper is a CRM specifically engineered for the Google Workspace ecosystem, prioritizing simplicity and "zero-input" data management for small-to-medium businesses. For AI agents, Copper serves as a lightweight, structured memory for relationship management. It allows agents to automate the lead-to-deal lifecycle, from ingesting new contacts to updating pipeline stages based on external triggers. While it lacks the enterprise complexity of Salesforce, its REST API is highly predictable, making it an excellent target for agents performing sales development (SDR) or customer success (CS) tasks. Copper does not offer a permanent free API tier; programmatic access requires a paid subscription, though a 14-day trial is available for initial development and testing.

---

## 2. Connection Methods

### REST API
Copper provides a standard JSON-based REST API (v1) hosted at `https://api.copper.com/developer_api/v1/`. The API follows standard HTTP verbs and uses JSON for both request and response bodies. It is highly resource-oriented, making it easy for agents to map LLM entities (like "a new customer") directly to API resources (like `people` or `leads`).

### SDKs
While Copper does not maintain a broad range of high-level SDKs, they provide a maintained Node.js library and comprehensive documentation for raw HTTP implementation. Most agent operators find that using standard HTTP clients (like `httpx` in Python or `axios` in JS) is more reliable for agent-native workflows due to the specific header requirements.

### Webhooks
Copper supports outbound webhooks for real-time event synchronization. Agents can subscribe to events such as `lead.create`, `opportunity.stage_change`, or `task.complete`. This is critical for building "reactive" agents that trigger workflows (e.g., sending a Slack notification) the moment a human updates a record in the Copper UI.

### Auth Flows
Copper uses a custom header-based authentication scheme. Unlike standard Bearer tokens, you must provide three specific headers for every request:
1. `X-PW-AccessToken`: Your API key.
2. `X-PW-Application`: Always set to `developer_api`.
3. `X-PW-UserEmail`: The email address of the user associated with the API key.

This "dual-key" approach (Key + Email) adds a small layer of friction for agent configuration but allows for clear attribution of agent actions in the CRM audit log.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Lead** | `/leads` | Potential customers who haven't been qualified yet. |
| **Person** | `/people` | Qualified contacts; the core "identity" in the CRM. |
| **Company** | `/companies` | Organizations that People belong to. |
| **Opportunity** | `/opportunities` | Potential deals tracked through pipeline stages. |
| **Task** | `/tasks` | Action items associated with a record (e.g., "Follow up"). |
| **Activity** | `/activities` | Logged interactions like calls, notes, or emails. |
| **Pipeline** | `/pipelines` | Definitions of the sales stages used by Opportunities. |

---

## 4. Setup Guide

### For Humans
1. Log in to your Copper account as an **Administrator**.
2. Navigate to **Settings** > **Integrations** > **API Keys**.
3. Click **Generate API Key**.
4. Copy the **API Key** immediately (it will not be shown again).
5. Note the **User Email** associated with the key.
6. Ensure the user has the necessary permissions for the records the agent will access.

### For Agents
1. **Store Credentials:** Securely inject `COPPER_API_KEY` and `COPPER_USER_EMAIL`.
2. **Define Headers:** Set `X-PW-Application: developer_api`.
3. **Validate Connection:** Perform a `GET` request to the `/account` endpoint.
4. **Check Response:** Confirm a `200 OK` status to ensure the key and email pair are valid.

```python
import requests

headers = {
    "X-PW-AccessToken": "your_api_key",
    "X-PW-Application": "developer_api",
    "X-PW-UserEmail": "agent-owner@company.com",
    "Content-Type": "application/json"
}

# Validation check
response = requests.get("https://api.copper.com/developer_api/v1/account", headers=headers)
if response.status_code == 200:
    print("Agent connection verified.")
```

---

## 5. Integration Example

This Python example demonstrates an agent creating a new Lead and then logging an initial activity note.

```python
import requests

BASE_URL = "https://api.copper.com/developer_api/v1"
HEADERS = {
    "X-PW-AccessToken": "sk_live_...",
    "X-PW-Application": "developer_api",
    "X-PW-UserEmail": "bot@company.com",
    "Content-Type": "application/json"
}

def create_lead_with_note(name, email, note_text):
    # 1. Create the Lead
    lead_data = {"name": name, "email": {"email": email, "category": "work"}}
    lead_res = requests.post(f"{BASE_URL}/leads", json=lead_data, headers=HEADERS)
    lead_res.raise_for_status()
    lead_id = lead_res.json()['id']

    # 2. Log an Activity (Note)
    activity_data = {
        "parent": {"id": lead_id, "type": "lead"},
        "type": {"category": "user", "id": 0}, # '0' is usually the default 'Note' type
        "details": note_text
    }
    act_res = requests.post(f"{BASE_URL}/activities", json=activity_data, headers=HEADERS)
    return act_res.json()

# Usage by Agent
result = create_lead_with_note("Alice Smith", "alice@example.com", "Agent-initiated lead via Rhumb.")
print(f"Lead created with Activity ID: {result['id']}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Latency P50** | 220ms | Snappy for standard CRUD operations. |
| **Latency P95** | 520ms | Occasional spikes during complex search queries. |
| **Latency P99** | 900ms | Rare; usually seen during heavy bulk updates. |
| **Rate Limit** | 600 req / 10 min | Per API key. High enough for most single-agent workflows. |
| **Uptime** | 99.9% | Highly stable SaaS infrastructure. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Copper does **not** support native idempotency keys (e.g., `Idempotency-Key` headers). Agents must perform a "search-before-create" check using the email address or external ID to avoid creating duplicate People or Leads.
*   **Retry Behavior:** Use exponential backoff for `429 Too Many Requests`. For `5xx` errors, a single retry after 2 seconds is usually sufficient.
*   **Error Codes:** `400` usually indicates a missing required field (like `name` for a Lead). `401` indicates a mismatch between the API key and the `X-PW-UserEmail` header.
*   **Schema Stability:** The API is L2 "Developing." While the core entities are stable, custom fields are referenced by ID (e.g., `custom_field_12345`), requiring the agent to first fetch the field definitions via `/custom_field_definitions`.
*   **Cost-per-operation:** Negligible. Copper’s pricing is per-seat, so once the agent’s user account is paid for, API call volume (within rate limits) is free.
*   **Context Window Management:** When fetching "Activities," Copper returns a flat list. Agents should be instructed to only fetch the last 5-10 activities to avoid blowing out the context window with historical log data.

---

## 8. Rhumb Context: Why Copper Scores 4.66 (L2)

Copper’s **4.66 score** identifies it as a capable but standard SaaS integration that requires specific handling for agent autonomy:

1. **Execution Autonomy (5.6)** — The REST API is logical and well-documented. However, the lack of idempotency tokens means the agent must be "smarter" about checking for existing records before acting. The search endpoints are robust, which helps mitigate this, but it requires more complex multi-step logic than an L3 service.

2. **Access Readiness (3.6)** — This is the primary friction point. To get an agent online, a human administrator must manually generate a key and provide a specific user email. There is no "one-click" OAuth flow for third-party agents to self-provision, limiting its readiness for zero-touch deployment.

3. **Agent Autonomy (4.67)** — Copper provides excellent webhooks and a clear relationship model (Leads → People → Opportunities). The governance is solid (SOC 2), and the per-seat billing model is predictable. However, the dependency on custom field IDs (which vary by workspace) means agents cannot be truly "plug-and-play" without an initial discovery phase to map the environment.

**Bottom line:** Copper is a reliable L2 service for agents that need to manage sales data. It is significantly easier to integrate than enterprise giants, but it requires the agent operator to implement custom logic for deduplication and field discovery.

**Competitor context:** **Salesforce (3.2)** scores lower due to extreme schema complexity and "API-heavy" pricing. **Pipedrive (5.1)** scores slightly higher due to a more modern API token system and better native support for idempotent updates. For agents operating primarily within Google Workspace, Copper remains the superior choice despite the lower score.
