"""Read-only preflight for a future private database migration.

Inspects the opportunity and reviewer-account SQLite databases.
Does not export records, migrate data, or send email.
"""

import argparse
import json
import sqlite3
from pathlib import Path

from src.database.schema import DATABASE_PATH
from src.database.storage_readiness import inspect_storage
from src.reviewer_accounts import ACCOUNT_DATABASE


ACCOUNT_TABLES = frozenset({
    "reviewer_accounts",
    "reviewer_account_audit",
})

ACCOUNT_TRIGGERS = frozenset({
    "protect_account_audit_updates",
    "protect_account_audit_deletes",
})


def inspect_accounts(path=ACCOUNT_DATABASE):
    """Inspect account-store structure without exposing credentials."""

    path = Path(path)

    if not path.is_file():
        raise ValueError("Reviewer account database not found.")

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

        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        missing_tables = sorted(ACCOUNT_TABLES - tables)

        if integrity != "ok" or missing_tables:
            return {
                "ready": False,
                "integrity_ok": integrity == "ok",
                "missing_tables": missing_tables,
                "audit_protected": False,
                "account_count": None,
                "active_administrators": None,
                "invalid_accounts": None,
            }

        triggers = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='trigger'
                  AND tbl_name='reviewer_account_audit'
                """
            )
        }

        audit_protected = ACCOUNT_TRIGGERS.issubset(triggers)

        account_count = connection.execute(
            "SELECT COUNT(*) FROM reviewer_accounts"
        ).fetchone()[0]

        active_admins = connection.execute(
            """
            SELECT COUNT(*) FROM reviewer_accounts
            WHERE role='administrator' AND active=1
            """
        ).fetchone()[0]

        invalid_accounts = connection.execute(
            """
            SELECT COUNT(*) FROM reviewer_accounts
            WHERE role NOT IN (
                'administrator', 'reviewer', 'viewer'
            )
               OR active NOT IN (0, 1)
               OR password_hash IS NULL
               OR length(password_hash) = 0
            """
        ).fetchone()[0]

        return {
            "ready": (
                audit_protected
                and active_admins >= 1
                and invalid_accounts == 0
            ),
            "integrity_ok": True,
            "missing_tables": [],
            "audit_protected": audit_protected,
            "account_count": account_count,
            "active_administrators": active_admins,
            "invalid_accounts": invalid_accounts,
        }

    finally:
        connection.close()


def inspect_migration(
    opportunity_path=DATABASE_PATH,
    account_path=ACCOUNT_DATABASE,
):
    """Combine independent read-only checks into one report."""

    opportunities = inspect_storage(opportunity_path)
    accounts = inspect_accounts(account_path)

    job_states = opportunities["notification_job_states"]

    ambiguous_jobs = (
        job_states.get("sending", 0)
        + job_states.get("uncertain", 0)
    )

    blockers = []

    if not opportunities["migration_inventory_ready"]:
        blockers.append("opportunity_database_not_ready")

    if not accounts["ready"]:
        blockers.append("reviewer_account_database_not_ready")

    if ambiguous_jobs:
        blockers.append("unresolved_delivery_states")

    return {
        "preflight_passed": not blockers,
        "blockers": blockers,
        "opportunities": {
            "schema_version": opportunities["schema_version"],
            "integrity_ok": opportunities["integrity_ok"],
            "table_counts": opportunities["table_counts"],
            "notification_job_states": job_states,
        },
        "reviewer_accounts": accounts,
        "unresolved_delivery_jobs": ambiguous_jobs,
        "migration_performed": False,
        "records_exported": False,
        "credentials_exported": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only migration safety preflight"
    )

    parser.add_argument(
        "--opportunities",
        default=str(DATABASE_PATH),
    )
    parser.add_argument(
        "--accounts",
        default=str(ACCOUNT_DATABASE),
    )

    args = parser.parse_args()

    try:
        report = inspect_migration(
            args.opportunities,
            args.accounts,
        )
    except (ValueError, OSError, sqlite3.Error) as error:
        print(
            "Migration preflight failed: "
            f"{type(error).__name__}"
        )
        raise SystemExit(1) from None

    print("PH TECH OPPORTUNITIES - MIGRATION PREFLIGHT")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("No data was migrated, exported, or modified.")

    if not report["preflight_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()