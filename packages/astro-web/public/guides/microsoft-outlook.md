# Microsoft Outlook Calendar API — Agent-Native Service Guide

> **AN Score:** 5.66 · **Tier:** L2 · **Category:** Scheduling & Calendar

---

## 1. Synopsis
The Microsoft Outlook Calendar API, delivered via the Microsoft Graph, is the primary interface for agents to manage schedules, check availability, and coordinate meetings within the Microsoft 365 ecosystem. For agents, this service is essential for executive assistant workflows, automated resource booking, and cross-organization synchronization. Unlike consumer-first APIs, Outlook provides deep enterprise primitives like "Find Meeting Times" and "Get Schedule" for multi-user availability analysis. There is no traditional "free tier" for production; use requires a Microsoft 365 subscription. However, developers can access a free, renewable sandbox through the Microsoft 365 Developer Program. For agents, the API offers high governance but carries significant setup friction due to Entra ID (Azure AD) configuration requirements.

---

## 2. Connection Methods

### REST API
The service is hosted under the unified Microsoft Graph endpoint: `https://graph.microsoft.com/v1.0`. It follows standard REST patterns using JSON for payloads. Agents should primarily interact with the `/me/events` or `/users/{id}/events` collections. The API supports OData query parameters (e.g., `$select`, `$filter`, `$top`), which allows agents to minimize payload size and reduce token consumption during parsing.

### SDKs
Microsoft maintains robust, auto-generated SDKs for Python (`msgraph-sdk`), JavaScript/TypeScript (`@microsoft/microsoft-graph-client`), Go, and .NET. These SDKs are recommended for agents as they handle authentication provider abstraction, request building, and response modeling, which reduces the likelihood of schema-related runtime errors.

### Webhooks
Outlook supports "Change Notifications" via a subscription model. Agents can subscribe to specific calendars or event collections. When a change occurs, Microsoft pushes a POST request to the agent's notification URL. This is critical for reactive agents (e.g., "Alert me when a meeting is rescheduled"). Subscriptions expire and must be renewed by the agent programmatically before the `expirationDateTime`.

### Auth Flows
Authentication is strictly managed via Microsoft Entra ID (formerly Azure AD). For user-facing agents, the **OAuth 2.0 Authorization Code Flow** is used. For background "daemon" agents operating without a signed-in user, the **Client Credentials Flow** is required, which necessitates "Application" permissions and typically requires a one-time admin consent.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **List Events** | `GET /me/events` | Retrieves a collection of events in the user's default calendar. |
| **Create Event** | `POST /me/events` | Creates a new calendar event; supports online meeting (Teams) generation. |
| **Find Meeting Times** | `POST /me/findMeetingTimes` | Suggests meeting times based on availability and constraints of multiple attendees. |
| **Get Schedule** | `POST /me/calendar/getSchedule` | Returns free/busy information for multiple users/resources in a specific window. |
| **Delta Query** | `GET /me/calendarView/delta` | Retrieves only the changes (new/updated/deleted) since the last sync. |
| **Update Event** | `PATCH /me/events/{id}` | Modifies an existing event; triggers notifications to attendees automatically. |
| **Cancel Event** | `POST /me/events/{id}/cancel` | Cancels a meeting and removes it from the calendar. |

---

## 4. Setup Guide

