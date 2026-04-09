"""Deployment capability request/response schemas for the AUD-18 Vercel read-first wedge."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DEPLOYMENT_REF_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"

DEPLOYMENT_LIST_DEFAULT_LIMIT = 10
DEPLOYMENT_LIST_MAX_LIMIT = 25
DEPLOYMENT_REASON_MAX_CHARS = 300
DEPLOYMENT_REF_MAX_CHARS = 64
DEPLOYMENT_ID_MAX_CHARS = 128
DEPLOYMENT_PROJECT_ID_MAX_CHARS = 128
DEPLOYMENT_TARGET_MAX_CHARS = 32
DEPLOYMENT_STATE_MAX_CHARS = 32
DEPLOYMENT_ERROR_MAX_CHARS = 500

CredentialMode = Literal["byok"]
ProviderUsed = Literal["vercel"]


class DeploymentBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class VercelDeploymentSummary(DeploymentBaseModel):
    deployment_id: str = Field(..., min_length=1, max_length=DEPLOYMENT_ID_MAX_CHARS)
    project_id: str = Field(..., min_length=1, max_length=DEPLOYMENT_PROJECT_ID_MAX_CHARS)
    project_name: str
    target: str | None = Field(default=None, max_length=DEPLOYMENT_TARGET_MAX_CHARS)
    state: str | None = Field(default=None, max_length=DEPLOYMENT_STATE_MAX_CHARS)
    url: str | None = None
    created_at: int | None = Field(default=None, ge=0)
    ready_at: int | None = Field(default=None, ge=0)
    creator_id: str | None = None
    creator_username: str | None = None
    aliases: list[str] = Field(default_factory=list)


class DeploymentListRequest(DeploymentBaseModel):
    deployment_ref: str = Field(..., pattern=_DEPLOYMENT_REF_PATTERN)
    limit: int = Field(default=DEPLOYMENT_LIST_DEFAULT_LIMIT, ge=1, le=DEPLOYMENT_LIST_MAX_LIMIT)
    project_id: str | None = Field(default=None, max_length=DEPLOYMENT_PROJECT_ID_MAX_CHARS)
    target: str | None = Field(default=None, max_length=DEPLOYMENT_TARGET_MAX_CHARS)
    state: str | None = Field(default=None, max_length=DEPLOYMENT_STATE_MAX_CHARS)
    created_after: int | None = Field(default=None, ge=0)
    created_before: int | None = Field(default=None, ge=0)
    page_after: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=DEPLOYMENT_REASON_MAX_CHARS)

    @field_validator("project_id")
    @classmethod
    def _normalize_project_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("target")
    @classmethod
    def _normalize_target(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @field_validator("state")
    @classmethod
    def _normalize_state(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None


class DeploymentListResponse(DeploymentBaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["deployment.list"]
    receipt_id: str
    execution_id: str
    deployment_ref: str
    deployments: list[VercelDeploymentSummary] = Field(default_factory=list)
    deployment_count_returned: int = Field(..., ge=0)
    has_more: bool
    next_page_after: int | None = None


class DeploymentGetRequest(DeploymentBaseModel):
    deployment_ref: str = Field(..., pattern=_DEPLOYMENT_REF_PATTERN)
    deployment_id: str = Field(..., min_length=1, max_length=DEPLOYMENT_ID_MAX_CHARS)
    reason: str | None = Field(default=None, max_length=DEPLOYMENT_REASON_MAX_CHARS)

    @field_validator("deployment_id")
    @classmethod
    def _normalize_deployment_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("deployment_id must not be empty")
        return normalized


class DeploymentGetResponse(DeploymentBaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["deployment.get"]
    receipt_id: str
    execution_id: str
    deployment_ref: str
    deployment_id: str
    project_id: str
    project_name: str
    target: str | None = Field(default=None, max_length=DEPLOYMENT_TARGET_MAX_CHARS)
    state: str | None = Field(default=None, max_length=DEPLOYMENT_STATE_MAX_CHARS)
    url: str | None = None
    created_at: int | None = Field(default=None, ge=0)
    ready_at: int | None = Field(default=None, ge=0)
    creator_id: str | None = None
    creator_username: str | None = None
    aliases: list[str] = Field(default_factory=list)
    error_code: str | None = Field(default=None, max_length=DEPLOYMENT_ERROR_MAX_CHARS)
    error_message: str | None = Field(default=None, max_length=DEPLOYMENT_ERROR_MAX_CHARS)


SUPPORTED_DEPLOYMENT_CAPABILITY_IDS = frozenset({
    "deployment.list",
    "deployment.get",
})
