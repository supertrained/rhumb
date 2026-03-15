# Salesforce — Agent-Native Service Guide

> **AN Score:** 4.75 · **Tier:** L2 · **Category:** CRM & Sales

---

## 1. Synopsis
Salesforce is the global standard for enterprise Customer Relationship Management (CRM), acting as the definitive system of record for sales, service, and marketing data. For agents, Salesforce is a high-gravity data source: it provides the context (leads, accounts, opportunities) required to execute business logic. While powerful, its API ecosystem is massive and complex, requiring agents to navigate legacy SOAP structures alongside modern REST and GraphQL interfaces. There is no traditional "free tier" for production, but developers can access a "Developer Edition" for testing. Pricing is enterprise-first, typically involving annual contracts and per-user licensing, making it a high-cost, high-governance environment for autonomous agents.

---

## 2. Connection Methods

### REST API
The Salesforce REST API is the primary integration point for agents. It provides access to SObjects (Salesforce Objects) for CRUD operations and supports SOQL (Salesforce Object Query Language) for complex data retrieval. The API is versioned (e.g., `/services/data/v60.0/`) and returns JSON or XML.

### SDKs
For Python-based agents, `simple-salesforce` is the industry standard, abstracting the authentication and SObject management. For JavaScript/Node.js, `jsforce` provides a robust library that handles both REST and Bulk APIs. Both SDKs support the specialized SOQL syntax required for data discovery.

### MCP (Model Context Protocol)
Salesforce has official support for the Model Context Protocol (MCP), allowing agents to connect directly to Salesforce data using a standardized schema. This is the preferred method for LLM-based agents that need to browse the CRM schema dynamically without custom tool-calling code for every object.

### Webhooks & Streaming
Agents should avoid polling. Salesforce offers **Change Data Capture (CDC)** and **Platform Events** via the Pub/Sub API (gRPC-based). This allows agents to react in real-time to record creations or status changes (e.g., "Trigger agent when an Opportunity moves to 'Closed-Won'").

### Auth Flows
For autonomous agents, the **OAuth 2.0 JWT Bearer Flow** is mandatory. It allows for headless authentication using a private key and a pre-approved "Connected App," eliminating the need for interactive user login.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Account** | `/sobjects/Account/` | Represents a company or organization; the root of most CRM hierarchies. |
| **Lead** | `/sobjects/Lead/` | A prospect or potential customer that has not yet been qualified. |
| **Contact** | `/sobjects/Contact/` | An individual associated with an Account. |
| **Opportunity** | `/sobjects/Opportunity/` | A pending deal or sales contract tracked through stages. |
| **SOQL Query** | `/query?q=SELECT...` | SQL-like syntax for filtering and joining related CRM records. |
| **Describe** | `/sobjects/{name}/describe` | Returns metadata (fields, types, picklist values) for an object. |
| **Composite** | `/composite/` | Allows agents to execute multiple related requests in a single call. |

---

## 4. Setup Guide

### For Humans
1. Sign up for a **Salesforce Developer Edition** at developer.salesforce.com.
2. In the Setup menu, navigate to **App Manager** and create a **New Connected App**.
3. Enable **OAuth Settings**, provide a callback URL (even if dummy), and select scopes (e.g., `api`, `refresh_token`).
4. Generate or upload a **Digital Certificate** for the JWT Bearer flow.
5. Note the **Consumer Key** (Client ID) and the **Instance URL**.
6. In **Manage Connected Apps**, set "Permitted Users" to "Admin approved users are pre-authorized" and add your profile.

### For Agents
1. **Initialize Auth**: Use the JWT flow to exchange a signed assertion for an `access_token`.
2. **Discover Schema**: Fetch `describe` metadata for target objects to map custom fields.
3. **Validate Connection**: Execute a simple identity query.
4. **Cache Limits**: Query the `/limits` endpoint to understand remaining API daily quota.

```python
from simple_salesforce import Salesforce
import jwt # PyJWT

# Connection Validation
sf = Salesforce(instance_url='https://your-domain.my.salesforce.com', session_id='ACCESS_TOKEN')
try:
    limits = sf.limits()
    print(f"Connection Secure. Daily API Remaining: {limits['DailyApiRequests']['Remaining']}")
except Exception as e:
    print(f"Connection Failed: {e}")
```

