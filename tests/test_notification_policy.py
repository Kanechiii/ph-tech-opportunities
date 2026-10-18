"""Offline tests for notification eligibility rules."""

from datetime import datetime, timezone

import pytest

from src.notification_policy import assess_notification_policy


NOW = datetime(
    2026, 10, 18, 12, 0, tzinfo=timezone.utc
)


@pytest.fixture
def opportunity():
    return {
        "source_id": "github_blog",
        "url": "https://github.blog/example",
        "title": "Example Developer Workshop",
        "category": "tech_event",
        "classification_status": "potential_match",
        "verification": "verified",
        "free_status": "confirmed_free",
        "ph_eligibility": "confirmed",
        "deadline_status": "open",
    }


@pytest.fixture
def review():
    return {
        "decision": "approved",
        "method": "manual",
        "reviewer_id": "test_reviewer",
        "evidence_url": "https://example.org/official-details",
        "reviewed_at": "2026-10-17T12:00:00+00:00",
    }


def evaluate(opportunity, review):
    return assess_notification_policy(
        opportunity, review, now=NOW
    )


def test_complete_review_passes_policy(opportunity, review):
    result = evaluate(opportunity, review)

    assert result["policy_passed"] is True
    assert result["decision"] == "preliminary_pass"
    assert result["reasons"] == []
    assert result["delivery_authorized"] is False


def test_review_missing_blocks(opportunity):
    result = evaluate(opportunity, None)

    assert "review_missing" in result["reasons"]
    assert result["policy_passed"] is False


def test_unclassified_article_blocks(opportunity, review):
    opportunity["category"] = "unclassified"
    opportunity["classification_status"] = "unclassified"

    result = evaluate(opportunity, review)

    assert "unsupported_category" in result["reasons"]
    assert "not_a_potential_match" in result["reasons"]


def test_unverified_article_blocks(opportunity, review):
    opportunity["verification"] = "not_verified"

    result = evaluate(opportunity, review)

    assert "not_verified" in result["reasons"]


def test_unknown_free_status_blocks(opportunity, review):
    opportunity["free_status"] = "unknown"

    result = evaluate(opportunity, review)

    assert "free_status_unconfirmed" in result["reasons"]


def test_unconfirmed_ph_eligibility_blocks(
    opportunity, review
):
    opportunity["ph_eligibility"] = "unknown"

    result = evaluate(opportunity, review)

    assert "ph_eligibility_unconfirmed" in result["reasons"]


def test_closed_opportunity_blocks(opportunity, review):
    opportunity["deadline_status"] = "closed"

    result = evaluate(opportunity, review)

    assert "availability_unconfirmed" in result["reasons"]


def test_stale_review_blocks(opportunity, review):
    review["reviewed_at"] = "2026-10-01T12:00:00Z"

    result = evaluate(opportunity, review)

    assert "review_date_invalid_or_stale" in result["reasons"]


def test_future_review_blocks(opportunity, review):
    review["reviewed_at"] = "2026-10-19T12:00:00Z"

    result = evaluate(opportunity, review)

    assert "review_date_invalid_or_stale" in result["reasons"]


def test_invalid_evidence_url_blocks(opportunity, review):
    review["evidence_url"] = "http://example.org/details"

    result = evaluate(opportunity, review)

    assert "evidence_url_invalid" in result["reasons"]


def test_rejected_review_blocks(opportunity, review):
    review["decision"] = "rejected"

    result = evaluate(opportunity, review)

    assert "manual_approval_missing" in result["reasons"]


def test_missing_reviewer_blocks(opportunity, review):
    review["reviewer_id"] = ""

    result = evaluate(opportunity, review)

    assert "reviewer_missing" in result["reasons"]


def test_invalid_opportunity_blocks(opportunity, review):
    opportunity["url"] = "javascript:alert(1)"

    result = evaluate(opportunity, review)

    assert "invalid_opportunity" in result["reasons"]


def test_naive_current_time_rejected(opportunity, review):
    with pytest.raises(ValueError):
        assess_notification_policy(
            opportunity,
            review,
            now=datetime(2026, 10, 18, 12, 0),
        )