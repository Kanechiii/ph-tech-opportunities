"""Validate, restore, and back up SQLite workflow snapshots."""

import os
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

from src.database.schema import (
    DATABASE_PATH,
    SCHEMA_VERSION,
    initialize_database,
)


SNAPSHOT_DIRECTORY = DATABASE_PATH.parent / "snapshot_upload"
SNAPSHOT_PATH = SNAPSHOT_DIRECTORY / "opportunities.sqlite3"

REQUIRED_TABLES = {
    "opportunities",
    "collection_runs",
    "notification_history",
}

MAX_SNAPSHOT_SIZE = 20 * 1024 * 1024


def validate_database(
    path=DATABASE_PATH,
    accepted_versions=None,
):
    """Validate SQLite structure and integrity.

    Legacy version 1 is only accepted when explicitly requested
    for migration. Normal validation requires the latest schema.
    """

    path = Path(path)

    if accepted_versions is None:
        accepted_versions = (SCHEMA_VERSION,)

    if not path.is_file():
        raise ValueError("Database snapshot does not exist.")

    if path.stat().st_size > MAX_SNAPSHOT_SIZE:
        raise ValueError("Database exceeds snapshot size limit.")

    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise ValueError("SQLite integrity check failed.")

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if version not in accepted_versions:
            raise ValueError("Unsupported database schema version.")

        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

        tables = {row[0] for row in rows}

        required = set(REQUIRED_TABLES)

        if version >= 2:
            required.add("opportunity_reviews")

        if version >= 3:
            required.add("notification_jobs")

        if not required.issubset(tables):
            raise ValueError("Required database tables are missing.")

    finally:
        connection.close()

    return True


def create_snapshot(
    database_path=DATABASE_PATH,
    snapshot_path=SNAPSHOT_PATH,
):
    """Atomically publish a validated SQLite snapshot.

    Preserve the existing snapshot if backup or validation fails.
    """

    database_path = Path(database_path)
    snapshot_path = Path(snapshot_path)

    # Fail before creating a temporary file if the source is bad.
    validate_database(database_path)

    if database_path.resolve() == snapshot_path.resolve():
        raise ValueError("Snapshot must use a different path.")

    snapshot_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Create the temporary file in the destination directory.
    # os.replace() is atomic when the filesystem supports it.
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".snapshot-pending-",
        suffix=".sqlite3",
        dir=snapshot_path.parent,
    )

    temporary_path = Path(temporary_name)
    os.close(descriptor)

    source = None
    destination = None

    try:
        source = sqlite3.connect(
            database_path.resolve().as_uri() + "?mode=ro",
            uri=True,
        )

        destination = sqlite3.connect(temporary_path)

        # SQLite creates a transactionally consistent copy.
        source.backup(destination)

        destination.close()
        destination = None

        source.close()
        source = None

        # Verify the temporary backup before publishing it.
        validate_database(temporary_path)

        # Publish a fully validated file.
        # The old snapshot is replaced only at this point.
        os.replace(temporary_path, snapshot_path)

        return snapshot_path

    finally:
        if destination is not None:
            destination.close()

        if source is not None:
            source.close()

        # On failure, delete only the temporary file.
        # Never delete the existing published snapshot.
        temporary_path.unlink(missing_ok=True)


def restore_snapshot(
    archive_path,
    database_path=DATABASE_PATH,
):
    """Restore a validated SQLite file from an artifact archive."""

    archive_path = Path(archive_path)
    database_path = Path(database_path)

    with zipfile.ZipFile(archive_path) as archive:
        files = [
            entry
            for entry in archive.infolist()
            if not entry.is_dir()
        ]

        if (
            len(files) != 1
            or files[0].filename != "opportunities.sqlite3"
        ):
            raise ValueError("Unexpected snapshot archive contents.")

        if files[0].file_size > MAX_SNAPSHOT_SIZE:
            raise ValueError("Snapshot is too large.")

        contents = archive.read(files[0])

    if len(contents) > MAX_SNAPSHOT_SIZE:
        raise ValueError("Snapshot exceeds size limit.")

    database_path.parent.mkdir(parents=True, exist_ok=True)

    descriptor, temp_name = tempfile.mkstemp(
        prefix="sqlite-restore-",
        suffix=".sqlite3",
        dir=database_path.parent,
    )

    temp_path = Path(temp_name)

    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(contents)

                # Accept only the known legacy or current schema.
        validate_database(
            temp_path,
            accepted_versions=(1, 2, SCHEMA_VERSION),
        )

        # Migrate the temporary copy, never the original artifact.
        initialize_database(temp_path)

        # Require full current-schema integrity before replacement.
        validate_database(temp_path)

        os.replace(temp_path, database_path)

    finally:
        temp_path.unlink(missing_ok=True)

    return database_path


def main():
    """Command-line entrypoint for workflow snapshot operations."""

    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python -m src.database.snapshot "
            "validate|backup|restore [archive]"
        )

    command = sys.argv[1]

    try:
        if command == "validate" and len(sys.argv) == 2:
            validate_database()
            print("SQLite database validation passed.")

        elif command == "backup" and len(sys.argv) == 2:
            create_snapshot()
            print("Validated SQLite backup created.")

        elif command == "restore" and len(sys.argv) == 3:
            restore_snapshot(sys.argv[2])
            print("SQLite snapshot restored and validated.")

        else:
            raise ValueError("Invalid snapshot command.")

    except (
        ValueError,
        OSError,
        sqlite3.Error,
        zipfile.BadZipFile,
    ) as error:
        print(f"Snapshot operation failed: {type(error).__name__}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()