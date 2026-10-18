"""Offline tests for role revocation and account audit integrity."""

import sqlite3

import pytest

from src.reviewer_accounts import (
    bootstrap_administrator,
    change_account_access,
    check_permission,
    initialize_accounts,
)

PASSWORD = "Offline-Admin-Password-2026"


@pytest.fixture
def accounts(tmp_path):
    path = tmp_path / "reviewer_accounts.sqlite3"

    bootstrap_administrator("test_admin", PASSWORD, path)

    # A local test fixture, not public user registration.
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO reviewer_accounts (
                account_id, role, password_hash, active
            )
            SELECT 'test_reviewer', 'reviewer',
                   password_hash, 1
            FROM reviewer_accounts
            WHERE account_id='test_admin'
            """
        )

    return path


def audit_rows(path):
    with sqlite3.connect(path) as connection:
        return connection.execute(
            """
            SELECT actor_id, target_id, action,
                   old_value, new_value
            FROM reviewer_account_audit
            ORDER BY id
            """
        ).fetchall()


def test_existing_store_initialization_preserves_accounts(accounts):
    initialize_accounts(accounts)

    assert check_permission(
        "test_admin", PASSWORD,
        "manage_reviewers", accounts,
    ) is True


def test_admin_can_suspend_reviewer(accounts):
    assert change_account_access(
        "test_admin", PASSWORD,
        "test_reviewer",
        active=False, path=accounts,
    ) is True

    assert check_permission(
        "test_reviewer", PASSWORD,
        "approve_opportunity", accounts,
    ) is False

    rows = audit_rows(accounts)
    assert len(rows) == 1
    assert rows[0][2:] == ("status_changed", "1", "0")


def test_admin_can_reactivate_reviewer(accounts):
    change_account_access(
        "test_admin", PASSWORD,
        "test_reviewer", active=False, path=accounts,
    )

    change_account_access(
        "test_admin", PASSWORD,
        "test_reviewer", active=True, path=accounts,
    )

    assert check_permission(
        "test_reviewer", PASSWORD,
        "approve_opportunity", accounts,
    ) is True
    assert len(audit_rows(accounts)) == 2


def test_role_demotion_revokes_approval(accounts):
    change_account_access(
        "test_admin", PASSWORD,
        "test_reviewer", role="viewer", path=accounts,
    )

    assert check_permission(
        "test_reviewer", PASSWORD,
        "approve_opportunity", accounts,
    ) is False

    assert check_permission(
        "test_reviewer", PASSWORD,
        "read_opportunities", accounts,
    ) is True


def test_wrong_admin_password_cannot_change_roles(accounts):
    with pytest.raises(PermissionError):
        change_account_access(
            "test_admin",
            "Incorrect-Password-2026",
            "test_reviewer",
            role="viewer",
            path=accounts,
        )

    assert audit_rows(accounts) == []
    assert check_permission(
        "test_reviewer", PASSWORD,
        "approve_opportunity", accounts,
    ) is True


def test_reviewer_cannot_manage_accounts(accounts):
    with pytest.raises(PermissionError):
        change_account_access(
            "test_reviewer", PASSWORD,
            "test_admin",
            active=False, path=accounts,
        )

    assert audit_rows(accounts) == []


def test_last_admin_cannot_be_suspended_or_demoted(accounts):
    for changes in ({"active": False}, {"role": "viewer"}):
        with pytest.raises(PermissionError, match="last active"):
            change_account_access(
                "test_admin", PASSWORD,
                "test_admin", path=accounts,
                **changes,
            )

    assert check_permission(
        "test_admin", PASSWORD,
        "manage_reviewers", accounts,
    ) is True
    assert audit_rows(accounts) == []


def test_account_audit_history_is_append_only(accounts):
    change_account_access(
        "test_admin", PASSWORD,
        "test_reviewer", active=False, path=accounts,
    )

    with sqlite3.connect(accounts) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE reviewer_account_audit
                SET new_value = '1'
                WHERE id = 1
                """
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM reviewer_account_audit WHERE id = 1"
            )

    assert len(audit_rows(accounts)) == 1