"""Tests for read-only SQL classification."""

from services.db_sql_classifier import classify_read_only_query


def test_classify_single_select_allows_read_only_query() -> None:
    classification = classify_read_only_query(
        "SELECT id, email FROM public.users WHERE org_id = $1 ORDER BY created_at DESC"
    )

    assert classification.read_only is True
    assert classification.statement_type == "select"
    assert classification.reason is None
    assert classification.tables_referenced == ["public.users"]


def test_classify_multi_statement_query_is_denied() -> None:
    classification = classify_read_only_query("SELECT 1; DELETE FROM users")

    assert classification.read_only is False
    assert classification.statement_type == "multi_statement"
    assert classification.reason == "multi_statement"
    assert classification.tables_referenced == []


def test_classify_read_only_cte_stays_allowed() -> None:
    classification = classify_read_only_query(
        "WITH recent AS (SELECT id FROM public.users) SELECT * FROM recent"
    )

    assert classification.read_only is True
    assert classification.statement_type == "select"
    assert classification.reason is None
    assert classification.tables_referenced == ["public.users"]


def test_classify_mutating_cte_is_denied() -> None:
    classification = classify_read_only_query(
        "WITH doomed AS (DELETE FROM public.users WHERE id = 1 RETURNING id) SELECT * FROM doomed"
    )

    assert classification.read_only is False
    assert classification.statement_type == "select"
    assert classification.reason == "delete_stmt_denied"
    assert classification.tables_referenced == ["public.users"]


def test_classify_hidden_mutation_via_comments_still_fails() -> None:
    classification = classify_read_only_query(
        "/* harmless */\nSELECT 1;\n-- actually not harmless\nDELETE FROM users"
    )

    assert classification.read_only is False
    assert classification.reason == "multi_statement"


def test_classify_call_statement_is_denied() -> None:
    classification = classify_read_only_query("CALL rotate_keys()")

    assert classification.read_only is False
    assert classification.statement_type == "call"
    assert classification.reason == "root_statement_not_select"


def test_classify_do_block_is_denied() -> None:
    classification = classify_read_only_query("DO $$ BEGIN PERFORM 1; END $$;")

    assert classification.read_only is False
    assert classification.statement_type == "do"
    assert classification.reason == "root_statement_not_select"


def test_classify_explain_analyze_is_denied_in_wave_one() -> None:
    classification = classify_read_only_query("EXPLAIN ANALYZE SELECT * FROM users")

    assert classification.read_only is False
    assert classification.statement_type == "explain"
    assert classification.reason == "root_statement_not_select"
    assert classification.tables_referenced == ["users"]


def test_classify_select_into_is_denied() -> None:
    classification = classify_read_only_query(
        "SELECT * INTO archive_users FROM public.users"
    )

    assert classification.read_only is False
    assert classification.statement_type == "select"
    assert classification.reason == "select_into_denied"
    assert classification.tables_referenced == ["public.users"]
