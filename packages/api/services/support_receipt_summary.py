"""Human-readable summaries for support capability executions."""

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

    if capability_id == "conversation.list":
        conversation_count = payload.get("conversation_count_returned", 0)
        return f"Listed {conversation_count} Intercom conversations via support_ref {support_ref}"

    if capability_id == "conversation.get":
        conversation_id = payload.get("conversation_id") or "unknown"
        return f"Fetched Intercom conversation {conversation_id} via support_ref {support_ref}"

    if capability_id == "conversation.list_parts":
        conversation_id = payload.get("conversation_id") or "unknown"
        part_count = payload.get("part_count_returned", 0)
        return f"Fetched {part_count} visible parts for Intercom conversation {conversation_id} via support_ref {support_ref}"

    return f"Completed {capability_id} via support_ref {support_ref}"
