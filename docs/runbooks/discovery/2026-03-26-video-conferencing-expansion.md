# Video-conferencing discovery expansion — 2026-03-26

Date: 2026-03-26
Operator: Pedro / Keel runtime loop

## Why this category

Video conferencing remains underweighted relative to how often agents need to schedule, create, manage, and inspect meetings. The catalog has only a small cluster of conferencing providers today, and much of that surface is duplicates rather than breadth. This is a real operating category for sales calls, support escalations, internal reviews, telehealth, and embedded product collaboration.

## Added services

- `webex-meetings`
- `vonage-video`
- `amazon-chime-sdk`
- `stream-video`

## Category read

This batch broadens coverage across the main design centers in programmable conferencing:

- **Enterprise meeting scheduling + management:** Webex Meetings
- **Embeddable session/video infrastructure:** Vonage Video, Amazon Chime SDK
- **Modern in-app calling/product video:** Stream Video

That gives Rhumb better coverage across hosted meeting suites and API-first real-time media stacks.

## Phase 0 capability assessment

### Best immediate Resolve candidate: Webex Meetings

Webex Meetings is the cleanest first Resolve target in this batch because its API already maps to agent-meaningful meeting-management primitives.

Recommended first capability set:
- `meeting.list` → list scheduled meetings
- `meeting.get` → fetch details for a meeting
- `meeting.create` → create a scheduled meeting
- `meeting.update` → reschedule or edit a meeting
- `meeting.cancel` → delete/cancel a meeting

Why Webex first:
- the API is explicit about list/create/get/update/delete meeting workflows
- the object model is close to existing calendar/meeting primitives agents already reason about
- it produces a practical business capability quickly instead of a low-level media infrastructure abstraction

### Secondary candidates

- **Vonage Video:** strong follow-on for session creation, archive control, token/session management, and embedded video flows
- **Amazon Chime SDK:** powerful but more infrastructure-heavy; better for later real-time/media capabilities than first-wave Resolve primitives
- **Stream Video:** good fit for call/session orchestration and moderation after Rhumb has a cleaner normalized conferencing model

## Operator takeaway

Video conferencing is a meaningful high-demand category, and Webex Meetings now stands out as the best immediate Phase 0 candidate for a normalized Resolve meeting-management surface.