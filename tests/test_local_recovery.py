"""Offline tests for isolated two-database recovery."""

import sqlite3

import pytest

from src.database.schema import (
    PROJECT_ROOT,
    initialize_database,
)
from src.database.local_backup import create_local_backup
from src.database.local_recovery import (
    recover_to_isolated_directory,
)
from src.database.storage_readiness import inspect_storage
from src.database.migration_preflight import inspect_accounts
from src.reviewer_accounts import (
    bootstrap_administrator,
    change_account_access,
    check_permission,
)


PASSWORD = "Offline-Recovery-Password-2026"


@pytest.fixture
def backup_bundle(tmp_path):
    """Create isolated source databases with history to preserve."""

    opportunities = tmp_path / "source_opportunities.sqlite3"
    accounts = tmp_path / "source_accounts.sqlite3"

    initialize_database(opportunities)
    bootstrap_administrator(
        "test_admin",
        PASSWORD,
        accounts,
    )

    with sqlite3.connect(opportunities) as connection:
        connection.execute("PRAGMA foreign_keys = ON")

        first = connection.execute(
            """
            INSERT INTO opportunities (
                source_id, url, title, category,
                classification_status
            )
            VALUES (
                'github_blog',
                'https://example.org/event-one',
                'Recovery event one',
                'tech_event',
                'potential_match'
            )
            """
        ).lastrowid

        second = connection.execute(
            """
            INSERT INTO opportunities (
                source_id, url, title, category,
                classification_status
            )
            VALUES (
                'github_blog',
                'https://example.org/event-two',
                'Recovery event two',
                'tech_event',
                'potential_match'
            )
            """
        ).lastrowid

        connection.execute(
            """
            INSERT INTO opportunity_reviews (
                opportunity_id, decision, reviewer_id,
                evidence_url, free_confirmed,
                ph_confirmed, open_confirmed, reviewed_at
            )
            VALUES (
                ?, 'approved', 'test_admin',
                'https://example.org/evidence',
                1, 1, 1, CURRENT_TIMESTAMP
            )
            """,
            (first,),
        )

        connection.execute(
            """
            UPDATE opportunities
            SET verification='verified',
                free_status='confirmed_free',
                ph_eligibility='confirmed',
                deadline_status='open'
            WHERE id=?
            """,
            (first,),
        )

        connection.execute(
            """
            INSERT INTO notification_jobs (
                opportunity_id, status, sent_at
            )
            VALUES (?, 'sent', CURRENT_TIMESTAMP)
            """,
            (first,),
        )

        connection.execute(
            """
            INSERT INTO notification_jobs (
                opportunity_id, status
            )
            VALUES (?, 'uncertain')
            """,
            (second,),
        )

    # Create a synthetic secondary reviewer and a genuine
    # account-audit event in the temporary fixture.
    with sqlite3.connect(accounts) as connection:
        connection.execute(
            """
            INSERT INTO reviewer_accounts (
                account_id, role, password_hash, active
            )
            SELECT 'test_reviewer', 'reviewer',
                   password_hash, 1
            FROM reviewer_accounts
            WHERE account_id='test_admin'
            """
        )

    change_account_access(
        "test_admin",
        PASSWORD,
        "test_reviewer",
        active=False,
        path=accounts,
    )

    backup = tmp_path / "private-backup"

    create_local_backup(
        backup,
        opportunities,
        accounts,
    )

    return {
        "backup": backup,
        "opportunities": opportunities,
        "accounts": accounts,
    }


def test_recovery_creates_valid_isolated_copies(
    backup_bundle, tmp_path
):
    destination = tmp_path / "recovered"

    result = recover_to_isolated_directory(
        backup_bundle["backup"],
        destination,
    )

    assert result["recovery_verified"] is True
    assert result["live_databases_replaced"] is False
    assert result["email_sent"] is False
    assert (destination / "manifest.json").is_file()

    assert inspect_storage(
        destination / "opportunities.sqlite3"
    )["migration_inventory_ready"] is True

    assert inspect_accounts(
        destination / "reviewer_accounts.sqlite3"
    )["ready"] is True


