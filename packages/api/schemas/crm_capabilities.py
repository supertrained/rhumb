"""HubSpot CRM capability request/response schemas for the AUD-18 read-first wedge."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CRM_REF_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
_OBJECT_TYPE_PATTERN = r"^[A-Za-z0-9_.:-]{1,128}$"
_PROPERTY_PATTERN = r"^[A-Za-z0-9_.-]{1,128}$"
_RECORD_ID_PATTERN = r"^[A-Za-z0-9_.:-]{1,128}$"

CRM_DEFAULT_LIMIT = 10
CRM_MAX_LIMIT = 25
CRM_MAX_PROPERTY_NAMES = 50
CRM_MAX_FILTERS = 5
CRM_MAX_SORTS = 2
CRM_QUERY_MAX_CHARS = 200
CRM_REASON_MAX_CHARS = 300
CRM_TEXT_MAX_CHARS = 1000
CRM_OBJECT_TYPE_MAX_CHARS = 128
CRM_PROPERTY_NAME_MAX_CHARS = 128
CRM_RECORD_ID_MAX_CHARS = 128
CRM_AFTER_MAX_CHARS = 2048
CRM_DESCRIBE_PROPERTY_MAX = 100

SUPPORTED_FILTER_OPERATORS = frozenset({
    "EQ",
    "NEQ",
    "LT",
    "LTE",
    "GT",
    "GTE",
    "CONTAINS_TOKEN",
    "HAS_PROPERTY",
    "NOT_HAS_PROPERTY",
})

CredentialMode = Literal["byok"]
ProviderUsed = Literal["hubspot"]
ScalarValue = str | int | float | bool | None


class CrmBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CrmObjectDescribeRequest(CrmBaseModel):
    crm_ref: str = Field(..., pattern=_CRM_REF_PATTERN)
    object_type: str = Field(..., pattern=_OBJECT_TYPE_PATTERN, max_length=CRM_OBJECT_TYPE_MAX_CHARS)
    reason: str | None = Field(default=None, max_length=CRM_REASON_MAX_CHARS)

    @field_validator("object_type")
    @classmethod
    def _normalize_object_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("object_type must not be empty")
        return normalized


class HubSpotCrmPropertyDescriptor(CrmBaseModel):
    name: str = Field(..., min_length=1, max_length=CRM_PROPERTY_NAME_MAX_CHARS)
    label: str | None = Field(default=None, max_length=CRM_TEXT_MAX_CHARS)
    type: str | None = Field(default=None, max_length=CRM_TEXT_MAX_CHARS)
    field_type: str | None = Field(default=None, max_length=CRM_TEXT_MAX_CHARS)
    searchable: bool = False
    sortable: bool = False
    read_only: bool = False
    archived: bool = False


class CrmObjectDescribeResponse(CrmBaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["crm.object.describe"]
    receipt_id: str
    execution_id: str
    crm_ref: str
    object_type: str
    portal_id: str | None = Field(default=None, max_length=CRM_TEXT_MAX_CHARS)
    label: str | None = Field(default=None, max_length=CRM_TEXT_MAX_CHARS)
    plural_label: str | None = Field(default=None, max_length=CRM_TEXT_MAX_CHARS)
    primary_display_property: str | None = Field(default=None, max_length=CRM_PROPERTY_NAME_MAX_CHARS)
    required_properties: list[str] = Field(default_factory=list)
    properties: list[HubSpotCrmPropertyDescriptor] = Field(default_factory=list)
    property_count_returned: int = Field(..., ge=0, le=CRM_DESCRIBE_PROPERTY_MAX)


class CrmRecordSearchFilter(CrmBaseModel):
    property: str = Field(..., pattern=_PROPERTY_PATTERN, max_length=CRM_PROPERTY_NAME_MAX_CHARS)
    operator: str = Field(..., min_length=1, max_length=32)
    value: ScalarValue = None

    @field_validator("property")
    @classmethod
    def _normalize_property(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("property must not be empty")
        return normalized

    @field_validator("operator")
    @classmethod
    def _normalize_operator(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in SUPPORTED_FILTER_OPERATORS:
            allowed = ", ".join(sorted(SUPPORTED_FILTER_OPERATORS))
            raise ValueError(f"operator must be one of: {allowed}")
        return normalized

    @model_validator(mode="after")
    def _validate_value_shape(self) -> "CrmRecordSearchFilter":
        if self.operator in {"HAS_PROPERTY", "NOT_HAS_PROPERTY"}:
            if self.value is not None:
                raise ValueError(f"{self.operator} filters do not accept value")
            return self
        if self.value is None:
            raise ValueError(f"{self.operator} filters require value")
        return self


class CrmRecordSort(CrmBaseModel):
    property: str = Field(..., pattern=_PROPERTY_PATTERN, max_length=CRM_PROPERTY_NAME_MAX_CHARS)
    direction: Literal["asc", "desc"] = "asc"

    @field_validator("property")
    @classmethod
    def _normalize_property(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("property must not be empty")
        return normalized


class CrmRecordSearchRequest(CrmBaseModel):
    crm_ref: str = Field(..., pattern=_CRM_REF_PATTERN)
    object_type: str = Field(..., pattern=_OBJECT_TYPE_PATTERN, max_length=CRM_OBJECT_TYPE_MAX_CHARS)
    limit: int = Field(default=CRM_DEFAULT_LIMIT, ge=1, le=CRM_MAX_LIMIT)
    after: str | None = Field(default=None, max_length=CRM_AFTER_MAX_CHARS)
    query: str | None = Field(default=None, max_length=CRM_QUERY_MAX_CHARS)
    property_names: list[str] | None = Field(default=None, min_length=1, max_length=CRM_MAX_PROPERTY_NAMES)
    filters: list[CrmRecordSearchFilter] = Field(default_factory=list, max_length=CRM_MAX_FILTERS)
    sorts: list[CrmRecordSort] = Field(default_factory=list, max_length=CRM_MAX_SORTS)
    reason: str | None = Field(default=None, max_length=CRM_REASON_MAX_CHARS)

    @field_validator("object_type")
    @classmethod
    def _normalize_object_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("object_type must not be empty")
        return normalized

    @field_validator("after")
    @classmethod
    def _normalize_after(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("property_names")
    @classmethod
    def _normalize_property_names(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_property_list(value)


class HubSpotCrmRecordSummary(CrmBaseModel):
    record_id: str = Field(..., min_length=1, max_length=CRM_RECORD_ID_MAX_CHARS)
    archived: bool = False
    created_at: str | None = Field(default=None, max_length=CRM_TEXT_MAX_CHARS)
    updated_at: str | None = Field(default=None, max_length=CRM_TEXT_MAX_CHARS)
    properties: dict[str, ScalarValue] = Field(default_factory=dict)


class CrmRecordSearchResponse(CrmBaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["crm.record.search"]
    receipt_id: str
    execution_id: str
    crm_ref: str
    object_type: str
    records: list[HubSpotCrmRecordSummary] = Field(default_factory=list)
    record_count_returned: int = Field(..., ge=0, le=CRM_MAX_LIMIT)
    next_after: str | None = None


class CrmRecordGetRequest(CrmBaseModel):
    crm_ref: str = Field(..., pattern=_CRM_REF_PATTERN)
    object_type: str = Field(..., pattern=_OBJECT_TYPE_PATTERN, max_length=CRM_OBJECT_TYPE_MAX_CHARS)
    record_id: str = Field(..., pattern=_RECORD_ID_PATTERN, max_length=CRM_RECORD_ID_MAX_CHARS)
    property_names: list[str] | None = Field(default=None, min_length=1, max_length=CRM_MAX_PROPERTY_NAMES)
    reason: str | None = Field(default=None, max_length=CRM_REASON_MAX_CHARS)

    @field_validator("object_type")
    @classmethod
    def _normalize_object_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("object_type must not be empty")
        return normalized

    @field_validator("record_id")
    @classmethod
    def _normalize_record_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("record_id must not be empty")
        return normalized

    @field_validator("property_names")
    @classmethod
    def _normalize_property_names(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_property_list(value)


class CrmRecordGetResponse(CrmBaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["crm.record.get"]
    receipt_id: str
    execution_id: str
    crm_ref: str
    object_type: str
    record_id: str
    archived: bool = False
    created_at: str | None = Field(default=None, max_length=CRM_TEXT_MAX_CHARS)
    updated_at: str | None = Field(default=None, max_length=CRM_TEXT_MAX_CHARS)
    properties: dict[str, ScalarValue] = Field(default_factory=dict)


SUPPORTED_CRM_CAPABILITY_IDS = frozenset({
    "crm.object.describe",
    "crm.record.search",
    "crm.record.get",
})


def _normalize_property_list(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        candidate = item.strip().lower()
        if not candidate:
            raise ValueError("property_names entries must not be empty")
        if len(candidate) > CRM_PROPERTY_NAME_MAX_CHARS:
            raise ValueError("property name too long")
        if candidate not in seen:
            seen.add(candidate)
            normalized.append(candidate)
    return normalized
