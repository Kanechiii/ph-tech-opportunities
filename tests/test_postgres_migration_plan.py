"""Offline tests of a zero-export, fail-closed migration planning contract."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.local_backup import copy_sqlite
from src.database.postgres_migration_plan import (
    build_migration_plan,
    parameterized_insert,
)
from src.reviewer_accounts import bootstrap_administrator


@pytest.fixture
def source_triple(tmp_path):
    local = tmp_path / "local.sqlite3"
    accounts = tmp_path / "accounts.sqlite3"
    hosted = tmp_path / "hosted.sqlite3"
    initialize_database(local)
    bootstrap_administrator("test_admin", "Phase10-Offline-Strong-Password-2026!", accounts)
    with sqlite3.connect(local) as connection:
        connection.execute(
            "INSERT INTO opportunities (source_id,url,title) VALUES (?,?,?)",
            ("github_blog", "https://example.org/one", "First"),
        )
    copy_sqlite(local, hosted)
    return local, accounts, hosted


def test_matching_sources_produce_non_authorizing_plan(source_triple):
    report = build_migration_plan(*source_triple)
    assert report["blockers"] == []
    assert report["inventory_complete"]
    assert all(report["opportunity_table_matches"].values())
    assert len(report["target_table_order"]) == 7
    assert not report["postgres_import_authorized"]
    assert not report["cutover_authorized"]


def test_different_histories_not_silently_merged(source_triple):
    with sqlite3.connect(source_triple[2]) as connection:
        connection.execute(
            "INSERT INTO opportunities (source_id,url,title) VALUES (?,?,?)",
            ("python", "https://example.org/two", "Second"),
        )
    report = build_migration_plan(*source_triple)
    assert "histories_diverged" in report["blockers"]
    assert report["tables"]["hosted"]["opportunities"]["rows"] == 2
    assert report["tables"]["local"]["opportunities"]["rows"] == 1
    assert not report["postgres_import_authorized"]


def test_state_uncertain_is_always_blocked(source_triple):
    with sqlite3.connect(source_triple[0]) as connection:
        connection.execute(
            "INSERT INTO notification_jobs(opportunity_id,status) VALUES(1,'uncertain')"
        )
    report = build_migration_plan(*source_triple)
    assert "local_ambiguous_delivery" in report["blockers"]
    assert not report["postgres_import_authorized"]


def test_state_sending_is_always_blocked(source_triple):
    with sqlite3.connect(source_triple[2]) as connection:
        connection.execute(
            "INSERT INTO notification_jobs(opportunity_id,status) VALUES(1,'sending')"
        )
    report = build_migration_plan(*source_triple)
    assert "hosted_ambiguous_delivery" in report["blockers"]


def test_missing_file_cannot_create_blank_database(source_triple, tmp_path):
    missing = tmp_path / "not-there.sqlite3"
    with pytest.raises(FileNotFoundError):
        build_migration_plan(source_triple[0], source_triple[1], missing)
    assert not missing.exists()


def test_same_source_file_is_rejected(source_triple):
    with pytest.raises(ValueError, match="Three separate"):
        build_migration_plan(source_triple[0], source_triple[1], source_triple[0])


def test_fingerprints_have_no_plaintext_data(source_triple):
    report = build_migration_plan(*source_triple)
    rendered = str(report)
    assert "Phase10-Offline-Strong-Password" not in rendered
    assert "https://example.org/one" not in rendered
    assert "password_hash" in report["tables"]["accounts"]["reviewer_accounts"]["columns"]


def test_inventory_never_modifies_sqlite_bytes(source_triple):
    before = [p.read_bytes() for p in source_triple]
    report = build_migration_plan(*source_triple)
    assert [p.read_bytes() for p in source_triple] == before
    assert not report["files_modified"]
    assert not report["email_sent"]
    assert not report["records_exported"]


def test_sql_templates_are_parameterized_and_allowlisted():
    sql = parameterized_insert(
        "reviewer_accounts",
        ["account_id", "role", "password_hash", "active", "created_at"],
    )
    assert '"phtech_private"."reviewer_accounts"' in sql
    assert sql.count("%s") == 5
    assert "PASSWORD '""'" not in sql.upper()
    with pytest.raises(ValueError):
        parameterized_insert("reviewer_accounts; DROP TABLE x", ["account_id"])
    with pytest.raises(ValueError):
        parameterized_insert("opportunities", ["id", "title"])
