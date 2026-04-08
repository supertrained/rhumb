"""Human-readable summaries for storage capability executions."""

from __future__ import annotations


def summarize_storage_execution(capability_id: str, payload: dict) -> str:
    storage_ref = payload.get("storage_ref") or "unknown storage_ref"
    bucket = payload.get("bucket") or "unknown-bucket"

    if capability_id == "object.list":
        prefix = payload.get("prefix") or ""
        object_count = payload.get("object_count_returned", 0)
        location = f"s3://{bucket}/{prefix}" if prefix else f"s3://{bucket}"
        return f"Listed {object_count} objects in {location} via storage_ref {storage_ref}"

    if capability_id == "object.head":
        key = payload.get("key") or "unknown-key"
        size = payload.get("size")
        size_text = f" ({size} bytes)" if isinstance(size, int) else ""
        return f"Fetched metadata for s3://{bucket}/{key}{size_text} via storage_ref {storage_ref}"

    if capability_id == "object.get":
        key = payload.get("key") or "unknown-key"
        size = payload.get("bytes_returned")
        size_text = f"{size} bytes" if isinstance(size, int) else "object bytes"
        return f"Fetched {size_text} from s3://{bucket}/{key} via storage_ref {storage_ref}"

    return f"Completed {capability_id} via storage_ref {storage_ref}"
