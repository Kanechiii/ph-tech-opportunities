"""Offline tests for multi-source RSS configuration."""

from unittest.mock import patch

import pytest

from src.collectors.source_registry import (
    APPROVED_FEED_URLS,
    load_sources,
    collect_all_sources,
)


def write_config(tmp_path, content):
    """Create a temporary YAML config for testing."""

    path = tmp_path / "sources.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_default_sources():
    """The real configuration contains two approved feeds."""

    sources = load_sources()

    assert len(sources) == 2
    assert all(source["enabled"] for source in sources)
    assert all(
        source["url"] in APPROVED_FEED_URLS
        for source in sources
    )


def test_reject_unknown_source(tmp_path):
    """Unknown websites cannot be enabled through YAML."""

    path = write_config(tmp_path, """
version: 1
sources:
  - id: unknown
    name: Unknown Site
    url: https://example.com/rss
    enabled: true
    max_results: 5
""")

    with pytest.raises(ValueError, match="not approved"):
        load_sources(path)


def test_reject_modified_source_url(tmp_path):
    """Approved IDs cannot be redirected to another URL."""

    path = write_config(tmp_path, """
version: 1
sources:
  - id: github_blog
    name: GitHub Blog
    url: https://example.com/feed
    enabled: true
    max_results: 5
""")

    with pytest.raises(ValueError, match="Invalid source URL"):
        load_sources(path)


def test_reject_duplicate_source(tmp_path):
    """Source IDs must be unique."""

    path = write_config(tmp_path, """
version: 1
sources:
  - id: github_blog
    name: GitHub Blog
    url: https://github.blog/feed/
    enabled: true
    max_results: 5
  - id: github_blog
    name: GitHub Blog
    url: https://github.blog/feed/
    enabled: true
    max_results: 5
""")

    with pytest.raises(ValueError, match="Duplicate"):
        load_sources(path)


def test_reject_invalid_result_limit(tmp_path):
    """Invalid result limits must be rejected."""

    path = write_config(tmp_path, """
version: 1
sources:
  - id: github_blog
    name: GitHub Blog
    url: https://github.blog/feed/
    enabled: true
    max_results: 100
""")

    with pytest.raises(ValueError, match="max_results"):
        load_sources(path)


def test_disabled_source_is_skipped(tmp_path):
    """Disabled sources must not make network calls."""

    path = write_config(tmp_path, """
version: 1
sources:
  - id: github_blog
    name: GitHub Blog
    url: https://github.blog/feed/
    enabled: false
    max_results: 5
""")

    with patch(
        "src.collectors.rss_collector.collect_rss"
    ) as mock_collect:
        items, errors = collect_all_sources(path)

    mock_collect.assert_not_called()
    assert items == []
    assert errors == []


def test_collect_two_sources():
    """Both sources can be collected using mocked requests."""

    sample_item = {
        "title": "Sample announcement",
        "url": "https://example.com/article",
        "published_at": None,
        "category": "unclassified",
        "verification": "not_verified",
    }

    with patch(
        "src.collectors.rss_collector.collect_rss",
        side_effect=lambda url, limit: [sample_item.copy()],
    ) as mock_collect:

        items, errors = collect_all_sources()

    assert mock_collect.call_count == 2
    assert len(items) == 2
    assert errors == []
    assert {item["source_id"] for item in items} == {
        "github_blog",
        "python_insider",
    }


def test_one_source_failure_does_not_stop_others():
    """A failing source does not prevent later collection."""

    def fake_collect(url, limit):
        if "github.blog" in url:
            raise ConnectionError("Simulated network failure")

        return [{
            "title": "Python announcement",
            "url": "https://blog.python.org/example",
            "published_at": None,
            "category": "unclassified",
            "verification": "not_verified",
        }]

    with patch(
        "src.collectors.rss_collector.collect_rss",
        side_effect=fake_collect,
    ):
        items, errors = collect_all_sources()

    assert len(items) == 1
    assert items[0]["source_id"] == "python_insider"
    assert len(errors) == 1
    assert errors[0]["source_id"] == "github_blog"

def test_classifies_certification_voucher():
    """Collected voucher announcements are potential matches."""

    sample = {
        "title": "AWS Certification Exam Voucher Available",
        "url": "https://example.com/voucher",
        "published_at": None,
        "category": "unclassified",
        "verification": "not_verified",
    }

    with patch(
        "src.collectors.rss_collector.collect_rss",
        return_value=[sample.copy()],
    ):
        items, errors = collect_all_sources()

    assert errors == []
    assert len(items) == 2

    for item in items:
        assert item["category"] == "certification_voucher"
        assert item["is_candidate"] is True
        assert item["classification_status"] == "potential_match"
        assert item["verification"] == "not_verified"


def test_classifies_technology_event():
    """Collected technology events receive a potential-match label."""

    sample = {
        "title": "Free Python Developer Workshop",
        "url": "https://example.com/workshop",
        "published_at": None,
        "category": "unclassified",
        "verification": "not_verified",
    }

    with patch(
        "src.collectors.rss_collector.collect_rss",
        return_value=[sample.copy()],
    ):
        items, errors = collect_all_sources()

    assert errors == []

    for item in items:
        assert item["category"] == "tech_event"
        assert item["is_candidate"] is True
        assert item["free_status"] == "unknown"
        assert item["ph_eligibility"] == "unknown"


def test_classifies_hackathon():
    """Hackathon announcements remain unverified."""

    sample = {
        "title": "Philippines Student AI Hackathon",
        "url": "https://example.com/hackathon",
        "published_at": None,
        "category": "unclassified",
        "verification": "not_verified",
    }

    with patch(
        "src.collectors.rss_collector.collect_rss",
        return_value=[sample.copy()],
    ):
        items, errors = collect_all_sources()

    assert errors == []

    for item in items:
        assert item["category"] == "hackathon"
        assert item["classification_status"] == "potential_match"
        assert item["verification"] == "not_verified"
        assert item["deadline_status"] == "unknown"


def test_unrelated_announcement_remains_unclassified():
    """Unrelated articles do not become opportunities."""

    sample = {
        "title": "New Python Release Announced",
        "url": "https://example.com/release",
        "published_at": None,
        "category": "unclassified",
        "verification": "not_verified",
    }

    with patch(
        "src.collectors.rss_collector.collect_rss",
        return_value=[sample.copy()],
    ):
        items, errors = collect_all_sources()

    assert errors == []

    for item in items:
        assert item["category"] == "unclassified"
        assert item["is_candidate"] is False
        assert item["classification_status"] == "unclassified"
        assert item["matched_terms"] == []