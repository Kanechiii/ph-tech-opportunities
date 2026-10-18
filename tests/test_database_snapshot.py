"""Offline tests for persistent SQLite snapshots."""

import sqlite3
import zipfile

import pytest

from src.database.schema import SCHEMA_SQL, connect_database
from src.database.schema import initialize_database
from src.database.snapshot import (
    create_snapshot,
    restore_snapshot,
    validate_database,
)


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "original.sqlite3"
    initialize_database(path)
    return path


def test_valid_database_passes_integrity_check(database_path):
    assert validate_database(database_path) is True


def test_missing_database_rejected(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        validate_database(tmp_path / "missing.sqlite3")


def test_backup_preserves_database_records(
    database_path, tmp_path
):
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO opportunities (source_id, url, title)
            VALUES (?, ?, ?)
            """,
            (
                "github_blog",
                "https://github.blog/test",
                "Original announcement",
            ),
        )

    backup = tmp_path / "backup" / "opportunities.sqlite3"

    create_snapshot(database_path, backup)

    assert validate_database(backup) is True

    with sqlite3.connect(backup) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM opportunities"
        ).fetchone()[0]

    assert count == 1


def test_snapshot_archive_restores_database(
    database_path, tmp_path
):
    archive_path = tmp_path / "snapshot.zip"
    destination = tmp_path / "restored.sqlite3"

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(database_path, "opportunities.sqlite3")

    restore_snapshot(archive_path, destination)

    assert validate_database(destination) is True


def test_invalid_archive_preserves_existing_database(
    database_path, tmp_path
):
    archive_path = tmp_path / "invalid.zip"
    original_bytes = database_path.read_bytes()

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("unapproved.txt", "invalid content")

    with pytest.raises(ValueError, match="Unexpected"):
        restore_snapshot(archive_path, database_path)

    assert database_path.read_bytes() == original_bytes


def test_version_one_artifact_migrates_on_restore(tmp_path):
    """Old hosted snapshots upgrade without losing opportunities."""

    legacy = tmp_path / "legacy.sqlite3"

    connection = sqlite3.connect(legacy)
    try:
        connection.executescript(SCHEMA_SQL)

        connection.execute(
            """
            INSERT INTO opportunities (source_id, url, title)
            VALUES (?, ?, ?)
            """,
            (
                "github_blog",
                "https://github.blog/old-article",
                "Previously collected article",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    archive = tmp_path / "legacy.zip"
    restored = tmp_path / "restored.sqlite3"

    with zipfile.ZipFile(archive, "w") as file:
        file.write(legacy, "opportunities.sqlite3")

    restore_snapshot(archive, restored)

    assert validate_database(restored) is True

    connection = connect_database(restored)
    try:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        count = connection.execute(
            "SELECT COUNT(*) FROM opportunities"
        ).fetchone()[0]

        assert version == 2
        assert count == 1
    finally:
        connection.close()