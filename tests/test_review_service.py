"""Offline tests for SQLite manual review history."""

import sqlite3

import pytest

from src.database.schema import (
    SCHEMA_VERSION,
    connect_database,
    initialize_database,
)
from src.database.storage import (
    get_opportunity,
    save_opportunity,
)
from src.database.review_service import (
    get_latest_review,
    get_review_history,
)
from src.notification_policy import assess_notification_policy
from review_helpers import record_review


@pytest.fixture
def reviewed_item(tmp_path):
    path = tmp_path / "reviews.sqlite3"
    initialize_database(path)

    item = {
        "source_id": "github_blog",
        "url": "https://github.blog/sample",
        "title": "Example Python Developer Workshop",
        "category": "tech_event",
        "classification_status": "potential_match",
        "verification": "not_verified",
        "free_status": "unknown",
        "ph_eligibility": "unknown",
        "deadline_status": "unknown",
        "published_at": None,
    }

    saved = save_opportunity(item, path)
    return path, saved["id"], item


def approve(path, opportunity_id):
    return record_review(
        opportunity_id,
        "approved",
        "https://example.org/official-listing",
        free_confirmed=True,
        ph_confirmed=True,
        open_confirmed=True,
        database_path=path,
    )


def test_version_two_review_table(reviewed_item):
    path, _, _ = reviewed_item

    connection = connect_database(path)
    try:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='opportunity_reviews'
            """
        ).fetchone()

        assert version == SCHEMA_VERSION == 3
        assert table is not None
    finally:
        connection.close()


def test_approval_records_evidence(reviewed_item):
    path, opportunity_id, _ = reviewed_item
    result = approve(path, opportunity_id)

    record = get_opportunity(opportunity_id, path)
    review = get_latest_review(opportunity_id, path)

    assert result["decision"] == "approved"
    assert record["verification"] == "verified"
    assert record["free_status"] == "confirmed_free"
    assert record["ph_eligibility"] == "confirmed"
    assert record["deadline_status"] == "open"
    assert review["method"] == "manual"
    assert review["evidence_url"].startswith("https://")


def test_incomplete_approval_rejected(reviewed_item):
    path, opportunity_id, _ = reviewed_item

    with pytest.raises(ValueError, match="confirmations"):
        record_review(
            opportunity_id,
            "approved",
            "https://example.org/details",
            free_confirmed=True,
            ph_confirmed=False,
            open_confirmed=True,
            database_path=path,
        )

    assert get_review_history(opportunity_id, path) == []


def test_rejection_revokes_previous_approval(reviewed_item):
    path, opportunity_id, _ = reviewed_item
    approve(path, opportunity_id)

    record_review(
        opportunity_id,
        "rejected",
        "https://example.org/updated-details",
        database_path=path,
    )

    record = get_opportunity(opportunity_id, path)
    history = get_review_history(opportunity_id, path)

    assert record["verification"] == "rejected"
    assert record["free_status"] == "unknown"
    assert len(history) == 2
    assert history[0]["decision"] == "rejected"
    assert history[1]["decision"] == "approved"


def test_review_history_cannot_be_modified(reviewed_item):
    path, opportunity_id, _ = reviewed_item
    result = approve(path, opportunity_id)

    connection = connect_database(path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE opportunity_reviews
                SET decision = 'rejected'
                WHERE id = ?
                """,
                (result["review_id"],),
            )
    finally:
        connection.close()


def test_rss_refresh_preserves_approval(reviewed_item):
    path, opportunity_id, item = reviewed_item
    approve(path, opportunity_id)

    save_opportunity(item, path)

    record = get_opportunity(opportunity_id, path)
    assert record["verification"] == "verified"
    assert record["ph_eligibility"] == "confirmed"


def test_invalid_evidence_rejected(reviewed_item):
    path, opportunity_id, _ = reviewed_item

    with pytest.raises(ValueError, match="HTTPS"):
        record_review(
            opportunity_id,
            "rejected",
            "http://example.org/details",
            database_path=path,
        )


def test_stored_review_remains_preliminary(reviewed_item):
    path, opportunity_id, _ = reviewed_item
    approve(path, opportunity_id)

    opportunity = get_opportunity(opportunity_id, path)
    review = get_latest_review(opportunity_id, path)

    result = assess_notification_policy(
        opportunity,
        review,
    )

    assert result["policy_passed"] is True
    assert result["decision"] == "preliminary_pass"
    assert result["delivery_authorized"] is False