"""Phase 12 Step 5: read-only, fail-closed production-readiness assessment.

Inspects three supplied existing SQLite sources without exporting row values.
A passing *development* assessment is never approval to import or cut over.
Recovery behavior is tested separately on synthetic fixtures in pytest.
"""

import argparse
import json
import sqlite3

from src.database.phase12_reconciliation import assess_source_reconciliation
from src.security_acceptance import assess_phase11


UNRESOLVED_PRODUCTION_REQUIREMENTS = (
    "encrypted_backup_and_authenticated_decryption_not_implemented",
    "independent_hosted_backup_restore_not_verified",
    "real_local_hosted_history_reconciliation_pending",
    "no_verified_live_sqlite_to_postgresql_migration",
    "no_postgresql_application_runtime_adapter",
    "no_credential_rotation_and_deployment_role_rollout",
    "no_approved_cutover_and_rollback",
    "windows_acl_and_direct_file_tamper_controls_incomplete",
    "reviewed_email_delivery_automation_not_authorized",
)


def assess_phase12(local_opportunities, local_accounts, hosted_opportunities):
    """Report verifiable local state, with permanent no-cutover flags."""
    reconciliation = assess_source_reconciliation(
        local_opportunities, local_accounts, hosted_opportunities
    )
    security = assess_phase11(local_opportunities, local_accounts)
    blockers = list(reconciliation["blockers"])
    blockers.extend(security["findings"])
    blockers.extend(UNRESOLVED_PRODUCTION_REQUIREMENTS)
    return {
        "phase": 12,
        "step": 5,
        "assessment": "development_recovery_and_migration_safety",
        "source_comparison_completed": reconciliation["comparison_completed"],
        "source_tables_equal": reconciliation["table_equal"],
        "different_source_tables": reconciliation["different_tables"],
        "source_reconciliation_clear": reconciliation["source_reconciliation_clear"],
        "local_security_foundations_acceptable": security[
            "phase_foundations_acceptable"
        ],
        "reviewer_audit_triggers_present": security[
            "reviewer_audit_triggers_present"
        ],
        "blockers": sorted(set(blockers)),
        "production_ready": False,
        "postgres_import_authorized": False,
        "production_cutover_authorized": False,
        "sqlite_backend_remains_authoritative": True,
        "reviewed_email_automation_enabled": False,
        "encrypted_backup_operational": False,
        "independent_hosted_restore_verified": False,
        "real_postgres_migration_verified": False,
        "source_records_exported": False,
        "password_verifiers_exported": False,
        "sqlite_sources_modified": False,
        "postgres_connected": False,
        "email_sent": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Offline Phase 12 final recovery and readiness report"
    )
    parser.add_argument("--local-opportunities", required=True)
    parser.add_argument("--local-accounts", required=True)
    parser.add_argument("--hosted-opportunities", required=True)
    args = parser.parse_args()

    try:
        report = assess_phase12(
            args.local_opportunities, args.local_accounts,
            args.hosted_opportunities,
        )
    except (ValueError, OSError, sqlite3.Error) as error:
        print("Phase 12 acceptance failed: " + type(error).__name__)
        raise SystemExit(1) from None

    print(json.dumps(report, indent=2, sort_keys=True))
    print("Assessment only: no migration, cutover, or automatic email.")
    # Exit nonzero for actual source integrity problems, not merely because
    # future production features remain intentionally unavailable.
    if (not report["source_comparison_completed"]
            or not report["local_security_foundations_acceptable"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
