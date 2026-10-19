"""Offline tests for authenticated SQLite backup manifests."""

import json

import pytest

from src.database.schema import initialize_database
from src.reviewer_accounts import bootstrap_administrator
from src.database.local_backup import (
    create_local_backup,
    file_hash,
)
from src.database.local_recovery import (
    recover_to_isolated_directory,
)


PASSPHRASE = "Offline-Backup-Secret-2026"


@pytest.fixture
def databases(tmp_path):
    opportunities = tmp_path / "opportunities.sqlite3"
    accounts = tmp_path / "reviewer_accounts.sqlite3"

    initialize_database(opportunities)

    bootstrap_administrator(
        "test_admin",
        "Offline-Admin-Password-2026",
        accounts,
    )

    return opportunities, accounts


def make_authenticated_backup(databases, tmp_path):
    opportunities, accounts = databases
    backup = tmp_path / "authenticated-backup"

    create_local_backup(
        backup,
        opportunities,
        accounts,
        authentication_password=PASSPHRASE,
    )

    return backup


def test_authenticated_backup_recovers_with_correct_passphrase(
    databases, tmp_path
):
    backup = make_authenticated_backup(databases, tmp_path)
    destination = tmp_path / "verified-recovery"

    result = recover_to_isolated_directory(
        backup,
        destination,
        authentication_password=PASSPHRASE,
        require_authenticated=True,
    )

    assert result["recovery_verified"] is True
    assert result["backup_authenticated"] is True

    manifest_text = (
        backup / "manifest.json"
    ).read_text(encoding="utf-8")

    assert PASSPHRASE not in manifest_text
    assert (destination / "opportunities.sqlite3").is_file()
    assert (destination / "reviewer_accounts.sqlite3").is_file()


def test_wrong_passphrase_is_rejected(databases, tmp_path):
    backup = make_authenticated_backup(databases, tmp_path)
    destination = tmp_path / "wrong-password-recovery"

    with pytest.raises(ValueError, match="authentication failed"):
        recover_to_isolated_directory(
            backup,
            destination,
            authentication_password="Incorrect-Backup-Secret-2026",
            require_authenticated=True,
        )

    assert not destination.exists()


def test_missing_passphrase_is_rejected(databases, tmp_path):
    backup = make_authenticated_backup(databases, tmp_path)
    destination = tmp_path / "missing-password-recovery"

    with pytest.raises(ValueError, match="passphrase is required"):
        recover_to_isolated_directory(
            backup,
            destination,
        )

    assert not destination.exists()


def test_changed_manifest_metadata_is_rejected(
    databases, tmp_path
):
    backup = make_authenticated_backup(databases, tmp_path)
    manifest_path = backup / "manifest.json"

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    manifest["created_at_utc"] = "2020-01-01T00:00:00+00:00"

    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="authentication failed"):
        recover_to_isolated_directory(
            backup,
            tmp_path / "tampered-manifest",
            authentication_password=PASSPHRASE,
            require_authenticated=True,
        )


def test_recomputed_checksum_cannot_forge_authentication(
    databases, tmp_path
):
    backup = make_authenticated_backup(databases, tmp_path)
    opportunity_file = backup / "opportunities.sqlite3"
    manifest_path = backup / "manifest.json"

    # Simulate an attacker who can alter files and SHA-256
    # checksums, but does not know the HMAC passphrase.
    with opportunity_file.open("ab") as file:
        file.write(b"unauthorized-modification")

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

    destination = tmp_path / "forged-recovery"

    with pytest.raises(ValueError, match="authentication failed"):
        recover_to_isolated_directory(
            backup,
            destination,
            authentication_password=PASSPHRASE,
            require_authenticated=True,
        )

    assert not destination.exists()


def test_signature_removal_cannot_bypass_strict_mode(
    databases, tmp_path
):
    backup = make_authenticated_backup(databases, tmp_path)
    manifest_path = backup / "manifest.json"

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    del manifest["authentication"]

    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Authenticated backup required",
    ):
        recover_to_isolated_directory(
            backup,
            tmp_path / "downgrade-attempt",
            authentication_password=PASSPHRASE,
            require_authenticated=True,
        )


def test_legacy_backups_remain_recoverable(
    databases, tmp_path
):
    opportunities, accounts = databases
    backup = tmp_path / "legacy-backup"

    create_local_backup(
        backup,
        opportunities,
        accounts,
    )

    destination = tmp_path / "legacy-recovery"

    result = recover_to_isolated_directory(
        backup,
        destination,
    )

    assert result["recovery_verified"] is True
    assert result["backup_authenticated"] is False


def test_strict_mode_rejects_legacy_backups(
    databases, tmp_path
):
    opportunities, accounts = databases
    backup = tmp_path / "legacy-backup"

    create_local_backup(
        backup,
        opportunities,
        accounts,
    )

    destination = tmp_path / "strict-recovery"

    with pytest.raises(
        ValueError,
        match="Authenticated backup required",
    ):
        recover_to_isolated_directory(
            backup,
            destination,
            authentication_password=PASSPHRASE,
            require_authenticated=True,
        )

    assert not destination.exists()