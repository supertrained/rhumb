"""Tests for schema fingerprinting engine (Round 13 Module 1)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.schema_fingerprint import (  # noqa: E402
    compare_schema_structures,
    detect_likely_renames,
    field_name_similarity,
    fingerprint_response,
)


class TestSchemaFingerprint:
    """Schema fingerprint engine behavior."""

    def test_fingerprint_stable_response_consistent_hash(self) -> None:
        payload = {"id": "cus_123", "email": "a@example.com", "active": True}
        fp1 = fingerprint_response(payload)
        fp2 = fingerprint_response(payload)
        assert fp1.fingerprint_hash == fp2.fingerprint_hash

    def test_add_field_detected_as_change(self) -> None:
        base = fingerprint_response({"id": "cus_123"})
        changed = fingerprint_response({"id": "cus_123", "email": "a@example.com"})
        diff = compare_schema_structures(base.schema_tree, changed.schema_tree)
        assert "email" in diff.added_fields

    def test_remove_field_detected_as_change(self) -> None:
        base = fingerprint_response({"id": "cus_123", "email": "a@example.com"})
        changed = fingerprint_response({"id": "cus_123"})
        diff = compare_schema_structures(base.schema_tree, changed.schema_tree)
        assert "email" in diff.removed_fields

    def test_type_change_detected(self) -> None:
        base = fingerprint_response({"amount": "1000"})
        changed = fingerprint_response({"amount": 1000})
        diff = compare_schema_structures(base.schema_tree, changed.schema_tree)
        assert any(path == "amount" for path, _, _ in diff.type_changes)

    def test_nested_object_structure_change_detected(self) -> None:
        base = fingerprint_response({"customer": {"name": "A"}})
        changed = fingerprint_response({"customer": [{"name": "A"}]})
        diff = compare_schema_structures(base.schema_tree, changed.schema_tree)
        assert any(path == "customer" for path, _, _ in diff.nesting_changes)

    def test_order_insensitive_hash(self) -> None:
        left = fingerprint_response({"a": 1, "b": 2, "c": 3})
        right = fingerprint_response({"c": 3, "a": 1, "b": 2})
        assert left.fingerprint_hash == right.fingerprint_hash

    def test_semantic_rename_similarity_flags(self) -> None:
        similarity = field_name_similarity("old_field", "new_field")
        hints = detect_likely_renames(("old_field",), ("new_field",), threshold=0.8)
        assert similarity > 0.8
        assert hints and hints[0].similarity > 0.8

    def test_null_optional_fields_tracked_as_type_delta(self) -> None:
        base = fingerprint_response({"nickname": None})
        changed = fingerprint_response({"nickname": "pedro"})
        diff = compare_schema_structures(base.schema_tree, changed.schema_tree)
        assert any(path == "nickname" for path, _, _ in diff.type_changes)

    def test_array_single_object_change_detected(self) -> None:
        base = fingerprint_response({"items": [{"id": "1"}]})
        changed = fingerprint_response({"items": {"id": "1"}})
        diff = compare_schema_structures(base.schema_tree, changed.schema_tree)
        assert any(path == "items" for path, _, _ in diff.cardinality_changes)

    def test_complex_nested_structure_fingerprinted(self) -> None:
        payload = {
            "data": {
                "items": [
                    {
                        "id": "evt_1",
                        "attributes": {
                            "owner": {"id": "u_1", "name": "Tom"},
                            "flags": [True, False],
                        },
                    }
                ]
            }
        }
        fp = fingerprint_response(payload)
        assert fp.max_depth >= 4
        assert "data.items[].attributes.owner.id" in fp.field_paths
