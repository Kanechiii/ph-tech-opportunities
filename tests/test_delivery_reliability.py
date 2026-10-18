"""Offline regression tests for reviewed email delivery safety."""

from unittest.mock import patch

import pytest

from src.database.schema import initialize_database
from src.database.storage import save_opportunity
from src.database.review_service import record_review
from src.database.notification_queue import (
    enqueue_notification,
    get_job,
    quarantine_stale_claims,
)
from src.notification_delivery import (
    prepare_notification,
    deliver_notification,
    safe_email_subject,
)


@pytest.fixture
def ready_job(tmp_path):
    """Create an isolated, approved opportunity and pending job."""

    database = tmp_path / "reliability.sqlite3"
    initialize_database(database)

    saved = save_opportunity({
        "source_id": "github_blog",
        "url": "https://github.blog/example",
        "title": "Example Developer Workshop",
        "category": "tech_event",
        "classification_status": "potential_match",
        "verification": "not_verified",
        "free_status": "unknown",
        "ph_eligibility": "unknown",
        "deadline_status": "unknown",
        "published_at": None,
    }, database)

    opportunity_id = saved["id"]

    record_review(
        opportunity_id,
        "approved",
        "https://example.org/public-listing",
        free_confirmed=True,
        ph_confirmed=True,
        open_confirmed=True,
        database_path=database,
    )

    job = enqueue_notification(opportunity_id, database)

    return database, job["id"], opportunity_id


def test_subject_removes_newlines():
    subject = safe_email_subject("Python\r\nDeveloper\tWorkshop")

    assert subject == "PH Tech Opportunity: Python Developer Workshop"
    assert "\n" not in subject
    assert "\r" not in subject


def test_subject_length_is_bounded():
    subject = safe_email_subject("A" * 500)

    assert len(subject) <= 181


def test_html_escapes_untrusted_title(ready_job):
    database, job_id, opportunity_id = ready_job

    from src.database.storage import update_opportunity

    update_opportunity(
        opportunity_id,
        {"title": "<script>alert('test')</script>"},
        database,
    )

    message = prepare_notification(job_id, database)

    assert "&lt;script&gt;" in message["html_body"]
    assert "<script>" not in message["html_body"]


def test_preview_never_calls_gmail(ready_job):
    database, job_id, _ = ready_job

    with patch(
        "src.notification_delivery.send_email"
    ) as mocked_sender:
        prepare_notification(job_id, database)

    mocked_sender.assert_not_called()

    assert get_job(job_id, database)["status"] == "pending"


def test_revoked_review_blocks_delivery(ready_job):
    database, job_id, opportunity_id = ready_job

    record_review(
        opportunity_id,
        "rejected",
        "https://example.org/updated-listing",
        database_path=database,
    )

    calls = []

    def fake_sender(**kwargs):
        calls.append(kwargs)
        return True

    with pytest.raises(ValueError, match="review policy"):
        deliver_notification(
            job_id,
            database,
            authorized=True,
            sender=fake_sender,
            config_validator=lambda: True,
        )

    assert calls == []
    assert get_job(job_id, database)["status"] == "pending"


def test_uncertain_delivery_never_auto_retries(ready_job):
    database, job_id, _ = ready_job

    calls = []

    def ambiguous_sender(**kwargs):
        calls.append(kwargs)
        raise TimeoutError("Simulated SMTP timeout")

    with pytest.raises(RuntimeError, match="uncertain"):
        deliver_notification(
            job_id,
            database,
            authorized=True,
            sender=ambiguous_sender,
            config_validator=lambda: True,
        )

    assert len(calls) == 1
    assert get_job(job_id, database)["status"] == "uncertain"

    # Quarantine cannot return an uncertain job to pending.
    assert quarantine_stale_claims(database) == 0

    with pytest.raises(ValueError, match="not pending"):
        deliver_notification(
            job_id,
            database,
            authorized=True,
            sender=ambiguous_sender,
            config_validator=lambda: True,
        )

    assert len(calls) == 1