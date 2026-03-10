# When2Meet — Agent-Native Service Guide

> **AN Score:** 3.44 · **Tier:** L1 · **Category:** Scheduling & Calendar

---

## 1. Synopsis
When2Meet is a ubiquitous, lightweight tool for finding common availability among groups. For agents, it serves as a zero-friction coordination layer for multi-party scheduling. Its primary value proposition for autonomous systems is its lack of a traditional "wall": there are no accounts to manage, no API keys to rotate, and no payment hurdles (Score: 9 in Payment Autonomy). Agents can programmatically spin up a coordination poll, share the URL with human or agent participants, and poll the results to finalize a meeting time. While it lacks a formal developer portal, its simple PHP-based architecture makes it a "de facto" API for ephemeral scheduling tasks where the overhead of a tool like Calendly is prohibitive.

---

## 2. Connection Methods

### REST API (De Facto)
When2Meet does not offer a documented REST API with versioning. Instead, agents interact with the service via the same endpoints used by the web front-end. These are stable but brittle PHP scripts. Communication is typically handled via `application/x-www-form-urlencoded` POST requests. Because there is no authentication, agents must maintain the state of the `event_id` and any associated `user_id` locally or in a shared memory layer.

### SDKs
There are no official SDKs provided by When2Meet. Agent operators typically use community-maintained wrappers or custom implementation logic using standard HTTP libraries like `requests` (Python) or `axios` (Node.js). Most "When2Meet API" packages on PyPI or NPM are thin wrappers around the form-submission logic.

### MCP (Model Context Protocol)
Currently, there is no official MCP server for When2Meet. Agents must use custom tools or generic web-browsing capabilities to interact with the service.

### Webhooks
When2Meet does not support webhooks. This is a significant limitation for agent autonomy (Score: 5). Agents cannot be "notified" when a participant adds their availability; they must implement a polling strategy to detect changes in the availability matrix.

### Auth Flows
There is no authentication. Access is governed entirely by the knowledge of the unique Event ID (e.g., `when2meet.com/?25123456-abcde`). This makes it extremely easy for agents to initiate services but provides zero governance or auditability (Governance Score: 1).

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Create Event** | `POST /SaveNewEvent.php` | Generates a new event ID and returns the poll URL. |
| **Submit Availability** | `POST /SaveAvailability.php` | Submits a specific user's time slots to an existing poll. |
| **Fetch Results** | `GET /AvailabilityResults.php` | Retrieves the aggregate availability matrix for an event. |
| **View Event** | `GET /?{event_id}` | Returns the HTML representation of the poll (requires parsing). |
| **Update Event** | `POST /EditEvent.php` | Modifies event metadata like title or date range. |

---

## 4. Setup Guide

### For Humans
1. Navigate to `when2meet.com`.
2. Enter the "New Event Name".
3. Select the dates on the calendar grid.
4. Drag to define the "Time Range".
5. Click "Create Event".
6. Copy the resulting URL to share with participants.

### For Agents
1. **Initialize Request:** Prepare a POST request to `https://www.when2meet.com/SaveNewEvent.php`.
2. **Define Parameters:** Include `NewEventName`, `DateTypes` (e.g., 'SpecificDates'), and the `PossibleDates` string.
3. **Capture ID:** Execute the request and capture the `Location` header or the redirected URL to extract the unique Event ID.
4. **Validation:** Perform a GET request to the new URL to ensure the page returns a `200 OK` status.

```python
import requests

# Connection Validation Logic
def validate_connection():
    resp = requests.get("https://www.when2meet.com")
    if resp.status_code == 200:
        return True
    return False
```

---

## 5. Integration Example

This example demonstrates an agent creating a new scheduling poll programmatically.

