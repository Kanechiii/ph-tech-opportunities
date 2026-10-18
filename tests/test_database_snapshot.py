"""Offline tests for persistent SQLite snapshots."""

from pathlib import Path
import sqlite3
import zipfile

import pytest

from unittest.mock import patch
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

        assert version == 3
        assert count == 1
    finally:
        connection.close()


def test_version_two_snapshot_migrates_to_three(tmp_path):
    """A version-2 snapshot preserves records during migration."""

    from src.database.schema import (
        SCHEMA_SQL,
        MIGRATION_1_TO_2,
        connect_database,
    )

    legacy = tmp_path / "version2.sqlite3"

    connection = sqlite3.connect(legacy)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.executescript(MIGRATION_1_TO_2)

        connection.execute(
            """
            INSERT INTO opportunities (source_id, url, title)
            VALUES (?, ?, ?)
            """,
            (
                "github_blog",
                "https://github.blog/preserved",
                "Preserved article",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    archive = tmp_path / "version2.zip"
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

        jobs_table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table'
              AND name = 'notification_jobs'
            """
        ).fetchone()

        assert version == 3
        assert count == 1
        assert jobs_table is not None

    finally:
        connection.close()


def test_atomic_snapshot_replaces_existing_backup(
    database_path, tmp_path
):
    """A valid replacement preserves the database contents."""

    snapshot = tmp_path / "snapshots" / "opportunities.sqlite3"

    # Create an initial valid snapshot.
    create_snapshot(database_path, snapshot)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO opportunities (source_id, url, title)
            VALUES (?, ?, ?)
            """,
            (
                "github_blog",
                "https://github.blog/atomic-test",
                "Atomic backup test",
            ),
        )

    # Publish a replacement with the new record.
    create_snapshot(database_path, snapshot)

    assert validate_database(snapshot) is True

    with sqlite3.connect(snapshot) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM opportunities"
        ).fetchone()[0]

    assert count == 1

    assert list(
        snapshot.parent.glob(".snapshot-pending-*")
    ) == []


def test_failed_snapshot_preserves_previous_backup(
    database_path, tmp_path
):
    """A validation failure must not destroy the old snapshot."""

    snapshot = tmp_path / "snapshots" / "opportunities.sqlite3"

    create_snapshot(database_path, snapshot)

    previous_bytes = snapshot.read_bytes()

    original_validate = validate_database

    def simulated_validation(path, *args, **kwargs):
        # Source validation succeeds; temporary validation fails.
        if Path(path).name.startswith(".snapshot-pending-"):
            raise ValueError("Simulated snapshot validation failure")

        return original_validate(path, *args, **kwargs)

    from src.database import snapshot as snapshot_module

    with patch.object(
        snapshot_module,
        "validate_database",
        side_effect=simulated_validation,
    ):
        with pytest.raises(
            ValueError,
            match="Simulated snapshot validation failure",
        ):
            create_snapshot(database_path, snapshot)

    # The previously published backup is unchanged.
    assert snapshot.read_bytes() == previous_bytes
    assert validate_database(snapshot) is True

    # No incomplete temporary snapshot is left behind.
    assert list(
        snapshot.parent.glob(".snapshot-pending-*")
    ) == []