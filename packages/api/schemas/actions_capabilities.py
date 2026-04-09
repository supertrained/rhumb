"""GitHub Actions workflow-run capability schemas for the AUD-18 read-first wedge."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ACTIONS_REF_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
_REPOSITORY_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"

WORKFLOW_RUN_LIST_DEFAULT_LIMIT = 10
WORKFLOW_RUN_LIST_MAX_LIMIT = 25
WORKFLOW_RUN_PAGE_MAX = 100
WORKFLOW_RUN_REASON_MAX_CHARS = 300
WORKFLOW_RUN_STATUS_MAX_CHARS = 32
WORKFLOW_RUN_EVENT_MAX_CHARS = 64
WORKFLOW_RUN_BRANCH_MAX_CHARS = 255
WORKFLOW_RUN_NAME_MAX_CHARS = 255
WORKFLOW_RUN_TITLE_MAX_CHARS = 255
WORKFLOW_RUN_SHA_MAX_CHARS = 128
WORKFLOW_RUN_URL_MAX_CHARS = 500
WORKFLOW_RUN_TIMESTAMP_MAX_CHARS = 64
WORKFLOW_RUN_REPOSITORY_MAX_CHARS = 200
WORKFLOW_RUN_ACTOR_MAX_CHARS = 255

CredentialMode = Literal["byok"]
ProviderUsed = Literal["github"]


class ActionsBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class GitHubWorkflowRunSummary(ActionsBaseModel):
    run_id: int = Field(..., ge=1)
    workflow_id: int | None = Field(default=None, ge=1)
    repository: str = Field(..., min_length=1, max_length=WORKFLOW_RUN_REPOSITORY_MAX_CHARS)
    workflow_name: str | None = Field(default=None, max_length=WORKFLOW_RUN_NAME_MAX_CHARS)
    display_title: str | None = Field(default=None, max_length=WORKFLOW_RUN_TITLE_MAX_CHARS)
    run_number: int | None = Field(default=None, ge=1)
    event: str | None = Field(default=None, max_length=WORKFLOW_RUN_EVENT_MAX_CHARS)
    status: str | None = Field(default=None, max_length=WORKFLOW_RUN_STATUS_MAX_CHARS)
    conclusion: str | None = Field(default=None, max_length=WORKFLOW_RUN_STATUS_MAX_CHARS)
    branch: str | None = Field(default=None, max_length=WORKFLOW_RUN_BRANCH_MAX_CHARS)
    head_sha: str | None = Field(default=None, max_length=WORKFLOW_RUN_SHA_MAX_CHARS)
    actor_login: str | None = Field(default=None, max_length=WORKFLOW_RUN_ACTOR_MAX_CHARS)
    html_url: str | None = Field(default=None, max_length=WORKFLOW_RUN_URL_MAX_CHARS)
    created_at: str | None = Field(default=None, max_length=WORKFLOW_RUN_TIMESTAMP_MAX_CHARS)
    updated_at: str | None = Field(default=None, max_length=WORKFLOW_RUN_TIMESTAMP_MAX_CHARS)
    run_started_at: str | None = Field(default=None, max_length=WORKFLOW_RUN_TIMESTAMP_MAX_CHARS)


class WorkflowRunListRequest(ActionsBaseModel):
    actions_ref: str = Field(..., pattern=_ACTIONS_REF_PATTERN)
    repository: str = Field(..., pattern=_REPOSITORY_PATTERN, max_length=WORKFLOW_RUN_REPOSITORY_MAX_CHARS)
    limit: int = Field(default=WORKFLOW_RUN_LIST_DEFAULT_LIMIT, ge=1, le=WORKFLOW_RUN_LIST_MAX_LIMIT)
    page: int = Field(default=1, ge=1, le=WORKFLOW_RUN_PAGE_MAX)
    branch: str | None = Field(default=None, max_length=WORKFLOW_RUN_BRANCH_MAX_CHARS)
    status: str | None = Field(default=None, max_length=WORKFLOW_RUN_STATUS_MAX_CHARS)
    event: str | None = Field(default=None, max_length=WORKFLOW_RUN_EVENT_MAX_CHARS)
    exclude_pull_requests: bool = False
    reason: str | None = Field(default=None, max_length=WORKFLOW_RUN_REASON_MAX_CHARS)

    @field_validator("repository")
    @classmethod
    def _normalize_repository(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("repository must not be empty")
        return normalized

    @field_validator("branch")
    @classmethod
    def _normalize_branch(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("status", "event")
    @classmethod
    def _normalize_small_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None


class WorkflowRunListResponse(ActionsBaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["workflow_run.list"]
    receipt_id: str
    execution_id: str
    actions_ref: str
    repository: str
    workflow_runs: list[GitHubWorkflowRunSummary] = Field(default_factory=list)
    run_count_returned: int = Field(..., ge=0)
    total_count: int | None = Field(default=None, ge=0)
    has_more: bool
    next_page: int | None = Field(default=None, ge=1)


class WorkflowRunGetRequest(ActionsBaseModel):
    actions_ref: str = Field(..., pattern=_ACTIONS_REF_PATTERN)
    repository: str = Field(..., pattern=_REPOSITORY_PATTERN, max_length=WORKFLOW_RUN_REPOSITORY_MAX_CHARS)
    run_id: int = Field(..., ge=1)
    reason: str | None = Field(default=None, max_length=WORKFLOW_RUN_REASON_MAX_CHARS)

    @field_validator("repository")
    @classmethod
    def _normalize_repository(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("repository must not be empty")
        return normalized


class WorkflowRunGetResponse(ActionsBaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["workflow_run.get"]
    receipt_id: str
    execution_id: str
    actions_ref: str
    repository: str
    run_id: int = Field(..., ge=1)
    workflow_id: int | None = Field(default=None, ge=1)
    workflow_name: str | None = Field(default=None, max_length=WORKFLOW_RUN_NAME_MAX_CHARS)
    display_title: str | None = Field(default=None, max_length=WORKFLOW_RUN_TITLE_MAX_CHARS)
    run_number: int | None = Field(default=None, ge=1)
    run_attempt: int | None = Field(default=None, ge=1)
    event: str | None = Field(default=None, max_length=WORKFLOW_RUN_EVENT_MAX_CHARS)
    status: str | None = Field(default=None, max_length=WORKFLOW_RUN_STATUS_MAX_CHARS)
    conclusion: str | None = Field(default=None, max_length=WORKFLOW_RUN_STATUS_MAX_CHARS)
    branch: str | None = Field(default=None, max_length=WORKFLOW_RUN_BRANCH_MAX_CHARS)
    head_sha: str | None = Field(default=None, max_length=WORKFLOW_RUN_SHA_MAX_CHARS)
    actor_login: str | None = Field(default=None, max_length=WORKFLOW_RUN_ACTOR_MAX_CHARS)
    html_url: str | None = Field(default=None, max_length=WORKFLOW_RUN_URL_MAX_CHARS)
    created_at: str | None = Field(default=None, max_length=WORKFLOW_RUN_TIMESTAMP_MAX_CHARS)
    updated_at: str | None = Field(default=None, max_length=WORKFLOW_RUN_TIMESTAMP_MAX_CHARS)
    run_started_at: str | None = Field(default=None, max_length=WORKFLOW_RUN_TIMESTAMP_MAX_CHARS)


SUPPORTED_ACTIONS_CAPABILITY_IDS = frozenset({
    "workflow_run.list",
    "workflow_run.get",
})
