"""Offline tests for safe future database migration preflight."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.storage import save_opportunity
from src.reviewer_accounts import bootstrap_administrator
from src.database.migration_preflight import (
    inspect_accounts,
    inspect_migration,
)


@pytest.fixture
def databases(tmp_path):
    opportunities = tmp_path / "opportunities.sqlite3"
    accounts = tmp_path / "reviewer_accounts.sqlite3"

    initialize_database(opportunities)

    bootstrap_administrator(
        "test_admin",
        "Offline-Strong-Password-2026",
        accounts,
    )

    return opportunities, accounts


def test_healthy_databases_pass_preflight(databases):
    opportunities, accounts = databases

    result = inspect_migration(opportunities, accounts)

    assert result["preflight_passed"] is True
    assert result["blockers"] == []
    assert result["migration_performed"] is False
    assert result["records_exported"] is False
    assert result["credentials_exported"] is False


def test_missing_account_database_is_not_created(
    databases, tmp_path
):
    opportunities, _ = databases
    missing = tmp_path / "missing_accounts.sqlite3"

    with pytest.raises(ValueError, match="not found"):
        inspect_migration(opportunities, missing)

    assert not missing.exists()


def test_account_audit_trigger_required(databases):
    _, accounts = databases

    with sqlite3.connect(accounts) as connection:
        connection.execute(
            "DROP TRIGGER protect_account_audit_deletes"
        )

    result = inspect_accounts(accounts)

    assert result["ready"] is False
    assert result["audit_protected"] is False


def test_active_administrator_required(databases):
    opportunities, accounts = databases

    with sqlite3.connect(accounts) as connection:
        connection.execute(
            """
            UPDATE reviewer_accounts
            SET active=0
            WHERE account_id='test_admin'
            """
        )

    result = inspect_migration(opportunities, accounts)

    assert result["preflight_passed"] is False
    assert "reviewer_account_database_not_ready" in result["blockers"]


def test_uncertain_delivery_blocks_preflight(databases):
    opportunities, accounts = databases

    saved = save_opportunity({
        "source_id": "github_blog",
        "url": "https://example.org/test-event",
        "title": "Example Developer Workshop",
        "category": "tech_event",
        "classification_status": "potential_match",
    }, opportunities)

    with sqlite3.connect(opportunities) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO notification_jobs (
                opportunity_id, status
            )
            VALUES (?, 'uncertain')
            """,
            (saved["id"],),
        )

    result = inspect_migration(opportunities, accounts)

    assert result["preflight_passed"] is False
    assert "unresolved_delivery_states" in result["blockers"]
    assert result["unresolved_delivery_jobs"] == 1


def test_preflight_does_not_change_either_database(databases):
    opportunities, accounts = databases

    before_opportunities = opportunities.read_bytes()
    before_accounts = accounts.read_bytes()

    result = inspect_migration(opportunities, accounts)

    assert result["preflight_passed"] is True
    assert opportunities.read_bytes() == before_opportunities
    assert accounts.read_bytes() == before_accounts