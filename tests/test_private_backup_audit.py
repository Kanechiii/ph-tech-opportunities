"""Offline security regression tests with synthetic local backup fixtures."""

import json
import os
import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.local_backup import create_local_backup
from src.database.private_backup_audit import inspect_private_backup
from src.reviewer_accounts import bootstrap_administrator


@pytest.fixture
def protected_sources(tmp_path):
    opportunities = tmp_path / "opportunities.sqlite3"
    accounts = tmp_path / "reviewer_accounts.sqlite3"
    backup = tmp_path / "private-backup"
    initialize_database(opportunities)
    bootstrap_administrator(
        "synthetic_admin", "Synthetic-Backup-Password-2026!", accounts
    )
    create_local_backup(
        backup,
        opportunity_path=opportunities,
        account_path=accounts,
        authentication_password="Synthetic-Independent-Backup-Passphrase!",
    )
    return backup, accounts, opportunities


def test_signed_manifest_is_not_mistaken_for_encryption(protected_sources):
    backup, accounts, _ = protected_sources
    report = inspect_private_backup(backup, accounts)
    assert report["audit_completed"]
    assert report["manifest_signed_metadata_present"]
    assert not report["manifest_signature_cryptographically_verified"]
    assert not report["backup_encrypted"]
    assert "backup_contents_not_encrypted" in report["findings"]
    assert not report["production_ready"]


def test_source_and_backup_bytes_remain_unchanged(protected_sources):
    backup, accounts, opportunities = protected_sources
    paths = [accounts, opportunities, *backup.iterdir()]
    before = {str(p): p.read_bytes() for p in paths}
    report = inspect_private_backup(backup, accounts)
    assert before == {str(p): p.read_bytes() for p in paths}
    assert not report["sources_modified"]
    assert not report["backup_modified"]
    assert not report["credentials_exported"]
    assert not report["email_sent"]


def test_missing_manifest_reports_failure_without_repair(protected_sources):
    backup, accounts, _ = protected_sources
    (backup / "manifest.json").unlink()
    report = inspect_private_backup(backup, accounts)
    assert "unexpected_or_missing_backup_files" in report["findings"]
    assert "manifest_missing_or_unsafe" in report["findings"]
    assert not (backup / "manifest.json").exists()


def test_unexpected_file_is_flagged(protected_sources):
    backup, accounts, _ = protected_sources
    extra = backup / "unexpected.txt"
    extra.write_text("Synthetic extra", encoding="utf-8")
    report = inspect_private_backup(backup, accounts)
    assert "unexpected_or_missing_backup_files" in report["findings"]
    assert extra.exists()


def test_corrupt_manifest_is_detected(protected_sources):
    backup, accounts, _ = protected_sources
    (backup / "manifest.json").write_text("{invalid", encoding="utf-8")
    report = inspect_private_backup(backup, accounts)
    assert "manifest_invalid" in report["findings"]
    assert not report["manifest_signed_metadata_present"]


def test_missing_account_audit_trigger_is_reported(protected_sources):
    backup, accounts, _ = protected_sources
    with sqlite3.connect(accounts) as db:
        db.execute("DROP TRIGGER protect_account_audit_deletes")
    report = inspect_private_backup(backup, accounts)
    assert "reviewer_account_integrity_not_ready" in report["findings"]
    assert "reviewer_account_audit_not_append_only" in report["findings"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits only")
def test_world_access_is_flagged_on_posix(protected_sources):
    backup, accounts, _ = protected_sources
    (backup / "manifest.json").chmod(0o644)
    report = inspect_private_backup(backup, accounts)
    assert "group_or_other_file_access_detected" in report["findings"]


def test_absent_paths_do_not_create_databases(tmp_path):
    absent = tmp_path / "missing"
    with pytest.raises(ValueError):
        inspect_private_backup(absent, absent / "accounts.sqlite3")
    assert not absent.exists()


def test_symlink_backup_is_not_trusted(protected_sources, tmp_path):
    backup, accounts, _ = protected_sources
    link = tmp_path / "symlink"
    try:
        link.symlink_to(backup, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError):
        inspect_private_backup(link, accounts)
