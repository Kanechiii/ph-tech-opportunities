"""Offline tests for private local reviewer account storage."""

import sqlite3

import pytest

from src.reviewer_accounts import (
    bootstrap_administrator,
    check_permission,
    load_account,
)


@pytest.fixture
def account_store(tmp_path):
    return tmp_path / "reviewer_accounts.sqlite3"


def test_bootstrap_creates_admin(account_store):
    bootstrap_administrator(
        "test_admin",
        "Example-Strong-Password-2026",
        account_store,
    )

    account = load_account("test_admin", account_store)

    assert account is not None
    assert account.role == "administrator"
    assert account.active is True


def test_correct_password_allows_admin_action(account_store):
    bootstrap_administrator(
        "test_admin",
        "Example-Strong-Password-2026",
        account_store,
    )

    assert check_permission(
        "test_admin",
        "Example-Strong-Password-2026",
        "manage_reviewers",
        account_store,
    ) is True


def test_wrong_password_denied(account_store):
    bootstrap_administrator(
        "test_admin",
        "Example-Strong-Password-2026",
        account_store,
    )

    assert check_permission(
        "test_admin",
        "Incorrect-Password-2026",
        "approve_opportunity",
        account_store,
    ) is False


def test_second_bootstrap_is_blocked(account_store):
    bootstrap_administrator(
        "test_admin",
        "Example-Strong-Password-2026",
        account_store,
    )

    with pytest.raises(PermissionError):
        bootstrap_administrator(
            "another_admin",
            "Another-Strong-Password-2026",
            account_store,
        )


def test_missing_account_store_not_created(account_store):
    assert check_permission(
        "missing",
        "Example-Strong-Password-2026",
        "approve_opportunity",
        account_store,
    ) is False

    assert not account_store.exists()


def test_suspended_account_cannot_approve(account_store):
    bootstrap_administrator(
        "test_admin",
        "Example-Strong-Password-2026",
        account_store,
    )

    with sqlite3.connect(account_store) as connection:
        connection.execute(
            """
            UPDATE reviewer_accounts
            SET active = 0
            WHERE account_id = ?
            """,
            ("test_admin",),
        )

    assert check_permission(
        "test_admin",
        "Example-Strong-Password-2026",
        "approve_opportunity",
        account_store,
    ) is False


def test_password_is_never_stored_in_plaintext(account_store):
    password = "Example-Strong-Password-2026"

    bootstrap_administrator(
        "test_admin",
        password,
        account_store,
    )

    with sqlite3.connect(account_store) as connection:
        stored = connection.execute(
            """
            SELECT password_hash FROM reviewer_accounts
            WHERE account_id = ?
            """,
            ("test_admin",),
        ).fetchone()[0]

    assert stored != password
    assert password not in stored
    assert stored.startswith("scrypt$")


def test_email_permission_is_not_granted(account_store):
    bootstrap_administrator(
        "test_admin",
        "Example-Strong-Password-2026",
        account_store,
    )

    assert check_permission(
        "test_admin",
        "Example-Strong-Password-2026",
        "send_email",
        account_store,
    ) is False