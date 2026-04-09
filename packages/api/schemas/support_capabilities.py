"""Support capability request/response schemas for the AUD-18 read-first wedge."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SUPPORT_REF_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"

SUPPORT_SEARCH_DEFAULT_LIMIT = 10
SUPPORT_SEARCH_MAX_LIMIT = 25
SUPPORT_LIST_DEFAULT_LIMIT = 20
SUPPORT_LIST_MAX_LIMIT = 50
SUPPORT_COMMENT_DEFAULT_LIMIT = 20
SUPPORT_COMMENT_MAX_LIMIT = 50
SUPPORT_PART_DEFAULT_LIMIT = 20
SUPPORT_PART_MAX_LIMIT = 50
SUPPORT_TEXT_MAX_CHARS = 4000
SUPPORT_SNIPPET_MAX_CHARS = 500
SUPPORT_QUERY_MAX_CHARS = 500
SUPPORT_PAGE_TOKEN_MAX_CHARS = 2048
SUPPORT_REASON_MAX_CHARS = 300
SUPPORT_CUSTOM_FIELDS_MAX = 25
SUPPORT_TAGS_MAX = 25
SUPPORT_STATE_MAX_CHARS = 50
SUPPORT_CONVERSATION_ID_MAX_CHARS = 128
SUPPORT_PART_ID_MAX_CHARS = 128


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


class IntercomConversationSummary(SupportBaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=SUPPORT_CONVERSATION_ID_MAX_CHARS)
    title: str
    state: str | None = None
    open: bool | None = None
    read: bool | None = None
    created_at: int | None = None
    updated_at: int | None = None
    admin_assignee_id: int | None = None
    team_assignee_id: int | None = None
    source_author_id: int | None = None
    text_snippet: str | None = Field(default=None, validation_alias="snippet")


class IntercomConversationSource(SupportBaseModel):
    author_id: int | None = None
    delivered_as: str | None = None
    subject: str | None = None
    body_text: str | None = None


class IntercomConversationPart(SupportBaseModel):
    part_id: str = Field(..., min_length=1, max_length=SUPPORT_PART_ID_MAX_CHARS)
    part_type: str
    author_id: int | None = None
    created_at: int | None = None
    redacted: bool
    body_text: str | None = None


class ConversationListRequest(SupportBaseModel):
    support_ref: str = Field(..., pattern=_SUPPORT_REF_PATTERN)
    limit: int = Field(default=SUPPORT_LIST_DEFAULT_LIMIT, ge=1, le=SUPPORT_LIST_MAX_LIMIT)
    page_after: str | None = Field(default=None, max_length=SUPPORT_PAGE_TOKEN_MAX_CHARS)
    state: str | None = Field(default=None, max_length=SUPPORT_STATE_MAX_CHARS)
    updated_after: int | None = Field(default=None, ge=0)
    updated_before: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=SUPPORT_REASON_MAX_CHARS)

    @field_validator("state")
    @classmethod
    def _normalize_state(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None


class ConversationListResponse(SupportBaseModel):
    provider_used: str
    credential_mode: str
    capability_id: str
    receipt_id: str
    execution_id: str
    support_ref: str
    conversations: list[IntercomConversationSummary] = Field(default_factory=list)
    conversation_count_returned: int = Field(validation_alias="result_count_returned")
    has_more: bool
    next_page_after: str | None = None


class ConversationGetRequest(SupportBaseModel):
    support_ref: str = Field(..., pattern=_SUPPORT_REF_PATTERN)
    conversation_id: str = Field(..., min_length=1, max_length=SUPPORT_CONVERSATION_ID_MAX_CHARS)
    reason: str | None = Field(default=None, max_length=SUPPORT_REASON_MAX_CHARS)

    @field_validator("conversation_id")
    @classmethod
    def _normalize_conversation_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("conversation_id must not be empty")
        return normalized


class ConversationGetResponse(SupportBaseModel):
    provider_used: str
    credential_mode: str
    capability_id: str
    receipt_id: str
    execution_id: str
    support_ref: str
    conversation_id: str
    title: str
    state: str | None = None
    open: bool | None = None
    read: bool | None = None
    created_at: int | None = None
    updated_at: int | None = None
    admin_assignee_id: int | None = None
    team_assignee_id: int | None = None
    source: IntercomConversationSource | None = None
    tags: list[str] = Field(default_factory=list)


class ConversationListPartsRequest(SupportBaseModel):
    support_ref: str = Field(..., pattern=_SUPPORT_REF_PATTERN)
    conversation_id: str = Field(..., min_length=1, max_length=SUPPORT_CONVERSATION_ID_MAX_CHARS)
    limit: int = Field(default=SUPPORT_PART_DEFAULT_LIMIT, ge=1, le=SUPPORT_PART_MAX_LIMIT)
    page_after: str | None = Field(default=None, max_length=SUPPORT_PAGE_TOKEN_MAX_CHARS)
    include_internal: bool = False
    reason: str | None = Field(default=None, max_length=SUPPORT_REASON_MAX_CHARS)

    @field_validator("conversation_id")
    @classmethod
    def _normalize_parts_conversation_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("conversation_id must not be empty")
        return normalized


class ConversationListPartsResponse(SupportBaseModel):
    provider_used: str
    credential_mode: str
    capability_id: str
    receipt_id: str
    execution_id: str
    support_ref: str
    conversation_id: str
    parts: list[IntercomConversationPart] = Field(default_factory=list)
    part_count_returned: int
    has_more: bool
    next_page_after: str | None = None


SUPPORTED_TICKET_CAPABILITY_IDS = frozenset({
    "ticket.search",
    "ticket.get",
    "ticket.list_comments",
})

SUPPORTED_CONVERSATION_CAPABILITY_IDS = frozenset({
    "conversation.list",
    "conversation.get",
    "conversation.list_parts",
})

SUPPORTED_SUPPORT_CAPABILITY_IDS = (
    SUPPORTED_TICKET_CAPABILITY_IDS | SUPPORTED_CONVERSATION_CAPABILITY_IDS
)


def normalize_custom_field_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


ZendeskCustomFieldValue = ZendeskCustomField
ZendeskTicketComment = ZendeskComment
