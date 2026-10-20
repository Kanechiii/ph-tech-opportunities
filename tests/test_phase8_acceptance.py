"""Phase 8 final offline backup and recovery acceptance tests.

All data is synthetic and stored under pytest's temporary directory.
Never writes live databases, sends email, or performs a cutover.
"""

import json
import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.local_backup import create_local_backup, file_hash
from src.database.local_recovery import (
    recover_to_isolated_directory,
)
from src.database.cutover_readiness import assess_cutover
from src.database.storage_readiness import inspect_storage
from src.database.migration_preflight import inspect_accounts
from src.reviewer_accounts import (
    bootstrap_administrator,
    change_account_access,
    check_permission,
)


ADMIN_PASSWORD = "Offline-Phase8-Admin-Password-2026"
BACKUP_PASSPHRASE = "Offline-Phase8-Backup-Passphrase-2026"


@pytest.fixture
def environment(tmp_path):
    opportunities = tmp_path / "source_opportunities.sqlite3"
    accounts = tmp_path / "source_accounts.sqlite3"
    backup = tmp_path / "authenticated_backup"

    initialize_database(opportunities)
    bootstrap_administrator(
        "test_admin",
        ADMIN_PASSWORD,
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
                'https://example.org/phase8-one',
                'Verified workshop',
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
                'https://example.org/phase8-two',
                'Pending investigation',
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
                'https://example.org/verification',
                1, 1, 1, CURRENT_TIMESTAMP
            )
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

    # Synthetic secondary account used to generate a real
    # account-audit event in the temporary test database.
    with sqlite3.connect(accounts) as connection:
        connection.execute(
            """
            INSERT INTO reviewer_accounts (
                account_id, role, password_hash, active
            )
            SELECT
                'test_reviewer', 'reviewer', password_hash, 1
            FROM reviewer_accounts
            WHERE account_id = 'test_admin'
            """
        )

    change_account_access(
        "test_admin",
        ADMIN_PASSWORD,
        "test_reviewer",
        active=False,
        path=accounts,
    )

    create_local_backup(
        backup,
        opportunities,
        accounts,
        authentication_password=BACKUP_PASSPHRASE,
    )

    return {
        "opportunities": opportunities,
        "accounts": accounts,
        "backup": backup,
        "root": tmp_path,
    }


def restore(environment, name="recovered"):
    destination = environment["root"] / name

    result = recover_to_isolated_directory(
        environment["backup"],
        destination,
        authentication_password=BACKUP_PASSPHRASE,
        require_authenticated=True,
    )

    return destination, result


def compare(environment, destination):
    return assess_cutover(
        environment["opportunities"],
        environment["accounts"],
        candidate_opportunities=(
            destination / "opportunities.sqlite3"
        ),
        candidate_accounts=(
            destination / "reviewer_accounts.sqlite3"
        ),
    )


def test_authenticated_full_recovery(environment):
    destination, report = restore(environment)

    assert report["recovery_verified"] is True
    assert report["backup_authenticated"] is True
    assert report["live_databases_replaced"] is False
    assert report["email_sent"] is False

    assert inspect_storage(
        destination / "opportunities.sqlite3"
    )["migration_inventory_ready"] is True

    assert inspect_accounts(
        destination / "reviewer_accounts.sqlite3"
    )["ready"] is True


def test_review_and_delivery_history_survive(environment):
    destination, _ = restore(environment)

    with sqlite3.connect(
        destination / "opportunities.sqlite3"
    ) as connection:
        reviews = connection.execute(
            """
            SELECT decision, reviewer_id
            FROM opportunity_reviews
            """
        ).fetchall()

        statuses = connection.execute(
            """
            SELECT status
            FROM notification_jobs
            ORDER BY id
            """
        ).fetchall()

    assert reviews == [("approved", "test_admin")]
    assert statuses == [("sent",), ("uncertain",)]


