"""Human-readable summaries for Zendesk support capability executions."""

from __future__ import annotations


def summarize_support_execution(capability_id: str, payload: dict) -> str:
    support_ref = payload.get("support_ref") or "unknown support_ref"

    if capability_id == "ticket.search":
        ticket_count = payload.get("ticket_count_returned", 0)
        return f"Searched {ticket_count} Zendesk tickets via support_ref {support_ref}"

    if capability_id == "ticket.get":
        ticket_id = payload.get("ticket_id") or "unknown"
        return f"Fetched Zendesk ticket {ticket_id} via support_ref {support_ref}"

    if capability_id == "ticket.list_comments":
        ticket_id = payload.get("ticket_id") or "unknown"
        comment_count = payload.get("comment_count_returned", 0)
        return f"Fetched {comment_count} Zendesk comments for ticket {ticket_id} via support_ref {support_ref}"

    return f"Completed {capability_id} via support_ref {support_ref}"
