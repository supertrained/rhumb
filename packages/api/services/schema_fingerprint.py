"""Schema fingerprinting utilities for proxy response payloads."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SchemaMetadata:
    """Metadata captured alongside a schema fingerprint."""

    status_code: int
    latency_ms: float
    content_type: str | None
    cache_control: str | None


@dataclass(frozen=True, slots=True)
class RenameHint:
    """Potential rename mapping between removed and added fields."""

    old_field: str
    new_field: str
    similarity: float


@dataclass(frozen=True, slots=True)
class SchemaDiff:
    """Structural diff between two normalized schema trees."""

    added_fields: tuple[str, ...]
    removed_fields: tuple[str, ...]
    type_changes: tuple[tuple[str, str, str], ...]
    nesting_changes: tuple[tuple[str, str, str], ...]
    cardinality_changes: tuple[tuple[str, str, str], ...]
    likely_renames: tuple[RenameHint, ...]


@dataclass(frozen=True, slots=True)
class SchemaFingerprint:
    """Content-agnostic schema fingerprint for a response payload."""

    schema_tree: dict[str, Any]
    fingerprint_hash: str
    field_paths: tuple[str, ...]
    max_depth: int
    metadata: SchemaMetadata


def fingerprint_response(
    payload: Any,
    *,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
    latency_ms: float = 0.0,
) -> SchemaFingerprint:
    """Create a stable fingerprint for a response payload.

    The hash ignores scalar values and captures only structure and types.
    """
    schema_tree = _normalize_schema(payload)
    canonical = _canonical_json(schema_tree)
    fingerprint_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    field_paths = tuple(sorted(_collect_field_paths(schema_tree)))

    content_type: str | None = None
    cache_control: str | None = None
    if headers:
        lowered = {str(k).lower(): str(v) for k, v in headers.items()}
        content_type = lowered.get("content-type")
        cache_control = lowered.get("cache-control")

    return SchemaFingerprint(
        schema_tree=schema_tree,
        fingerprint_hash=fingerprint_hash,
        field_paths=field_paths,
        max_depth=_compute_max_depth(schema_tree),
        metadata=SchemaMetadata(
            status_code=int(status_code),
            latency_ms=float(latency_ms),
            content_type=content_type,
            cache_control=cache_control,
        ),
    )


def compare_schema_structures(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> SchemaDiff:
    """Compute deep structural differences between two schema trees."""
    added: set[str] = set()
    removed: set[str] = set()
    type_changes: list[tuple[str, str, str]] = []
    nesting_changes: list[tuple[str, str, str]] = []
    cardinality_changes: list[tuple[str, str, str]] = []

    def visit(old_node: dict[str, Any], new_node: dict[str, Any], path: str) -> None:
        old_type = str(old_node.get("type", "unknown"))
        new_type = str(new_node.get("type", "unknown"))

        if old_type != new_type:
            if "array" in (old_type, new_type):
                cardinality_changes.append((path, old_type, new_type))
                if "object" in (old_type, new_type):
                    nesting_changes.append((path, old_type, new_type))
                return
            if {old_type, new_type} == {"object", "union"}:
                nesting_changes.append((path, old_type, new_type))
                return
            type_changes.append((path, old_type, new_type))
            return

        if old_type == "object":
            old_fields = old_node.get("fields", {})
            new_fields = new_node.get("fields", {})
            if not isinstance(old_fields, dict) or not isinstance(new_fields, dict):
                return

            old_keys = set(old_fields.keys())
            new_keys = set(new_fields.keys())
            for name in sorted(new_keys - old_keys):
                added.add(f"{path}.{name}" if path != "$" else name)
            for name in sorted(old_keys - new_keys):
                removed.add(f"{path}.{name}" if path != "$" else name)

            for name in sorted(old_keys & new_keys):
                child_path = f"{path}.{name}" if path != "$" else name
                old_child = old_fields.get(name)
                new_child = new_fields.get(name)
                if isinstance(old_child, dict) and isinstance(new_child, dict):
                    visit(old_child, new_child, child_path)
            return

        if old_type == "array":
            old_items = old_node.get("items")
            new_items = new_node.get("items")
            if isinstance(old_items, dict) and isinstance(new_items, dict):
                visit(old_items, new_items, f"{path}[]")

    visit(baseline, candidate, "$")
    renames = detect_likely_renames(tuple(sorted(removed)), tuple(sorted(added)))

    return SchemaDiff(
        added_fields=tuple(sorted(added)),
        removed_fields=tuple(sorted(removed)),
        type_changes=tuple(sorted(type_changes)),
        nesting_changes=tuple(sorted(nesting_changes)),
        cardinality_changes=tuple(sorted(cardinality_changes)),
        likely_renames=tuple(renames),
    )


def detect_likely_renames(
    removed_fields: tuple[str, ...],
    added_fields: tuple[str, ...],
    *,
    threshold: float = 0.8,
) -> list[RenameHint]:
    """Find likely field renames based on normalized name similarity."""
    hints: list[RenameHint] = []

    for old_path in removed_fields:
        old_name = _leaf_name(old_path)
        best_score = 0.0
        best_new: str | None = None

        for new_path in added_fields:
            new_name = _leaf_name(new_path)
            score = field_name_similarity(old_name, new_name)
            if score > best_score:
                best_score = score
                best_new = new_path

        if best_new is not None and best_score >= threshold:
            hints.append(
                RenameHint(
                    old_field=old_path,
                    new_field=best_new,
                    similarity=round(best_score, 4),
                )
            )

    return hints


def field_name_similarity(old_name: str, new_name: str) -> float:
    """Compute similarity between field names using normalized edit distance."""
    old_norm = _normalize_name(old_name)
    new_norm = _normalize_name(new_name)
    if not old_norm or not new_norm:
        return 0.0
    if old_norm == new_norm:
        return 1.0

    score = SequenceMatcher(None, old_norm, new_norm).ratio()

    old_tokens = _name_tokens(old_name)
    new_tokens = _name_tokens(new_name)
    if old_tokens and new_tokens and old_tokens[-1] == new_tokens[-1]:
        score = max(score, 0.85)

    return score


def _normalize_schema(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        fields = {key: _normalize_schema(val) for key, val in sorted(value.items())}
        return {
            "type": "object",
            "fields": fields,
        }

    if isinstance(value, list):
        if not value:
            return {"type": "array", "items": {"type": "unknown"}}

        item_schemas = [_normalize_schema(item) for item in value]
        merged = _merge_schema_nodes(item_schemas)
        return {"type": "array", "items": merged}

    if value is None:
        return {"type": "null"}

    if isinstance(value, bool):
        return {"type": "boolean"}

    if isinstance(value, int):
        return {"type": "integer"}

    if isinstance(value, float):
        return {"type": "number"}

    if isinstance(value, str):
        return {"type": "string"}

    return {"type": "unknown"}


def _merge_schema_nodes(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    if not nodes:
        return {"type": "unknown"}

    first = nodes[0]
    if all(node == first for node in nodes[1:]):
        return first

    node_types = {str(node.get("type", "unknown")) for node in nodes}
    if len(node_types) == 1 and "object" in node_types:
        all_keys: set[str] = set()
        for node in nodes:
            fields = node.get("fields", {})
            if isinstance(fields, dict):
                all_keys.update(fields.keys())

        merged_fields: dict[str, dict[str, Any]] = {}
        for key in sorted(all_keys):
            children = []
            for node in nodes:
                fields = node.get("fields", {})
                if isinstance(fields, dict) and key in fields:
                    child = fields.get(key)
                    if isinstance(child, dict):
                        children.append(child)
                else:
                    children.append({"type": "null"})
            merged_fields[key] = _merge_schema_nodes(children)
        return {"type": "object", "fields": merged_fields}

    unique_options = sorted({_canonical_json(node) for node in nodes})
    return {
        "type": "union",
        "options": [json.loads(option) for option in unique_options],
    }


def _collect_field_paths(node: dict[str, Any], path: str = "$") -> set[str]:
    fields: set[str] = set()
    node_type = str(node.get("type", "unknown"))

    if node_type == "object":
        node_fields = node.get("fields", {})
        if isinstance(node_fields, dict):
            for key, child in node_fields.items():
                child_path = f"{path}.{key}" if path != "$" else key
                fields.add(child_path)
                if isinstance(child, dict):
                    fields.update(_collect_field_paths(child, child_path))
    elif node_type == "array":
        items = node.get("items")
        if isinstance(items, dict):
            fields.update(_collect_field_paths(items, f"{path}[]"))

    return fields


def _compute_max_depth(node: dict[str, Any], depth: int = 1) -> int:
    node_type = str(node.get("type", "unknown"))
    if node_type == "object":
        node_fields = node.get("fields", {})
        if not isinstance(node_fields, dict) or not node_fields:
            return depth
        return max(_compute_max_depth(child, depth + 1) for child in node_fields.values())
    if node_type == "array":
        items = node.get("items")
        if isinstance(items, dict):
            return _compute_max_depth(items, depth + 1)
    if node_type == "union":
        options = node.get("options", [])
        if isinstance(options, list) and options:
            depths = [
                _compute_max_depth(option, depth + 1)
                for option in options
                if isinstance(option, dict)
            ]
            if depths:
                return max(depths)
    return depth


def _canonical_json(node: dict[str, Any]) -> str:
    return json.dumps(node, sort_keys=True, separators=(",", ":"))


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _name_tokens(name: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", name.lower()) if token]


def _leaf_name(path: str) -> str:
    leaf = path.split(".")[-1]
    return leaf.replace("[]", "")
