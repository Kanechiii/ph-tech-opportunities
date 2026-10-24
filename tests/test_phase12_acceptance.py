"""Offline Phase 12 acceptance and synthetic authenticated recovery drill."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.local_backup import create_local_backup
from src.database.local_recovery import recover_to_isolated_directory
from src.database.migration_preflight import inspect_accounts
from src.database.storage_readiness import inspect_storage
from src.reviewer_accounts import bootstrap_administrator
from src.database.phase12_acceptance import assess_phase12


BACKUP_PASSWORD = "Synthetic-Independent-Backup-Passphrase-2026!"


@pytest.fixture
def sources(tmp_path):
    local = tmp_path / "local.sqlite3"
    accounts = tmp_path / "accounts.sqlite3"
    hosted = tmp_path / "hosted.sqlite3"
    initialize_database(local)
    bootstrap_administrator("synthetic_admin", "Synthetic-Reviewer-Password-2026!", accounts)
    with sqlite3.connect(local) as db:
        db.execute(
            "INSERT INTO opportunities (source_id,url,title) VALUES (?,?,?)",
            ("synthetic", "https://example.invalid/step5", "Synthetic only"),
        )
    with sqlite3.connect(local) as src, sqlite3.connect(hosted) as dst:
        src.backup(dst)
    return local, accounts, hosted


def test_final_assessment_never_authorizes_cutover(sources):
    report = assess_phase12(*sources)
    assert report["source_reconciliation_clear"]
    assert report["local_security_foundations_acceptable"]
    assert report["production_ready"] is False
    assert report["production_cutover_authorized"] is False
    assert report["postgres_import_authorized"] is False
    assert report["sqlite_backend_remains_authoritative"]
    assert not report["reviewed_email_automation_enabled"]


def test_production_blockers_are_explicit(sources):
    report = assess_phase12(*sources)
    assert "encrypted_backup_and_authenticated_decryption_not_implemented" in report["blockers"]
    assert "independent_hosted_backup_restore_not_verified" in report["blockers"]
    assert "no_postgresql_application_runtime_adapter" in report["blockers"]


def test_diverged_sources_remain_unresolved(sources):
    with sqlite3.connect(sources[2]) as db:
        db.execute("UPDATE opportunities SET title='Divergent' WHERE id=1")
    report = assess_phase12(*sources)
    assert not report["source_reconciliation_clear"]
    assert report["different_source_tables"] == ["opportunities"]
    assert "histories_diverged" in report["blockers"]
    assert "Divergent" not in str(report)


def test_uncertain_delivery_is_preserved_not_reset(sources):
    with sqlite3.connect(sources[0]) as db:
        db.execute(
            "INSERT INTO notification_jobs(opportunity_id,status) VALUES(1,'uncertain')"
        )
    report = assess_phase12(*sources)
    assert "local_ambiguous_delivery" in report["blockers"]
    with sqlite3.connect(sources[0]) as db:
        assert db.execute(
            "SELECT status FROM notification_jobs WHERE opportunity_id=1"
        ).fetchone()[0] == "uncertain"


def test_read_only_report_does_not_change_sources(sources):
    before = [p.read_bytes() for p in sources]
    report = assess_phase12(*sources)
    assert before == [p.read_bytes() for p in sources]
    assert not report["sqlite_sources_modified"]
    assert not report["source_records_exported"]
    assert not report["password_verifiers_exported"]
    assert not report["postgres_connected"]
    assert not report["email_sent"]


def test_synthetic_authenticated_backup_recovers_in_isolation(sources, tmp_path):
    original = [p.read_bytes() for p in sources]
    backup = tmp_path / "authenticated_backup"
    destination = tmp_path / "isolated_recovery"
    create_local_backup(
        backup, sources[0], sources[1],
        authentication_password=BACKUP_PASSWORD,
    )
    result = recover_to_isolated_directory(
        backup, destination,
        authentication_password=BACKUP_PASSWORD,
        require_authenticated=True,
    )
    assert result["recovery_verified"]
    assert result["backup_authenticated"]
    assert not result["live_databases_replaced"]
    assert not result["email_sent"]
    assert inspect_storage(destination / "opportunities.sqlite3")["migration_inventory_ready"]
    assert inspect_accounts(destination / "reviewer_accounts.sqlite3")["ready"]
    assert original == [p.read_bytes() for p in sources]


def test_wrong_passphrase_cannot_create_recovery(sources, tmp_path):
    backup = tmp_path / "authenticated_backup"
    target = tmp_path / "must_not_exist"
    create_local_backup(
        backup, sources[0], sources[1],
        authentication_password=BACKUP_PASSWORD,
    )
    with pytest.raises(ValueError):
        recover_to_isolated_directory(
            backup, target,
            authentication_password="Incorrect-Synthetic-Passphrase-2026!",
            require_authenticated=True,
        )
    assert not target.exists()


def test_existing_destination_is_not_replaced(sources, tmp_path):
    backup = tmp_path / "authenticated_backup"
    target = tmp_path / "existing_recovery"
    target.mkdir()
    marker = target / "preserve.txt"
    marker.write_text("keep", encoding="utf-8")
    create_local_backup(
        backup, sources[0], sources[1],
        authentication_password=BACKUP_PASSWORD,
    )
    with pytest.raises(FileExistsError):
        recover_to_isolated_directory(
            backup, target,
            authentication_password=BACKUP_PASSWORD,
            require_authenticated=True,
        )
    assert marker.read_text(encoding="utf-8") == "keep"
