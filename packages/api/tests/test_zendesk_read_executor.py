"""Tests for the Zendesk read-first executor."""

from __future__ import annotations

import base64

import pytest

from schemas.support_capabilities import (
    TicketGetRequest,
    TicketListCommentsRequest,
    TicketSearchRequest,
)
from services.support_connection_registry import ZendeskSupportBundle
from services.zendesk_read_executor import (
    ZendeskExecutorError,
    _build_headers,
    get_ticket,
    list_comments,
    search_tickets,
)


class MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class MockAsyncClient:
    def __init__(self, *, responses: dict[str, MockResponse], **_kwargs):
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, path: str, params=None):
        response = self.responses.get(path)
        if response is None:
            raise AssertionError(f"unexpected path: {path} params={params}")
        return response


def _bundle(**overrides) -> ZendeskSupportBundle:
    data = {
        "support_ref": "sup_main",
        "provider": "zendesk",
        "auth_mode": "bearer_token",
        "subdomain": "acme",
        "bearer_token": "token-123",
        "allowed_group_ids": (10,),
        "allowed_brand_ids": (),
        "allow_internal_comments": False,
        "email": None,
        "api_token": None,
    }
    data.update(overrides)
    return ZendeskSupportBundle(**data)


@pytest.mark.asyncio
async def test_search_tickets_filters_out_of_scope() -> None:
    request = TicketSearchRequest(support_ref="sup_main", query="billing")
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/search.json": MockResponse(
                200,
                {
                    "results": [
                        {"id": 101, "subject": "Allowed", "group_id": 10, "status": "open", "tags": ["billing"]},
                        {"id": 102, "subject": "Blocked", "group_id": 99, "status": "open"},
                    ]
                },
            )
        }
    )

    response = await search_tickets(request, bundle=bundle, client_factory=client_factory)

    assert response.ticket_count_returned == 1
    assert response.tickets[0].ticket_id == 101


@pytest.mark.asyncio
async def test_get_ticket_rejects_out_of_scope() -> None:
    request = TicketGetRequest(support_ref="sup_main", ticket_id=123)
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/tickets/123.json": MockResponse(
                200,
                {"ticket": {"id": 123, "subject": "Blocked", "group_id": 99}},
            )
        }
    )

    with pytest.raises(Exception):
        await get_ticket(request, bundle=bundle, client_factory=client_factory)


@pytest.mark.asyncio
async def test_list_comments_defaults_to_public_only() -> None:
    request = TicketListCommentsRequest(support_ref="sup_main", ticket_id=123)
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/tickets/123.json": MockResponse(200, {"ticket": {"id": 123, "subject": "Allowed", "group_id": 10}}),
            "/tickets/123/comments.json": MockResponse(
                200,
                {
                    "comments": [
                        {"id": 1, "author_id": 5, "public": True, "body": "Public reply"},
                        {"id": 2, "author_id": 6, "public": False, "body": "Internal note"},
                    ]
                },
            ),
        }
    )

    response = await list_comments(request, bundle=bundle, client_factory=client_factory)

    assert response.comment_count_returned == 1
    assert response.comments[0].comment_id == 1
    assert response.comments[0].public is True


@pytest.mark.asyncio
async def test_list_comments_rejects_internal_when_bundle_disallows() -> None:
    request = TicketListCommentsRequest(
        support_ref="sup_main",
        ticket_id=123,
        include_internal=True,
    )
    bundle = _bundle(allow_internal_comments=False)

    with pytest.raises(Exception):
        await list_comments(request, bundle=bundle, client_factory=lambda **kwargs: MockAsyncClient(responses={}))


@pytest.mark.asyncio
async def test_search_tickets_maps_404() -> None:
    request = TicketSearchRequest(support_ref="sup_main", query="billing")
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={"/search.json": MockResponse(404, {})}
    )

    with pytest.raises(ZendeskExecutorError) as exc:
        await search_tickets(request, bundle=bundle, client_factory=client_factory)

    assert exc.value.code == "support_search_unavailable"


def test_build_headers_api_token() -> None:
    bundle = _bundle(
        auth_mode="api_token",
        email="ops@acme.com",
        api_token="secret",
        bearer_token=None,
    )

    headers = _build_headers(bundle)

    assert headers["Accept"] == "application/json"
    decoded = base64.b64decode(headers["Authorization"].split(" ", 1)[1]).decode("utf-8")
    assert decoded == "ops@acme.com/token:secret"
