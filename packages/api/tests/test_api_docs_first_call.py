"""Contract checks for PP-9 first-call quickstart docs."""

from __future__ import annotations

from pathlib import Path


DOCS_API = Path(__file__).resolve().parents[3] / "docs" / "API.md"


def test_api_docs_include_pp9_first_call_verify_flow():
    text = DOCS_API.read_text(encoding="utf-8")

    assert "## Resolve v2 first-call proof: `search.query`" in text
    assert "search -> resolve -> estimate -> execute -> receipt -> verify" in text
    assert "-X GET" in text
    assert "\"$RHUMB_API_BASE/v2/capabilities?search=web%20research&limit=5\"" in text
    assert "\"$RHUMB_API_BASE/v2/capabilities/search.query/resolve?credential_mode=rhumb_managed\"" in text
    assert "\"$RHUMB_API_BASE/v2/capabilities/search.query/execute/estimate?provider=brave-search-api&credential_mode=rhumb_managed\"" in text
    assert "-X POST" in text
    assert "\"$RHUMB_API_BASE/v2/capabilities/search.query/execute\"" in text
    assert "\"$RHUMB_API_BASE/v2/receipts/$RECEIPT_ID/verify\"" in text
    assert "verifier_status" in text
    assert "missing_credentials" in text
    assert "invalid_rhumb_key" in text
    assert "payment_required" in text
    assert "scripts/resolve_v2_dogfood.py" in text
