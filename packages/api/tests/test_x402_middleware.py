from __future__ import annotations

import base64
import json

from services.x402_middleware import decode_x_payment_header, inspect_x_payment_header


def test_inspect_x_payment_header_raw_json_legacy_payload():
    payload = {
        "tx_hash": "0xabc",
        "network": "base-sepolia",
        "wallet_address": "0x123",
    }

    result = inspect_x_payment_header(json.dumps(payload))

    assert result["parse_mode"] == "raw_json"
    assert result["payment_data"] == payload
    assert result["top_level_keys"] == ["network", "tx_hash", "wallet_address"]


def test_inspect_x_payment_header_base64_json_legacy_payload():
    payload = {
        "tx_hash": "0xabc",
        "network": "base-sepolia",
        "wallet_address": "0x123",
    }
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()

    result = inspect_x_payment_header(encoded)

    assert result["parse_mode"] == "base64_json"
    assert result["payment_data"] == payload


def test_inspect_x_payment_header_standard_x402_payload():
    payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base-sepolia",
        "payload": {
            "authorization": {
                "from": "0x123",
                "to": "0x456",
                "value": "100000",
                "validAfter": "1",
                "validBefore": "2",
                "nonce": "0x789",
            },
            "signature": "0xsig",
        },
    }

    result = inspect_x_payment_header(json.dumps(payload))

    assert result["parse_mode"] == "x402_payload"
    assert result["payment_data"] == payload
    assert result["proof_format"] == "standard_authorization_payload"
    assert result["declared_network"] == "base-sepolia"
    assert result["declared_scheme"] == "exact"
    assert result["declared_from"] == "0x123"
    assert result["declared_to"] == "0x456"
    assert result["top_level_keys"] == ["network", "payload", "scheme", "x402Version"]
    assert decode_x_payment_header(json.dumps(payload)) == payload


def test_inspect_x_payment_header_standard_x402_payload_base64_awal_shape():
    payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base",
        "payload": {
            "authorization": {
                "from": "0x123",
                "to": "0x456",
                "value": "100000",
                "validAfter": "1",
                "validBefore": "2",
                "nonce": "0x789",
            },
            "signature": "0xsig",
        },
    }
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()

    result = inspect_x_payment_header(encoded)

    assert result["parse_mode"] == "x402_payload"
    assert result["payment_data"] == payload
    assert result["proof_format"] == "standard_authorization_payload"
    assert result["declared_network"] == "base"
    assert result["declared_from"] == "0x123"
    assert result["declared_to"] == "0x456"


def test_inspect_x_payment_header_invalid_payload():
    result = inspect_x_payment_header("not-json-or-base64")

    assert result["parse_mode"] == "invalid"
    assert result["payment_data"] is None
    assert result["top_level_keys"] == []
