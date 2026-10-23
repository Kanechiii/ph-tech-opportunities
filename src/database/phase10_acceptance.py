"""Phase 10 final read-only acceptance assessment.

Reports observed SQLite inventory and explicit production blockers.
No PostgreSQL connections, credential access, exports, migrations or SMTP.
"""

import argparse
import json
import sqlite3

from src.database.postgres_migration_plan import build_migration_plan


REMAINING_PRODUCTION_BLOCKERS = (
    "no_authoritative_postgresql_runtime_adapter",
    "no_verified_live_sqlite_to_postgresql_migration",
    "no_cross_environment_immutable_history_reconciliation",
    "no_independent_hosted_backup_and_restore_drill",
    "no_postgresql_credential_rotation_or_runtime_role_rollout",
    "no_approved_production_cutover",
)


def assess_phase10(local_opportunities, local_accounts, hosted_opportunities):
    """Assess the supplied immutable sources; never authorize a cutover."""
    plan = build_migration_plan(
        local_opportunities, local_accounts, hosted_opportunities
    )
    source_blockers = list(plan["blockers"])
    return {
        "phase": 10,
        "readiness_type": "development_infrastructure_acceptance",
        "source_inventory_complete": plan["inventory_complete"],
        "source_history_equal": (
            plan["opportunity_table_matches"] is not None
            and all(plan["opportunity_table_matches"].values())
        ),
        "source_blockers": source_blockers,
        "required_future_capabilities": list(REMAINING_PRODUCTION_BLOCKERS),
        "storage_backend": "sqlite",
        "postgres_staging_only": True,
        "cutover_authorized": False,
        "production_ready": False,
        "unattended_reviewed_email_enabled": False,
        "source_files_modified": False,
        "records_exported": False,
        "postgres_connected": False,
        "email_sent": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only Phase 10 acceptance report"
    )
    parser.add_argument("--local-opportunities", required=True)
    parser.add_argument("--local-accounts", required=True)
    parser.add_argument("--hosted-opportunities", required=True)
    args = parser.parse_args()
    try:
        result = assess_phase10(
            args.local_opportunities,
            args.local_accounts,
            args.hosted_opportunities,
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Phase 10 acceptance inventory failed: {type(error).__name__}")
        raise SystemExit(1) from None

    print(json.dumps(result, indent=2, sort_keys=True))
    print("This is an offline assessment; production cutover is not authorized.")
    # Source blockers must remain visible and make the command nonzero.
    if result["source_blockers"] or not result["source_inventory_complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
