"""Human-readable summaries for HubSpot CRM capability executions."""

from __future__ import annotations


def summarize_crm_execution(capability_id: str, payload: dict) -> str:
    crm_ref = payload.get("crm_ref") or "unknown crm_ref"
    object_type = payload.get("object_type") or "object"
    singular_object = _singularize(object_type)

    if capability_id == "crm.object.describe":
        return f"Described HubSpot {object_type} schema via crm_ref {crm_ref}"

    if capability_id == "crm.record.search":
        count = int(payload.get("record_count_returned") or 0)
        noun = singular_object if count == 1 else object_type
        return f"Found {count} HubSpot {noun} via crm_ref {crm_ref}"

    if capability_id == "crm.record.get":
        record_id = payload.get("record_id") or "unknown record"
        return f"Fetched HubSpot {singular_object} {record_id} via crm_ref {crm_ref}"

    return f"Completed {capability_id} for HubSpot {object_type} via crm_ref {crm_ref}"


def _singularize(value: str) -> str:
    if value.endswith("ies") and len(value) > 3:
        return value[:-3] + "y"
    if value.endswith("s") and len(value) > 1:
        return value[:-1]
    return value
