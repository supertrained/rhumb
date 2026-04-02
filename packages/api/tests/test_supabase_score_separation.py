"""Focused AUD-8 coverage for score-truth credential separation."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

import routes._supabase as supabase_module
from routes._supabase import SupabaseWriteUnavailable
from services.score_cache import fetch_scores_from_db


@pytest.mark.asyncio
async def test_supabase_fetch_uses_score_reader_key_for_scores(monkeypatch):
    monkeypatch.setattr(supabase_module.settings, "supabase_service_role_key", "service-role", raising=False)
    monkeypatch.setattr(supabase_module.settings, "supabase_score_reader_key", "score-reader", raising=False)

    with patch("routes._supabase._request", new=AsyncMock(return_value=[])) as mock_request:
        result = await supabase_module.supabase_fetch("scores?select=service_slug")

    assert result == []
    assert mock_request.await_args.kwargs["headers"]["apikey"] == "score-reader"
    assert mock_request.await_args.kwargs["headers"]["Authorization"] == "Bearer score-reader"


@pytest.mark.asyncio
async def test_supabase_fetch_keeps_service_role_for_non_score_tables(monkeypatch):
    monkeypatch.setattr(supabase_module.settings, "supabase_service_role_key", "service-role", raising=False)
    monkeypatch.setattr(supabase_module.settings, "supabase_score_reader_key", "score-reader", raising=False)

    with patch("routes._supabase._request", new=AsyncMock(return_value=[])) as mock_request:
        await supabase_module.supabase_fetch("services?select=slug")

    assert mock_request.await_args.kwargs["headers"]["apikey"] == "service-role"
    assert mock_request.await_args.kwargs["headers"]["Authorization"] == "Bearer service-role"


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["scores", "score_audit_chain"])
async def test_generic_supabase_insert_cannot_write_score_truth(table):
    with patch("routes._supabase._request", new=AsyncMock()) as mock_request:
        ok = await supabase_module.supabase_insert(table, {"service_slug": "stripe"})

    assert ok is False
    mock_request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "scores?service_slug=eq.stripe",
        "score_audit_chain?service_slug=eq.stripe",
    ],
)
async def test_generic_supabase_patch_cannot_write_score_truth(path):
    with patch("routes._supabase._request", new=AsyncMock()) as mock_request:
        result = await supabase_module.supabase_patch(path, {"tier": "L4"})

    assert result is None
    mock_request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["scores", "score_audit_chain"])
async def test_generic_supabase_insert_returning_cannot_write_score_truth(table):
    with patch("routes._supabase._request", new=AsyncMock()) as mock_request:
        result = await supabase_module.supabase_insert_returning(table, {"service_slug": "stripe"})

    assert result is None
    mock_request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["scores", "score_audit_chain"])
async def test_publisher_only_insert_uses_score_publisher_key(monkeypatch, table):
    monkeypatch.setattr(supabase_module.settings, "supabase_score_publisher_key", "score-publisher", raising=False)
    monkeypatch.setattr(supabase_module.settings, "supabase_service_role_key", "service-role", raising=False)

    with patch("routes._supabase._request", new=AsyncMock(return_value=True)) as mock_request:
        ok = await supabase_module.supabase_score_insert(table, {"service_slug": "stripe"})

    assert ok is True
    assert mock_request.await_args.kwargs["headers"]["apikey"] == "score-publisher"
    assert mock_request.await_args.kwargs["headers"]["Authorization"] == "Bearer score-publisher"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "scores?service_slug=eq.stripe",
        "score_audit_chain?service_slug=eq.stripe",
    ],
)
async def test_publisher_only_patch_uses_score_publisher_key(monkeypatch, path):
    monkeypatch.setattr(supabase_module.settings, "supabase_score_publisher_key", "score-publisher", raising=False)
    monkeypatch.setattr(supabase_module.settings, "supabase_service_role_key", "service-role", raising=False)

    with patch("routes._supabase._request", new=AsyncMock(return_value=[])) as mock_request:
        result = await supabase_module.supabase_score_patch(path, {"tier": "L4"})

    assert result == []
    assert mock_request.await_args.kwargs["headers"]["apikey"] == "score-publisher"
    assert mock_request.await_args.kwargs["headers"]["Authorization"] == "Bearer score-publisher"


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["scores", "score_audit_chain"])
async def test_publisher_only_insert_returning_uses_score_publisher_key(monkeypatch, table):
    monkeypatch.setattr(supabase_module.settings, "supabase_score_publisher_key", "score-publisher", raising=False)
    monkeypatch.setattr(supabase_module.settings, "supabase_service_role_key", "service-role", raising=False)

    with patch("routes._supabase._request", new=AsyncMock(return_value={"service_slug": "stripe"})) as mock_request:
        result = await supabase_module.supabase_score_insert_returning(table, {"service_slug": "stripe"})

    assert result == {"service_slug": "stripe"}
    assert mock_request.await_args.kwargs["headers"]["apikey"] == "score-publisher"
    assert mock_request.await_args.kwargs["headers"]["Authorization"] == "Bearer score-publisher"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("table", "path"),
    [
        ("services", "services?slug=eq.stripe"),
        ("execution_receipts", "execution_receipts?id=eq.1"),
    ],
)
async def test_publisher_only_helpers_reject_non_score_targets(table, path):
    with patch("routes._supabase._request", new=AsyncMock()) as mock_request:
        ok = await supabase_module.supabase_score_insert(table, {"service_slug": "stripe"})
        patched = await supabase_module.supabase_score_patch(path, {"tier": "L4"})
        inserted = await supabase_module.supabase_score_insert_returning(table, {"service_slug": "stripe"})

    assert ok is False
    assert patched is None
    assert inserted is None
    mock_request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["scores", "score_audit_chain"])
async def test_publisher_required_insert_raises_on_failure(table):
    with patch("routes._supabase._request", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(SupabaseWriteUnavailable):
            await supabase_module.supabase_score_insert_required(table, {"service_slug": "stripe"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "scores?service_slug=eq.stripe",
        "score_audit_chain?service_slug=eq.stripe",
    ],
)
async def test_publisher_required_patch_raises_on_failure(path):
    with patch("routes._supabase._request", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(SupabaseWriteUnavailable):
            await supabase_module.supabase_score_patch_required(path, {"tier": "L4"})


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["scores", "score_audit_chain"])
async def test_publisher_required_insert_returning_raises_on_failure(table):
    with patch("routes._supabase._request", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(SupabaseWriteUnavailable):
            await supabase_module.supabase_score_insert_returning_required(
                table,
                {"service_slug": "stripe"},
            )


@pytest.mark.asyncio
async def test_fetch_scores_from_db_uses_score_reader_key_when_configured(monkeypatch):
    monkeypatch.setattr(supabase_module.settings, "supabase_service_role_key", "service-role", raising=False)
    monkeypatch.setattr(supabase_module.settings, "supabase_score_reader_key", "score-reader", raising=False)

    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = []

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("services.score_cache.httpx.AsyncClient", return_value=mock_client):
        await fetch_scores_from_db()

    assert mock_client.get.call_args.kwargs["headers"]["apikey"] == "score-reader"
    assert mock_client.get.call_args.kwargs["headers"]["Authorization"] == "Bearer score-reader"
