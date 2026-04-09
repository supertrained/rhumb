"""Zendesk read-first executor for AUD-18."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import httpx

from schemas.support_capabilities import (
    TicketGetRequest,
    TicketGetResponse,
    TicketListCommentsRequest,
    TicketListCommentsResponse,
    TicketSearchRequest,
    TicketSearchResponse,
    ZendeskComment,
    ZendeskCustomField,
    ZendeskTicketSummary,
    normalize_custom_field_value,
)
from services.support_connection_registry import (
    SupportRefError,
    ZendeskSupportBundle,
    ensure_internal_comments_allowed,
    ensure_ticket_access,
)

ZendeskClientFactory = Callable[..., Any]

_MAX_SNIPPET_CHARS = 280
_MAX_BODY_TEXT_CHARS = 4000
_MAX_CUSTOM_FIELDS = 50


@dataclass(slots=True)
class ZendeskExecutorError(RuntimeError):
    code: str
    message: str
    status_code: int = 422

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


async def search_tickets(
    request: TicketSearchRequest,
    *,
    bundle: ZendeskSupportBundle,
    client_factory: ZendeskClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> TicketSearchResponse:
    params: dict[str, Any] = {
        "query": f"type:ticket {request.query}",
        "per_page": min(max(request.limit, 1), 25),
    }
    if request.page_after:
        params["page"] = request.page_after

    payload = await _zendesk_get_json(
        bundle,
        "/search.json",
        params=params,
        client_factory=client_factory,
        not_found_code="support_search_unavailable",
        not_found_message="Zendesk ticket search endpoint unavailable",
    )

    filtered: list[ZendeskTicketSummary] = []
    raw_results = payload.get("results") or []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        ticket_id = _as_int(item.get("id"))
        group_id = _as_int(item.get("group_id"))
        brand_id = _as_int(item.get("brand_id"))
        if ticket_id is None:
            continue
        if not _ticket_allowed(bundle, item):
            continue
        filtered.append(
            ZendeskTicketSummary(
                ticket_id=ticket_id,
                subject=_clean_text(item.get("subject")) or f"Ticket {ticket_id}",
                status=_clean_text(item.get("status")),
                priority=_clean_text(item.get("priority")),
                brand_id=brand_id,
                group_id=group_id,
                assignee_id=_as_int(item.get("assignee_id")),
                requester_id=_as_int(item.get("requester_id")),
                updated_at=_clean_text(item.get("updated_at")),
                tags=_normalize_tags(item.get("tags")),
                snippet=_truncate(_clean_text(item.get("description")) or _clean_text(item.get("raw_subject")), _MAX_SNIPPET_CHARS),
            )
        )
        if len(filtered) >= request.limit:
            break

    next_page_after = _extract_next_page_after(payload.get("next_page"))
    has_more = bool(next_page_after) or len(raw_results) > len(filtered)

    return TicketSearchResponse(
        provider_used="zendesk",
        credential_mode="byok",
        capability_id="ticket.search",
        receipt_id=receipt_id,
        execution_id=execution_id,
        support_ref=bundle.support_ref,
        tickets=filtered,
        result_count_returned=len(filtered),
        has_more=has_more,
        next_page_after=next_page_after,
    )


async def get_ticket(
    request: TicketGetRequest,
    *,
    bundle: ZendeskSupportBundle,
    client_factory: ZendeskClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> TicketGetResponse:
    ticket = await _fetch_ticket(
        bundle,
        ticket_id=request.ticket_id,
        client_factory=client_factory,
    )
    return _build_ticket_get_response(
        request=request,
        bundle=bundle,
        ticket=ticket,
        receipt_id=receipt_id,
        execution_id=execution_id,
    )


async def list_comments(
    request: TicketListCommentsRequest,
    *,
    bundle: ZendeskSupportBundle,
    client_factory: ZendeskClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> TicketListCommentsResponse:
    try:
        ensure_internal_comments_allowed(bundle, include_internal=request.include_internal)
    except SupportRefError as exc:
        raise ZendeskExecutorError(
            code="support_internal_comments_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    await _fetch_ticket(
        bundle,
        ticket_id=request.ticket_id,
        client_factory=client_factory,
    )

    payload = await _zendesk_get_json(
        bundle,
        f"/tickets/{request.ticket_id}/comments.json",
        params={"per_page": min(max(request.limit, 1), 50), "sort_order": "asc"},
        client_factory=client_factory,
        not_found_code="support_ticket_not_found",
        not_found_message=f"Zendesk ticket '{request.ticket_id}' not found",
    )

    comments: list[ZendeskComment] = []
    raw_comments = payload.get("comments") or []
    for item in raw_comments:
        if not isinstance(item, dict):
            continue
        comment_id = _as_int(item.get("id"))
        if comment_id is None:
            continue
        public = bool(item.get("public", False))
        if not request.include_internal and not public:
            continue
        comments.append(
            ZendeskComment(
                comment_id=comment_id,
                author_id=_as_int(item.get("author_id")),
                created_at=_clean_text(item.get("created_at")),
                public=public,
                body_text=_truncate(_extract_comment_body(item), _MAX_BODY_TEXT_CHARS),
            )
        )
        if len(comments) >= request.limit:
            break

    has_more = bool(payload.get("next_page")) or len(raw_comments) > len(comments)

    return TicketListCommentsResponse(
        provider_used="zendesk",
        credential_mode="byok",
        capability_id="ticket.list_comments",
        receipt_id=receipt_id,
        execution_id=execution_id,
        support_ref=bundle.support_ref,
        ticket_id=request.ticket_id,
        comments=comments,
        comment_count_returned=len(comments),
        has_more=has_more,
    )


async def _fetch_ticket(
    bundle: ZendeskSupportBundle,
    *,
    ticket_id: int,
    client_factory: ZendeskClientFactory,
) -> dict[str, Any]:
    payload = await _zendesk_get_json(
        bundle,
        f"/tickets/{ticket_id}.json",
        params=None,
        client_factory=client_factory,
        not_found_code="support_ticket_not_found",
        not_found_message=f"Zendesk ticket '{ticket_id}' not found",
    )
    ticket = payload.get("ticket")
    if not isinstance(ticket, dict):
        raise ZendeskExecutorError(
            code="support_provider_unavailable",
            message="Zendesk ticket response was missing ticket payload",
            status_code=503,
        )
    try:
        ensure_ticket_access(
            bundle,
            ticket_id=ticket_id,
            group_id=_as_int(ticket.get("group_id")),
            brand_id=_as_int(ticket.get("brand_id")),
        )
    except SupportRefError as exc:
        raise ZendeskExecutorError(
            code="support_ticket_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc
    return ticket


def _build_ticket_get_response(
    *,
    request: TicketGetRequest,
    bundle: ZendeskSupportBundle,
    ticket: dict[str, Any],
    receipt_id: str,
    execution_id: str,
) -> TicketGetResponse:
    custom_fields = []
    for field in (ticket.get("custom_fields") or [])[:_MAX_CUSTOM_FIELDS]:
        if not isinstance(field, dict):
            continue
        field_id = _as_int(field.get("id"))
        if field_id is None:
            continue
        custom_fields.append(
            ZendeskCustomField(
                field_id=field_id,
                value=normalize_custom_field_value(field.get("value")),
            )
        )

    ticket_id = _as_int(ticket.get("id")) or request.ticket_id
    return TicketGetResponse(
        provider_used="zendesk",
        credential_mode="byok",
        capability_id="ticket.get",
        receipt_id=receipt_id,
        execution_id=execution_id,
        support_ref=bundle.support_ref,
        ticket_id=ticket_id,
        subject=_clean_text(ticket.get("subject")) or f"Ticket {ticket_id}",
        status=_clean_text(ticket.get("status")),
        priority=_clean_text(ticket.get("priority")),
        type=_clean_text(ticket.get("type")),
        brand_id=_as_int(ticket.get("brand_id")),
        group_id=_as_int(ticket.get("group_id")),
        assignee_id=_as_int(ticket.get("assignee_id")),
        requester_id=_as_int(ticket.get("requester_id")),
        created_at=_clean_text(ticket.get("created_at")),
        updated_at=_clean_text(ticket.get("updated_at")),
        tags=_normalize_tags(ticket.get("tags")),
        description_text=_truncate(_clean_text(ticket.get("description")), _MAX_BODY_TEXT_CHARS),
        custom_fields=custom_fields,
    )


async def _zendesk_get_json(
    bundle: ZendeskSupportBundle,
    path: str,
    *,
    params: dict[str, Any] | None,
    client_factory: ZendeskClientFactory,
    not_found_code: str,
    not_found_message: str,
) -> dict[str, Any]:
    base_url = f"https://{bundle.subdomain}.zendesk.com/api/v2"
    headers = _build_headers(bundle)
    try:
        async with client_factory(base_url=base_url, headers=headers, timeout=30.0) as client:
            response = await client.get(path, params=params)
    except httpx.HTTPError as exc:
        raise ZendeskExecutorError(
            code="support_provider_unavailable",
            message=str(exc) or "Zendesk request failed",
            status_code=503,
        ) from exc

    if response.status_code == 404:
        raise ZendeskExecutorError(not_found_code, not_found_message, 404)
    if response.status_code == 401:
        raise ZendeskExecutorError(
            code="support_access_denied",
            message="Zendesk credentials were rejected",
            status_code=401,
        )
    if response.status_code == 403:
        raise ZendeskExecutorError(
            code="support_access_denied",
            message="Zendesk access denied",
            status_code=403,
        )
    if response.status_code == 429:
        raise ZendeskExecutorError(
            code="support_rate_limited",
            message="Zendesk rate limit exceeded",
            status_code=429,
        )
    if response.status_code >= 500:
        raise ZendeskExecutorError(
            code="support_provider_unavailable",
            message="Zendesk temporarily unavailable",
            status_code=503,
        )
    if response.status_code >= 400:
        raise ZendeskExecutorError(
            code="support_request_failed",
            message=f"Zendesk request failed with status {response.status_code}",
            status_code=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ZendeskExecutorError(
            code="support_provider_unavailable",
            message="Zendesk returned invalid JSON",
            status_code=503,
        ) from exc

    if not isinstance(payload, dict):
        raise ZendeskExecutorError(
            code="support_provider_unavailable",
            message="Zendesk returned a non-object payload",
            status_code=503,
        )
    return payload


def _build_headers(bundle: ZendeskSupportBundle) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if bundle.auth_mode == "bearer_token":
        headers["Authorization"] = f"Bearer {bundle.bearer_token}"
        return headers

    assert bundle.email is not None
    assert bundle.api_token is not None
    basic = base64.b64encode(f"{bundle.email}/token:{bundle.api_token}".encode("utf-8")).decode("utf-8")
    headers["Authorization"] = f"Basic {basic}"
    return headers


def _ticket_allowed(bundle: ZendeskSupportBundle, ticket: dict[str, Any]) -> bool:
    try:
        ensure_ticket_access(
            bundle,
            ticket_id=_as_int(ticket.get("id")),
            group_id=_as_int(ticket.get("group_id")),
            brand_id=_as_int(ticket.get("brand_id")),
        )
        return True
    except SupportRefError:
        return False


def _extract_next_page_after(next_page: Any) -> str | None:
    if not isinstance(next_page, str) or not next_page:
        return None
    query = parse_qs(urlparse(next_page).query)
    page = query.get("page")
    if page:
        return page[0]
    return None


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            tags.append(item.strip())
    return tags


def _extract_comment_body(item: dict[str, Any]) -> str | None:
    return (
        _clean_text(item.get("plain_body"))
        or _clean_text(item.get("body"))
        or _clean_text(item.get("html_body"))
    )


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1] + "…"


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
