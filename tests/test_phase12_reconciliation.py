"""Synthetic read-only reconciliation tests. No real records are used."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.local_backup import copy_sqlite
from src.reviewer_accounts import bootstrap_administrator
from src.database.phase12_reconciliation import assess_source_reconciliation


@pytest.fixture
def sources(tmp_path):
    local = tmp_path / "local.sqlite3"
    accounts = tmp_path / "accounts.sqlite3"
    hosted = tmp_path / "hosted.sqlite3"
    initialize_database(local)
    bootstrap_administrator("synthetic_admin", "Synthetic-Phase12-Password-2026!", accounts)
    with sqlite3.connect(local) as db:
        db.execute(
            "INSERT INTO opportunities(source_id,url,title) VALUES (?,?,?)",
            ("synthetic", "https://example.invalid/one", "Synthetic event"),
        )
    copy_sqlite(local, hosted)
    return local, accounts, hosted


def test_equal_sources_do_not_authorize_migration(sources):
    report = assess_source_reconciliation(*sources)
    assert report["source_reconciliation_clear"]
    assert report["different_tables"] == []
    assert all(report["table_equal"].values())
    assert not report["migration_authorized"]
    assert not report["cutover_authorized"]
    assert report["sqlite_remains_authoritative"]


def test_divergence_is_named_without_records(sources):
    with sqlite3.connect(sources[2]) as db:
        db.execute("UPDATE opportunities SET title='Divergent' WHERE id=1")
    report = assess_source_reconciliation(*sources)
    assert not report["source_reconciliation_clear"]
    assert report["different_tables"] == ["opportunities"]
    assert "histories_diverged" in report["blockers"]
    assert "Synthetic event" not in str(report)
    assert "Divergent" not in str(report)


@pytest.mark.parametrize("index,state,label", [
    (0, "uncertain", "local_ambiguous_delivery"),
    (2, "sending", "hosted_ambiguous_delivery"),
])
def test_ambiguous_delivery_is_blocked(sources, index, state, label):
    with sqlite3.connect(sources[index]) as db:
        db.execute(
            "INSERT INTO notification_jobs(opportunity_id,status) VALUES (?,?)",
            (1, state),
        )
    report = assess_source_reconciliation(*sources)
    assert label in report["blockers"]
    assert not report["source_reconciliation_clear"]
    assert not report["migration_authorized"]


def test_missing_source_never_creates_database(sources, tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(ValueError):
        assess_source_reconciliation(sources[0], sources[1], missing)
    assert not missing.exists()


def test_duplicate_source_refused(sources):
    with pytest.raises(ValueError, match="distinct"):
        assess_source_reconciliation(sources[0], sources[1], sources[0])


def test_files_and_account_secrets_never_exported(sources):
    before = [p.read_bytes() for p in sources]
    report = assess_source_reconciliation(*sources)
    assert before == [p.read_bytes() for p in sources]
    assert not report["source_files_modified"]
    assert not report["raw_rows_exported"]
    assert not report["password_verifiers_exported"]
    assert not report["postgres_connected"]
    assert not report["email_sent"]
    assert "password_hash" not in str(report)


def test_missing_account_audit_trigger_fails_closed(sources):
    with sqlite3.connect(sources[1]) as db:
        db.execute("DROP TRIGGER protect_account_audit_deletes")
    report = assess_source_reconciliation(*sources)
    assert "account_database_invalid" in report["blockers"]
    assert not report["source_reconciliation_clear"]
