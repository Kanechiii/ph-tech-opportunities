"""Offline tests for opportunity classification."""

import pytest

from src.collectors.opportunity_classifier import (
    classify_announcement,
    normalize_text,
    find_matches,
)


def test_certification_voucher():
    result = classify_announcement(
        "AWS Certification Exam Voucher Available"
    )

    assert result["category"] == "certification_voucher"
    assert result["is_candidate"] is True


def test_free_certification_exam():
    result = classify_announcement(
        "Free Exam for Cloud Certification"
    )

    assert result["category"] == "certification_voucher"


def test_generic_certification_not_voucher():
    result = classify_announcement(
        "Understanding Cloud Certification Paths"
    )

    assert result["category"] == "unclassified"


def test_free_course_not_certification_voucher():
    result = classify_announcement(
        "Free Python Programming Course"
    )

    assert result["category"] == "unclassified"


def test_technology_workshop():
    result = classify_announcement(
        "Free Python Developer Workshop"
    )

    assert result["category"] == "tech_event"


def test_generic_workshop():
    result = classify_announcement(
        "Free Cooking Workshop"
    )

    assert result["category"] == "unclassified"


def test_hackathon():
    result = classify_announcement(
        "Philippines Student AI Hackathon"
    )

    assert result["category"] == "hackathon"


def test_hackathon_priority():
    result = classify_announcement(
        "Developer Workshop and Hackathon"
    )

    assert result["category"] == "hackathon"


def test_description_classification():
    result = classify_announcement(
        "Upcoming Community Session",
        description="Join our Python developer webinar.",
    )

    assert result["category"] == "tech_event"


def test_no_false_partial_keyword():
    text = normalize_text("This is a prehackathonish name")

    assert find_matches(text, ("hackathon",)) == []


def test_unverified_status():
    result = classify_announcement(
        "Philippines Student AI Hackathon"
    )

    assert result["verification"] == "not_verified"
    assert result["free_status"] == "unknown"
    assert result["ph_eligibility"] == "unknown"
    assert result["deadline_status"] == "unknown"


def test_invalid_input():
    with pytest.raises(TypeError):
        classify_announcement(None)