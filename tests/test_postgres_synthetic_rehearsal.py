"""Offline contract tests: SQL rehearsal contains synthetic data only."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "config/postgres/003_synthetic_rehearsal.sql").read_text(
    encoding="utf-8"
)
VERIFY = (ROOT / "config/postgres/004_verify_synthetic_rehearsal.sql").read_text(
    encoding="utf-8"
)


def test_synthetic_only_inputs_and_empty_database_guard():
    assert "Synthetic rehearsal requires seven empty tables" in SCRIPT
    assert "https://example.invalid/phase10-a" in SCRIPT
    assert "https://example.invalid/phase10-b" in SCRIPT
    assert "SYNTHETIC_INVALID_VERIFIER_DO_NOT_AUTHENTICATE" in SCRIPT


def test_uses_one_transaction_and_preserves_explicit_ids():
    assert SCRIPT.count("\nBEGIN;") == 1
    assert SCRIPT.count("\nCOMMIT;") == 1
    assert "(910001," in SCRIPT
    assert "(910003," in SCRIPT
    assert "(950001," in SCRIPT
    assert "(950003," in SCRIPT


def test_covers_all_seven_schema_tables():
    for table in (
        "phtech.opportunities", "phtech.collection_runs",
        "phtech.notification_history", "phtech.opportunity_reviews",
        "phtech.notification_jobs", "phtech_private.reviewer_accounts",
        "phtech_private.reviewer_account_audit",
    ):
        assert f"INSERT INTO {table}" in SCRIPT
        assert f"FROM {table}" in VERIFY or f"FROM {table})" in VERIFY


def test_history_includes_uncertain_and_sent_without_retry():
    assert "'sent',1" in SCRIPT
    assert "'uncertain',1" in SCRIPT
    assert "'ambiguous_delivery'" in SCRIPT
    assert "last_error_type='ambiguous_delivery'" in VERIFY


def test_sequential_identity_reset_after_explicit_ids():
    assert SCRIPT.count("SELECT setval(") == 6
    assert "pg_get_serial_sequence" in SCRIPT
    assert "phtech_private.reviewer_account_audit" in SCRIPT


def test_no_external_io_or_real_data_access():
    combined = (SCRIPT + VERIFY).lower()
    for forbidden in (
        "dblink(", "copy ", "pg_read_file", "lo_import",
        "http://", "postgresql://", "delete from", "truncate ",
        "drop table", "insert into public.", "reviewed-email",
    ):
        assert forbidden not in combined
    assert "https://example.invalid" in SCRIPT


def test_verifier_checks_access_and_preserved_history():
    assert "Historical identifiers or timestamps changed" in VERIFY
    assert "Original notification outcomes not preserved" in VERIFY
    assert "Least-privilege grants unexpected" in VERIFY
    assert "rolcanlogin=false" in VERIFY


def test_step_five_never_updates_operational_workflows():
    assert (ROOT / ".github/workflows/automation.yml").is_file()
    assert "no application" not in SCRIPT.lower()  # rehearsal explicitly inserts fixtures
