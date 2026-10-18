"""Offline tests for read-only opportunity quality analysis."""

import sqlite3

from src.database.schema import initialize_database
from src.database.storage import save_opportunity
from src.collectors.opportunity_quality import (
    normalized_title,
    canonical_url,
    title_similarity,
    analyze_candidate,
    find_possible_duplicates,
    inspect_quality,
)


def item(
    record_id,
    source_id,
    url,
    title,
    category="tech_event",
):
    return {
        "id": record_id,
        "source_id": source_id,
        "url": url,
        "title": title,
        "category": category,
        "classification_status": "potential_match",
    }


def test_normalizes_title_whitespace():
    assert normalized_title(
        "  FREE  Python\nDeveloper Workshop! "
    ) == "free python developer workshop"


def test_removes_known_tracking_parameters():
    first = canonical_url(
        "https://www.example.org/event?utm_source=mail&ref=official"
    )
    second = canonical_url(
        "https://example.org/event?ref=official"
    )
    assert first == second


def test_preserves_meaningful_query_parameters():
    first = canonical_url(
        "https://example.org/event?id=100"
    )
    second = canonical_url(
        "https://example.org/event?id=200"
    )
    assert first != second


def test_rejects_unsafe_url_schemes():
    assert canonical_url("http://example.org/event") is None
    assert canonical_url("javascript:alert(1)") is None


def test_short_generic_titles_not_matched():
    assert title_similarity(
        "Python Workshop",
        "Python Workshop",
    ) == 0.0


def test_quality_hints_remain_unverified():
    result = analyze_candidate(item(
        1,
        "github_blog",
        "https://example.org/event",
        "Free Python Developer Workshop Philippines Register Now",
    ))

    assert result["quality_score"] == 5
    assert result["review_priority"] == "high"
    assert result["signals"]["free_hint"] is True
    assert result["signals"]["philippines_hint"] is True
    assert result["requires_manual_verification"] is True
    assert result["verified_by_analyzer"] is False


def test_equivalent_url_detected_across_sources():
    records = [
        item(
            1, "github_blog",
            "https://example.org/event?utm_source=rss",
            "Developer Workshop Announcement",
        ),
        item(
            2, "python_insider",
            "https://example.org/event",
            "An Event Announcement",
        ),
    ]

    duplicates = find_possible_duplicates(records)

    assert len(duplicates) == 1
    assert duplicates[0]["reason"] == "equivalent_url"
    assert duplicates[0]["automatically_merged"] is False


def test_distinct_event_ids_not_merged():
    records = [
        item(
            1, "github_blog",
            "https://example.org/event?id=100",
            "Developer Workshop",
        ),
        item(
            2, "python_insider",
            "https://example.org/event?id=200",
            "Developer Workshop",
        ),
    ]

    assert find_possible_duplicates(records) == []


def test_title_similarity_does_not_cross_categories():
    records = [
        item(
            1, "github_blog",
            "https://example.org/a",
            "Philippines Student AI Developer Competition 2026",
            category="hackathon",
        ),
        item(
            2, "python_insider",
            "https://example.org/b",
            "Philippines Student AI Developer Competition 2026",
            category="tech_event",
        ),
    ]

    assert find_possible_duplicates(records) == []


def test_quality_inspection_does_not_change_database(tmp_path):
    path = tmp_path / "quality.sqlite3"
    initialize_database(path)

    saved = save_opportunity({
        "source_id": "github_blog",
        "url": "https://example.org/workshop",
        "title": "Free Python Developer Workshop Philippines",
        "category": "tech_event",
        "classification_status": "potential_match",
    }, path)

    before = path.read_bytes()

    result = inspect_quality(path)

    after = path.read_bytes()

    assert result["records_inspected"] == 1
    assert result["candidate_count"] == 1
    assert result["evaluations"][0]["id"] == saved["id"]
    assert result["database_modified"] is False
    assert before == after