"""Read-only inventory of local and hosted SQLite opportunity histories.

Requires separately preserved existing SQLite files. No download, data
export, reconciliation, migration, account copy, or SMTP operation.
"""

import argparse
import json
import sqlite3
from pathlib import Path

from src.database.cutover_readiness import (
    OPPORTUNITY_TABLES,
    compare_database_tables,
)
from src.database.migration_preflight import inspect_accounts
from src.database.storage_readiness import inspect_storage


def audit_source_histories(
    local_opportunities,
    local_accounts,
    hosted_opportunities,
):
    """Compare full opportunity histories and identify migration blockers.

    The hosted path must be an independently preserved, local SQLite copy
    of the GitHub Actions artifact, NOT a live GitHub URL.
    """
    paths = {
        "local_opportunities": Path(local_opportunities).resolve(strict=True),
        "local_accounts": Path(local_accounts).resolve(strict=True),
        "hosted_opportunities": Path(hosted_opportunities).resolve(strict=True),
    }

    if len(set(paths.values())) != 3:
        raise ValueError("Three distinct source database files are required.")

    if any(not p.is_file() for p in paths.values()):
        raise ValueError("Each source must be an existing SQLite file.")

    local = inspect_storage(paths["local_opportunities"])
    hosted = inspect_storage(paths["hosted_opportunities"])
    accounts = inspect_accounts(paths["local_accounts"])

    blockers = []

    if not local["migration_inventory_ready"]:
        blockers.append("local_opportunity_database_invalid")
    if not hosted["migration_inventory_ready"]:
        blockers.append("hosted_opportunity_database_invalid")
    if not accounts["ready"]:
        blockers.append("local_reviewer_database_invalid")

    for label, info in (("local", local), ("hosted", hosted)):
        states = info["notification_job_states"]
        if states.get("sending", 0) or states.get("uncertain", 0):
            blockers.append(f"{label}_unresolved_delivery_states")

    table_matches = None
    if local["migration_inventory_ready"] and hosted["migration_inventory_ready"]:
        table_matches = compare_database_tables(
            paths["local_opportunities"],
            paths["hosted_opportunities"],
            OPPORTUNITY_TABLES,
        )
        if not all(table_matches.values()):
            blockers.append("opportunity_histories_diverged")

    return {
        "inventory_complete": bool(
            local["migration_inventory_ready"]
            and hosted["migration_inventory_ready"]
            and accounts["ready"]
        ),
        "opportunity_histories_match": (
            all(table_matches.values()) if table_matches is not None else False
        ),
        "table_matches": table_matches,
        "local": {
            "schema_version": local["schema_version"],
            "table_counts": local["table_counts"],
            "notification_job_states": local["notification_job_states"],
        },
        "hosted": {
            "schema_version": hosted["schema_version"],
            "table_counts": hosted["table_counts"],
            "notification_job_states": hosted["notification_job_states"],
        },
        "reviewer_accounts": {
            "ready": accounts["ready"],
            "account_count": accounts["account_count"],
            "audit_protected": accounts["audit_protected"],
        },
        "blockers": blockers,
        "safe_to_reconcile_later": not blockers,
        "production_cutover_authorized": False,
        "data_modified": False,
        "records_exported": False,
        "credentials_exported": False,
        "email_sent": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only source-history inventory; never migrates data"
    )
    parser.add_argument("--local-opportunities", required=True)
    parser.add_argument("--local-accounts", required=True)
    parser.add_argument("--hosted-opportunities", required=True)
    args = parser.parse_args()
    try:
        result = audit_source_histories(
            args.local_opportunities,
            args.local_accounts,
            args.hosted_opportunities,
        )
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f"Source-history audit failed: {type(error).__name__}")
        raise SystemExit(1) from None

    print(json.dumps(result, indent=2, sort_keys=True))
    print("No files were modified or migrated. No email was sent.")
    if result["blockers"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
