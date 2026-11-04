"""Offline readiness checks never authorize real-data encryption or restoration."""

import os
import pytest

from src.database.encrypted_backup_readiness import (
    inspect_private_backup_destination, assess_encrypted_backup_release,
)


def test_fresh_destination_is_assessed_without_being_created(tmp_path):
    target = tmp_path / "encrypted-bundle"
    report = inspect_private_backup_destination(target)
    assert report["preflight_passed"] is True
    assert report["production_encryption_authorized"] is False
    assert report["windows_acl_approved"] is False
    assert report["atomic_noreplace_approved"] is False
    assert report["operational_data_accessed"] is False
    assert not target.exists()


def test_existing_destination_is_refused_without_changes(tmp_path):
    target = tmp_path / "protected"
    target.mkdir()
    marker = target / "preserve.txt"
    marker.write_text("unchanged")
    report = inspect_private_backup_destination(target)
    assert report["preflight_passed"] is False
    assert report["checks"]["destination_absent"] is False
    assert marker.read_text() == "unchanged"


def test_nonexistent_parent_is_refused_without_creating_anything(tmp_path):
    target = tmp_path / "absent" / "bundle"
    report = inspect_private_backup_destination(target)
    assert report["preflight_passed"] is False
    assert report["checks"]["parent_exists"] is False
    assert not target.parent.exists()


def test_linked_parent_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink privileges unavailable")
    report = inspect_private_backup_destination(link / "bundle")
    assert report["preflight_passed"] is False
    assert report["checks"]["all_path_ancestors_no_symlinks"] is False


def test_release_gate_refuses_missing_or_invalid_evidence():
    with pytest.raises(ValueError):
        assess_encrypted_backup_release({})
    with pytest.raises(ValueError):
        assess_encrypted_backup_release({"sqlite_consistent_snapshot": True})
    report = inspect_private_backup_destination(".")
    assert report["production_encryption_authorized"] is False


def test_release_gate_never_auto_approves_even_all_flags_true():
    names = {
        "sqlite_consistent_snapshot",
        "encrypted_payloads_authenticated",
        "private_windows_acl_verified",
        "atomic_noreplace_tested",
        "crash_recovery_tested",
        "isolated_sqlite_recovery_verified",
        "history_parity_verified",
        "secret_management_reviewed",
    }
    evidence = dict.fromkeys(names, True)
    report = assess_encrypted_backup_release(evidence)
    assert report["evidence_claims_complete"] is True
    assert report["production_release_approved"] is False
    assert report["real_data_backup_enabled"] is False
    assert report["recovery_cutover_enabled"] is False
    evidence["history_parity_verified"] = False
    report = assess_encrypted_backup_release(evidence)
    assert report["evidence_claims_complete"] is False
    assert report["missing_evidence"] == ["history_parity_verified"]


def test_evidence_rejects_nonboolean_truthy_values():
    names = {
        "sqlite_consistent_snapshot",
        "encrypted_payloads_authenticated",
        "private_windows_acl_verified",
        "atomic_noreplace_tested",
        "crash_recovery_tested",
        "isolated_sqlite_recovery_verified",
        "history_parity_verified",
        "secret_management_reviewed",
    }
    evidence = dict.fromkeys(names, True)
    evidence["private_windows_acl_verified"] = 1
    with pytest.raises(ValueError):
        assess_encrypted_backup_release(evidence)
