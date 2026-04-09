"""Intercom conversation-first executor for AUD-18."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from schemas.support_capabilities import (
    ConversationGetRequest,
    ConversationGetResponse,
    ConversationListPartsRequest,
    ConversationListPartsResponse,
    ConversationListRequest,
    ConversationListResponse,
    IntercomConversationPart,
    IntercomConversationSource,
    IntercomConversationSummary,
)
from services.support_connection_registry import (
    IntercomSupportBundle,
    SupportRefError,
    ensure_conversation_access,
    ensure_internal_notes_allowed,
)

IntercomClientFactory = Callable[..., Any]

_MAX_SNIPPET_CHARS = 280
_MAX_BODY_TEXT_CHARS = 4000
_INTERCOM_VERSION = "2.14"
_INTERCOM_BASE_URLS = {
    "us": "https://api.intercom.io",
    "eu": "https://api.eu.intercom.io",
    "au": "https://api.au.intercom.io",
}
_TAG_RE = re.compile(r"<[^>]+>")
_BREAK_RE = re.compile(r"<(?:br\s*/?|/p|/div|/li|/tr|/h[1-6])>", re.I)
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_NEWLINE_RE = re.compile(r"\n{3,}")


@dataclass(slots=True)
class IntercomExecutorError(RuntimeError):
    code: str
    message: str
    status_code: int = 422

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


async def list_conversations(
    request: ConversationListRequest,
    *,
    bundle: IntercomSupportBundle,
    client_factory: IntercomClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> ConversationListResponse:
    params: dict[str, Any] = {
        "per_page": min(max(request.limit, 1), 50),
    }
    if request.page_after:
        params["starting_after"] = request.page_after

    payload = await _intercom_get_json(
        bundle,
        "/conversations",
        params=params,
        client_factory=client_factory,
        not_found_code="support_conversation_list_unavailable",
        not_found_message="Intercom conversation list endpoint unavailable",
    )

    conversations: list[IntercomConversationSummary] = []
    raw_conversations = payload.get("conversations") or []
    for item in raw_conversations:
        if not isinstance(item, dict):
            continue
        if not _conversation_matches_filters(item, request):
            continue
        conversation_id = _conversation_id(item)
        if not conversation_id:
            continue
        try:
            ensure_conversation_access(bundle, item, conversation_id=conversation_id)
        except SupportRefError:
            continue
        conversations.append(_build_conversation_summary(item))
        if len(conversations) >= request.limit:
            break

    next_page_after = _extract_next_page_after(payload.get("pages"))
    has_more = bool(next_page_after) or len(raw_conversations) > len(conversations)

    return ConversationListResponse(
        provider_used="intercom",
        credential_mode="byok",
        capability_id="conversation.list",
        receipt_id=receipt_id,
        execution_id=execution_id,
        support_ref=bundle.support_ref,
        conversations=conversations,
        result_count_returned=len(conversations),
        has_more=has_more,
        next_page_after=next_page_after,
    )


async def get_conversation(
    request: ConversationGetRequest,
    *,
    bundle: IntercomSupportBundle,
    client_factory: IntercomClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> ConversationGetResponse:
    conversation = await _fetch_conversation(
        bundle,
        conversation_id=request.conversation_id,
        client_factory=client_factory,
    )
    return _build_conversation_get_response(
        request=request,
        bundle=bundle,
        conversation=conversation,
        receipt_id=receipt_id,
        execution_id=execution_id,
    )


async def list_conversation_parts(
    request: ConversationListPartsRequest,
    *,
    bundle: IntercomSupportBundle,
    client_factory: IntercomClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> ConversationListPartsResponse:
    try:
        ensure_internal_notes_allowed(bundle, include_internal=request.include_internal)
    except SupportRefError as exc:
        raise IntercomExecutorError(
            code="support_internal_notes_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    conversation = await _fetch_conversation(
        bundle,
        conversation_id=request.conversation_id,
        client_factory=client_factory,
    )

    normalized_parts = [
        part
        for raw_part in _raw_conversation_parts(conversation)
        if (part := _normalize_part(raw_part, include_internal=request.include_internal)) is not None
    ]

    start_index = 0
    if request.page_after:
        for idx, part in enumerate(normalized_parts):
            if part.part_id == request.page_after:
                start_index = idx + 1
                break

    paged_parts = normalized_parts[start_index:start_index + request.limit]
    has_more = len(normalized_parts) > start_index + len(paged_parts)
    next_page_after = paged_parts[-1].part_id if has_more and paged_parts else None

    return ConversationListPartsResponse(
        provider_used="intercom",
        credential_mode="byok",
        capability_id="conversation.list_parts",
        receipt_id=receipt_id,
        execution_id=execution_id,
        support_ref=bundle.support_ref,
        conversation_id=request.conversation_id,
        parts=paged_parts,
        part_count_returned=len(paged_parts),
        has_more=has_more,
        next_page_after=next_page_after,
    )


async def _fetch_conversation(
    bundle: IntercomSupportBundle,
    *,
    conversation_id: str,
    client_factory: IntercomClientFactory,
) -> dict[str, Any]:
    payload = await _intercom_get_json(
        bundle,
        f"/conversations/{conversation_id}",
        params=None,
        client_factory=client_factory,
        not_found_code="support_conversation_not_found",
        not_found_message=f"Intercom conversation '{conversation_id}' not found",
    )
    if not isinstance(payload, dict) or not _conversation_id(payload):
        raise IntercomExecutorError(
            code="support_provider_unavailable",
            message="Intercom conversation response was missing conversation payload",
            status_code=503,
        )
    try:
        ensure_conversation_access(bundle, payload, conversation_id=conversation_id)
    except SupportRefError as exc:
        raise IntercomExecutorError(
            code="support_conversation_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc
    return payload


def _build_conversation_get_response(
    *,
    request: ConversationGetRequest,
    bundle: IntercomSupportBundle,
    conversation: dict[str, Any],
    receipt_id: str,
    execution_id: str,
) -> ConversationGetResponse:
    conversation_id = _conversation_id(conversation) or request.conversation_id
    source = _source_payload(conversation)

    return ConversationGetResponse(
        provider_used="intercom",
        credential_mode="byok",
        capability_id="conversation.get",
        receipt_id=receipt_id,
        execution_id=execution_id,
        support_ref=bundle.support_ref,
        conversation_id=conversation_id,
        title=_conversation_title(conversation),
        state=_clean_text(conversation.get("state")),
        open=_as_bool(conversation.get("open")),
        read=_as_bool(conversation.get("read")),
        created_at=_as_int(conversation.get("created_at")),
        updated_at=_as_int(conversation.get("updated_at")),
        admin_assignee_id=_admin_assignee_id(conversation),
        team_assignee_id=_team_assignee_id(conversation),
        source=_build_source(source),
        tags=_extract_tag_names(conversation),
    )


async def _intercom_get_json(
    bundle: IntercomSupportBundle,
    path: str,
    *,
    params: dict[str, Any] | None,
    client_factory: IntercomClientFactory,
    not_found_code: str,
    not_found_message: str,
) -> dict[str, Any]:
    base_url = _INTERCOM_BASE_URLS[bundle.region]
    headers = _build_headers(bundle)
    try:
        async with client_factory(base_url=base_url, headers=headers, timeout=30.0) as client:
            response = await client.get(path, params=params)
    except httpx.HTTPError as exc:
        raise IntercomExecutorError(
            code="support_provider_unavailable",
            message=str(exc) or "Intercom request failed",
            status_code=503,
        ) from exc

    if response.status_code == 404:
        raise IntercomExecutorError(not_found_code, not_found_message, 404)
    if response.status_code in {401, 403}:
        raise IntercomExecutorError(
            code="support_access_denied",
            message="Intercom denied access with the provided support_ref credentials",
            status_code=response.status_code,
        )
    if response.status_code == 429:
        raise IntercomExecutorError(
            code="support_rate_limited",
            message="Intercom rate limited the request",
            status_code=429,
        )
    if response.status_code >= 500:
        raise IntercomExecutorError(
            code="support_provider_unavailable",
            message="Intercom upstream error",
            status_code=503,
        )
    if response.status_code >= 400:
        raise IntercomExecutorError(
            code="support_provider_unavailable",
            message=f"Intercom request failed with status {response.status_code}",
            status_code=502,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise IntercomExecutorError(
            code="support_provider_unavailable",
            message="Intercom returned invalid JSON",
            status_code=503,
        ) from exc

    if not isinstance(payload, dict):
        raise IntercomExecutorError(
            code="support_provider_unavailable",
            message="Intercom returned an unexpected response payload",
            status_code=503,
        )
    return payload


def _build_headers(bundle: IntercomSupportBundle) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {bundle.bearer_token}",
        "Intercom-Version": _INTERCOM_VERSION,
    }


def _build_conversation_summary(conversation: dict[str, Any]) -> IntercomConversationSummary:
    source = _source_payload(conversation)
    conversation_id = _conversation_id(conversation) or "unknown"
    return IntercomConversationSummary(
        conversation_id=conversation_id,
        title=_conversation_title(conversation),
        state=_clean_text(conversation.get("state")),
        open=_as_bool(conversation.get("open")),
        read=_as_bool(conversation.get("read")),
        created_at=_as_int(conversation.get("created_at")),
        updated_at=_as_int(conversation.get("updated_at")),
        admin_assignee_id=_admin_assignee_id(conversation),
        team_assignee_id=_team_assignee_id(conversation),
        source_author_id=_source_author_id(source),
        snippet=_truncate(_source_body_text(source), _MAX_SNIPPET_CHARS),
    )


def _build_source(source: dict[str, Any] | None) -> IntercomConversationSource | None:
    if not isinstance(source, dict):
        return None
    return IntercomConversationSource(
        author_id=_source_author_id(source),
        delivered_as=_clean_text(source.get("delivered_as") or source.get("message_type")),
        subject=_clean_text(source.get("subject")),
        body_text=_truncate(_source_body_text(source), _MAX_BODY_TEXT_CHARS),
    )


def _normalize_part(
    part: object,
    *,
    include_internal: bool,
) -> IntercomConversationPart | None:
    if not isinstance(part, dict):
        return None
    part_id = _string_id(part.get("id"))
    if not part_id:
        return None
    if _is_internal_part(part) and not include_internal:
        return None
    return IntercomConversationPart(
        part_id=part_id,
        part_type=_clean_text(part.get("part_type")) or "unknown",
        author_id=_reference_id(part.get("author")) or _as_int(part.get("author_id")),
        created_at=_as_int(part.get("created_at")),
        redacted=bool(part.get("redacted", False)),
        body_text=_truncate(_body_text(part), _MAX_BODY_TEXT_CHARS),
    )


def _raw_conversation_parts(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    conversation_parts = conversation.get("conversation_parts")
    if isinstance(conversation_parts, dict):
        items = conversation_parts.get("conversation_parts") or conversation_parts.get("items") or []
    elif isinstance(conversation_parts, list):
        items = conversation_parts
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def _conversation_matches_filters(
    conversation: dict[str, Any],
    request: ConversationListRequest,
) -> bool:
    if request.state:
        state = (_clean_text(conversation.get("state")) or "").lower()
        if state != request.state:
            return False

    updated_at = _as_int(conversation.get("updated_at"))
    if request.updated_after is not None and updated_at is not None and updated_at < request.updated_after:
        return False
    if request.updated_before is not None and updated_at is not None and updated_at > request.updated_before:
        return False
    return True


def _conversation_id(conversation: dict[str, Any]) -> str | None:
    return _string_id(conversation.get("id"))


def _conversation_title(conversation: dict[str, Any]) -> str:
    title = _clean_text(conversation.get("title"))
    if title:
        return title
    source = _source_payload(conversation)
    subject = _clean_text(source.get("subject")) if isinstance(source, dict) else None
    if subject:
        return subject
    conversation_id = _conversation_id(conversation) or "unknown"
    return f"Conversation {conversation_id}"


def _source_payload(conversation: dict[str, Any]) -> dict[str, Any] | None:
    source = conversation.get("source")
    return source if isinstance(source, dict) else None


def _source_author_id(source: dict[str, Any] | None) -> int | None:
    if not isinstance(source, dict):
        return None
    return _reference_id(source.get("author")) or _as_int(source.get("author_id"))


def _source_body_text(source: dict[str, Any] | None) -> str | None:
    if not isinstance(source, dict):
        return None
    return _html_to_text(source.get("body") or source.get("body_text") or source.get("text"))


def _body_text(part: dict[str, Any]) -> str | None:
    return _html_to_text(part.get("body") or part.get("body_text") or part.get("summary"))


def _is_internal_part(part: dict[str, Any]) -> bool:
    part_type = (_clean_text(part.get("part_type")) or "").lower()
    return part_type in {"note", "assignment"}


def _extract_tag_names(conversation: dict[str, Any]) -> list[str]:
    raw_tags = conversation.get("tags")
    if isinstance(raw_tags, dict):
        raw_tags = raw_tags.get("tags") or raw_tags.get("items") or []
    names: list[str] = []
    for item in raw_tags or []:
        if isinstance(item, dict):
            name = _clean_text(item.get("name"))
        else:
            name = _clean_text(item)
        if name:
            names.append(name)
        if len(names) >= 25:
            break
    return names


def _extract_next_page_after(pages: object) -> str | None:
    if not isinstance(pages, dict):
        return None
    next_page = pages.get("next")
    if isinstance(next_page, dict):
        for key in ("starting_after", "cursor", "page_after", "after"):
            token = _clean_text(next_page.get(key))
            if token:
                return token
    if isinstance(next_page, str):
        token = next_page.strip()
        return token or None
    for key in ("starting_after", "next_page_after"):
        token = _clean_text(pages.get(key))
        if token:
            return token
    return None


def _reference_id(value: object) -> int | None:
    if isinstance(value, dict):
        return _as_int(value.get("id"))
    return _as_int(value)


def _admin_assignee_id(conversation: dict[str, Any]) -> int | None:
    return _as_int(conversation.get("admin_assignee_id")) or _reference_id(conversation.get("admin_assignee")) or _as_int(conversation.get("assignee_id")) or _reference_id(conversation.get("assignee"))


def _team_assignee_id(conversation: dict[str, Any]) -> int | None:
    return _as_int(conversation.get("team_assignee_id")) or _reference_id(conversation.get("team_assignee"))


def _html_to_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    text = _BREAK_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = _NEWLINE_RE.sub("\n\n", text)
    normalized = text.strip()
    return normalized or None


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return value[: max(limit - 1, 0)].rstrip() + "…"


def _string_id(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None
