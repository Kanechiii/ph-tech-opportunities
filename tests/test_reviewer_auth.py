"""Offline tests for reviewer authentication foundation."""

import pytest

from src.reviewer_auth import (
    ReviewerAccount,
    authenticate_reviewer,
    authorize_reviewer,
    hash_password,
    verify_password,
)


@pytest.fixture
def reviewer():
    return ReviewerAccount(
        account_id="test_reviewer",
        role="reviewer",
        password_hash=hash_password(
            "Example-Strong-Test-Password-2026"
        ),
    )


def test_password_hash_is_not_plaintext():
    password = "Example-Strong-Test-Password-2026"
    stored = hash_password(password)

    assert stored != password
    assert password not in stored
    assert stored.startswith("scrypt$")


def test_password_hash_uses_unique_salts():
    password = "Example-Strong-Test-Password-2026"

    first = hash_password(password)
    second = hash_password(password)

    assert first != second
    assert verify_password(password, first)
    assert verify_password(password, second)


def test_wrong_password_is_rejected(reviewer):
    assert authenticate_reviewer(
        reviewer,
        "Definitely-Wrong-Password-2026",
    ) is False


def test_correct_reviewer_can_approve(reviewer):
    assert authorize_reviewer(
        reviewer,
        "Example-Strong-Test-Password-2026",
        "approve_opportunity",
    ) is True


def test_viewer_cannot_approve():
    viewer = ReviewerAccount(
        account_id="test_viewer",
        role="viewer",
        password_hash=hash_password(
            "Example-Viewer-Password-2026"
        ),
    )

    assert authorize_reviewer(
        viewer,
        "Example-Viewer-Password-2026",
        "approve_opportunity",
    ) is False


def test_suspended_account_is_rejected():
    account = ReviewerAccount(
        account_id="suspended_reviewer",
        role="administrator",
        password_hash=hash_password(
            "Example-Admin-Password-2026"
        ),
        active=False,
    )

    assert authenticate_reviewer(
        account,
        "Example-Admin-Password-2026",
    ) is False

    assert authorize_reviewer(
        account,
        "Example-Admin-Password-2026",
        "manage_reviewers",
    ) is False


def test_reviewer_cannot_manage_accounts(reviewer):
    assert authorize_reviewer(
        reviewer,
        "Example-Strong-Test-Password-2026",
        "manage_reviewers",
    ) is False


def test_review_roles_cannot_authorize_email(reviewer):
    assert authorize_reviewer(
        reviewer,
        "Example-Strong-Test-Password-2026",
        "send_email",
    ) is False


def test_malformed_password_hash_is_rejected():
    malformed = (
        "scrypt$999999999$8$1$"
        + "00" * 16
        + "$"
        + "00" * 32
    )

    assert verify_password(
        "Example-Strong-Test-Password-2026",
        malformed,
    ) is False


def test_password_length_policy():
    with pytest.raises(ValueError, match="12 to 128"):
        hash_password("short")


def test_invalid_account_id_is_rejected():
    account = ReviewerAccount(
        account_id="../operator",
        role="administrator",
        password_hash=hash_password(
            "Example-Admin-Password-2026"
        ),
    )

    assert authorize_reviewer(
        account,
        "Example-Admin-Password-2026",
        "manage_reviewers",
    ) is False


def test_administrator_can_manage_accounts():
    account = ReviewerAccount(
        account_id="test_admin",
        role="administrator",
        password_hash=hash_password(
            "Example-Admin-Password-2026"
        ),
    )

    assert authorize_reviewer(
        account,
        "Example-Admin-Password-2026",
        "manage_reviewers",
    ) is True