### For Humans
1.  Sign in to the [Azure Portal](https://portal.azure.com) and navigate to **App Registrations**.
2.  Create a "New Registration" and note the `Client ID` and `Tenant ID`.
3.  Under **API Permissions**, add Microsoft Graph permissions (e.g., `Calendars.ReadWrite`).
4.  If using a background agent, click "Grant admin consent" for the organization.
5.  Navigate to **Certificates & Secrets** and generate a new Client Secret.
6.  Configure a **Redirect URI** if using the Authorization Code flow.

### For Agents
1.  **Identity Bootstrap:** Retrieve `CLIENT_ID`, `CLIENT_SECRET`, and `TENANT_ID` from the environment.
2.  **Token Acquisition:** Request a Bearer token from `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`.
3.  **Scope Verification:** On the first run, the agent should decode the JWT to ensure the `scp` or `roles` claim contains `Calendars.ReadWrite`.
4.  **Connectivity Check:** Perform a lightweight `GET https://graph.microsoft.com/v1.0/me` to verify the token is valid and the user profile is accessible.
5.  **Timezone Sync:** Query `GET /me/settings/regionalAndLanguageSettings` to ensure the agent creates events in the user's preferred timezone.

---

## 5. Integration Example

```python
# Using msgraph-sdk for Python
from msgraph import GraphServiceClient
from azure.identity import ClientSecretCredential

# Initialize the Graph Client (Application/Daemon context)
credential = ClientSecretCredential(
    tenant_id='YOUR_TENANT_ID',
    client_id='YOUR_CLIENT_ID',
    client_secret='YOUR_CLIENT_SECRET'
)
client = GraphServiceClient(credential, scopes=['https://graph.microsoft.com/.default'])

async def create_agent_meeting(subject, start_time, end_time, attendees):
    new_event = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": "Automated meeting scheduled by Rhumb Agent."
        },
        "start": {
            "dateTime": start_time, # ISO 8601 format
            "timeZone": "Pacific Standard Time"
        },
        "end": {
            "dateTime": end_time,
            "timeZone": "Pacific Standard Time"
        },
        "location": {"displayName": "Virtual Meeting"},
        "attendees": [{"emailAddress": {"address": email}, "type": "required"} for email in attendees],
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness"
    }
    
    # Execute creation
    result = await client.me.events.post(new_event)
    return result.id
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 190ms | Standard for single event retrieval or simple list operations. |
| **P95 Latency** | 440ms | Common when performing complex filters or cross-user availability checks. |
| **P99 Latency** | 780ms | Occurs during heavy multi-attendee "Find Meeting Times" requests. |
| **Rate Limits** | Variable | Typically 10,000 requests per 10 mins per app/user; check `Rate-Limit` headers. |
| **Max Payload** | 4MB | Maximum size for an event (including large HTML bodies/attachments). |

---

## 7. Agent-Native Notes

*   **Idempotency:** Microsoft Graph does not support a native `Idempotency-Key` header for event creation. Agents should use the `iCalUId` field or store the created `id` in a local state to prevent duplicate bookings during retries.
*   **Retry Behavior:** The API returns a `429 Too Many Requests` status code when throttled. Agents must look for the `Retry-After` header and implement exponential backoff based on that value.
*   **Error Codes:**
    *   `ErrorInvalidUser`: The target mailbox doesn't exist; agent should stop retrying.
    *   `ErrorQuotaExceeded`: Mailbox is full; agent should escalate to human.
    *   `ErrorItemNotFound`: The event was likely deleted by a human; agent should refresh its state.
*   **Schema Stability:** The `/v1.0` endpoint is extremely stable. Agents can rely on the schema not breaking, though new optional fields are added periodically.
*   **Cost-per-operation:** $0.00. Microsoft bills per user license (SaaS), not per API call. This makes it ideal for high-frequency polling or synchronization tasks without variable cost risk.
*   **Delta Queries:** Use these for efficiency. Instead of listing all events to find changes, the `delta` link provides a state-aware stream of updates, significantly reducing data processing for the agent.
*   **Timezone Handling:** Always specify `timeZone` in requests. If omitted, the API defaults to UTC, which often causes "invisible" scheduling conflicts for human users.

---

## 8. Rhumb Context: Why Microsoft Outlook Calendar API Scores 5.66 (L2)

Microsoft Outlook’s **5.66 score** reflects an enterprise-grade service that provides immense power but suffers from significant integration friction compared to modern "API-first" tools:

1.  **Execution Autonomy (6.7)** — The API provides sophisticated primitives like `findMeetingTimes` and `getSchedule` that allow agents to perform complex reasoning (e.g., "Find 30 minutes for 5 people next Tuesday") without manual brute-force polling. This high level of "intent-based" endpoints is superior to many competitors. However, the lack of native idempotency headers for POST operations requires agents to manage state carefully to avoid duplicate events.

2.  **Access Readiness (4.1)** — This is the service's weakest dimension. Bootstrapping an agent requires navigating the Microsoft Entra ID portal, managing app registrations, and handling complex OAuth/Client Credential flows. Unlike services that offer simple API keys, Outlook requires a multi-step handshake and often "Admin Consent," which acts as a major roadblock for autonomous agent deployment in corporate environments.

3.  **Agent Autonomy (6.67)** — The availability of Delta Queries and robust Webhooks allows agents to operate in a truly event-driven manner. An agent can "watch" a calendar for years with minimal overhead. The governance features (Score: 9) are world-class, providing the audit logs and RBAC that enterprise security teams require before allowing an agent to touch executive calendars.

**Bottom line:** Microsoft Outlook is the L2 "Standard" for enterprise scheduling. While the setup is arduous for developers, the resulting integration is highly stable and provides the granular control necessary for production agents. It is the best choice for agents operating within the Microsoft 365 tenant, provided the developer can clear the Entra ID hurdle.

**Competitor context:** **Google Calendar (6.1)** scores higher primarily due to its more accessible API key and OAuth setup, though it lacks some of the deep "find meeting times" logic found in Graph. **Calendly (7.2)** scores higher for agent-to-human scheduling due to its simpler abstraction, but lacks the raw mailbox-level access that Outlook provides.
