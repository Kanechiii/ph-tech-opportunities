"""Collect classified RSS announcements and persist them locally."""

import sqlite3

from src.collectors.source_registry import (
    DEFAULT_CONFIG,
    collect_all_sources,
    load_sources,
)
from src.database.schema import (
    DATABASE_PATH,
    connect_database,
    initialize_database,
)
from src.database.storage import save_opportunity


def record_collection_run(
    source_id,
    status,
    items_found,
    error_type=None,
    database_path=DATABASE_PATH,
):
    """Record a completed source collection attempt."""

    allowed_statuses = {"success", "partial", "failed"}

    if status not in allowed_statuses:
        raise ValueError("Invalid collection status.")

    if type(items_found) is not int or items_found < 0:
        raise ValueError("Invalid items_found count.")

    connection = connect_database(database_path)

    try:
        cursor = connection.execute(
            """
            INSERT INTO collection_runs (
                source_id,
                started_at,
                finished_at,
                status,
                items_found,
                error_type
            )
            VALUES (
                ?,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                ?,
                ?,
                ?
            )
            """,
            (
                source_id,
                status,
                items_found,
                error_type,
            ),
        )

        connection.commit()
        return cursor.lastrowid

    finally:
        connection.close()


def get_collection_history(
    database_path=DATABASE_PATH,
    limit=20,
):
    """Retrieve recent collection history records."""

    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid history limit.")

    connection = connect_database(database_path)

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM collection_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def run_collection(
    database_path=DATABASE_PATH,
    config_path=DEFAULT_CONFIG,
):
    """Collect, classify, store, and log enabled RSS sources."""

    # Validate configuration before retrieving anything.
    sources = load_sources(config_path)

    # Safe to repeat: existing tables and records remain intact.
    initialize_database(database_path)

    # Reuse Phase 3 collection and classification.
    announcements, source_errors = collect_all_sources(
        config_path
    )

    error_map = {
        error["source_id"]: error["error_type"]
        for error in source_errors
    }

    summary = {
        "sources_checked": 0,
        "new": 0,
        "updated": 0,
        "failed_items": 0,
        "failed_sources": 0,
        "source_results": [],
    }

    for source in sources:
        if not source["enabled"]:
            continue

        summary["sources_checked"] += 1
        source_id = source["id"]

        source_items = [
            item for item in announcements
            if item["source_id"] == source_id
        ]

        feed_error = error_map.get(source_id)

        if feed_error is not None:
            status = "failed"
            error_type = feed_error
            summary["failed_sources"] += 1

        else:
            source_new = 0
            source_updated = 0
            source_failed_items = 0
            error_type = None

            for item in source_items:
                try:
                    result = save_opportunity(
                        item,
                        database_path=database_path,
                    )

                    if result["created"]:
                        source_new += 1
                    else:
                        source_updated += 1

                except (
                    sqlite3.Error,
                    ValueError,
                    TypeError,
                ) as error:
                    source_failed_items += 1
                    error_type = type(error).__name__

            summary["new"] += source_new
            summary["updated"] += source_updated
            summary["failed_items"] += source_failed_items

            if source_failed_items == 0:
                status = "success"
            elif source_new + source_updated > 0:
                status = "partial"
            else:
                status = "failed"

            if status == "failed":
                summary["failed_sources"] += 1

        run_id = record_collection_run(
            source_id=source_id,
            status=status,
            items_found=len(source_items),
            error_type=error_type,
            database_path=database_path,
        )

        summary["source_results"].append({
            "source_id": source_id,
            "run_id": run_id,
            "status": status,
            "items_found": len(source_items),
            "error_type": error_type,
        })

    return summary


def main():
    """Run a local collection and database storage preview."""

    print("=" * 55)
    print("PH TECH OPPORTUNITIES - PERSISTENT COLLECTION")
    print("=" * 55)
    print("Mode: Local SQLite storage")
    print("Automatic email delivery: Disabled")
    print()

    try:
        summary = run_collection()

    except (
        sqlite3.Error,
        OSError,
        ValueError,
        RuntimeError,
    ) as error:
        print(f"Pipeline failed: {type(error).__name__}")
        raise SystemExit(1) from None

    print()
    print("DATABASE SUMMARY")
    print("-" * 55)
    print(f"Sources checked: {summary['sources_checked']}")
    print(f"New records: {summary['new']}")
    print(f"Updated records: {summary['updated']}")
    print(f"Failed items: {summary['failed_items']}")
    print(f"Failed sources: {summary['failed_sources']}")

    for result in summary["source_results"]:
        print(
            f"{result['source_id']}: {result['status']} "
            f"({result['items_found']} found)"
        )

    print()
    print("Collection history saved locally.")
    print("No email was sent.")

    if (
        summary["failed_items"] > 0
        or summary["failed_sources"] > 0
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()