# Cal.com — Agent-Native Service Guide

> **AN Score:** 6.86 · **Tier:** L3 · **Category:** Scheduling & Calendar

---

## 1. Synopsis
Cal.com is open-source scheduling infrastructure designed to take the friction out of meeting orchestration. While competitors focus on a consumer-facing UI, Cal.com prioritizes being a "scheduling API" that developers—and now agents—can build upon. For agents, Cal.com acts as the bridge between digital reasoning and physical time management. It allows agents to autonomously check availability, reserve slots, and manage cancellations across multiple time zones. The service is particularly valuable for sales, recruitment, and support agents that need to transition a conversation into a calendar event. Cal.com offers a generous free tier for individuals on their cloud platform and is entirely free to run for those who choose the self-hosted open-source route.

---

## 2. Connection Methods

### REST API
Cal.com provides a comprehensive REST API (currently transitioning from v1 to v2). The API is the primary interface for agents to perform CRUD operations on bookings, event types, and availability. Most agentic workflows utilize the `/v1/bookings` and `/v1/slots` endpoints to programmatically find and claim time.

### SDKs
While Cal.com provides a JavaScript/TypeScript SDK primarily focused on the "Embed" (UI) experience, most backend agents interact with the service using standard HTTP clients (like `axios` or `requests`) against the REST endpoints. There is no official "Agent SDK" yet, but the API's adherence to standard REST patterns makes wrapper generation via OpenAPI schemas straightforward.

### Webhooks
Webhooks are a first-class citizen in Cal.com, allowing agents to stay "event-driven." Agents can subscribe to triggers like `BOOKING_CREATED`, `BOOKING_RESCHEDULED`, and `BOOKING_CANCELLED`. This prevents the need for agents to poll the API to see if a human has confirmed or changed a meeting time.

### Auth Flows
Agents typically authenticate using **API Keys**, which are generated in the user settings dashboard. For multi-tenant agent platforms, Cal.com supports **OAuth2**, allowing an agent to request permission to manage a user's calendar on their behalf. API keys are passed in the request header as `apiKey`.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Booking** | `/v1/bookings` | The core record of a scheduled meeting between an agent's principal and an attendee. |
| **Event Type** | `/v1/event-types` | Templates defining meeting duration, location, and metadata (e.g., "15-min Discovery"). |
| **Slot** | `/v1/slots` | Available windows of time calculated by intersecting availability and existing calendar busy-times. |
| **Availability** | `/v1/availability` | The raw time ranges where a user is willing to accept meetings (e.g., Mon-Fri, 9-5). |
| **Attendee** | N/A (Object) | The metadata for the person booking the meeting (name, email, time zone). |
| **Schedule** | `/v1/schedules` | A collection of availability rules that can be applied to different event types. |

---

## 4. Setup Guide