def test_review_and_notification_history_preserved(
    backup_bundle, tmp_path
):
    destination = tmp_path / "recovered"

    recover_to_isolated_directory(
        backup_bundle["backup"],
        destination,
    )

    with sqlite3.connect(
        destination / "opportunities.sqlite3"
    ) as connection:
        review_count = connection.execute(
            "SELECT COUNT(*) FROM opportunity_reviews"
        ).fetchone()[0]

        statuses = [
            row[0]
            for row in connection.execute(
                "SELECT status FROM notification_jobs ORDER BY id"
            )
        ]

    assert review_count == 1
    assert statuses == ["sent", "uncertain"]


def test_reviewer_accounts_and_audit_preserved(
    backup_bundle, tmp_path
):
    destination = tmp_path / "recovered"

    recover_to_isolated_directory(
        backup_bundle["backup"],
        destination,
    )

    account_database = (
        destination / "reviewer_accounts.sqlite3"
    )

    assert check_permission(
        "test_admin",
        PASSWORD,
        "manage_reviewers",
        account_database,
    ) is True

    assert check_permission(
        "test_reviewer",
        PASSWORD,
        "approve_opportunity",
        account_database,
    ) is False

    with sqlite3.connect(account_database) as connection:
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM reviewer_account_audit"
        ).fetchone()[0]

    assert audit_count == 1


def test_recovery_does_not_change_sources_or_backup(
    backup_bundle, tmp_path
):
    original_files = [
        backup_bundle["opportunities"],
        backup_bundle["accounts"],
        backup_bundle["backup"] / "opportunities.sqlite3",
        backup_bundle["backup"] / "reviewer_accounts.sqlite3",
        backup_bundle["backup"] / "manifest.json",
    ]

    before = {
        str(path): path.read_bytes()
        for path in original_files
    }

    recover_to_isolated_directory(
        backup_bundle["backup"],
        tmp_path / "recovered",
    )

    for path in original_files:
        assert path.read_bytes() == before[str(path)]


def test_modified_backup_is_rejected(
    backup_bundle, tmp_path
):
    damaged_file = (
        backup_bundle["backup"] / "opportunities.sqlite3"
    )

    with damaged_file.open("ab") as file:
        file.write(b"tampering")

    destination = tmp_path / "rejected-recovery"

    with pytest.raises(ValueError, match="mismatch"):
        recover_to_isolated_directory(
            backup_bundle["backup"],
            destination,
        )

    assert not destination.exists()


def test_missing_manifest_is_rejected(
    backup_bundle, tmp_path
):
    (backup_bundle["backup"] / "manifest.json").unlink()

    destination = tmp_path / "missing-manifest"

    with pytest.raises(ValueError):
        recover_to_isolated_directory(
            backup_bundle["backup"],
            destination,
        )

    assert not destination.exists()


def test_existing_destination_is_preserved(
    backup_bundle, tmp_path
):
    destination = tmp_path / "existing-recovery"
    destination.mkdir()

    marker = destination / "keep.txt"
    marker.write_text("unchanged", encoding="utf-8")

    with pytest.raises(FileExistsError):
        recover_to_isolated_directory(
            backup_bundle["backup"],
            destination,
        )

    assert marker.read_text(
        encoding="utf-8"
    ) == "unchanged"


def test_recovery_inside_project_is_refused(
    backup_bundle, tmp_path
):
    destination = (
        PROJECT_ROOT / "data"
        / f"forbidden-recovery-{tmp_path.name}"
    )

    with pytest.raises(ValueError, match="outside the project"):
        recover_to_isolated_directory(
            backup_bundle["backup"],
            destination,
        )

    assert not destination.exists()