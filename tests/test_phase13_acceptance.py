"""Offline-only Phase 13 acceptance and fail-closed status tests."""

from src.database.phase13_acceptance import (
    UNRESOLVED_BLOCKERS,
    assess_synthetic_encryption,
)


def test_synthetic_acceptance_passes_without_authorizing_real_backup():
    result = assess_synthetic_encryption()
    assert result["gate"] == "phase13-synthetic-acceptance"
    assert result["all_synthetic_checks_passed"] is True
    assert len(result["checks"]) == 5
    assert all(result["checks"].values())
    assert result["operational_encrypted_backup_enabled"] is False
    assert result["real_sqlite_access_performed"] is False
    assert result["restoration_authorized"] is False
    assert result["production_ready"] is False
    assert result["production_cutover_authorized"] is False
    assert result["reviewed_email_automation_enabled"] is False


def test_acceptance_lists_explicit_real_data_blockers():
    result = assess_synthetic_encryption()
    assert result["outstanding_production_blockers"] == list(UNRESOLVED_BLOCKERS)
    assert len(UNRESOLVED_BLOCKERS) >= 6
    assert any("NTFS ACLs" in b for b in UNRESOLVED_BLOCKERS)
    assert any("SQLite" in b for b in UNRESOLVED_BLOCKERS)


def test_acceptance_is_repeatable_without_persistent_artifacts():
    first = assess_synthetic_encryption()
    second = assess_synthetic_encryption()
    assert first == second


def test_acceptance_report_contains_no_fixture_values():
    from src.database.phase13_acceptance import TEST_BYTES, TEST_PASSPHRASE

    result = assess_synthetic_encryption()
    serialized = repr(result)
    assert TEST_PASSPHRASE not in serialized
    for value in TEST_BYTES.values():
        assert repr(value) not in serialized
        assert value.decode("ascii") not in serialized


def test_acceptance_failure_does_not_claim_success(monkeypatch):
    import src.database.phase13_acceptance as module

    original = module.read_synthetic_encrypted_bundle

    def incorrect_read(*args, **kwargs):
        result = original(*args, **kwargs)
        if len(result) == 2:
            return {**result, "opportunities.sqlite3": b"fictional-modification"}
        return result

    monkeypatch.setattr(module, "read_synthetic_encrypted_bundle", incorrect_read)
    # Deliberately injected verification failure must fail closed, never
    # assert operational readiness even when the synthetic check is false.
    result = assess_synthetic_encryption()
    assert result["all_synthetic_checks_passed"] is False
    assert result["production_ready"] is False
    assert result["operational_encrypted_backup_enabled"] is False
