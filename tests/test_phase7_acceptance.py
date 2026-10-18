"""Phase 7 offline security and reliability acceptance tests."""

import sqlite3
from unittest.mock import patch

import pytest

from src.database.schema import initialize_database
from src.database.storage import save_opportunity, get_opportunity
from src.database.review_service import (
    record_review,
    get_review_history,
)
from src.database.health_audit import audit_database
from src.database.migration_preflight import inspect_migration
from src.reviewer_accounts import (
    bootstrap_administrator,
    change_account_access,
    check_permission,
)

PASSWORD = "Offline-Acceptance-Password-2026"


@pytest.fixture
def environment(tmp_path):
    opportunities = tmp_path / "opportunities.sqlite3"
    accounts = tmp_path / "reviewer_accounts.sqlite3"

    initialize_database(opportunities)
    bootstrap_administrator(
        "test_admin",
        PASSWORD,
        accounts,
    )

    saved = save_opportunity({
        "source_id": "github_blog",
        "url": "https://example.org/acceptance-workshop",
        "title": "Example Python Developer Workshop",
        "category": "tech_event",
        "classification_status": "potential_match",
    }, opportunities)

    return opportunities, accounts, saved["id"]


def approve(opportunities, accounts, opportunity_id,
            password=PASSWORD):
    return record_review(
        opportunity_id,
        "approved",
        "https://example.org/public-evidence",
        reviewer_id="test_admin",
        reviewer_password=password,
        account_database_path=accounts,
        free_confirmed=True,
        ph_confirmed=True,
        open_confirmed=True,
        database_path=opportunities,
    )


def test_health_audit_passes_on_valid_database(environment):
    opportunities, _, _ = environment

    result = audit_database(opportunities)

    assert result["healthy"] is True
    assert result["schema_version"] == 3
    assert result["database_modified"] is False


def test_migration_preflight_passes_without_export(environment):
    opportunities, accounts, _ = environment

    result = inspect_migration(opportunities, accounts)

    assert result["preflight_passed"] is True
    assert result["migration_performed"] is False
    assert result["credentials_exported"] is False


def test_invalid_password_cannot_change_review_history(environment):
    opportunities, accounts, opportunity_id = environment

    with pytest.raises(PermissionError):
        approve(
            opportunities,
            accounts,
            opportunity_id,
            password="Incorrect-Password-2026",
        )

    assert get_review_history(
        opportunity_id, opportunities
    ) == []


def test_revoked_role_blocks_subsequent_approval(environment):
    opportunities, accounts, opportunity_id = environment

    # Add a second account so the last-admin safeguard
    # remains effective.
    with sqlite3.connect(accounts) as connection:
        connection.execute(
            """
            INSERT INTO reviewer_accounts (
                account_id, role, password_hash, active
            )
            SELECT 'test_reviewer', 'reviewer',
                   password_hash, 1
            FROM reviewer_accounts
            WHERE account_id = 'test_admin'
            """
        )

    change_account_access(
        "test_admin",
        PASSWORD,
        "test_reviewer",
        role="viewer",
        path=accounts,
    )

    assert check_permission(
        "test_reviewer",
        PASSWORD,
        "approve_opportunity",
        accounts,
    ) is False


def test_approved_review_history_is_preserved(environment):
    opportunities, accounts, opportunity_id = environment

    approve(opportunities, accounts, opportunity_id)

    history = get_review_history(
        opportunity_id, opportunities
    )

    assert len(history) == 1
    assert history[0]["decision"] == "approved"
    assert history[0]["reviewer_id"] == "test_admin"
    assert get_opportunity(
        opportunity_id, opportunities
    )["verification"] == "verified"


def test_account_audit_history_is_immutable(environment):
    _, accounts, _ = environment

    with sqlite3.connect(accounts) as connection:
        connection.execute(
            """
            INSERT INTO reviewer_accounts (
                account_id, role, password_hash, active
            )
            SELECT 'test_reviewer', 'reviewer',
                   password_hash, 1
            FROM reviewer_accounts
            WHERE account_id = 'test_admin'
            """
        )

    change_account_access(
        "test_admin",
        PASSWORD,
        "test_reviewer",
        active=False,
        path=accounts,
    )

    with sqlite3.connect(accounts) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                DELETE FROM reviewer_account_audit
                """
            )


def test_ambiguous_delivery_blocks_migration(environment):
    opportunities, accounts, opportunity_id = environment

    with sqlite3.connect(opportunities) as connection:
        connection.execute(
            """
            INSERT INTO notification_jobs (
                opportunity_id, status
            )
            VALUES (?, 'uncertain')
            """,
            (opportunity_id,),
        )

    result = inspect_migration(opportunities, accounts)

    assert result["preflight_passed"] is False
    assert "unresolved_delivery_states" in result["blockers"]


def test_read_only_audits_do_not_send_or_write(environment):
    opportunities, accounts, _ = environment

    original_opportunities = opportunities.read_bytes()
    original_accounts = accounts.read_bytes()

    with patch(
        "src.notification_delivery.send_email"
    ) as mock_send:
        audit_database(opportunities)
        inspect_migration(opportunities, accounts)

    mock_send.assert_not_called()

    assert opportunities.read_bytes() == original_opportunities
    assert accounts.read_bytes() == original_accounts