---

## 5. Integration Example

This example demonstrates an agent searching for a Lead and updating its status using the `simple-salesforce` Python SDK.

```python
from simple_salesforce import Salesforce

# Initialize with pre-obtained session or credentials
sf = Salesforce(username='agent@company.com', 
                password='password', 
                security_token='token')

def triage_lead(email_address, new_status):
    # 1. Search for Lead using SOQL
    query = f"SELECT Id, Name, Status FROM Lead WHERE Email = '{email_address}' LIMIT 1"
    results = sf.query(query)
    
    if results['totalSize'] > 0:
        lead_id = results['records'][0]['Id']
        
        # 2. Update Lead using SObject method
        # Agents should use external IDs for idempotency where possible
        sf.Lead.update(lead_id, {
            'Status': new_status,
            'Description': 'Processed by Autonomous Triage Agent.'
        })
        return f"Lead {lead_id} updated to {new_status}."
    
    return "Lead not found."

# Agent execution
print(triage_lead('prospect@example.com', 'Working - Contacted'))
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 350ms | Standard REST SObject GET/PATCH operations. |
| **P95 Latency** | 850ms | Complex SOQL queries with multiple joins. |
| **P99 Latency** | 1500ms | Bulk API 2.0 jobs or heavy Apex trigger execution. |
| **Rate Limit** | Variable | Based on license type; usually 15,000+ calls/24h. |
| **Max Batch Size** | 200 | For REST Composite requests. |

---

## 7. Agent-Native Notes

*   **Idempotency**: Salesforce does not support a native `Idempotency-Key` header. Agents **must** use "External ID" fields and the `upsert` (PATCH) method to ensure retries do not create duplicate records.
*   **Retry Behavior**: Agents should implement exponential backoff for `503 Service Unavailable` (maintenance) and `429 Too Many Requests` (limit exceeded).
*   **Error Codes**: `REQUEST_LIMIT_EXCEEDED` should trigger an agent to pause for the 24-hour reset or switch to a lower-priority queue. `MALFORMED_QUERY` indicates an agent hallucination in SOQL syntax.
*   **Schema Stability**: Core objects are stable, but Salesforce environments are heavily customized. Agents must use the `describe` API to validate that custom fields (e.g., `Lead_Score__c`) exist before attempting to write to them.
*   **Cost-per-operation**: High. Every API call counts against a hard daily limit. Agents should favor the **Composite API** to bundle up to 25 sub-requests into a single call.
*   **Picklists**: Agents often fail when trying to write values to "Restricted Picklists" that aren't in the defined set. Always fetch picklist values via metadata first.

---

## 8. Rhumb Context: Why Salesforce Scores 4.75 (L2)

Salesforce's **4.75 score** reflects its status as a powerful but friction-heavy legacy giant that is slowly modernizing for the agentic era:

1. **Execution Autonomy (5.4)** — SOQL provides a robust way for agents to "think" about data relationships. However, the lack of native idempotency headers and the reliance on complex "Connected App" configurations for auth prevent it from reaching L3. The Composite API is a saving grace for autonomous efficiency.

2. **Access Readiness (3.8)** — This is Salesforce’s weakest point. There is no self-serve, pay-as-you-go tier. The "Developer Edition" is isolated from production. For an agent to "just start working," a human admin must navigate a complex UI to grant permissions, manage scopes, and handle certificate rotations.

3. **Agent Autonomy (5.33)** — Salesforce Shield and granular Field-Level Security (FLS) provide the best governance in the industry, allowing agents to operate in highly regulated environments (HIPAA/FedRAMP). The introduction of the Salesforce MCP server significantly improves the ability of LLMs to browse the schema autonomously.

**Bottom line:** Salesforce is the unavoidable "End Boss" of CRM integrations. It offers unmatched governance and data depth, but its high setup friction and restrictive API limits mean agents must be specifically architected to handle its quirks. It is an L2 service that requires "Agent-in-the-Loop" setup but provides "Agent-Native" execution once configured.

**Competitor context:** **HubSpot (7.2)** and **Pipedrive (6.8)** score significantly higher due to simpler OAuth flows, more generous free tiers, and REST APIs that are easier for agents to parse without specialized SDKs. For enterprise-grade governance, however, Salesforce remains the only viable choice.
