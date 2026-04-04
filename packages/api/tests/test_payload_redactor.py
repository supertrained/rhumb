"""Tests for AUD-24: payload redaction for audit/billing exports.

Verifies that sensitive data is redacted before export while
preserving structure and non-sensitive data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from services.payload_redactor import (
    REDACTED,
    TRUNCATED,
    UNSERIALIZABLE,
    redact_event_detail,
    redact_event_metadata,
    redact_headers,
    redact_payload,
    sanitize_external_payload,
)


class TestKeyBasedRedaction:
    """Sensitive keys are always redacted regardless of value."""

    def test_api_key_redacted(self):
        result = redact_payload({"api_key": "sk-live-12345"})
        assert result["api_key"] == REDACTED

    def test_token_redacted(self):
        result = redact_payload({"token": "abc123"})
        assert result["token"] == REDACTED

    def test_authorization_redacted(self):
        result = redact_payload({"authorization": "Bearer xyz"})
        assert result["authorization"] == REDACTED

    def test_password_redacted(self):
        result = redact_payload({"password": "hunter2"})
        assert result["password"] == REDACTED

    def test_credential_redacted(self):
        result = redact_payload({"credential": "secret-value"})
        assert result["credential"] == REDACTED

    def test_private_key_redacted(self):
        result = redact_payload({"private_key": "-----BEGIN RSA PRIVATE KEY-----"})
        assert result["private_key"] == REDACTED

    def test_rhumb_key_header_redacted(self):
        result = redact_payload({"x-rhumb-key": "rhumb_abc123"})
        assert result["x-rhumb-key"] == REDACTED

    def test_case_insensitive(self):
        result = redact_payload({"API_KEY": "val", "Token": "val", "SECRET": "val"})
        assert result["API_KEY"] == REDACTED
        assert result["Token"] == REDACTED
        assert result["SECRET"] == REDACTED

    def test_hyphen_underscore_normalized(self):
        result = redact_payload({"api-key": "val", "client_secret": "val"})
        assert result["api-key"] == REDACTED
        assert result["client_secret"] == REDACTED


class TestValuePatternRedaction:
    """Values matching secret patterns are redacted in strict mode."""

    def test_bearer_token_value(self):
        result = redact_payload({"header": "Bearer eyJhbGciOiJIUzI1NiJ9.test"})
        assert result["header"] == REDACTED

    def test_rhumb_api_key_value(self):
        result = redact_payload({"key": "rhumb_5c5ec7bb37a225028d826ee00ef5c289e167c54176c96c1bdbb065f025538835"})
        assert result["key"] == REDACTED

    def test_stripe_key_value(self):
        result = redact_payload({"key": "sk-live-abcdef123456"})
        assert result["key"] == REDACTED

    def test_slack_token_value(self):
        result = redact_payload({"bot": "xoxb-FAKE000000000-FAKE000000000-FAKETOKEN00000000000000"})
        assert result["bot"] == REDACTED

    def test_github_pat_value(self):
        result = redact_payload({"pat": "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890"})
        assert result["pat"] == REDACTED

    def test_jwt_value(self):
        result = redact_payload({"session": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"})
        assert result["session"] == REDACTED

    def test_tavily_key_value(self):
        result = redact_payload({"provider_token": "tvly-aBcDeFgHiJkLmNoPqRsT"}, strict=True)
        assert result["provider_token"] == REDACTED

    def test_exa_key_value(self):
        result = redact_payload({"provider_token": "exa_AbCdEfGh12345678"}, strict=True)
        assert result["provider_token"] == REDACTED

    def test_unstructured_key_value(self):
        result = redact_payload({"provider_token": "UNST-aBcDeFg"}, strict=True)
        assert result["provider_token"] == REDACTED

    def test_brave_key_value(self):
        result = redact_payload({"provider_token": "BSAabcdefghijklmnop1234567890"}, strict=True)
        assert result["provider_token"] == REDACTED

    def test_generic_provider_style_secret_value(self):
        result = redact_payload({"provider_token": "abcde-1234567890abcdefghijklmn"}, strict=True)
        assert result["provider_token"] == REDACTED

    def test_safe_providerish_short_value_not_redacted(self):
        result = redact_payload({"label": "exa-search"}, strict=True)
        assert result["label"] == "exa-search"

    def test_non_strict_skips_value_patterns(self):
        """In non-strict mode, only key-based redaction applies."""
        result = redact_payload(
            {"header": "Bearer eyJhbGci.test"},
            strict=False,
        )
        assert result["header"] != REDACTED  # Value pattern not checked


class TestStructurePreservation:
    """Redaction preserves structure and non-sensitive data."""

    def test_non_sensitive_preserved(self):
        data = {"name": "John", "age": 30, "active": True}
        result = redact_payload(data)
        assert result == data

    def test_nested_redaction(self):
        data = {
            "config": {
                "url": "https://api.stripe.com",
                "api_key": "sk-live-123",
                "timeout": 30,
            }
        }
        result = redact_payload(data)
        assert result["config"]["url"] == "https://api.stripe.com"
        assert result["config"]["api_key"] == REDACTED
        assert result["config"]["timeout"] == 30

    def test_list_redaction(self):
        data = {"tokens": ["xoxb-abc123", "safe-value"]}
        result = redact_payload(data)
        assert result["tokens"][0] == REDACTED
        assert result["tokens"][1] == "safe-value"

    def test_deep_nesting_redacted(self):
        """Structures deeper than max_depth get fully redacted."""
        data = {"a": "safe"}
        for _ in range(25):
            data = {"nested": data}
        result = redact_payload(data)
        # Should have redacted somewhere deep
        current = result
        found_redacted = False
        for _ in range(25):
            if isinstance(current, str):
                if current == REDACTED:
                    found_redacted = True
                break
            current = current.get("nested", current)
        assert found_redacted

    def test_mixed_sensitive_non_sensitive(self):
        data = {
            "provider": "stripe",
            "capability": "payment.charge",
            "api_key": "sk-live-abc",
            "amount": 1000,
            "headers": {
                "authorization": "Bearer xyz",
                "content-type": "application/json",
            },
        }
        result = redact_payload(data)
        assert result["provider"] == "stripe"
        assert result["capability"] == "payment.charge"
        assert result["api_key"] == REDACTED
        assert result["amount"] == 1000
        assert result["headers"]["authorization"] == REDACTED
        assert result["headers"]["content-type"] == "application/json"


class TestHeaderRedaction:
    def test_auth_header_redacted(self):
        headers = {"Authorization": "Bearer abc", "Content-Type": "application/json"}
        result = redact_headers(headers)
        assert result["Authorization"] == REDACTED
        assert result["Content-Type"] == "application/json"

    def test_rhumb_headers_redacted(self):
        headers = {"X-Rhumb-Key": "rhumb_abc", "X-Rhumb-Receipt-Id": "rcpt_123"}
        result = redact_headers(headers)
        assert result["X-Rhumb-Key"] == REDACTED
        assert result["X-Rhumb-Receipt-Id"] == REDACTED

    def test_value_pattern_header_redacted(self):
        headers = {"X-Provider-Credential": "tvly-aBcDeFgHiJkLmNoPqRsT"}
        result = redact_headers(headers)
        assert result["X-Provider-Credential"] == REDACTED

    def test_none_headers(self):
        assert redact_headers(None) is None


class TestExternalPayloadSanitization:
    def test_secret_values_and_unserializable_objects_are_sanitized(self):
        class Weird:
            pass

        payload = {
            "token": "abc123",
            "bearer": "Bearer super-secret-token",
            "nested": {"password": "hunter2"},
            "obj": Weird(),
        }

        result = sanitize_external_payload(payload)
        assert result["token"] == REDACTED
        assert result["bearer"] == REDACTED
        assert result["nested"]["password"] == REDACTED
        assert result["obj"] == f"{UNSERIALIZABLE}:Weird"

    def test_strings_and_collections_are_bounded(self):
        result = sanitize_external_payload(
            {
                "text": ("abc-" * 80),
                "items": list(range(60)),
            },
            max_items=3,
            max_string_length=10,
        )
        assert result["text"] == f"{'abc-' * 2}ab…{TRUNCATED}"
        assert result["items"] == [0, 1, 2, TRUNCATED]
        assert "__truncated_items__" not in result

    def test_dates_paths_and_uuids_are_json_safe(self):
        value = UUID("12345678-1234-5678-1234-567812345678")
        result = sanitize_external_payload(
            {
                "ts": datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                "path": Path("/tmp/demo"),
                "id": value,
            }
        )
        assert result["ts"] == "2026-04-03T12:00:00+00:00"
        assert result["path"] == "/tmp/demo"
        assert result["id"] == str(value)


class TestEventHelpers:
    def test_redact_event_detail(self):
        detail = {"action": "execute", "api_key": "secret", "latency_ms": 150}
        result = redact_event_detail(detail)
        assert result["action"] == "execute"
        assert result["api_key"] == REDACTED
        assert result["latency_ms"] == 150

    def test_redact_event_metadata(self):
        metadata = {"request_id": "req_1", "token": "abc"}
        result = redact_event_metadata(metadata)
        assert result["request_id"] == "req_1"
        assert result["token"] == REDACTED

    def test_none_detail(self):
        assert redact_event_detail(None) == {}

    def test_none_metadata(self):
        assert redact_event_metadata(None) == {}