def test_account_access_and_audit_survive(environment):
    destination, _ = restore(environment)
    recovered_accounts = (
        destination / "reviewer_accounts.sqlite3"
    )

    assert check_permission(
        "test_admin",
        ADMIN_PASSWORD,
        "manage_reviewers",
        recovered_accounts,
    ) is True

    assert check_permission(
        "test_reviewer",
        ADMIN_PASSWORD,
        "approve_opportunity",
        recovered_accounts,
    ) is False

    with sqlite3.connect(recovered_accounts) as connection:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM reviewer_account_audit
            """
        ).fetchone()[0]

        assert count == 1

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM reviewer_account_audit"
            )


def test_recovery_preserves_original_files(environment):
    protected = [
        environment["opportunities"],
        environment["accounts"],
        environment["backup"] / "opportunities.sqlite3",
        environment["backup"] / "reviewer_accounts.sqlite3",
        environment["backup"] / "manifest.json",
    ]

    before = [path.read_bytes() for path in protected]

    restore(environment)

    after = [path.read_bytes() for path in protected]

    assert before == after


def test_wrong_passphrase_refuses_recovery(environment):
    destination = environment["root"] / "wrong_password"

    with pytest.raises(
        ValueError,
        match="authentication failed",
    ):
        recover_to_isolated_directory(
            environment["backup"],
            destination,
            authentication_password="Incorrect-Passphrase-2026",
            require_authenticated=True,
        )

    assert not destination.exists()


def test_manifest_tampering_refuses_recovery(environment):
    manifest_path = environment["backup"] / "manifest.json"
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    manifest["created_at_utc"] = "2020-01-01T00:00:00+00:00"

    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    destination = environment["root"] / "tampered_manifest"

    with pytest.raises(
        ValueError,
        match="authentication failed",
    ):
        recover_to_isolated_directory(
            environment["backup"],
            destination,
            authentication_password=BACKUP_PASSPHRASE,
            require_authenticated=True,
        )

    assert not destination.exists()


def test_recomputed_sha256_cannot_bypass_hmac(environment):
    backup = environment["backup"]
    opportunity_file = backup / "opportunities.sqlite3"
    manifest_path = backup / "manifest.json"

    with opportunity_file.open("ab") as file:
        file.write(b"unauthorized-change")

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    metadata = manifest["files"]["opportunities.sqlite3"]
    metadata["sha256"] = file_hash(opportunity_file)
    metadata["size_bytes"] = opportunity_file.stat().st_size

    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    destination = environment["root"] / "forged_backup"

    with pytest.raises(
        ValueError,
        match="authentication failed",
    ):
        recover_to_isolated_directory(
            backup,
            destination,
            authentication_password=BACKUP_PASSPHRASE,
            require_authenticated=True,
        )

    assert not destination.exists()


def test_signature_downgrade_refused(environment):
    manifest_path = environment["backup"] / "manifest.json"
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    del manifest["authentication"]

    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    destination = environment["root"] / "downgrade"

    with pytest.raises(
        ValueError,
        match="Authenticated backup required",
    ):
        recover_to_isolated_directory(
            environment["backup"],
            destination,
            authentication_password=BACKUP_PASSPHRASE,
            require_authenticated=True,
        )

    assert not destination.exists()


def test_identical_history_still_blocks_uncertain_delivery(
    environment,
):
    destination, _ = restore(environment)

    result = compare(environment, destination)

    assert result["comparison_completed"] is True
    assert all(result["opportunity_table_matches"].values())
    assert all(result["reviewer_table_matches"].values())

    assert result["reconciliation_passed"] is False
    assert "source_unresolved_delivery_states" in result["blockers"]
    assert "candidate_unresolved_delivery_states" in result["blockers"]
    assert result["cutover_authorized"] is False


def test_opportunity_divergence_blocks_cutover(environment):
    destination, _ = restore(environment)

    with sqlite3.connect(
        destination / "opportunities.sqlite3"
    ) as connection:
        connection.execute(
            """
            UPDATE opportunities
            SET title = 'Diverged record'
            WHERE id = 1
            """
        )

    result = compare(environment, destination)

    assert (
        result["opportunity_table_matches"]["opportunities"]
        is False
    )
    assert "opportunity_history_diverged" in result["blockers"]
    assert result["cutover_authorized"] is False


def test_reviewer_divergence_blocks_cutover(environment):
    destination, _ = restore(environment)

    with sqlite3.connect(
        destination / "reviewer_accounts.sqlite3"
    ) as connection:
        connection.execute(
            """
            UPDATE reviewer_accounts
            SET role = 'viewer'
            WHERE account_id = 'test_reviewer'
            """
        )

    result = compare(environment, destination)

    assert (
        result["reviewer_table_matches"]["reviewer_accounts"]
        is False
    )
    assert "reviewer_history_diverged" in result["blockers"]
    assert result["credentials_exported"] is False
    assert result["cutover_authorized"] is False


def test_existing_recovery_directory_is_never_overwritten(
    environment,
):
    destination = environment["root"] / "existing"
    destination.mkdir()

    marker = destination / "preserve.txt"
    marker.write_text("existing-data", encoding="utf-8")

    with pytest.raises(FileExistsError):
        recover_to_isolated_directory(
            environment["backup"],
            destination,
            authentication_password=BACKUP_PASSPHRASE,
            require_authenticated=True,
        )

    assert marker.read_text(
        encoding="utf-8"
    ) == "existing-data"