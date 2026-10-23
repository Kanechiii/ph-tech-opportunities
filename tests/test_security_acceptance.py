"""Synthetic, offline final security acceptance regression tests."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.reviewer_accounts import bootstrap_administrator
from src.reviewer_throttle import attempts_path
from src.security_acceptance import assess_phase11, OPEN_SECURITY_GAPS


@pytest.fixture
def dbs(tmp_path):
    opportunity = tmp_path / "opportunities.sqlite3"
    accounts = tmp_path / "reviewer_accounts.sqlite3"
    initialize_database(opportunity)
    bootstrap_administrator(
        "synthetic_admin", "Offline-Security-Acceptance-Password-2026!",
        accounts,
    )
    return opportunity, accounts


def test_valid_sources_do_not_grant_production_authorization(dbs):
    result = assess_phase11(*dbs)
    assert result["phase_foundations_acceptable"]
    assert result["production_ready"] is False
    assert result["production_cutover_authorized"] is False
    assert result["sqlite_remains_authoritative"]
    assert result["reviewed_email_automation_enabled"] is False


def test_open_security_gaps_are_not_silently_closed(dbs):
    report = assess_phase11(*dbs)
    assert set(report["outstanding_security_gaps"]) == set(OPEN_SECURITY_GAPS)
    assert "backup_contents_are_not_encrypted" in report["outstanding_security_gaps"]
    assert "password_recovery_not_implemented" in report["outstanding_security_gaps"]
    assert "reviewed_email_delivery_lacks_reviewer_authentication" in (
        report["outstanding_security_gaps"]
    )


def test_ambiguous_delivery_is_reported_without_mutation(dbs):
    with sqlite3.connect(dbs[0]) as connection:
        connection.execute(
            "INSERT INTO opportunities (source_id,url,title) "
            "VALUES ('synthetic','https://example.invalid/x','Synthetic')"
        )
        connection.execute(
            "INSERT INTO notification_jobs(opportunity_id,status) "
            "VALUES (1,'uncertain')"
        )
    before = [path.read_bytes() for path in dbs]
    report = assess_phase11(*dbs)
    assert "ambiguous_notification_states_remain" in report["findings"]
    assert report["notification_job_states"]["uncertain"] == 1
    assert before == [path.read_bytes() for path in dbs]


def test_missing_account_audit_triggers_fails_foundation_check(dbs):
    with sqlite3.connect(dbs[1]) as connection:
        connection.execute("DROP TRIGGER protect_account_audit_deletes")
    result = assess_phase11(*dbs)
    assert result["phase_foundations_acceptable"] is False
    assert "append_only_account_audit_triggers_missing" in result["findings"]


def test_missing_databases_are_never_created(dbs, tmp_path):
    missing = tmp_path / "not_here.sqlite3"
    with pytest.raises(ValueError):
        assess_phase11(dbs[0], missing)
    assert not missing.exists()


def test_security_report_preserves_existing_files_and_hides_secrets(dbs):
    before = [path.read_bytes() for path in dbs]
    report = assess_phase11(*dbs)
    assert before == [path.read_bytes() for path in dbs]
    assert not report["files_modified"]
    assert not report["secrets_exported"]
    assert not report["email_sent"]
    assert not report["postgres_connected"]
    assert "Offline-Security-Acceptance-Password" not in str(report)
    assert "password_hash" not in str(report)


def test_optional_throttle_state_is_not_opened_or_exposed(dbs):
    ledger = attempts_path(dbs[1])
    assert not ledger.exists()
    report = assess_phase11(*dbs)
    assert report["throttle_ledger_present"] is False
    assert not ledger.exists()
