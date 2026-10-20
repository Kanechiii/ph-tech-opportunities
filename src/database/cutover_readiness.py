"""Read-only reconciliation before any future storage cutover.

Compares two explicit pairs of SQLite databases.
Never migrates, writes data, exports credentials, or sends email.
"""

import argparse
import json
import sqlite3
from itertools import zip_longest
from pathlib import Path

from src.database.schema import DATABASE_PATH
from src.database.storage_readiness import inspect_storage
from src.database.migration_preflight import inspect_accounts
from src.reviewer_accounts import ACCOUNT_DATABASE


OPPORTUNITY_TABLES = (
    "opportunities",
    "collection_runs",
    "notification_history",
    "opportunity_reviews",
    "notification_jobs",
)

ACCOUNT_TABLES = (
    "reviewer_accounts",
    "reviewer_account_audit",
)


def _open_read_only(path):
    """Open an existing SQLite file without creating it."""

    path = Path(path)

    if not path.is_file():
        raise ValueError("Database file does not exist.")

    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
    )
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")

    return connection


def compare_database_tables(left_path, right_path, tables):
    """Compare all rows without returning sensitive row contents."""

    left = _open_read_only(left_path)

    try:
        right = _open_read_only(right_path)

        try:
            matches = {}

            for table in tables:
                # Names come only from the fixed table allowlist.
                order_column = (
                    "account_id"
                    if table == "reviewer_accounts"
                    else "id"
                )

                query = (
                    f'SELECT * FROM "{table}" '
                    f'ORDER BY "{order_column}"'
                )

                left_cursor = left.execute(query)
                right_cursor = right.execute(query)

                left_columns = [
                    item[0] for item in left_cursor.description
                ]
                right_columns = [
                    item[0] for item in right_cursor.description
                ]

                if left_columns != right_columns:
                    matches[table] = False
                    continue

                equal = True

                for left_row, right_row in zip_longest(
                    left_cursor,
                    right_cursor,
                ):
                    if (
                        left_row is None
                        or right_row is None
                        or tuple(left_row) != tuple(right_row)
                    ):
                        equal = False
                        break

                matches[table] = equal

            return matches

        finally:
            right.close()

    finally:
        left.close()


def assess_cutover(
    source_opportunities=DATABASE_PATH,
    source_accounts=ACCOUNT_DATABASE,
    *,
    candidate_opportunities=None,
    candidate_accounts=None,
):
    """Report differences and blockers without authorizing cutover."""

    source_opportunities = Path(
        source_opportunities
    ).resolve()
    source_accounts = Path(source_accounts).resolve()

    source_info = inspect_storage(source_opportunities)
    source_account_info = inspect_accounts(source_accounts)

    blockers = []

    if not source_info["migration_inventory_ready"]:
        blockers.append("source_opportunities_not_ready")

    if not source_account_info["ready"]:
        blockers.append("source_accounts_not_ready")

    source_states = source_info["notification_job_states"]

    if (
        source_states.get("sending", 0)
        + source_states.get("uncertain", 0)
    ):
        blockers.append("source_unresolved_delivery_states")

    opportunity_matches = None
    account_matches = None
    candidate_info = None
    candidate_account_info = None
    comparison_completed = False

    if (
        candidate_opportunities is None
        and candidate_accounts is None
    ):
        blockers.append("candidate_not_supplied")

    elif (
        candidate_opportunities is None
        or candidate_accounts is None
    ):
        blockers.append("candidate_incomplete")

    else:
        candidate_opportunities = Path(
            candidate_opportunities
        ).resolve()
        candidate_accounts = Path(
            candidate_accounts
        ).resolve()

        # Refuse a tautological comparison of files to themselves.
        if (
            source_opportunities == candidate_opportunities
            or source_accounts == candidate_accounts
        ):
            raise ValueError(
                "Source and candidate must be separate files."
            )

        candidate_info = inspect_storage(
            candidate_opportunities
        )
        candidate_account_info = inspect_accounts(
            candidate_accounts
        )

        if not candidate_info["migration_inventory_ready"]:
            blockers.append("candidate_opportunities_not_ready")

        if not candidate_account_info["ready"]:
            blockers.append("candidate_accounts_not_ready")

        candidate_states = candidate_info[
            "notification_job_states"
        ]

        if (
            candidate_states.get("sending", 0)
            + candidate_states.get("uncertain", 0)
        ):
            blockers.append("candidate_unresolved_delivery_states")

        if (
            source_info["migration_inventory_ready"]
            and source_account_info["ready"]
            and candidate_info["migration_inventory_ready"]
            and candidate_account_info["ready"]
        ):
            opportunity_matches = compare_database_tables(
                source_opportunities,
                candidate_opportunities,
                OPPORTUNITY_TABLES,
            )

            account_matches = compare_database_tables(
                source_accounts,
                candidate_accounts,
                ACCOUNT_TABLES,
            )

            comparison_completed = True

            if not all(opportunity_matches.values()):
                blockers.append("opportunity_history_diverged")

            if not all(account_matches.values()):
                blockers.append("reviewer_history_diverged")

    return {
        "reconciliation_passed": (
            comparison_completed and not blockers
        ),
        "comparison_completed": comparison_completed,
        "blockers": blockers,
        "opportunity_table_matches": opportunity_matches,
        "reviewer_table_matches": account_matches,
        "source_schema_version": source_info["schema_version"],
        "candidate_schema_version": (
            candidate_info["schema_version"]
            if candidate_info else None
        ),
        "source_notification_states": source_states,
        "candidate_notification_states": (
            candidate_info["notification_job_states"]
            if candidate_info else None
        ),
        "source_accounts_ready": source_account_info["ready"],
        "candidate_accounts_ready": (
            candidate_account_info["ready"]
            if candidate_account_info else None
        ),
        # Readiness does not grant permission to switch storage.
        "cutover_authorized": False,
        "migration_performed": False,
        "database_modified": False,
        "credentials_exported": False,
        "email_sent": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only storage reconciliation"
    )

    parser.add_argument(
        "--source-opportunities",
        default=str(DATABASE_PATH),
    )
    parser.add_argument(
        "--source-accounts",
        default=str(ACCOUNT_DATABASE),
    )
    parser.add_argument("--candidate-opportunities")
    parser.add_argument("--candidate-accounts")

    args = parser.parse_args()

    try:
        result = assess_cutover(
            source_opportunities=args.source_opportunities,
            source_accounts=args.source_accounts,
            candidate_opportunities=args.candidate_opportunities,
            candidate_accounts=args.candidate_accounts,
        )

    except (ValueError, OSError, sqlite3.Error) as error:
        print(
            "Storage reconciliation failed: "
            f"{type(error).__name__}: {error}"
        )
        raise SystemExit(1) from None

    print("PH TECH OPPORTUNITIES - STORAGE RECONCILIATION")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("No database migration or storage switch occurred.")

    if not result["reconciliation_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()