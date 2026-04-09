"""Tests for the Zendesk support executor."""

from __future__ import annotations

import httpx
import pytest

from schemas.support_capabilities import (
    TicketGetRequest,
    TicketListCommentsRequest,
    TicketSearchRequest,
)
from services.support_connection_registry import ZendeskSupportBundle
from services.zendesk_support_executor import (
    SupportExecutorError,
    get_ticket,
    list_ticket_comments,
    search_tickets,
)


class _FakeClient:
    def __init__(self, responses: list[httpx.Response]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, path: str, params: dict | None = None) -> httpx.Response:
        self.calls.append(("GET", path, params))
        if not self._responses:
            raise AssertionError("No fake response queued")
        return self._responses.pop(0)


def _response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://example.zendesk.com/api/v2/test"),
    )


def _bundle(**overrides) -> ZendeskSupportBundle:
    payload = {
        "support_ref": "sup_help",
        "provider": "zendesk",
        "subdomain": "acme",
        "auth_mode": "bearer_token",
        "allowed_group_ids": (123,),
        "allowed_brand_ids": (),
        "allow_internal_comments": False,
        "email": None,
        "api_token": None,
        "bearer_token": "bearer-secret",
    }
    payload.update(overrides)
    return ZendeskSupportBundle(**payload)


@pytest.mark.asyncio
async def test_search_tickets_filters_out_of_scope_results() -> None:
    client = _FakeClient([
        _response(
            200,
            {
                "results": [
                    {
                        "result_type": "ticket",
                        "id": 101,
                        "subject": "Login broken",
                        "status": "open",
                        "priority": "high",
                        "group_id": 123,
                        "brand_id": 10,
                        "tags": ["urgent"],
                        "description": "Customer cannot sign in",
                        "updated_at": "2026-04-08T12:00:00Z",
                    },
                    {
                        "result_type": "ticket",
                        "id": 102,
                        "subject": "Out of scope",
                        "group_id": 999,
                    },
                ],
                "next_page": "https://acme.zendesk.com/api/v2/search.json?page=2",
            },
        )
    ])

    result = await search_tickets(
        TicketSearchRequest(support_ref="sup_help", query="login", limit=10),
        bundle=_bundle(),
        client_factory=lambda _bundle: client,
    )

    assert result.ticket_count_returned == 1
    assert result.tickets[0].ticket_id == 101
    assert result.tickets[0].text_snippet == "Customer cannot sign in"
    assert result.has_more is True
    assert result.next_page_after == "https://acme.zendesk.com/api/v2/search.json?page=2"
    assert client.calls[0][1] == "/search.json"
    assert client.calls[0][2]["query"] == "type:ticket login"


@pytest.mark.asyncio
async def test_get_ticket_rejects_out_of_scope_ticket() -> None:
    client = _FakeClient([
        _response(
            200,
            {
                "ticket": {
                    "id": 55,
                    "subject": "Private brand",
                    "group_id": 999,
                }
            },
        )
    ])

    with pytest.raises(SupportExecutorError, match="not allowed to access ticket '55'") as exc:
        await get_ticket(
            TicketGetRequest(support_ref="sup_help", ticket_id=55),
            bundle=_bundle(),
            client_factory=lambda _bundle: client,
        )

    assert exc.value.code == "support_ticket_scope_denied"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_ticket_comments_denies_internal_without_permission() -> None:
    with pytest.raises(SupportExecutorError, match="not allowed to include internal comments") as exc:
        await list_ticket_comments(
            TicketListCommentsRequest(
                support_ref="sup_help",
                ticket_id=55,
                include_internal=True,
            ),
            bundle=_bundle(allow_internal_comments=False),
            client_factory=lambda _bundle: _FakeClient([]),
        )

    assert exc.value.code == "support_internal_comments_denied"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_ticket_comments_filters_internal_by_default() -> None:
    client = _FakeClient([
        _response(200, {"ticket": {"id": 55, "group_id": 123}}),
        _response(
            200,
            {
                "comments": [
                    {
                        "id": 1,
                        "author_id": 100,
                        "created_at": "2026-04-08T12:00:00Z",
                        "public": True,
                        "plain_body": "Visible to requester",
                    },
                    {
                        "id": 2,
                        "author_id": 200,
                        "created_at": "2026-04-08T12:05:00Z",
                        "public": False,
                        "plain_body": "Internal note",
                    },
                ],
                "next_page": None,
            },
        ),
    ])

    result = await list_ticket_comments(
        TicketListCommentsRequest(support_ref="sup_help", ticket_id=55, limit=20),
        bundle=_bundle(),
        client_factory=lambda _bundle: client,
    )

    assert result.comment_count_returned == 1
    assert result.comments[0].comment_id == 1
    assert result.comments[0].body_text == "Visible to requester"
    assert client.calls[1][1] == "/tickets/55/comments.json"
