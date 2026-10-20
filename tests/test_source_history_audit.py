"""Offline tests for Phase 10 read-only source-history audit."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.local_backup import copy_sqlite
from src.database.source_history_audit import audit_source_histories
from src.reviewer_accounts import bootstrap_administrator


@pytest.fixture
def sources(tmp_path):
    local = tmp_path / "local.sqlite3"
    accounts = tmp_path / "accounts.sqlite3"
    hosted = tmp_path / "hosted.sqlite3"

    initialize_database(local)
    bootstrap_administrator("test_admin", "Offline-Phase10-Password-2026", accounts)

    with sqlite3.connect(local) as connection:
        connection.execute(
            "INSERT INTO opportunities (source_id, url, title) VALUES (?, ?, ?)",
            ("github_blog", "https://example.org/phase10", "Original"),
        )

    copy_sqlite(local, hosted)
    return local, accounts, hosted


def audit(sources):
    return audit_source_histories(*sources)


def test_identical_histories_are_visible_without_cutover(sources):
    report = audit(sources)
    assert report["inventory_complete"] is True
    assert report["opportunity_histories_match"] is True
    assert all(report["table_matches"].values())
    assert report["blockers"] == []
    assert report["production_cutover_authorized"] is False


def test_same_count_but_changed_title_is_detected(sources):
    with sqlite3.connect(sources[2]) as connection:
        connection.execute(
            "UPDATE opportunities SET title = ? WHERE id = 1",
            ("Divergent title",),
        )

    report = audit(sources)
    assert report["opportunity_histories_match"] is False
    assert report["table_matches"]["opportunities"] is False
    assert "opportunity_histories_diverged" in report["blockers"]


def test_append_only_review_history_divergence_is_detected(sources):
    with sqlite3.connect(sources[2]) as connection:
        connection.execute(
            """
            INSERT INTO opportunity_reviews (
                opportunity_id, decision, reviewer_id, evidence_url, reviewed_at
            ) VALUES (1, 'rejected', 'synthetic', 'https://example.org/evidence',
                      CURRENT_TIMESTAMP)
            """
        )

    report = audit(sources)
    assert report["table_matches"]["opportunity_reviews"] is False
    assert "opportunity_histories_diverged" in report["blockers"]


def test_local_uncertain_delivery_is_blocker(sources):
    with sqlite3.connect(sources[0]) as connection:
        connection.execute(
            "INSERT INTO notification_jobs (opportunity_id,status) "
            "VALUES (1,'uncertain')"
        )

    report = audit(sources)
    assert "local_unresolved_delivery_states" in report["blockers"]
    assert report["production_cutover_authorized"] is False


def test_hosted_sending_delivery_is_blocker(sources):
    with sqlite3.connect(sources[2]) as connection:
        connection.execute(
            "INSERT INTO notification_jobs (opportunity_id,status) "
            "VALUES (1,'sending')"
        )

    report = audit(sources)
    assert "hosted_unresolved_delivery_states" in report["blockers"]


def test_invalid_accounts_block_inventory(sources):
    with sqlite3.connect(sources[1]) as connection:
        connection.execute(
            "DROP TRIGGER protect_account_audit_deletes"
        )

    report = audit(sources)
    assert report["inventory_complete"] is False
    assert "local_reviewer_database_invalid" in report["blockers"]
    assert report["credentials_exported"] is False


def test_missing_hosted_snapshot_fails_closed(sources, tmp_path):
    with pytest.raises(FileNotFoundError):
        audit_source_histories(sources[0], sources[1], tmp_path / "absent.sqlite3")
    assert not (tmp_path / "absent.sqlite3").exists()


def test_duplicate_source_file_refused(sources):
    with pytest.raises(ValueError, match="distinct"):
        audit_source_histories(sources[0], sources[1], sources[0])


def test_audit_does_not_modify_source_bytes(sources):
    before = [path.read_bytes() for path in sources]
    report = audit(sources)
    after = [path.read_bytes() for path in sources]
    assert before == after
    assert report["data_modified"] is False
    assert report["records_exported"] is False
    assert report["email_sent"] is False
