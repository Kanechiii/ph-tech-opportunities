"""Read-only inventory for a future hosted database migration.

Does not create tables, export records, or modify SQLite.
"""

import argparse
import json
import sqlite3
from pathlib import Path

from src.database.schema import DATABASE_PATH, SCHEMA_VERSION


TABLES = (
    "opportunities",
    "collection_runs",
    "notification_history",
    "opportunity_reviews",
    "notification_jobs",
)

JOB_STATES = (
    "pending",
    "sending",
    "sent",
    "failed",
    "uncertain",
)


def inspect_storage(database_path=DATABASE_PATH):
    """Return non-sensitive schema and integrity metadata."""

    path = Path(database_path)

    if not path.is_file():
        raise ValueError("Existing SQLite database not found.")

    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        existing_tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

        missing = sorted(set(TABLES) - existing_tables)

        if missing:
            raise ValueError(
                "Required tables are missing: "
                + ", ".join(missing)
            )

        counts = {
            name: connection.execute(
                f'SELECT COUNT(*) FROM "{name}"'
            ).fetchone()[0]
            for name in TABLES
        }

        foreign_key_violations = len(
            connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        job_counts = {
            state: 0
            for state in JOB_STATES
        }

        for row in connection.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM notification_jobs
            GROUP BY status
            """
        ):
            if row["status"] in job_counts:
                job_counts[row["status"]] = row["total"]

        review_trigger_names = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'trigger'
                  AND tbl_name = 'opportunity_reviews'
                """
            )
        }

        review_history_protected = {
            "protect_review_updates",
            "protect_review_deletes",
        }.issubset(review_trigger_names)

        ready = (
            integrity == "ok"
            and version == SCHEMA_VERSION
            and foreign_key_violations == 0
            and review_history_protected
        )

        return {
            "schema_version": version,
            "expected_schema_version": SCHEMA_VERSION,
            "database_size_bytes": path.stat().st_size,
            "integrity_ok": integrity == "ok",
            "foreign_key_violations": foreign_key_violations,
            "review_history_protected": review_history_protected,
            "table_counts": counts,
            "notification_job_states": job_counts,
            "migration_inventory_ready": ready,
            "migration_performed": False,
        }

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Read-only SQLite migration readiness check"
    )
    parser.add_argument(
        "--database",
        default=str(DATABASE_PATH),
    )
    args = parser.parse_args()

    try:
        result = inspect_storage(args.database)
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f"Readiness check failed: {type(error).__name__}")
        raise SystemExit(1) from None

    print("PH TECH OPPORTUNITIES - STORAGE READINESS")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("No database changes were made.")

    if not result["migration_inventory_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()