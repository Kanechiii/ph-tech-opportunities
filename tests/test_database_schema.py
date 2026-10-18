"""Tests for the initial SQLite database schema."""

import sqlite3

import pytest

from src.database.schema import (
    SCHEMA_VERSION,
    connect_database,
    get_database_tables,
    initialize_database,
)


@pytest.fixture
def database_path(tmp_path):
    """Create a fresh test database."""

    path = tmp_path / "test.sqlite3"

    initialize_database(path)

    return path


def test_database_file_created(tmp_path):
    """Initialization creates the database file."""

    path = tmp_path / "nested" / "test.sqlite3"

    initialize_database(path)

    assert path.exists()
    assert path.is_file()


def test_required_tables_exist(database_path):
    """The database includes all four required tables."""

    tables = get_database_tables(database_path)

    assert tables == [
        "collection_runs",
        "notification_history",
        "opportunities",
        "opportunity_reviews",
    ]


def test_schema_version(database_path):
    """The database has the expected schema version."""

    connection = connect_database(database_path)

    try:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        assert version == SCHEMA_VERSION

    finally:
        connection.close()


def test_reinitialization_preserves_data(database_path):
    """Running initialization again does not erase records."""

    connection = connect_database(database_path)

    try:
        connection.execute(
            """
            INSERT INTO opportunities
                (source_id, url, title)
            VALUES (?, ?, ?)
            """,
            (
                "github_blog",
                "https://github.blog/test",
                "Example announcement",
            ),
        )

        connection.commit()

    finally:
        connection.close()

    initialize_database(database_path)

    connection = connect_database(database_path)

    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM opportunities"
        ).fetchone()[0]

        assert count == 1

    finally:
        connection.close()


def test_duplicate_source_url_rejected(database_path):
    """One source cannot store the same URL twice."""

    connection = connect_database(database_path)

    try:
        entry = (
            "github_blog",
            "https://github.blog/example",
            "Example announcement",
        )

        connection.execute(
            """
            INSERT INTO opportunities
                (source_id, url, title)
            VALUES (?, ?, ?)
            """,
            entry,
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO opportunities
                    (source_id, url, title)
                VALUES (?, ?, ?)
                """,
                entry,
            )

    finally:
        connection.close()


def test_invalid_category_rejected(database_path):
    """Only known classification categories are allowed."""

    connection = connect_database(database_path)

    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO opportunities
                    (source_id, url, title, category)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "github_blog",
                    "https://github.blog/example",
                    "Example announcement",
                    "unsupported_category",
                ),
            )

    finally:
        connection.close()


def test_foreign_key_enforcement(database_path):
    """Notifications must refer to existing opportunities."""

    connection = connect_database(database_path)

    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO notification_history
                    (opportunity_id)
                VALUES (?)
                """,
                (99999,),
            )

    finally:
        connection.close()


def test_notification_duplicate_rejected(database_path):
    """The same notification type cannot be repeated."""

    connection = connect_database(database_path)

    try:
        cursor = connection.execute(
            """
            INSERT INTO opportunities
                (source_id, url, title)
            VALUES (?, ?, ?)
            """,
            (
                "github_blog",
                "https://github.blog/example",
                "Example announcement",
            ),
        )

        opportunity_id = cursor.lastrowid

        connection.execute(
            """
            INSERT INTO notification_history
                (opportunity_id)
            VALUES (?)
            """,
            (opportunity_id,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO notification_history
                    (opportunity_id)
                VALUES (?)
                """,
                (opportunity_id,),
            )

    finally:
        connection.close()


def test_unsupported_schema_version_rejected(database_path):
    """Future database versions cannot be opened silently."""

    connection = connect_database(database_path)

    try:
        connection.execute("PRAGMA user_version = 99")

    finally:
        connection.close()

    with pytest.raises(
        RuntimeError,
        match="Unsupported database version",
    ):
        initialize_database(database_path)