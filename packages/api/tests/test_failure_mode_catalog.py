from pathlib import Path

from services.failure_mode_catalog import (
    CATALOG_CANDIDATES,
    catalog_failures,
    load_failure_mode_catalog,
    resolve_failure_modes,
)


def test_api_catalog_copy_matches_shared():
    api_copy = CATALOG_CANDIDATES[0]
    shared = CATALOG_CANDIDATES[1]
    assert api_copy.is_file()
    assert shared.is_file()
    assert api_copy.read_text() == shared.read_text()


def test_twilio_catalog_is_populated():
    rows = catalog_failures("twilio")
    titles = {row["title"] for row in rows}
    assert len(rows) >= 4
    assert "Phone number and 10DLC verification wall" in titles


def test_unknown_slug_is_unresearched():
    rows, coverage, honesty = resolve_failure_modes("not-a-real-service", [])
    assert rows == []
    assert coverage == "unresearched"
    assert "coverage gap" in honesty


def test_email_providers_without_rows_are_unresearched_not_an_error():
    for slug in ("sendgrid", "mailgun", "postmark"):
        rows, coverage, honesty = resolve_failure_modes(slug, [])
        assert rows == []
        assert coverage == "unresearched"
        assert "coverage gap" in honesty


def test_missing_catalog_file_is_unresearched(monkeypatch, tmp_path: Path):
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(
        "services.failure_mode_catalog.CATALOG_CANDIDATES",
        (missing,),
    )
    load_failure_mode_catalog.cache_clear()
    try:
        assert load_failure_mode_catalog() == {}
        rows, coverage, honesty = resolve_failure_modes("sendgrid", [])
        assert rows == []
        assert coverage == "unresearched"
        assert "coverage gap" in honesty
    finally:
        load_failure_mode_catalog.cache_clear()


def test_unreadable_catalog_does_not_raise(monkeypatch, tmp_path: Path):
    def _boom(_path: Path) -> str:
        raise OSError("catalog unreadable")

    monkeypatch.setattr(Path, "read_text", _boom)
    load_failure_mode_catalog.cache_clear()
    try:
        assert load_failure_mode_catalog() == {}
        rows, coverage, _honesty = resolve_failure_modes("mailgun", [])
        assert rows == []
        assert coverage == "unresearched"
    finally:
        load_failure_mode_catalog.cache_clear()


def test_stored_rows_win_over_catalog():
    stored = [{"title": "Live row", "description": "from db"}]
    rows, coverage, honesty = resolve_failure_modes("twilio", stored)
    assert rows == stored
    assert coverage == "reported"
    assert "complete incident history" in honesty
