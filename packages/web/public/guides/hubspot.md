# HubSpot — Agent-Native Service Guide

> **AN Score:** 4.64 · **Tier:** L2 · **Category:** CRM & Sales

---

## 1. Synopsis
HubSpot is a comprehensive CRM platform that centralizes customer data, sales pipelines, and marketing automation. For agents, HubSpot serves as the primary "source of truth" for customer interactions, enabling programmatic lead qualification, contact enrichment, and deal tracking. The platform's API-first architecture allows agents to automate the entire sales lifecycle, from initial record creation to complex workflow triggers. HubSpot offers a robust free tier for basic CRM features, while advanced automation and custom objects require paid tiers (Starter, Professional, or Enterprise). Its mature API documentation and standardized object model make it a reliable, though occasionally complex, choice for agents needing to persist and retrieve relational customer data at scale.

---

## 2. Connection Methods

### REST API
The HubSpot REST API (v3) is the primary interface for agent integration. It follows standard RESTful patterns, using JSON for request and response bodies. The API is organized around "Objects" (Contacts, Companies, Deals) and "Engagements" (Tasks, Notes, Meetings). Agents should prioritize v3 endpoints for better schema consistency and performance compared to legacy v1/v2 routes.

### SDKs
HubSpot maintains high-quality, official SDKs for Python (`hubspot-api-client`), JavaScript (`@hubspot/api-client`), PHP, Ruby, and Java. These libraries handle boilerplate tasks like header management, automatic serialization, and basic retry logic. For agent development, the Python and Node.js SDKs are the most mature, offering full type definitions that assist agents in generating valid requests.

### Webhooks
HubSpot supports webhooks through its "Webhooks API" (available in developer accounts) or through Workflow extensions in Professional/Enterprise tiers. Agents can subscribe to events such as `contact.creation`, `deal.propertyChange`, or `company.deletion`. This is critical for building "reactive" agents that trigger logic based on human activity within the CRM UI.

### Auth Flows
HubSpot supports two main authentication methods:
1.  **Private App Access Tokens:** The preferred method for single-tenant agents or internal integrations. It provides a long-lived Bearer token with specific scopes.
2.  **OAuth 2.0:** Required for multi-tenant applications where an agent needs to access multiple different HubSpot portals. This follows the standard authorization code grant flow.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Contact** | `/crm/v3/objects/contacts` | Individual persons; the core unit of the CRM. |
| **Company** | `/crm/v3/objects/companies` | Organizations associated with contacts and deals. |
| **Deal** | `/crm/v3/objects/deals` | Revenue opportunities tracked through pipeline stages. |
| **Association** | `/crm/v3/associations` | The "glue" that links contacts to companies or deals. |
| **Search** | `/crm/v3/objects/{object}/search` | High-performance filtering (e.g., find contact by email). |
| **Property** | `/crm/v3/properties/{object}` | Metadata definitions for custom or standard fields. |
| **Owner** | `/crm/v3/owners/` | Maps CRM records to specific human users/agents. |

---

## 4. Setup Guide

### For Humans
1.  Log into your HubSpot portal and navigate to **Settings** (gear icon).
2.  In the left sidebar, go to **Integrations** > **Private Apps**.
3.  Click **Create a private app**.
4.  Provide a name (e.g., "Autonomous Sales Agent") and select the **Scopes** tab.
5.  Check the required scopes (typically `crm.objects.contacts.read/write`, `crm.objects.deals.read/write`).
6.  Click **Create app** and copy the provided **Access Token**.
7.  Store this token securely in your agent's environment variables.

### For Agents
1.  **Validate Connection:** Execute a `GET` request to `/crm/v3/objects/contacts?limit=1` to ensure the token is valid.
2.  **Verify Scopes:** Check if the agent can perform a write operation by creating a "Test Contact."
3.  **Map Schema:** Query `/crm/v3/properties/contacts` to identify required fields and custom properties.
4.  **Confirm Identity:** Fetch `/crm/v3/owners/` to find the internal ID the agent should use for record assignment.

```python
# Quick connection check for an agent
from hubspot import HubSpot

client = HubSpot(access_token="your_token")
try:
    api_response = client.crm.contacts.basic_api.get_page(limit=1)
    print("Connection Verified: HubSpot API is accessible.")
except Exception as e:
    print(f"Connection Failed: {e}")
```

---

## 5. Integration Example

