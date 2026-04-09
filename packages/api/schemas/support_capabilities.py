"""Support capability request/response schemas for the Zendesk read-first wedge."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SUPPORT_REF_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"

SUPPORT_SEARCH_DEFAULT_LIMIT = 10
SUPPORT_SEARCH_MAX_LIMIT = 25
SUPPORT_COMMENT_DEFAULT_LIMIT = 20
SUPPORT_COMMENT_MAX_LIMIT = 50
SUPPORT_TEXT_MAX_CHARS = 4000
SUPPORT_SNIPPET_MAX_CHARS = 500
SUPPORT_QUERY_MAX_CHARS = 500
SUPPORT_PAGE_TOKEN_MAX_CHARS = 2048
SUPPORT_REASON_MAX_CHARS = 300
SUPPORT_CUSTOM_FIELDS_MAX = 25
SUPPORT_TAGS_MAX = 25


class SupportBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ZendeskCustomField(SupportBaseModel):
    id: int = Field(..., gt=0, validation_alias="field_id")
    value: str | int | float | bool | None = None


class ZendeskTicketSummary(SupportBaseModel):
    ticket_id: int = Field(..., gt=0)
    subject: str
    status: str | None = None
    priority: str | None = None
    brand_id: int | None = None
    group_id: int | None = None
    assignee_id: int | None = None
    requester_id: int | None = None
    updated_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    text_snippet: str | None = Field(default=None, validation_alias="snippet")


class ZendeskComment(SupportBaseModel):
    comment_id: int = Field(..., gt=0)
    author_id: int | None = None
    created_at: str | None = None
    public: bool
    body_text: str | None = None


class TicketSearchRequest(SupportBaseModel):
    support_ref: str = Field(..., pattern=_SUPPORT_REF_PATTERN)
    query: str = Field(..., min_length=1, max_length=SUPPORT_QUERY_MAX_CHARS)
    limit: int = Field(default=SUPPORT_SEARCH_DEFAULT_LIMIT, ge=1, le=SUPPORT_SEARCH_MAX_LIMIT)
    page_after: str | None = Field(default=None, max_length=SUPPORT_PAGE_TOKEN_MAX_CHARS)
    reason: str | None = Field(default=None, max_length=SUPPORT_REASON_MAX_CHARS)

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized


class TicketSearchResponse(SupportBaseModel):
    provider_used: str
    credential_mode: str
    capability_id: str
    receipt_id: str
    execution_id: str
    support_ref: str
    tickets: list[ZendeskTicketSummary] = Field(default_factory=list)
    ticket_count_returned: int = Field(validation_alias="result_count_returned")
    has_more: bool
    next_page_after: str | None = None


class TicketGetRequest(SupportBaseModel):
    support_ref: str = Field(..., pattern=_SUPPORT_REF_PATTERN)
    ticket_id: int = Field(..., gt=0)
    reason: str | None = Field(default=None, max_length=SUPPORT_REASON_MAX_CHARS)


class TicketGetResponse(SupportBaseModel):
    provider_used: str
    credential_mode: str
    capability_id: str
    receipt_id: str
    execution_id: str
    support_ref: str
    ticket_id: int
    subject: str
    status: str | None = None
    priority: str | None = None
    type: str | None = None
    brand_id: int | None = None
    group_id: int | None = None
    assignee_id: int | None = None
    requester_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    description_text: str | None = None
    custom_fields: list[ZendeskCustomField] = Field(default_factory=list)


class TicketListCommentsRequest(SupportBaseModel):
    support_ref: str = Field(..., pattern=_SUPPORT_REF_PATTERN)
    ticket_id: int = Field(..., gt=0)
    limit: int = Field(default=SUPPORT_COMMENT_DEFAULT_LIMIT, ge=1, le=SUPPORT_COMMENT_MAX_LIMIT)
    page_after: str | None = Field(default=None, max_length=SUPPORT_PAGE_TOKEN_MAX_CHARS)
    include_internal: bool = False
    reason: str | None = Field(default=None, max_length=SUPPORT_REASON_MAX_CHARS)


class TicketListCommentsResponse(SupportBaseModel):
    provider_used: str
    credential_mode: str
    capability_id: str
    receipt_id: str
    execution_id: str
    support_ref: str
    ticket_id: int
    comments: list[ZendeskComment] = Field(default_factory=list)
    comment_count_returned: int
    has_more: bool
    next_page_after: str | None = None


SUPPORTED_TICKET_CAPABILITY_IDS = frozenset({
    "ticket.search",
    "ticket.get",
    "ticket.list_comments",
})


def normalize_custom_field_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


ZendeskCustomFieldValue = ZendeskCustomField
ZendeskTicketComment = ZendeskComment
