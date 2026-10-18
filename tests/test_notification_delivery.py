"""Offline tests for reviewed opportunity email delivery."""

import pytest

from src.database.schema import initialize_database
from src.database.storage import save_opportunity
from src.database.review_service import record_review
from src.database.notification_queue import (
    enqueue_notification,
    get_job,
)
from src.notification_delivery import (
    prepare_notification,
    deliver_notification,
)


@pytest.fixture
def pending_job(tmp_path):
    """Create a reviewed opportunity and a pending job."""

    path = tmp_path / "delivery_test.sqlite3"
    initialize_database(path)

    item = save_opportunity({
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

    opportunity_id = item["id"]

    record_review(
        opportunity_id,
        "approved",
        "https://example.org/official-listing",
        free_confirmed=True,
        ph_confirmed=True,
        open_confirmed=True,
        database_path=path,
    )

    job = enqueue_notification(opportunity_id, path)

    return path, job["id"], opportunity_id


def test_preview_does_not_modify_queue(pending_job):
    path, job_id, _ = pending_job

    content = prepare_notification(job_id, path)

    assert "Example Developer Workshop" in content["subject"]
    assert "Official announcement" in content["text_body"]
    assert get_job(job_id, path)["status"] == "pending"
    assert get_job(job_id, path)["attempt_count"] == 0


def test_delivery_requires_authorization(pending_job):
    path, job_id, _ = pending_job

    with pytest.raises(PermissionError):
        deliver_notification(job_id, path)

    assert get_job(job_id, path)["status"] == "pending"


def test_successful_mock_delivery(pending_job):
    path, job_id, _ = pending_job
    calls = []

    def fake_sender(**kwargs):
        calls.append(kwargs)
        return True

    result = deliver_notification(
        job_id,
        path,
        authorized=True,
        sender=fake_sender,
        config_validator=lambda: {"configured": True},
    )

    assert result["status"] == "sent"
    assert len(calls) == 1
    assert get_job(job_id, path)["status"] == "sent"
    assert get_job(job_id, path)["attempt_count"] == 1


def test_same_job_cannot_send_twice(pending_job):
    path, job_id, _ = pending_job
    calls = []

    def fake_sender(**kwargs):
        calls.append(kwargs)
        return True

    kwargs = {
        "authorized": True,
        "sender": fake_sender,
        "config_validator": lambda: True,
    }

    deliver_notification(job_id, path, **kwargs)

    with pytest.raises(ValueError, match="not pending"):
        deliver_notification(job_id, path, **kwargs)

    assert len(calls) == 1


def test_configuration_failure_preserves_pending(pending_job):
    path, job_id, _ = pending_job

    def invalid_config():
        raise ValueError("Missing SMTP configuration")

    with pytest.raises(ValueError, match="Missing SMTP"):
        deliver_notification(
            job_id,
            path,
            authorized=True,
            sender=lambda **kwargs: True,
            config_validator=invalid_config,
        )

    assert get_job(job_id, path)["status"] == "pending"
    assert get_job(job_id, path)["attempt_count"] == 0


def test_smtp_exception_marks_uncertain(pending_job):
    path, job_id, _ = pending_job

    def failed_sender(**kwargs):
        raise TimeoutError("Simulated ambiguous timeout")

    with pytest.raises(RuntimeError, match="uncertain"):
        deliver_notification(
            job_id,
            path,
            authorized=True,
            sender=failed_sender,
            config_validator=lambda: True,
        )

    assert get_job(job_id, path)["status"] == "uncertain"

    with pytest.raises(ValueError, match="not pending"):
        prepare_notification(job_id, path)


def test_unconfirmed_result_marks_uncertain(pending_job):
    path, job_id, _ = pending_job

    with pytest.raises(RuntimeError, match="not positively"):
        deliver_notification(
            job_id,
            path,
            authorized=True,
            sender=lambda **kwargs: False,
            config_validator=lambda: True,
        )

    assert get_job(job_id, path)["status"] == "uncertain"


def test_review_revocation_blocks_preview(pending_job):
    path, job_id, opportunity_id = pending_job

    record_review(
        opportunity_id,
        "rejected",
        "https://example.org/updated-listing",
        database_path=path,
    )

    with pytest.raises(ValueError, match="review policy"):
        prepare_notification(job_id, path)

    assert get_job(job_id, path)["status"] == "pending"