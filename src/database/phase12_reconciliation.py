"""Phase 12 Step 1: privacy-minimized, read-only source-history reconciliation.

Reports table-level equality and delivery blockers only. No row values,
fingerprints, reviewer identities, passwords, source writes or email.
"""

import argparse
import json
import sqlite3
from pathlib import Path

from src.database.cutover_readiness import OPPORTUNITY_TABLES, compare_database_tables
from src.database.migration_preflight import inspect_accounts
from src.database.storage_readiness import inspect_storage


def _existing_regular_file(value):
    path = Path(value)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Existing regular SQLite source required.")
    return path.resolve(strict=True)


def assess_source_reconciliation(local_opportunities, local_accounts,
                                 hosted_opportunities):
    paths = (
        _existing_regular_file(local_opportunities),
        _existing_regular_file(local_accounts),
        _existing_regular_file(hosted_opportunities),
    )
    if len(set(paths)) != 3:
        raise ValueError("Three distinct source databases required.")

    local = inspect_storage(paths[0])
    accounts = inspect_accounts(paths[1])
    hosted = inspect_storage(paths[2])

    blockers = []
    if not local["migration_inventory_ready"]:
        blockers.append("local_database_invalid")
    if not hosted["migration_inventory_ready"]:
        blockers.append("hosted_database_invalid")
    if not accounts["ready"]:
        blockers.append("account_database_invalid")

    for label, report in (("local", local), ("hosted", hosted)):
        states = report["notification_job_states"]
        if states.get("uncertain", 0) or states.get("sending", 0):
            blockers.append(label + "_ambiguous_delivery")

    comparisons = None
    if local["migration_inventory_ready"] and hosted["migration_inventory_ready"]:
        comparisons = compare_database_tables(paths[0], paths[2], OPPORTUNITY_TABLES)
        if not all(comparisons.values()):
            blockers.append("histories_diverged")

    return {
        "phase": 12,
        "step": 1,
        "comparison_completed": comparisons is not None,
        "table_equal": comparisons,
        "different_tables": (
            sorted(table for table, match in comparisons.items() if not match)
            if comparisons is not None else None
        ),
        "source_inventory_ready": not any(
            name.endswith("_invalid") for name in blockers
        ),
        "blockers": sorted(set(blockers)),
        "source_reconciliation_clear": (
            comparisons is not None and all(comparisons.values()) and not blockers
        ),
        "migration_authorized": False,
        "cutover_authorized": False,
        "sqlite_remains_authoritative": True,
        "raw_rows_exported": False,
        "password_verifiers_exported": False,
        "source_files_modified": False,
        "postgres_connected": False,
        "email_sent": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Offline Phase 12 source-history reconciliation gate"
    )
    parser.add_argument("--local-opportunities", required=True)
    parser.add_argument("--local-accounts", required=True)
    parser.add_argument("--hosted-opportunities", required=True)
    args = parser.parse_args()
    try:
        report = assess_source_reconciliation(
            args.local_opportunities, args.local_accounts,
            args.hosted_opportunities,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        print("Reconciliation failed: " + type(error).__name__)
        raise SystemExit(1) from None
    print(json.dumps(report, sort_keys=True, indent=2))
    print("Read-only comparison only. No production migration authorized.")
    if not report["source_reconciliation_clear"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
