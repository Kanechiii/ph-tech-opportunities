"""Offline tests for verified independent SQLite backups."""

import json
import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.snapshot import validate_database
from src.reviewer_accounts import bootstrap_administrator
from src.database.migration_preflight import inspect_accounts
from src.database.local_backup import (
    create_local_backup,
    file_hash,
)


@pytest.fixture
def databases(tmp_path):
    opportunities = tmp_path / "opportunities.sqlite3"
    accounts = tmp_path / "reviewer_accounts.sqlite3"

    initialize_database(opportunities)

    bootstrap_administrator(
        "test_admin",
        "Offline-Backup-Password-2026",
        accounts,
    )

    with sqlite3.connect(opportunities) as connection:
        connection.execute(
            """
            INSERT INTO opportunities (source_id, url, title)
            VALUES (?, ?, ?)
            """,
            (
                "github_blog",
                "https://example.org/backup-test",
                "Test announcement",
            ),
        )

    return opportunities, accounts


def test_both_databases_are_backed_up(databases, tmp_path):
    opportunities, accounts = databases
    target = tmp_path / "safe-backup"

    result = create_local_backup(
        target, opportunities, accounts
    )

    assert result["verified"] is True
    assert validate_database(
        target / "opportunities.sqlite3"
    )
    assert inspect_accounts(
        target / "reviewer_accounts.sqlite3"
    )["ready"] is True


def test_existing_records_are_preserved(databases, tmp_path):
    opportunities, accounts = databases
    target = tmp_path / "record-backup"

    create_local_backup(target, opportunities, accounts)

    with sqlite3.connect(
        target / "opportunities.sqlite3"
    ) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM opportunities"
        ).fetchone()[0]

    assert count == 1


def test_sources_are_not_modified(databases, tmp_path):
    opportunities, accounts = databases
    before_opportunities = opportunities.read_bytes()
    before_accounts = accounts.read_bytes()

    create_local_backup(
        tmp_path / "read-only-backup",
        opportunities,
        accounts,
    )

    assert opportunities.read_bytes() == before_opportunities
    assert accounts.read_bytes() == before_accounts


def test_existing_destination_is_not_overwritten(
    databases, tmp_path
):
    opportunities, accounts = databases
    destination = tmp_path / "existing"
    destination.mkdir()

    marker = destination / "keep.txt"
    marker.write_text("original", encoding="utf-8")

    with pytest.raises(FileExistsError):
        create_local_backup(
            destination, opportunities, accounts
        )

    assert marker.read_text(encoding="utf-8") == "original"


def test_missing_source_cannot_create_backup(
    databases, tmp_path
):
    _, accounts = databases
    target = tmp_path / "should-not-exist"

    with pytest.raises(ValueError, match="does not exist"):
        create_local_backup(
            target,
            tmp_path / "missing.sqlite3",
            accounts,
        )

    assert not target.exists()


def test_invalid_account_database_blocks_backup(
    databases, tmp_path
):
    opportunities, accounts = databases
    target = tmp_path / "invalid-account-backup"

    with sqlite3.connect(accounts) as connection:
        connection.execute(
            "DROP TRIGGER protect_account_audit_deletes"
        )

    with pytest.raises(ValueError, match="Reviewer"):
        create_local_backup(target, opportunities, accounts)

    assert not target.exists()


def test_manifest_matches_backed_up_files(
    databases, tmp_path
):
    opportunities, accounts = databases
    target = tmp_path / "manifest-backup"

    create_local_backup(target, opportunities, accounts)

    manifest = json.loads(
        (target / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["format_version"] == 1

    for filename, metadata in manifest["files"].items():
        backup_file = target / filename

        assert backup_file.is_file()
        assert metadata["sha256"] == file_hash(backup_file)
        assert metadata["size_bytes"] == backup_file.stat().st_size