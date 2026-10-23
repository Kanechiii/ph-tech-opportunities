"""Offline acceptance checks for Phase 10 production-readiness boundaries."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.local_backup import copy_sqlite
from src.database.phase10_acceptance import (
    REMAINING_PRODUCTION_BLOCKERS,
    assess_phase10,
)
from src.reviewer_accounts import bootstrap_administrator


@pytest.fixture
def sources(tmp_path):
    local = tmp_path / "local.sqlite3"
    accounts = tmp_path / "accounts.sqlite3"
    hosted = tmp_path / "hosted.sqlite3"
    initialize_database(local)
    bootstrap_administrator(
        "synthetic_admin", "Offline-Phase10-Acceptance-Password-2026",
        accounts,
    )
    with sqlite3.connect(local) as conn:
        conn.execute(
            "INSERT INTO opportunities (source_id,url,title) "
            "VALUES ('synthetic','https://example.invalid/event','Event')"
        )
    copy_sqlite(local, hosted)
    return local, accounts, hosted


def test_matching_sources_still_do_not_authorize_production(sources):
    result = assess_phase10(*sources)
    assert result["source_inventory_complete"]
    assert result["source_history_equal"]
    assert result["source_blockers"] == []
    assert result["production_ready"] is False
    assert result["cutover_authorized"] is False
    assert result["storage_backend"] == "sqlite"


def test_divergence_remains_explicit_blocker(sources):
    with sqlite3.connect(sources[2]) as conn:
        conn.execute(
            "UPDATE opportunities SET title='Divergent' WHERE id=1"
        )
    result = assess_phase10(*sources)
    assert "histories_diverged" in result["source_blockers"]
    assert not result["source_history_equal"]
    assert not result["cutover_authorized"]


def test_uncertain_and_sending_remain_quarantined(sources):
    with sqlite3.connect(sources[0]) as conn:
        conn.execute(
            "INSERT INTO notification_jobs (opportunity_id,status) "
            "VALUES(1,'uncertain')"
        )
    with sqlite3.connect(sources[2]) as conn:
        conn.execute(
            "INSERT INTO notification_jobs (opportunity_id,status) "
            "VALUES(1,'sending')"
        )
    result = assess_phase10(*sources)
    assert "local_ambiguous_delivery" in result["source_blockers"]
    assert "hosted_ambiguous_delivery" in result["source_blockers"]
    assert result["unattended_reviewed_email_enabled"] is False


def test_all_known_production_blockers_stay_visible(sources):
    report = assess_phase10(*sources)
    assert set(report["required_future_capabilities"]) == set(
        REMAINING_PRODUCTION_BLOCKERS
    )
    assert len(report["required_future_capabilities"]) >= 6
    assert report["postgres_staging_only"]


def test_assessment_does_not_modify_any_source_database(sources):
    before = [path.read_bytes() for path in sources]
    result = assess_phase10(*sources)
    assert before == [path.read_bytes() for path in sources]
    assert not result["records_exported"]
    assert not result["source_files_modified"]
    assert not result["postgres_connected"]
    assert not result["email_sent"]


def test_missing_database_is_not_created(sources, tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError):
        assess_phase10(sources[0], sources[1], missing)
    assert not missing.exists()
