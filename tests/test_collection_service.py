"""Offline tests for RSS-to-SQLite persistence."""

from unittest.mock import patch

import pytest

from src.database.schema import initialize_database
from src.database.storage import (
    get_opportunity,
    list_opportunities,
    update_opportunity,
)
from src.database.collection_service import (
    get_collection_history,
    run_collection,
)


SOURCES = [
    {
        "id": "github_blog",
        "name": "GitHub Blog",
        "url": "https://github.blog/feed/",
        "enabled": True,
        "max_results": 5,
    },
    {
        "id": "python_insider",
        "name": "Python Insider",
        "url": "https://blog.python.org/rss.xml",
        "enabled": True,
        "max_results": 5,
    },
]


def sample_item(source_id="github_blog"):
    """Create a fictional classified RSS record."""

    return {
        "source_id": source_id,
        "source": (
            "GitHub Blog"
            if source_id == "github_blog"
            else "Python Insider"
        ),
        "title": "Free Python Developer Workshop",
        "url": f"https://example.com/{source_id}/workshop",
        "published_at": "2026-10-18T08:00:00+00:00",
        "category": "tech_event",
        "classification_status": "potential_match",
        "verification": "not_verified",
        "free_status": "unknown",
        "ph_eligibility": "unknown",
        "deadline_status": "unknown",
    }


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "collection_test.sqlite3"
    initialize_database(path)
    return path


def mocked_collection(items, errors=None, sources=None):
    """Patch source configuration and network collection."""

    configured = SOURCES if sources is None else sources

    return (
        patch(
            "src.database.collection_service.load_sources",
            return_value=configured,
        ),
        patch(
            "src.database.collection_service.collect_all_sources",
            return_value=(items, errors or []),
        ),
    )


def test_new_collection_creates_opportunity_and_history(
    database_path,
):
    item = sample_item()
    source_patch, collect_patch = mocked_collection([item])

    with source_patch, collect_patch:
        summary = run_collection(database_path)

    assert summary["new"] == 1
    assert summary["updated"] == 0
    assert summary["sources_checked"] == 2

    records = list_opportunities(database_path)
    history = get_collection_history(database_path)

    assert len(records) == 1
    assert len(history) == 2
    assert all(row["status"] == "success" for row in history)


def test_repeated_collection_updates_without_duplicates(
    database_path,
):
    item = sample_item()
    source_patch, collect_patch = mocked_collection([item])

    with source_patch, collect_patch:
        first = run_collection(database_path)
        second = run_collection(database_path)

    assert first["new"] == 1
    assert second["new"] == 0
    assert second["updated"] == 1
    assert len(list_opportunities(database_path)) == 1
    assert len(get_collection_history(database_path)) == 4


def test_verified_information_survives_collection(
    database_path,
):
    item = sample_item()
    source_patch, collect_patch = mocked_collection([item])

    with source_patch, collect_patch:
        run_collection(database_path)

        original = list_opportunities(database_path)[0]

        update_opportunity(
            original["id"],
            {
                "verification": "verified",
                "ph_eligibility": "confirmed",
            },
            database_path,
        )

        run_collection(database_path)

    updated = get_opportunity(original["id"], database_path)

    assert updated["verification"] == "verified"
    assert updated["ph_eligibility"] == "confirmed"
    assert updated["first_seen_at"] == original["first_seen_at"]


def test_source_failure_recorded_independently(
    database_path,
):
    item = sample_item("python_insider")

    errors = [{
        "source_id": "github_blog",
        "error_type": "ConnectionError",
    }]

    source_patch, collect_patch = mocked_collection(
        [item], errors
    )

    with source_patch, collect_patch:
        summary = run_collection(database_path)

    assert summary["failed_sources"] == 1
    assert summary["new"] == 1

    history = get_collection_history(database_path)

    statuses = {
        row["source_id"]: row["status"]
        for row in history
    }

    assert statuses["github_blog"] == "failed"
    assert statuses["python_insider"] == "success"


def test_partial_collection_recorded(database_path):
    valid_item = sample_item()
    invalid_item = sample_item()
    invalid_item["title"] = ""

    sources = [SOURCES[0]]
    source_patch, collect_patch = mocked_collection(
        [valid_item, invalid_item],
        sources=sources,
    )

    with source_patch, collect_patch:
        summary = run_collection(database_path)

    assert summary["new"] == 1
    assert summary["failed_items"] == 1

    history = get_collection_history(database_path)

    assert len(history) == 1
    assert history[0]["status"] == "partial"
    assert history[0]["items_found"] == 2


def test_disabled_source_not_recorded(database_path):
    disabled = {
        **SOURCES[1],
        "enabled": False,
    }

    source_patch, collect_patch = mocked_collection(
        [sample_item()],
        sources=[SOURCES[0], disabled],
    )

    with source_patch, collect_patch:
        summary = run_collection(database_path)

    assert summary["sources_checked"] == 1
    assert len(get_collection_history(database_path)) == 1


def test_collection_history_limit(database_path):
    source_patch, collect_patch = mocked_collection(
        [sample_item()]
    )

    with source_patch, collect_patch:
        run_collection(database_path)
        run_collection(database_path)

    history = get_collection_history(
        database_path,
        limit=2,
    )

    assert len(history) == 2

    with pytest.raises(ValueError):
        get_collection_history(database_path, limit=0)