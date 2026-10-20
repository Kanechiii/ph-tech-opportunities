"""Offline tests for read-only storage reconciliation."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.local_backup import copy_sqlite
from src.database.cutover_readiness import assess_cutover
from src.reviewer_accounts import bootstrap_administrator


PASSWORD = "Offline-Cutover-Test-Password-2026"


@pytest.fixture
def database_pairs(tmp_path):
    source_opportunities = tmp_path / "source_opportunities.sqlite3"
    source_accounts = tmp_path / "source_accounts.sqlite3"

    candidate_opportunities = (
        tmp_path / "candidate_opportunities.sqlite3"
    )
    candidate_accounts = tmp_path / "candidate_accounts.sqlite3"

    initialize_database(source_opportunities)

    bootstrap_administrator(
        "test_admin",
        PASSWORD,
        source_accounts,
    )

    with sqlite3.connect(source_opportunities) as connection:
        connection.execute(
            """
            INSERT INTO opportunities (
                source_id, url, title
            )
            VALUES (?, ?, ?)
            """,
            (
                "github_blog",
                "https://example.org/cutover-test",
                "Original opportunity",
            ),
        )

    # Create actual SQLite copies rather than new empty databases.
    copy_sqlite(
        source_opportunities,
        candidate_opportunities,
    )
    copy_sqlite(
        source_accounts,
        candidate_accounts,
    )

    return (
        source_opportunities,
        source_accounts,
        candidate_opportunities,
        candidate_accounts,
    )


def assess(paths):
    return assess_cutover(
        paths[0],
        paths[1],
        candidate_opportunities=paths[2],
        candidate_accounts=paths[3],
    )


def test_matching_database_pairs_pass_reconciliation(database_pairs):
    result = assess(database_pairs)

    assert result["reconciliation_passed"] is True
    assert result["comparison_completed"] is True
    assert result["blockers"] == []
    assert all(result["opportunity_table_matches"].values())
    assert all(result["reviewer_table_matches"].values())
    assert result["cutover_authorized"] is False


def test_missing_candidate_blocks_readiness(database_pairs):
    result = assess_cutover(
        database_pairs[0],
        database_pairs[1],
    )

    assert result["reconciliation_passed"] is False
    assert "candidate_not_supplied" in result["blockers"]
    assert result["comparison_completed"] is False


def test_partial_candidate_blocks_readiness(database_pairs):
    result = assess_cutover(
        database_pairs[0],
        database_pairs[1],
        candidate_opportunities=database_pairs[2],
    )

    assert result["reconciliation_passed"] is False
    assert "candidate_incomplete" in result["blockers"]


def test_changed_opportunity_detected_with_same_row_count(
    database_pairs,
):
    with sqlite3.connect(database_pairs[2]) as connection:
        connection.execute(
            """
            UPDATE opportunities
            SET title = 'Changed opportunity'
            WHERE id = 1
            """
        )

    result = assess(database_pairs)

    assert result["reconciliation_passed"] is False
    assert (
        result["opportunity_table_matches"]["opportunities"]
        is False
    )
    assert "opportunity_history_diverged" in result["blockers"]


def test_changed_password_hash_detected_without_exposure(
    database_pairs,
):
    with sqlite3.connect(database_pairs[3]) as connection:
        connection.execute(
            """
            UPDATE reviewer_accounts
            SET password_hash = 'synthetic-different-hash'
            WHERE account_id = 'test_admin'
            """
        )

    result = assess(database_pairs)

    assert result["reconciliation_passed"] is False
    assert (
        result["reviewer_table_matches"]["reviewer_accounts"]
        is False
    )
    assert "reviewer_history_diverged" in result["blockers"]
    assert "synthetic-different-hash" not in str(result)
    assert PASSWORD not in str(result)


def test_account_audit_difference_detected(database_pairs):
    with sqlite3.connect(database_pairs[3]) as connection:
        connection.execute(
            """
            INSERT INTO reviewer_account_audit (
                actor_id, target_id, action,
                old_value, new_value
            )
            VALUES (
                'test_admin', 'test_admin',
                'role_changed', 'reviewer', 'administrator'
            )
            """
        )

    result = assess(database_pairs)

    assert result["reconciliation_passed"] is False
    assert (
        result["reviewer_table_matches"]["reviewer_account_audit"]
        is False
    )


def test_source_uncertain_notification_blocks_readiness(
    database_pairs,
):
    with sqlite3.connect(database_pairs[0]) as connection:
        connection.execute(
            """
            INSERT INTO notification_jobs (
                opportunity_id, status
            )
            VALUES (1, 'uncertain')
            """
        )

    result = assess(database_pairs)

    assert result["reconciliation_passed"] is False
    assert (
        "source_unresolved_delivery_states"
        in result["blockers"]
    )
    assert result["source_notification_states"]["uncertain"] == 1


def test_candidate_sending_notification_blocks_readiness(
    database_pairs,
):
    with sqlite3.connect(database_pairs[2]) as connection:
        connection.execute(
            """
            INSERT INTO notification_jobs (
                opportunity_id, status,
                claim_token, claimed_at
            )
            VALUES (
                1, 'sending',
                'synthetic-test-claim', CURRENT_TIMESTAMP
            )
            """
        )

    result = assess(database_pairs)

    assert result["reconciliation_passed"] is False
    assert (
        "candidate_unresolved_delivery_states"
        in result["blockers"]
    )


def test_comparison_does_not_modify_any_database(
    database_pairs,
):
    before = [path.read_bytes() for path in database_pairs]

    result = assess(database_pairs)

    assert result["reconciliation_passed"] is True
    assert result["database_modified"] is False
    assert result["migration_performed"] is False
    assert result["credentials_exported"] is False
    assert result["email_sent"] is False

    after = [path.read_bytes() for path in database_pairs]

    assert before == after


def test_comparing_a_file_with_itself_is_rejected(
    database_pairs,
):
    with pytest.raises(
        ValueError,
        match="separate files",
    ):
        assess_cutover(
            database_pairs[0],
            database_pairs[1],
            candidate_opportunities=database_pairs[0],
            candidate_accounts=database_pairs[3],
        )


def test_missing_candidate_audit_trigger_blocks_readiness(
    database_pairs,
):
    with sqlite3.connect(database_pairs[3]) as connection:
        connection.execute(
            "DROP TRIGGER protect_account_audit_deletes"
        )

    result = assess(database_pairs)

    assert result["reconciliation_passed"] is False
    assert "candidate_accounts_not_ready" in result["blockers"]
    assert result["comparison_completed"] is False
    assert result["cutover_authorized"] is False