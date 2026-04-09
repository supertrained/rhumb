"""Zendesk ticket read-first executor for AUD-18."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import httpx

from schemas.support_capabilities import (
    SUPPORT_CUSTOM_FIELDS_MAX,
    SUPPORT_SNIPPET_MAX_CHARS,
    SUPPORT_TAGS_MAX,
    SUPPORT_TEXT_MAX_CHARS,
    TicketGetRequest,
    TicketGetResponse,
    TicketListCommentsRequest,
    TicketListCommentsResponse,
    TicketSearchRequest,
    TicketSearchResponse,
    ZendeskCustomFieldValue,
    ZendeskTicketComment,
    ZendeskTicketSummary,
)
from services.support_connection_registry import (
    SupportRefError,
    ZendeskSupportBundle,
    ensure_ticket_access,
    ticket_in_scope,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class SupportExecutorError(RuntimeError):
    code: str
    message: str
    status_code: int = 422

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


SupportClientFactory = Callable[[ZendeskSupportBundle], httpx.AsyncClient]


def get_zendesk_client(bundle: ZendeskSupportBundle) -> httpx.AsyncClient:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    auth: tuple[str, str] | None = None
    if bundle.auth_mode == "api_token":
        auth = (f"{bundle.email}/token", bundle.api_token or "")
    else:
        headers["Authorization"] = f"Bearer {bundle.bearer_token}"

    return httpx.AsyncClient(
        base_url=f"https://{bundle.subdomain}.zendesk.com/api/v2",
        headers=headers,
        auth=auth,
        timeout=15.0,
    )


async def search_tickets(
    request: TicketSearchRequest,
    *,
    bundle: ZendeskSupportBundle,
    client_factory: SupportClientFactory = get_zendesk_client,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> TicketSearchResponse:
    params: dict[str, Any] = {
        "query": f"type:ticket {request.query}",
        "per_page": request.limit,
    }
    _apply_page_after(params, request.page_after)

    async with client_factory(bundle) as client:
        response = await client.get("/search.json", params=params)
    payload = _parse_payload(response)

    tickets = [
        _build_ticket_summary(result)
        for result in payload.get("results") or []
        if _is_ticket_result(result) and ticket_in_scope(bundle, result)
    ]

    return TicketSearchResponse(
        provider_used="zendesk",
        credential_mode="byok",
        capability_id="ticket.search",
        receipt_id=receipt_id,
        execution_id=execution_id,
        support_ref=bundle.support_ref,
        tickets=tickets[: request.limit],
        ticket_count_returned=min(len(tickets), request.limit),
        has_more=bool(payload.get("next_page")),
        next_page_after=_next_page_after(payload),
    )


async def get_ticket(
    request: TicketGetRequest,
    *,
    bundle: ZendeskSupportBundle,
    client_factory: SupportClientFactory = get_zendesk_client,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> TicketGetResponse:
    async with client_factory(bundle) as client:
        response = await client.get(f"/tickets/{request.ticket_id}.json")
    payload = _parse_payload(response)

    ticket = payload.get("ticket")
    if not isinstance(ticket, dict):
        raise SupportExecutorError(
            code="support_ticket_not_found",
            message="Requested Zendesk ticket was not found",
            status_code=404,
        )

    try:
        ensure_ticket_access(bundle, ticket, ticket_id=request.ticket_id)
    except SupportRefError as exc:
        raise SupportExecutorError(
            code="support_ticket_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    return TicketGetResponse(
        provider_used="zendesk",
        credential_mode="byok",
        capability_id="ticket.get",
        receipt_id=receipt_id,
        execution_id=execution_id,
        support_ref=bundle.support_ref,
        ticket_id=int(ticket.get("id") or request.ticket_id),
        subject=_bounded_text(ticket.get("subject"), max_chars=SUPPORT_SNIPPET_MAX_CHARS),
        status=_optional_string(ticket.get("status")),
        priority=_optional_string(ticket.get("priority")),
        type=_optional_string(ticket.get("type")),
        brand_id=_optional_int(ticket.get("brand_id")),
        group_id=_optional_int(ticket.get("group_id")),
        assignee_id=_optional_int(ticket.get("assignee_id")),
        requester_id=_optional_int(ticket.get("requester_id")),
        created_at=_optional_string(ticket.get("created_at")),
        updated_at=_optional_string(ticket.get("updated_at")),
        tags=_normalize_tags(ticket.get("tags")),
        description_text=_bounded_text(
            ticket.get("description") or ticket.get("raw_subject"),
            max_chars=SUPPORT_TEXT_MAX_CHARS,
        ),
        custom_fields=_normalize_custom_fields(ticket.get("custom_fields")),
    )


async def list_ticket_comments(
    request: TicketListCommentsRequest,
    *,
    bundle: ZendeskSupportBundle,
    client_factory: SupportClientFactory = get_zendesk_client,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> TicketListCommentsResponse:
    if request.include_internal and not bundle.allow_internal_comments:
        raise SupportExecutorError(
            code="support_internal_comments_denied",
            message=(
                f"support_ref '{bundle.support_ref}' is not allowed to include internal comments"
            ),
            status_code=403,
        )

    async with client_factory(bundle) as client:
        ticket_response = await client.get(f"/tickets/{request.ticket_id}.json")
        ticket_payload = _parse_payload(ticket_response)
        ticket = ticket_payload.get("ticket")
        if not isinstance(ticket, dict):
            raise SupportExecutorError(
                code="support_ticket_not_found",
                message="Requested Zendesk ticket was not found",
                status_code=404,
            )
        try:
            ensure_ticket_access(bundle, ticket, ticket_id=request.ticket_id)
        except SupportRefError as exc:
            raise SupportExecutorError(
                code="support_ticket_scope_denied",
                message=str(exc),
                status_code=403,
            ) from exc

        params: dict[str, Any] = {"per_page": request.limit}
        _apply_page_after(params, request.page_after)
        comments_response = await client.get(
            f"/tickets/{request.ticket_id}/comments.json",
            params=params,
        )
    comments_payload = _parse_payload(comments_response)

    comments: list[ZendeskTicketComment] = []
    for raw_comment in comments_payload.get("comments") or []:
        if not isinstance(raw_comment, dict):
            continue
        public = bool(raw_comment.get("public", False))
        if not public and not request.include_internal:
            continue
        comments.append(
            ZendeskTicketComment(
                comment_id=int(raw_comment.get("id") or 0),
                author_id=_optional_int(raw_comment.get("author_id")),
                created_at=_optional_string(raw_comment.get("created_at")),
                public=public,
                body_text=_bounded_text(
                    raw_comment.get("plain_body") or raw_comment.get("body"),
                    max_chars=SUPPORT_TEXT_MAX_CHARS,
                ),
            )
        )
        if len(comments) >= request.limit:
            break

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
        has_more=bool(comments_payload.get("next_page")),
        next_page_after=_next_page_after(comments_payload),
    )


def _parse_payload(response: httpx.Response) -> dict[str, Any]:
    if response.status_code == 404:
        raise SupportExecutorError(
            code="support_ticket_not_found",
            message="Requested Zendesk ticket was not found",
            status_code=404,
        )
    if response.status_code in {401, 403}:
        raise SupportExecutorError(
            code="support_access_denied",
            message="Access denied by Zendesk",
            status_code=response.status_code,
        )
    if response.status_code >= 500:
        raise SupportExecutorError(
            code="support_provider_unavailable",
            message="Zendesk is temporarily unavailable",
            status_code=503,
        )
    if response.status_code >= 400:
        message = _extract_error_message(response)
        raise SupportExecutorError(
            code="support_request_rejected",
            message=message,
            status_code=response.status_code,
        )

    try:
        payload = response.json()
    except Exception as exc:  # pragma: no cover
        raise SupportExecutorError(
            code="support_provider_unavailable",
            message="Zendesk returned an invalid JSON response",
            status_code=503,
        ) from exc

    if not isinstance(payload, dict):
        raise SupportExecutorError(
            code="support_provider_unavailable",
            message="Zendesk returned an unexpected response payload",
            status_code=503,
        )
    return payload


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return "Zendesk request failed"

    if isinstance(payload, dict):
        for key in ("description", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return _bounded_text(value, max_chars=300) or "Zendesk request failed"
    return "Zendesk request failed"


def _is_ticket_result(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    result_type = value.get("result_type")
    return result_type in {None, "ticket"}


def _build_ticket_summary(ticket: dict[str, Any]) -> ZendeskTicketSummary:
    return ZendeskTicketSummary(
        ticket_id=int(ticket.get("id") or 0),
        subject=_bounded_text(ticket.get("subject"), max_chars=SUPPORT_SNIPPET_MAX_CHARS),
        status=_optional_string(ticket.get("status")),
        priority=_optional_string(ticket.get("priority")),
        brand_id=_optional_int(ticket.get("brand_id")),
        group_id=_optional_int(ticket.get("group_id")),
        assignee_id=_optional_int(ticket.get("assignee_id")),
        requester_id=_optional_int(ticket.get("requester_id")),
        updated_at=_optional_string(ticket.get("updated_at")),
        tags=_normalize_tags(ticket.get("tags")),
        text_snippet=_bounded_text(
            ticket.get("description") or ticket.get("snippet") or ticket.get("subject"),
            max_chars=SUPPORT_SNIPPET_MAX_CHARS,
        ),
    )


def _normalize_custom_fields(value: object) -> list[ZendeskCustomFieldValue]:
    if not isinstance(value, list):
        return []

    normalized: list[ZendeskCustomFieldValue] = []
    for raw_field in value[:SUPPORT_CUSTOM_FIELDS_MAX]:
        if not isinstance(raw_field, dict):
            continue
        field_id = _optional_int(raw_field.get("id"))
        if field_id is None or field_id <= 0:
            continue
        normalized.append(
            ZendeskCustomFieldValue(
                id=field_id,
                value=_normalize_custom_field_value(raw_field.get("value")),
            )
        )
    return normalized


def _normalize_custom_field_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _bounded_text(value, max_chars=SUPPORT_SNIPPET_MAX_CHARS)
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return _bounded_text(json.dumps(value, ensure_ascii=False), max_chars=SUPPORT_SNIPPET_MAX_CHARS)
    except Exception:
        return _bounded_text(str(value), max_chars=SUPPORT_SNIPPET_MAX_CHARS)


def _normalize_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for raw_tag in value[:SUPPORT_TAGS_MAX]:
        if not isinstance(raw_tag, str):
            continue
        tag = raw_tag.strip()
        if tag:
            tags.append(tag)
    return tags


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _bounded_text(value: object, *, max_chars: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = html.unescape(text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if not text:
        return None
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def _apply_page_after(params: dict[str, Any], page_after: str | None) -> None:
    if not page_after:
        return
    parsed = urlparse(page_after)
    if parsed.scheme and parsed.netloc:
        for key, values in parse_qs(parsed.query).items():
            if values:
                params[key] = values[-1]
        return
    params["page"] = page_after


def _next_page_after(payload: dict[str, Any]) -> str | None:
    next_page = payload.get("next_page")
    if isinstance(next_page, str) and next_page.strip():
        return next_page.strip()
    meta = payload.get("meta")
    after_cursor = meta.get("after_cursor") if isinstance(meta, dict) else None
    if isinstance(after_cursor, str) and after_cursor.strip():
        return after_cursor.strip()
    links = payload.get("links")
    next_link = links.get("next") if isinstance(links, dict) else None
    if isinstance(next_link, str) and next_link.strip():
        return next_link.strip()
    return None