### For Humans
1. Create an account at [Cal.com](https://cal.com/signup).
2. Connect your primary calendar (Google, Outlook, or Apple) in the "Apps" section.
3. Define your "Availability" (e.g., Working Hours).
4. Create at least one "Event Type" (e.g., "AI Consultation").
5. Navigate to **Settings > API Keys** and generate a new key.
6. Copy the key and the `eventTypeId` of the event you want the agent to book.

### For Agents
1. **Validate Connection:** Perform a GET request to `/v1/me?apiKey={KEY}` to ensure the token is valid and retrieve the `username`.
2. **Discover Event Types:** Query `/v1/event-types` to map human-readable names to the numeric IDs required for booking.
3. **Check Capabilities:** Verify the agent has write access by attempting to create a test "Busy" slot.
4. **Implementation Code (Python):**
```python
import requests

def validate_cal_connection(api_key):
    response = requests.get(f"https://api.cal.com/v1/me?apiKey={api_key}")
    if response.status_code == 200:
        print(f"Connected as: {response.json()['user']['username']}")
        return True
    return False
```

---

## 5. Integration Example

This Python example demonstrates an agent finding available slots for a specific event type and then creating a booking once a slot is selected.

```python
import requests

API_KEY = "cal_live_xxxxxxxxxxxx"
BASE_URL = "https://api.cal.com/v1"

# 1. Get available slots for a specific event
# Parameters: eventTypeId, startTime (ISO), endTime (ISO)
slot_params = {
    "apiKey": API_KEY,
    "eventTypeId": 123456,
    "startTime": "2023-11-01T00:00:00Z",
    "endTime": "2023-11-07T23:59:59Z"
}

slots_res = requests.get(f"{BASE_URL}/slots", params=slot_params)
available_slots = slots_res.json().get("slots", {})

# 2. Book the first available slot
if available_slots:
    # Get the first day with slots
    first_date = list(available_slots.keys())[0]
    target_slot = available_slots[first_date][0] # The first available time string

    booking_data = {
        "eventTypeId": 123456,
        "start": target_slot["time"],
        "responses": {
            "name": "Potential Client",
            "email": "client@example.com",
            "location": "https://zoom.us/j/123"
        },
        "timeZone": "America/New_York",
        "language": "en"
    }

    create_res = requests.post(f"{BASE_URL}/bookings?apiKey={API_KEY}", json=booking_data)
    print(f"Booking Status: {create_res.status_code}, ID: {create_res.json().get('booking', {}).get('id')}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Latency P50** | 115ms | Fast enough for real-time chat agent responses. |
| **Latency P95** | 260ms | Occurs during complex slot calculations for busy calendars. |
| **Latency P99** | 430ms | Usually seen on initial OAuth token exchanges or large date range queries. |
| **Rate Limit** | 100 req/min | Standard for Cloud. Self-hosted has no limits. |
| **Availability** | 99.9% | Highly stable; open-core allows for local redundancy. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Cal.com does not currently support an `Idempotency-Key` header. Agents should store the `bookingId` returned on success. If a timeout occurs, the agent must query `/v1/bookings` for the specific time/email to verify if the record was created before retrying.
*   **Retry Behavior:** Use exponential backoff for `429 Too Many Requests`. For `5xx` errors, agents should wait at least 2 seconds, as these are often transient database locks during concurrent slot checks.
*   **Error Codes:** `400` usually indicates an "Invalid Slot" (someone else booked it). The agent should re-fetch `/slots` and present a new option to the user rather than retrying the same payload.
*   **Schema Stability:** The transition from v1 to v2 is significant. Agents should explicitly target v1 endpoints (`/v1/...`) to avoid breaking changes in the v2 beta.
*   **Cost-per-operation:** On the Cloud "Team" plan, costs are per-seat ($15/mo). For agents, the "Individual" free tier is often sufficient, making the cost-per-operation essentially $0.
*   **Timezone Intelligence:** Cal.com expects ISO 8601 strings. Agents **must** clarify the attendee's timezone before calling `/slots`, as the API defaults to the account owner's timezone if unspecified.
*   **Conflict Resolution:** The API handles calendar conflicts automatically. If a human manually adds a "Doctor's Appointment" to their Google Calendar, Cal.com will instantly remove those slots from the API response.

---

## 8. Rhumb Context: Why Cal.com Scores 6.86 (L3)

Cal.com's **6.86 score** positions it as a "Ready" service that excels in execution but requires minor human oversight for governance:

1. **Execution Autonomy (7.5)** — The primitives for scheduling are robust. An agent can navigate the entire lifecycle of a meeting—discovery, slot selection, booking, and cancellation—without human intervention. The logic for "what is a valid time" is handled by Cal.com's engine, reducing the compute burden on the agent.

2. **Access Readiness (6.2)** — While the API is documented, there is some friction in "discovery." Agents cannot easily determine which `eventTypeId` corresponds to a specific intent (e.g., "Sales Call" vs "Technical Support") without fetching and parsing a list of types first. The lack of a "Sandbox" environment for the cloud version means agents often have to test on live production accounts.

3. **Agent Autonomy (6.67)** — The payment autonomy is high (8.0) because of the open-source model; an agent can technically "own" its infrastructure by spinning up a Docker container. However, Governance Readiness (5.0) holds the score back—there is no granular RBAC to allow an agent to "only book" without also being able to "delete account" using the same API key.

**Bottom line:** Cal.com is the premier choice for agents requiring calendar access. Its open-core nature provides a level of autonomy (Payment/Hosting) that proprietary competitors cannot match, making it a "Tier 1" integration for autonomous executive assistants.

**Competitor context:** Calendly (5.4) scores lower due to a more restrictive API access model and lack of a self-hosted option, which limits an agent's long-term infrastructure autonomy. Acuity Scheduling (4.9) suffers from a legacy API structure that is difficult for LLMs to parse reliably.
