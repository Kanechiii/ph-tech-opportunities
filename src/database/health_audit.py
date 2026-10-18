"""Read-only Phase 6 database health audit.

Does not modify records, send email, or contact external services.
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.database.schema import DATABASE_PATH, SCHEMA_VERSION


EXPECTED_TABLES = {
    "opportunities",
    "collection_runs",
    "notification_history",
    "opportunity_reviews",
    "notification_jobs",
}

REVIEW_TRIGGERS = {
    "protect_review_updates",
    "protect_review_deletes",
}

JOB_STATES = {
    "pending",
    "sending",
    "sent",
    "failed",
    "uncertain",
}


def audit_database(database_path=DATABASE_PATH, stale_minutes=30):
    """Inspect database health without writing to SQLite."""

    if type(stale_minutes) is not int or stale_minutes < 1:
        raise ValueError("stale_minutes must be positive.")

    path = Path(database_path)

    if not path.is_file():
        raise ValueError("Database file does not exist.")

    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA query_only = ON")

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        missing_tables = sorted(EXPECTED_TABLES - tables)

        if missing_tables:
            return {
                "healthy": False,
                "issues": ["missing_required_tables"],
                "schema_version": version,
                "missing_tables": missing_tables,
                "database_modified": False,
            }

        foreign_key_issues = len(
            connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        triggers = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='trigger'
                  AND tbl_name='opportunity_reviews'
                """
            )
        }

        counts = {}
        for table in sorted(EXPECTED_TABLES):
            counts[table] = connection.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]

        states = {status: 0 for status in sorted(JOB_STATES)}

        for row in connection.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM notification_jobs
            GROUP BY status
            """
        ):
            if row["status"] in states:
                states[row["status"]] = row["total"]

        inconsistent_jobs = connection.execute(
            """
            SELECT COUNT(*)
            FROM notification_jobs
            WHERE
                (status='sending'
                 AND (claim_token IS NULL OR claimed_at IS NULL))
                OR
                (status!='sending' AND claim_token IS NOT NULL)
                OR
                (status='sent' AND sent_at IS NULL)
            """
        ).fetchone()[0]

        # Parse the claim time using SQLite's UTC timestamp format.
        threshold = (
            datetime.now(timezone.utc)
            - timedelta(minutes=stale_minutes)
        ).strftime("%Y-%m-%d %H:%M:%S")

        stale_claims = connection.execute(
            """
            SELECT COUNT(*)
            FROM notification_jobs
            WHERE status='sending'
              AND claimed_at < ?
            """,
            (threshold,),
        ).fetchone()[0]

        issues = []

        if integrity != "ok":
            issues.append("sqlite_integrity_failure")

        if version != SCHEMA_VERSION:
            issues.append("schema_version_mismatch")

        if foreign_key_issues:
            issues.append("foreign_key_violations")

        if not REVIEW_TRIGGERS.issubset(triggers):
            issues.append("review_history_trigger_missing")

        if inconsistent_jobs:
            issues.append("inconsistent_notification_state")

        if stale_claims:
            issues.append("stale_sending_claims")

        return {
            "healthy": not issues,
            "issues": issues,
            "schema_version": version,
            "integrity_ok": integrity == "ok",
            "foreign_key_violations": foreign_key_issues,
            "review_history_protected": (
                REVIEW_TRIGGERS.issubset(triggers)
            ),
            "table_counts": counts,
            "notification_states": states,
            "inconsistent_jobs": inconsistent_jobs,
            "stale_sending_claims": stale_claims,
            "database_modified": False,
        }

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Read-only Phase 6 reliability audit"
    )
    parser.add_argument(
        "--database",
        default=str(DATABASE_PATH),
    )
    parser.add_argument(
        "--stale-minutes",
        type=int,
        default=30,
    )

    args = parser.parse_args()

    try:
        result = audit_database(
            args.database,
            args.stale_minutes,
        )
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f"Health audit failed: {type(error).__name__}")
        raise SystemExit(1) from None

    print("PH TECH OPPORTUNITIES - DATABASE HEALTH")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("No database records were modified.")
    print("No email was sent.")

    if not result["healthy"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
"""Read-only health audit for the existing SQLite database.