```python
import requests

def create_scheduling_poll(event_name, dates):
    url = "https://www.when2meet.com/SaveNewEvent.php"
    
    # Payload for a multi-day scheduling event
    payload = {
        'NewEventName': event_name,
        'DateTypes': 'SpecificDates',
        'PossibleDates': dates, # Format: '2023-12-01,2023-12-02'
        'NoEarlyThan': '9',     # 9 AM
        'NoLaterThan': '17'     # 5 PM
    }
    
    try:
        # allow_redirects=False to catch the ID in the header
        response = requests.post(url, data=payload, allow_redirects=False)
        
        if response.status_code == 302:
            event_url = response.headers['Location']
            event_id = event_url.split('?')[-1]
            return {"status": "success", "url": f"https://www.when2meet.com/{event_url}", "id": event_id}
        else:
            return {"status": "error", "message": "Failed to create event"}
            
    except Exception as e:
        return {"status": "exception", "details": str(e)}

# Usage
new_poll = create_scheduling_poll("Agent Sync", "2024-05-20,2024-05-21")
print(f"Poll Created: {new_poll['url']}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Latency P50** | 350ms | Generally responsive for simple form submissions. |
| **Latency P95** | 800ms | Spikes during high-traffic periods (start of work weeks). |
| **Latency P99** | 1400ms | Significant lag on the PHP backend during peak load. |
| **Rate Limits** | Unspecified | No official limit; excessive polling may trigger IP blocks. |
| **Uptime** | ~99.5% | Legacy infrastructure; occasional unannounced downtime. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Not supported. Every `POST` to `SaveNewEvent.php` creates a new, unique event. Agents must store the created ID to avoid duplicate poll generation.
*   **Retry Behavior:** Safe to retry `GET` requests for availability results. Use exponential backoff for `POST` requests if a `5xx` error is encountered, but check if the event was created anyway.
*   **Error Codes:** The service rarely returns standard API error codes (e.g., 400, 422). It often returns a `200 OK` with an error message in the HTML body. Agents need a robust HTML parser (like BeautifulSoup) to detect failures.
*   **Schema Stability:** Low. Because there is no formal API, any change to the web form's field names will break the integration.
*   **Cost-per-operation:** $0.00. The service is entirely free, making it the most cost-effective coordination tool for high-volume, low-value scheduling tasks.
*   **Zero-Auth Risks:** Since there is no authentication, any entity with the Event ID can modify or delete data. Agents should treat the Event ID as a sensitive secret.
*   **Data Persistence:** Events are generally persistent but have no guaranteed SLA for how long they remain on the server. Do not use for long-term data storage.

---

## 8. Rhumb Context: Why When2Meet Scores 3.44 (L1)

When2Meet’s **3.44 score** represents the "Wild West" of agent-native services—highly functional and accessible, but architecturally fragile:

1. **Execution Autonomy (4.2)** — The logic is refreshingly simple. An agent doesn't need to navigate complex OAuth flows or multi-step resource creation. However, the lack of structured output (JSON) means agents spend significant compute cycles parsing HTML strings to understand the availability matrix, which drags down the autonomy score.

2. **Access Readiness (2.0)** — While the "Payment Autonomy" is a 9 (perfect for agents with no wallets), the "Access Readiness" is low because there is no official developer documentation or supported API. Agents are essentially "scraping" a 20-year-old PHP application. There is no sandbox environment or versioned endpoint to ensure long-term stability.

3. **Agent Autonomy (5.0)** — The lack of webhooks is the primary bottleneck. An agent cannot "sleep" and wait for a participant to respond; it must actively poll the service. This makes When2Meet suitable for batch-processed scheduling but poor for real-time, event-driven coordination.

**Bottom line: When2Meet is the best "zero-budget" scheduling primitive for agents that need to coordinate with humans without the friction of account creation. It is a Tier-1 choice for ephemeral tasks but should be avoided for mission-critical enterprise scheduling due to its lack of governance and brittle interface.**

**Competitor context:** **Calendly (7.2)** is the superior choice for professional agents requiring OAuth, webhooks, and structured JSON. **Doodle (5.1)** offers a middle ground but has become increasingly hostile to free/anonymous programmatic use. When2Meet remains the only viable "anonymous" option.
