"""Offline tests for SQLite opportunity storage."""

import pytest

from src.database.schema import (
    connect_database,
    initialize_database,
)
from src.database.storage import (
    save_opportunity,
    get_opportunity,
    list_opportunities,
    update_opportunity,
    opportunity_exists,
)


@pytest.fixture
def database_path(tmp_path):
    """Prepare an isolated SQLite database."""

    path = tmp_path / "storage_test.sqlite3"
    initialize_database(path)
    return path


@pytest.fixture
def sample_opportunity():
    """A fictional normalized announcement."""

    return {
        "source_id": "github_blog",
        "url": "https://github.blog/example-workshop",
        "title": "Sample Python Developer Workshop",
        "category": "tech_event",
        "classification_status": "potential_match",
        "verification": "not_verified",
        "free_status": "unknown",
        "ph_eligibility": "unknown",
        "deadline_status": "unknown",
        "published_at": "2026-10-18T08:00:00+00:00",
    }


def test_insert_new_opportunity(
    database_path, sample_opportunity
):
    """A new opportunity receives a database ID."""

    result = save_opportunity(
        sample_opportunity, database_path
    )

    assert result["created"] is True
    assert result["status"] == "created"
    assert result["id"] > 0


def test_retrieve_opportunity(
    database_path, sample_opportunity
):
    """Stored records can be retrieved by ID."""

    result = save_opportunity(
        sample_opportunity, database_path
    )

    record = get_opportunity(
        result["id"], database_path
    )

    assert record["title"] == sample_opportunity["title"]
    assert record["source_id"] == "github_blog"
    assert record["category"] == "tech_event"


def test_duplicate_is_updated_not_inserted(
    database_path, sample_opportunity
):
    """Repeated source and URL reuse the same record."""

    first = save_opportunity(
        sample_opportunity, database_path
    )

    changed = sample_opportunity.copy()
    changed["title"] = "Updated Workshop Announcement"

    second = save_opportunity(
        changed, database_path
    )

    assert first["created"] is True
    assert second["created"] is False
    assert second["status"] == "updated"
    assert first["id"] == second["id"]

    records = list_opportunities(database_path)

    assert len(records) == 1
    assert records[0]["title"] == changed["title"]


def test_first_seen_timestamp_preserved(
    database_path, sample_opportunity
):
    """Refreshing a record retains its discovery timestamp."""

    result = save_opportunity(
        sample_opportunity, database_path
    )

    connection = connect_database(database_path)

    try:
        connection.execute(
            """
            UPDATE opportunities
            SET first_seen_at = ?,
                last_seen_at = ?
            WHERE id = ?
            """,
            (
                "2020-01-01 00:00:00",
                "2020-01-01 00:00:00",
                result["id"],
            ),
        )
        connection.commit()

    finally:
        connection.close()

    save_opportunity(sample_opportunity, database_path)

    record = get_opportunity(
        result["id"], database_path
    )

    assert record["first_seen_at"] == (
        "2020-01-01 00:00:00"
    )
    assert record["last_seen_at"] != (
        "2020-01-01 00:00:00"
    )


def test_opportunity_exists(
    database_path, sample_opportunity
):
    """Existence checks recognize matching source and URL."""

    assert opportunity_exists(
        "github_blog",
        sample_opportunity["url"],
        database_path,
    ) is False

    save_opportunity(sample_opportunity, database_path)

    assert opportunity_exists(
        "github_blog",
        sample_opportunity["url"],
        database_path,
    ) is True


def test_same_url_different_source(
    database_path, sample_opportunity
):
    """Different source IDs are separate records."""

    save_opportunity(sample_opportunity, database_path)

    second = sample_opportunity.copy()
    second["source_id"] = "python_insider"

    result = save_opportunity(second, database_path)

    assert result["created"] is True
    assert len(list_opportunities(database_path)) == 2


def test_update_opportunity(
    database_path, sample_opportunity
):
    """Allowed fields can be modified independently."""

    result = save_opportunity(
        sample_opportunity, database_path
    )

    updated = update_opportunity(
        result["id"],
        {
            "title": "Revised Workshop",
            "ph_eligibility": "confirmed",
        },
        database_path,
    )

    record = get_opportunity(
        result["id"], database_path
    )

    assert updated is True
    assert record["title"] == "Revised Workshop"
    assert record["ph_eligibility"] == "confirmed"


def test_protected_field_cannot_change(
    database_path, sample_opportunity
):
    """Database identity and original timestamp are protected."""

    result = save_opportunity(
        sample_opportunity, database_path
    )

    with pytest.raises(
        ValueError,
        match="protected field",
    ):
        update_opportunity(
            result["id"],
            {"first_seen_at": "2020-01-01"},
            database_path,
        )


def test_list_limit(
    database_path, sample_opportunity
):
    """Listing respects the requested result limit."""

    for index in range(3):
        item = sample_opportunity.copy()
        item["url"] = (
            f"https://github.blog/opportunity-{index}"
        )
        save_opportunity(item, database_path)

    records = list_opportunities(
        database_path, limit=2
    )

    assert len(records) == 2


def test_invalid_opportunity_rejected(database_path):
    """Incomplete opportunity records cannot be saved."""

    with pytest.raises(
        ValueError,
        match="Invalid required field",
    ):
        save_opportunity(
            {
                "source_id": "github_blog",
                "url": "https://github.blog/example",
            },
            database_path,
        )