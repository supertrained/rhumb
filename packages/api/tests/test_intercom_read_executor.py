"""Tests for the Intercom conversation-first executor."""

from __future__ import annotations

import pytest

from schemas.support_capabilities import (
    ConversationGetRequest,
    ConversationListPartsRequest,
    ConversationListRequest,
)
from services.intercom_read_executor import (
    IntercomExecutorError,
    _build_headers,
    get_conversation,
    list_conversation_parts,
    list_conversations,
)
from services.support_connection_registry import IntercomSupportBundle


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


def _bundle(**overrides) -> IntercomSupportBundle:
    data = {
        "support_ref": "sup_chat",
        "provider": "intercom",
        "region": "us",
        "auth_mode": "bearer_token",
        "bearer_token": "token-123",
        "allowed_team_ids": (12,),
        "allowed_admin_ids": (),
        "allowed_conversation_ids": (),
        "allow_internal_notes": False,
    }
    data.update(overrides)
    return IntercomSupportBundle(**data)


@pytest.mark.asyncio
async def test_list_conversations_filters_out_of_scope() -> None:
    request = ConversationListRequest(support_ref="sup_chat")
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/conversations": MockResponse(
                200,
                {
                    "conversations": [
                        {
                            "id": "conv_1",
                            "state": "open",
                            "team_assignee_id": 12,
                            "source": {"body": "<p>Allowed</p>", "subject": "Billing"},
                        },
                        {
                            "id": "conv_2",
                            "state": "open",
                            "team_assignee_id": 99,
                            "source": {"body": "<p>Blocked</p>", "subject": "Other"},
                        },
                    ],
                    "pages": {"next": {"starting_after": "cursor_2"}},
                },
            )
        }
    )

    response = await list_conversations(request, bundle=bundle, client_factory=client_factory)

    assert response.conversation_count_returned == 1
    assert response.conversations[0].conversation_id == "conv_1"
    assert response.next_page_after == "cursor_2"


@pytest.mark.asyncio
async def test_get_conversation_rejects_out_of_scope() -> None:
    request = ConversationGetRequest(support_ref="sup_chat", conversation_id="conv_123")
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/conversations/conv_123": MockResponse(
                200,
                {"id": "conv_123", "team_assignee_id": 99, "source": {"subject": "Blocked"}},
            )
        }
    )

    with pytest.raises(IntercomExecutorError) as exc:
        await get_conversation(request, bundle=bundle, client_factory=client_factory)

    assert exc.value.code == "support_conversation_scope_denied"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_conversation_allows_exact_conversation_scope_when_unassigned() -> None:
    request = ConversationGetRequest(support_ref="sup_chat", conversation_id="215473840934085")
    bundle = _bundle(allowed_team_ids=(), allowed_conversation_ids=("215473840934085",))
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/conversations/215473840934085": MockResponse(
                200,
                {
                    "id": "215473840934085",
                    "team_assignee_id": None,
                    "admin_assignee_id": None,
                    "source": {"subject": "Allowed"},
                },
            )
        }
    )

    response = await get_conversation(request, bundle=bundle, client_factory=client_factory)

    assert response.conversation_id == "215473840934085"
    assert response.title == "Allowed"


@pytest.mark.asyncio
async def test_list_conversation_parts_defaults_to_visible_only() -> None:
    request = ConversationListPartsRequest(support_ref="sup_chat", conversation_id="conv_123")
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/conversations/conv_123": MockResponse(
                200,
                {
                    "id": "conv_123",
                    "team_assignee_id": 12,
                    "conversation_parts": {
                        "conversation_parts": [
                            {"id": "part_1", "part_type": "comment", "author": {"id": "7"}, "body": "<p>Visible</p>"},
                            {"id": "part_2", "part_type": "note", "author": {"id": "8"}, "body": "<p>Internal</p>"},
                        ]
                    },
                },
            )
        }
    )

    response = await list_conversation_parts(request, bundle=bundle, client_factory=client_factory)

    assert response.part_count_returned == 1
    assert response.parts[0].part_id == "part_1"
    assert response.parts[0].body_text == "Visible"


@pytest.mark.asyncio
async def test_list_conversation_parts_rejects_internal_when_bundle_disallows() -> None:
    request = ConversationListPartsRequest(
        support_ref="sup_chat",
        conversation_id="conv_123",
        include_internal=True,
    )
    bundle = _bundle(allow_internal_notes=False)

    with pytest.raises(IntercomExecutorError) as exc:
        await list_conversation_parts(request, bundle=bundle, client_factory=lambda **kwargs: MockAsyncClient(responses={}))

    assert exc.value.code == "support_internal_notes_denied"
    assert exc.value.status_code == 403


def test_build_headers() -> None:
    bundle = _bundle(bearer_token="secret")

    headers = _build_headers(bundle)

    assert headers["Accept"] == "application/json"
    assert headers["Authorization"] == "Bearer secret"
    assert headers["Intercom-Version"] == "2.14"
