"""Offline tests for read-only migration preparation."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.storage_readiness import (
    TABLES,
    inspect_storage,
)


@pytest.fixture
def prepared_database(tmp_path):
    database = tmp_path / "storage.sqlite3"
    initialize_database(database)
    return database


def test_new_database_passes_readiness(prepared_database):
    result = inspect_storage(prepared_database)

    assert result["migration_inventory_ready"] is True
    assert result["schema_version"] == 3
    assert result["migration_performed"] is False


def test_reports_all_required_table_counts(prepared_database):
    result = inspect_storage(prepared_database)

    assert set(result["table_counts"]) == set(TABLES)
    assert all(
        count == 0
        for count in result["table_counts"].values()
    )


def test_missing_database_does_not_get_created(tmp_path):
    missing = tmp_path / "not-created.sqlite3"

    with pytest.raises(ValueError, match="not found"):
        inspect_storage(missing)

    assert not missing.exists()


def test_readiness_does_not_modify_existing_database(
    prepared_database,
):
    connection = sqlite3.connect(prepared_database)

    try:
        connection.execute(
            """
            INSERT INTO opportunities (source_id, url, title)
            VALUES (?, ?, ?)
            """,
            (
                "github_blog",
                "https://github.blog/inventory-test",
                "Inventory Test",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    before = prepared_database.read_bytes()

    result = inspect_storage(prepared_database)

    after = prepared_database.read_bytes()

    assert result["table_counts"]["opportunities"] == 1
    assert before == after


def test_missing_audit_trigger_blocks_readiness(
    prepared_database,
):
    connection = sqlite3.connect(prepared_database)

    try:
        connection.execute(
            "DROP TRIGGER protect_review_deletes"
        )
        connection.commit()
    finally:
        connection.close()

    result = inspect_storage(prepared_database)

    assert result["review_history_protected"] is False
    assert result["migration_inventory_ready"] is False