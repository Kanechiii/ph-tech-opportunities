"""Offline tests for transactional notification queue."""

from datetime import datetime, timezone

import pytest

from src.database.schema import (
    connect_database,
    initialize_database,
)
from src.database.storage import save_opportunity
from src.database.review_service import record_review
from src.database.notification_queue import (
    enqueue_notification,
    get_job,
    list_jobs,
    claim_notification,
    finish_attempt,
    retry_failed,
    quarantine_stale_claims,
)


@pytest.fixture
def ready_item(tmp_path):
    path = tmp_path / "queue_test.sqlite3"
    initialize_database(path)

    saved = save_opportunity({
        "source_id": "github_blog",
        "url": "https://github.blog/example-workshop",
        "title": "Example Developer Workshop",
        "category": "tech_event",
        "classification_status": "potential_match",
        "verification": "not_verified",
        "free_status": "unknown",
        "ph_eligibility": "unknown",
        "deadline_status": "unknown",
        "published_at": None,
    }, path)

    opportunity_id = saved["id"]

    record_review(
        opportunity_id,
        "approved",
        "https://example.org/official-listing",
        free_confirmed=True,
        ph_confirmed=True,
        open_confirmed=True,
        database_path=path,
    )

    return path, opportunity_id


def test_enqueue_creates_pending_job(ready_item):
    path, opportunity_id = ready_item

    result = enqueue_notification(opportunity_id, path)

    assert result["created"] is True
    assert result["status"] == "pending"
    assert get_job(result["id"], path)["attempt_count"] == 0


def test_duplicate_enqueue_reuses_job(ready_item):
    path, opportunity_id = ready_item

    first = enqueue_notification(opportunity_id, path)
    second = enqueue_notification(opportunity_id, path)

    assert second["created"] is False
    assert second["id"] == first["id"]
    assert len(list_jobs(path)) == 1


def test_claim_is_exclusive(ready_item):
    path, opportunity_id = ready_item

    job = enqueue_notification(opportunity_id, path)
    token = claim_notification(job["id"], path)

    assert isinstance(token, str)
    assert claim_notification(job["id"], path) is None

    record = get_job(job["id"], path)
    assert record["status"] == "sending"
    assert record["attempt_count"] == 1


def test_successful_submission_is_terminal(ready_item):
    path, opportunity_id = ready_item

    job = enqueue_notification(opportunity_id, path)
    token = claim_notification(job["id"], path)

    assert finish_attempt(
        job["id"], token, "sent", path
    ) is True

    assert get_job(job["id"], path)["status"] == "sent"
    assert retry_failed(job["id"], path) is False
    assert claim_notification(job["id"], path) is None

    duplicate = enqueue_notification(opportunity_id, path)
    assert duplicate["created"] is False
    assert duplicate["status"] == "sent"


def test_failed_job_requires_explicit_retry(ready_item):
    path, opportunity_id = ready_item

    job = enqueue_notification(opportunity_id, path)
    token = claim_notification(job["id"], path)

    assert finish_attempt(
        job["id"], token, "failed", path
    ) is True

    assert claim_notification(job["id"], path) is None
    assert retry_failed(job["id"], path) is True

    new_token = claim_notification(job["id"], path)
    assert new_token is not None
    assert new_token != token
    assert get_job(job["id"], path)["attempt_count"] == 2


def test_uncertain_delivery_is_not_retried(ready_item):
    path, opportunity_id = ready_item

    job = enqueue_notification(opportunity_id, path)
    token = claim_notification(job["id"], path)

    assert finish_attempt(
        job["id"], token, "uncertain", path
    ) is True

    assert retry_failed(job["id"], path) is False
    assert claim_notification(job["id"], path) is None


def test_abandoned_claim_becomes_uncertain(ready_item):
    path, opportunity_id = ready_item

    job = enqueue_notification(opportunity_id, path)
    claim_notification(job["id"], path)

    connection = connect_database(path)
    try:
        connection.execute(
            """
            UPDATE notification_jobs
            SET claimed_at = '2020-01-01 00:00:00'
            WHERE id = ?
            """,
            (job["id"],),
        )
        connection.commit()
    finally:
        connection.close()

    assert quarantine_stale_claims(path, minutes=30) == 1
    assert get_job(job["id"], path)["status"] == "uncertain"
    assert retry_failed(job["id"], path) is False


def test_rejected_review_blocks_claim(ready_item):
    path, opportunity_id = ready_item

    job = enqueue_notification(opportunity_id, path)

    record_review(
        opportunity_id,
        "rejected",
        "https://example.org/updated-listing",
        database_path=path,
    )

    assert claim_notification(job["id"], path) is None
    assert get_job(job["id"], path)["status"] == "pending"


def test_unreviewed_opportunity_cannot_be_queued(tmp_path):
    path = tmp_path / "unreviewed.sqlite3"
    initialize_database(path)

    saved = save_opportunity({
        "source_id": "github_blog",
        "url": "https://github.blog/not-reviewed",
        "title": "Potential Tech Event",
        "category": "tech_event",
        "classification_status": "potential_match",
    }, path)

    with pytest.raises(ValueError, match="not review-eligible"):
        enqueue_notification(saved["id"], path)


def test_incorrect_claim_token_cannot_finish(ready_item):
    path, opportunity_id = ready_item

    job = enqueue_notification(opportunity_id, path)
    token = claim_notification(job["id"], path)

    assert finish_attempt(
        job["id"], "incorrect-token", "sent", path
    ) is False

    assert get_job(job["id"], path)["status"] == "sending"

    assert finish_attempt(
        job["id"], token, "uncertain", path
    ) is True