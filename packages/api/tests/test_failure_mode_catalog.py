from services.failure_mode_catalog import catalog_failures, resolve_failure_modes


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


def test_stored_rows_win_over_catalog():
    stored = [{"title": "Live row", "description": "from db"}]
    rows, coverage, honesty = resolve_failure_modes("twilio", stored)
    assert rows == stored
    assert coverage == "reported"
    assert "complete incident history" in honesty
