"""Authorization regression tests for review-writing operations."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.storage import save_opportunity, get_opportunity
from src.database.review_service import (
    record_review,
    get_review_history,
)
from src.reviewer_accounts import bootstrap_administrator

PASSWORD = "Offline-Security-Password-2026"


@pytest.fixture
def secured_item(tmp_path):
    database = tmp_path / "opportunities.sqlite3"
    accounts = tmp_path / "reviewer_accounts.sqlite3"

    initialize_database(database)

    saved = save_opportunity({
        "source_id": "github_blog",
        "url": "https://github.blog/security-review-test",
        "title": "Free Python Developer Workshop",
        "category": "tech_event",
        "classification_status": "potential_match",
    }, database)

    bootstrap_administrator(
        "test_admin",
        PASSWORD,
        accounts,
    )

    return database, accounts, saved["id"]


def submit_review(
    database,
    accounts,
    opportunity_id,
    password=PASSWORD,
    account_id="test_admin",
    decision="approved",
):
    return record_review(
        opportunity_id,
        decision,
        "https://example.org/official-evidence",
        reviewer_id=account_id,
        reviewer_password=password,
        account_database_path=accounts,
        free_confirmed=(decision == "approved"),
        ph_confirmed=(decision == "approved"),
        open_confirmed=(decision == "approved"),
        database_path=database,
    )


def test_authenticated_admin_can_approve(secured_item):
    database, accounts, opportunity_id = secured_item

    result = submit_review(
        database, accounts, opportunity_id
    )

    assert result["decision"] == "approved"
    assert get_opportunity(
        opportunity_id, database
    )["verification"] == "verified"


def test_missing_password_cannot_approve(secured_item):
    database, accounts, opportunity_id = secured_item

    with pytest.raises(PermissionError):
        submit_review(
            database,
            accounts,
            opportunity_id,
            password=None,
        )

    assert get_review_history(opportunity_id, database) == []


def test_wrong_password_cannot_approve(secured_item):
    database, accounts, opportunity_id = secured_item

    with pytest.raises(PermissionError):
        submit_review(
            database,
            accounts,
            opportunity_id,
            password="Incorrect-Password-2026",
        )

    assert get_review_history(opportunity_id, database) == []
    assert get_opportunity(
        opportunity_id, database
    )["verification"] == "not_verified"


def test_unknown_identity_cannot_approve(secured_item):
    database, accounts, opportunity_id = secured_item

    with pytest.raises(PermissionError):
        submit_review(
            database,
            accounts,
            opportunity_id,
            account_id="unknown_admin",
        )

    assert get_review_history(opportunity_id, database) == []


def test_suspended_account_cannot_approve(secured_item):
    database, accounts, opportunity_id = secured_item

    with sqlite3.connect(accounts) as connection:
        connection.execute(
            """
            UPDATE reviewer_accounts
            SET active = 0
            WHERE account_id = ?
            """,
            ("test_admin",),
        )

    with pytest.raises(PermissionError):
        submit_review(
            database, accounts, opportunity_id
        )

    assert get_review_history(opportunity_id, database) == []


def test_rejection_requires_authentication(secured_item):
    database, accounts, opportunity_id = secured_item

    submit_review(
        database,
        accounts,
        opportunity_id,
        decision="approved",
    )

    with pytest.raises(PermissionError):
        submit_review(
            database,
            accounts,
            opportunity_id,
            decision="rejected",
            password="Incorrect-Password-2026",
        )

    assert get_opportunity(
        opportunity_id, database
    )["verification"] == "verified"
    assert len(get_review_history(opportunity_id, database)) == 1


def test_authorized_rejection_preserves_history(secured_item):
    database, accounts, opportunity_id = secured_item

    submit_review(
        database,
        accounts,
        opportunity_id,
        decision="approved",
    )

    submit_review(
        database,
        accounts,
        opportunity_id,
        decision="rejected",
    )

    history = get_review_history(opportunity_id, database)

    assert len(history) == 2
    assert history[0]["decision"] == "rejected"
    assert history[1]["decision"] == "approved"
    assert all(
        row["reviewer_id"] == "test_admin"
        for row in history
    )

def test_viewer_cannot_approve(secured_item):
    database, accounts, opportunity_id = secured_item

    with sqlite3.connect(accounts) as connection:
        connection.execute(
            """
            UPDATE reviewer_accounts
            SET role = 'viewer'
            WHERE account_id = ?
            """,
            ("test_admin",),
        )

    with pytest.raises(PermissionError):
        submit_review(
            database, accounts, opportunity_id
        )

    assert get_review_history(opportunity_id, database) == []