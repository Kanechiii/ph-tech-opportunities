"""Test-only helper for authenticated review fixtures.

Never uses real reviewer accounts or the production database.
"""

from pathlib import Path

from src.database.review_service import (
    record_review as real_record_review,
)
from src.reviewer_accounts import bootstrap_administrator

TEST_ACCOUNT_ID = "offline_test_admin"
TEST_PASSWORD = "Offline-Test-Password-2026"


def record_review(*args, **kwargs):
    """Use an isolated account store for existing review tests."""

    database = kwargs.get("database_path")

    if database is None:
        raise ValueError(
            "Test reviews require an explicit temporary database."
        )

    database = Path(database)

    account_database = (
        database.parent
        / f"{database.stem}_reviewer_accounts.sqlite3"
    )

    if not account_database.exists():
        bootstrap_administrator(
            TEST_ACCOUNT_ID,
            TEST_PASSWORD,
            account_database,
        )

    # Prevent a test from supplying a different identity
    # or overriding the trusted test account store.
    kwargs.pop("reviewer_id", None)
    kwargs.pop("reviewer_password", None)
    kwargs.pop("account_database_path", None)

    return real_record_review(
        *args,
        reviewer_id=TEST_ACCOUNT_ID,
        reviewer_password=TEST_PASSWORD,
        account_database_path=account_database,
        **kwargs,
    )