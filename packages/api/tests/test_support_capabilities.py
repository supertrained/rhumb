"""Tests for Zendesk support capability schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.support_capabilities import (
    TicketGetRequest,
    TicketListCommentsRequest,
    TicketSearchRequest,
    TicketSearchResponse,
    ZendeskTicketSummary,
)


def test_ticket_search_request_defaults() -> None:
    request = TicketSearchRequest.model_validate(
        {"support_ref": "sup_main", "query": "billing outage"}
    )

    assert request.limit == 10
    assert request.page_after is None


def test_ticket_search_request_rejects_blank_query() -> None:
    with pytest.raises(ValidationError):
        TicketSearchRequest.model_validate(
            {"support_ref": "sup_main", "query": "   "}
        )


def test_ticket_comments_request_rejects_high_limit() -> None:
    with pytest.raises(ValidationError):
        TicketListCommentsRequest.model_validate(
            {"support_ref": "sup_main", "ticket_id": 123, "limit": 100}
        )


def test_ticket_get_request_requires_positive_ticket_id() -> None:
    with pytest.raises(ValidationError):
        TicketGetRequest.model_validate(
            {"support_ref": "sup_main", "ticket_id": 0}
        )


def test_ticket_search_response_accepts_bounded_results() -> None:
    response = TicketSearchResponse(
        provider_used="zendesk",
        credential_mode="byok",
        capability_id="ticket.search",
        receipt_id="rcpt_123",
        execution_id="exec_123",
        support_ref="sup_main",
        tickets=[
            ZendeskTicketSummary(
                ticket_id=101,
                subject="Billing issue",
                status="open",
                tags=["billing"],
            )
        ],
        ticket_count_returned=1,
        has_more=False,
    )

    assert response.ticket_count_returned == 1
    assert response.tickets[0].ticket_id == 101
