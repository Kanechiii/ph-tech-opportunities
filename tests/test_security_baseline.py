"""Offline security baseline tests on synthetic files only."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.reviewer_accounts import bootstrap_administrator
from src.security_baseline import inspect_security_baseline


@pytest.fixture
def sources(tmp_path):
    opportunities = tmp_path / "opportunities.sqlite3"
    accounts = tmp_path / "reviewer_accounts.sqlite3"
    initialize_database(opportunities)
    bootstrap_administrator(
        "synthetic_admin", "Synthetic-Security-Baseline-Password-2026!",
        accounts,
    )
    return opportunities, accounts


def test_healthy_accounts_do_not_imply_production_ready(sources):
    result = inspect_security_baseline(*sources)
    assert result["security_baseline_ready_for_further_hardening"]
    assert result["active_administrators"] == 1
    assert not result["production_ready"]
    assert not result["email_sent"]


def test_known_auth_and_data_risks_are_visible(sources):
    report = inspect_security_baseline(*sources)
    assert "login_rate_limiting_not_implemented" in report["known_limitations"]
    assert "cross_database_authorization_not_atomic" in report["known_limitations"]
    assert "backup_manifest_authentication_does_not_encrypt_contents" in report["known_limitations"]
    assert "reviewed_email_send_requires_local_confirmation_not_reviewer_auth" in report["known_limitations"]


def test_ambiguous_jobs_are_flagged_without_reset(sources):
    with sqlite3.connect(sources[0]) as con:
        con.execute(
            "INSERT INTO opportunities(source_id,url,title) "
            "VALUES ('synthetic','https://example.invalid/1','Item')"
        )
        con.execute(
            "INSERT INTO notification_jobs(opportunity_id,status) "
            "VALUES (1,'uncertain')"
        )
    report = inspect_security_baseline(*sources)
    assert "unresolved_delivery_states_present" in report["findings"]
    with sqlite3.connect(sources[0]) as con:
        assert con.execute("SELECT status FROM notification_jobs").fetchone()[0] == "uncertain"


def test_missing_database_is_not_created(sources, tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(ValueError):
        inspect_security_baseline(sources[0], missing)
    assert not missing.exists()


def test_same_database_refused(sources):
    with pytest.raises(ValueError):
        inspect_security_baseline(sources[0], sources[0])


def test_audit_trigger_missing_is_not_hidden(sources):
    with sqlite3.connect(sources[1]) as con:
        con.execute("DROP TRIGGER protect_account_audit_deletes")
    result = inspect_security_baseline(*sources)
    assert not result["security_baseline_ready_for_further_hardening"]
    assert "reviewer_audit_triggers_missing" in result["findings"]


def test_report_contains_no_verifiers_or_passwords_and_preserves_files(sources):
    before = [p.read_bytes() for p in sources]
    report = inspect_security_baseline(*sources)
    rendered = str(report)
    assert "Synthetic-Security-Baseline-Password" not in rendered
    assert "password_hash" not in rendered
    assert before == [p.read_bytes() for p in sources]
    assert not report["credentials_exported"]
    assert not report["data_modified"]
    assert not report["postgres_connected"]