No account changes, migrations, queue transitions, or email delivery.
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.database.schema import DATABASE_PATH, SCHEMA_VERSION

TABLES = frozenset({
    "opportunities",
    "collection_runs",
    "notification_history",
    "opportunity_reviews",
    "notification_jobs",
})
REVIEW_TRIGGERS = frozenset({
    "protect_review_updates",
    "protect_review_deletes",
})
JOB_STATES = ("pending", "sending", "sent", "failed", "uncertain")


def audit_database(database_path=DATABASE_PATH, stale_minutes=30):
    """Return structural findings without modifying the database."""

    if type(stale_minutes) is not int or stale_minutes < 1:
        raise ValueError("stale_minutes must be a positive integer.")

    path = Path(database_path)
    if not path.is_file():
        raise ValueError("Database file does not exist.")

    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA query_only = ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]

        available = {
            row["name"] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = sorted(TABLES - available)
        issues = []
        if integrity != "ok":
            issues.append("sqlite_integrity_failure")
        if version != SCHEMA_VERSION:
            issues.append("schema_version_mismatch")
        if missing:
            issues.append("missing_required_tables")

        report = {
            "healthy": False,
            "issues": issues,
            "schema_version": version,
            "integrity_ok": integrity == "ok",
            "missing_tables": missing,
            "foreign_key_violations": None,
            "review_history_protected": None,
            "table_counts": {},
            "notification_states": {},
            "inconsistent_jobs": None,
            "stale_sending_claims": None,
            "database_modified": False,
        }

        if missing or integrity != "ok":
            return report

        foreign_key_issues = len(
            connection.execute("PRAGMA foreign_key_check").fetchall()
        )
        triggers = {
            row["name"] for row in connection.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='trigger'
                     AND tbl_name='opportunity_reviews'"""
            )
        }
        protected = REVIEW_TRIGGERS.issubset(triggers)
        counts = {
            table: connection.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]
            for table in sorted(TABLES)
        }
        states = {state: 0 for state in JOB_STATES}
        for row in connection.execute(
            "SELECT status, COUNT(*) AS total FROM notification_jobs GROUP BY status"
        ):
            states[row["status"]] = row["total"]

        inconsistent = connection.execute(
            """SELECT COUNT(*) FROM notification_jobs
               WHERE (status='sending'
                      AND (claim_token IS NULL OR claimed_at IS NULL))
                  OR (status!='sending' AND claim_token IS NOT NULL)
                  OR (status='sent' AND sent_at IS NULL)
                  OR (status!='sent' AND sent_at IS NOT NULL)
                  OR (status='pending' AND claimed_at IS NOT NULL)"""
        ).fetchone()[0]

        threshold = (
            datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
        ).strftime("%Y-%m-%d %H:%M:%S")
        stale = connection.execute(
            """SELECT COUNT(*) FROM notification_jobs
               WHERE status='sending' AND claimed_at < ?""",
            (threshold,),
        ).fetchone()[0]

        if foreign_key_issues:
            issues.append("foreign_key_violations")
        if not protected:
            issues.append("review_history_trigger_missing")
        if inconsistent:
            issues.append("inconsistent_notification_state")
        if stale:
            issues.append("stale_sending_claims")

        report.update({
            "healthy": not issues,
            "foreign_key_violations": foreign_key_issues,
            "review_history_protected": protected,
            "table_counts": counts,
            "notification_states": states,
            "inconsistent_jobs": inconsistent,
            "stale_sending_claims": stale,
        })
        return report
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description="Read-only SQLite health audit")
    parser.add_argument("--database", default=str(DATABASE_PATH))
    parser.add_argument("--stale-minutes", type=int, default=30)
    args = parser.parse_args()

    try:
        result = audit_database(args.database, args.stale_minutes)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Health audit failed: {type(exc).__name__}")
        raise SystemExit(1) from None

    print(json.dumps(result, indent=2, sort_keys=True))
    print("No SQLite changes or email delivery performed.")
    if not result["healthy"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