```python
import os
from hubspot import HubSpot
from hubspot.crm.contacts import SimplePublicObjectInput, ApiException

# Initialize the client
client = HubSpot(access_token=os.environ.get("HUBSPOT_ACCESS_TOKEN"))

def upsert_contact_and_deal(email, first_name, deal_name):
    try:
        # 1. Create a contact
        contact_props = {"email": email, "firstname": first_name}
        contact_input = SimplePublicObjectInput(properties=contact_props)
        contact = client.crm.contacts.basic_api.create(simple_public_object_input=contact_input)
        
        # 2. Create a deal
        deal_props = {"dealname": deal_name, "amount": "5000", "pipeline": "default", "dealstage": "appointmentscheduled"}
        deal_input = SimplePublicObjectInput(properties=deal_props)
        deal = client.crm.deals.basic_api.create(simple_public_object_input=deal_input)
        
        # 3. Associate Deal with Contact
        client.crm.associations.v4.basic_api.create(
            object_type="deals",
            object_id=deal.id,
            to_object_type="contacts",
            to_object_id=contact.id,
            association_spec=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}]
        )
        return f"Success: Created Deal {deal.id} for Contact {contact.id}"
    except ApiException as e:
        return f"Error: {e.body}"
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 280ms | Standard for single object CRUD operations. |
| **P95 Latency** | 680ms | Occurs during complex search queries or batch writes. |
| **P99 Latency** | 1200ms | Peak times or large association lookups. |
| **Rate Limit** | 100 req / 10s | Free/Starter tier limit (per token). |
| **Burst Limit** | Variable | Professional/Enterprise tiers allow up to 150-200 req/10s. |
| **Search Latency** | ~400ms | The `/search` endpoint is slightly slower than direct ID lookups. |

---

## 7. Agent-Native Notes

*   **Idempotency:** HubSpot does **not** support idempotency keys on POST requests. Creating a contact twice with the same email will result in a `409 Conflict`. Agents must implement a "Search-then-Update" pattern (using `/search` by email) to avoid duplicate records.
*   **Retry Behavior:** Agents should implement exponential backoff specifically for `429 Too Many Requests`. HubSpot's rate limits are sliding-window; a 2-5 second pause is usually sufficient to clear the buffer.
*   **Error Codes:** 
    *   `400`: Validation error (missing required property).
    *   `403`: Scope error (agent lacks permission for that object).
    *   `409`: Conflict (record already exists—trigger an update instead).
*   **Schema Stability:** HubSpot v3 is highly stable. However, "Custom Objects" are only available on Enterprise plans, so agents should check for object existence before attempting to query non-standard types.
*   **Cost-per-operation:** Effectively zero on the Free tier until rate limits are hit. For high-volume agents, the cost scales with the HubSpot subscription tier rather than per-API-call.
*   **Association Logic:** Linking objects (e.g., Contact to Company) is a separate API call in v3. Agents must be programmed to handle this multi-step process to maintain data integrity.
*   **Property Discovery:** Since users can add custom fields, agents should perform a one-time "Property Discovery" crawl at startup to map available fields to their internal logic.

---

## 8. Rhumb Context: Why HubSpot Scores 4.64 (L2)

HubSpot’s **4.64 score** identifies it as a reliable but "access-heavy" service that requires significant human configuration before an agent can operate autonomously:

1.  **Execution Autonomy (5.3)** — The CRM's object model is highly structured and predictable. The `/search` endpoint allows agents to find data with precision, and the v3 API provides clear, actionable error messages. However, the lack of native idempotency keys on creation endpoints forces agents to write extra "check-before-create" logic, which introduces potential race conditions.

2.  **Access Readiness (3.5)** — This is HubSpot's primary friction point. While there is a free tier, the setup process for "Private Apps" and the complex OAuth scope selection requires a human to navigate the UI. Agents cannot easily "self-provision" or upgrade their own capabilities. The 100 requests per 10 seconds limit on the free tier is a tight ceiling for high-velocity agents.

3.  **Agent Autonomy (5.67)** — HubSpot excels in governance and auditability. The Private App system allows for granular scoping, ensuring an agent can be restricted to "Contacts Only" without seeing "Deals" or "Financials." The availability of webhooks allows for event-driven architectures, but the high latency (P99 at 1.2s) means agents must be designed for asynchronous operations rather than real-time synchronous loops.

**Bottom line:** HubSpot is a Tier-2 service because it provides a rock-solid data foundation but requires a human "gatekeeper" for initial setup and scope management. It is the preferred CRM for agents due to its superior documentation and SDK support compared to legacy competitors.

**Competitor context:** **Salesforce (3.8)** scores lower due to its significantly more complex SOQL/REST overhead and higher cost of entry. **Pipedrive (4.5)** is a close competitor but lacks the breadth of HubSpot’s free tier and marketing integration ecosystem. For most agent-led sales workflows, HubSpot is the pragmatic choice.
