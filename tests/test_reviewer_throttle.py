"""Offline tests for reviewer abuse throttling; no live accounts or email."""

import sqlite3

import pytest

from src.reviewer_accounts import (
    bootstrap_administrator,
    check_permission,
    change_account_access,
)
from src.reviewer_throttle import (
    MAX_FAILURES,
    LOCK_SECONDS,
    attempts_path,
    authorize_with_throttle,
)
from src.reviewer_auth import ReviewerAccount, hash_password


@pytest.fixture
def accounts(tmp_path):
    p = tmp_path / "accounts.sqlite3"
    bootstrap_administrator("test_admin", "VeryStrong-Offline-Password-2026!", p)
    return p


def test_authorized_login_still_works(accounts):
    assert check_permission(
        "test_admin", "VeryStrong-Offline-Password-2026!",
        "manage_reviewers", accounts
    )


def test_five_failures_block_correct_password_across_calls(accounts):
    for _ in range(MAX_FAILURES):
        assert not check_permission("test_admin", "wrong", "manage_reviewers", accounts)
    assert not check_permission(
        "test_admin", "VeryStrong-Offline-Password-2026!",
        "manage_reviewers", accounts
    )
    with sqlite3.connect(attempts_path(accounts)) as db:
        failed, locked = db.execute(
            "SELECT failed_attempts, locked_until FROM auth_attempts "
            "WHERE account_id='test_admin'"
        ).fetchone()
    assert failed == MAX_FAILURES and locked > 0


def test_lock_expiry_and_recovery_without_secret_storage(tmp_path):
    p = tmp_path / "reviewer_accounts.sqlite3"
    pw = "IndependentSyntheticPassword-2026!"
    account = ReviewerAccount("test_user", "reviewer", hash_password(pw), True)
    for _ in range(MAX_FAILURES):
        assert not authorize_with_throttle(
            account, "test_user", "wrong", "approve_opportunity", p, now=100
        )
    assert not authorize_with_throttle(
        account, "test_user", pw, "approve_opportunity", p, now=101
    )
    assert authorize_with_throttle(
        account, "test_user", pw, "approve_opportunity",
        p, now=100 + LOCK_SECONDS
    )
    with sqlite3.connect(attempts_path(p)) as db:
        assert db.execute(
            "SELECT count(*) FROM auth_attempts WHERE account_id='test_user'"
        ).fetchone()[0] == 0


def test_unknown_account_consumes_budget(accounts):
    for _ in range(MAX_FAILURES):
        assert not check_permission("unknown_account", "bad", "read_reviews", accounts)
    with sqlite3.connect(attempts_path(accounts)) as db:
        assert db.execute(
            "SELECT failed_attempts FROM auth_attempts WHERE account_id='unknown_account'"
        ).fetchone()[0] == MAX_FAILURES


def test_valid_but_unauthorized_role_does_not_consume_password_budget(tmp_path):
    p = tmp_path / "accounts.sqlite3"
    account = ReviewerAccount(
        "test_viewer", "viewer", hash_password("ViewerSyntheticPassword-2026!"), True
    )
    assert not authorize_with_throttle(
        account, "test_viewer", "ViewerSyntheticPassword-2026!",
        "manage_reviewers", p, now=10
    )
    with sqlite3.connect(attempts_path(p)) as db:
        assert db.execute("SELECT count(*) FROM auth_attempts").fetchone()[0] == 0


def test_admin_access_changes_obey_throttle(accounts):
    for _ in range(MAX_FAILURES):
        with pytest.raises(PermissionError):
            change_account_access(
                "test_admin", "wrong", "test_admin",
                role="reviewer", path=accounts
            )
    with pytest.raises(PermissionError):
        change_account_access(
            "test_admin", "VeryStrong-Offline-Password-2026!",
            "test_admin", role="reviewer", path=accounts
        )
    with sqlite3.connect(accounts) as db:
        assert db.execute(
            "SELECT role FROM reviewer_accounts WHERE account_id='test_admin'"
        ).fetchone()[0] == "administrator"


def test_failure_ledger_does_not_modify_existing_database(accounts):
    before = accounts.read_bytes()
    assert not check_permission("test_admin", "incorrect", "manage_reviewers", accounts)
    assert accounts.read_bytes() == before
    with sqlite3.connect(attempts_path(accounts)) as db:
        assert "password" not in str(db.execute(
            "SELECT sql FROM sqlite_master WHERE name='auth_attempts'"
        ).fetchone()[0]).lower()


def test_missing_throttle_storage_fails_closed(accounts):
    ledger = attempts_path(accounts)
    ledger.mkdir()
    with pytest.raises(PermissionError):
        check_permission(
            "test_admin", "VeryStrong-Offline-Password-2026!",
            "manage_reviewers", accounts
        )


def test_invalid_actions_are_denied_before_creating_state(accounts):
    assert not check_permission(
        "test_admin", "VeryStrong-Offline-Password-2026!",
        "send_email", accounts
    )
    assert not attempts_path(accounts).exists()
