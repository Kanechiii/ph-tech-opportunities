"""Phase 11 Step 5: offline, fail-closed security acceptance report.

Reads local SQLite metadata only. Never authenticates users, prints password
hashes, writes databases, rotates credentials, contacts Neon, or sends emails.
Phase acceptance is NOT a production security certification.
"""

import argparse
import json
import sqlite3
from pathlib import Path

from src.database.schema import DATABASE_PATH
from src.database.storage_readiness import inspect_storage
from src.database.migration_preflight import inspect_accounts
from src.reviewer_accounts import ACCOUNT_DATABASE
from src.reviewer_throttle import attempts_path


OPEN_SECURITY_GAPS = (
    "backup_contents_are_not_encrypted",
    "windows_acl_review_not_completed_by_python",
    "local_throttle_can_be_bypassed_by_direct_file_access",
    "password_recovery_not_implemented",
    "user_session_management_not_implemented",
    "cross_database_atomicity_not_guaranteed",
    "reviewed_email_delivery_lacks_reviewer_authentication",
    "hosted_sqlite_artifacts_are_not_private_durable_storage",
    "postgresql_runtime_and_real_migration_not_implemented",
)


def assess_phase11(opportunity_path=DATABASE_PATH,
                   account_path=ACCOUNT_DATABASE):
    """Report protections and blockers without modifying sensitive files."""
    opportunity = Path(opportunity_path)
    accounts = Path(account_path)
    if (not opportunity.is_file() or not accounts.is_file()
            or opportunity.resolve() == accounts.resolve()):
        raise ValueError("Two distinct existing SQLite databases required.")

    opportunity_report = inspect_storage(opportunity)
    account_report = inspect_accounts(accounts)
    ledger = attempts_path(accounts)

    # Only stat the optional lockout ledger; never open or expose its rows.
    if ledger.is_symlink():
        raise ValueError("Unsafe authentication throttle ledger.")

    findings = []
    if not opportunity_report["migration_inventory_ready"]:
        findings.append("opportunity_integrity_not_ready")
    if not account_report["ready"]:
        findings.append("reviewer_account_integrity_not_ready")
    if not account_report["audit_protected"]:
        findings.append("append_only_account_audit_triggers_missing")

    jobs = opportunity_report["notification_job_states"]
    if jobs.get("sending", 0) or jobs.get("uncertain", 0):
        findings.append("ambiguous_notification_states_remain")

    return {
        "phase": 11,
        "assessment": "development_security_foundations",
        "offline_inspection_completed": True,
        "opportunity_integrity_ready": (
            opportunity_report["migration_inventory_ready"]
        ),
        "reviewer_account_integrity_ready": account_report["ready"],
        "reviewer_audit_triggers_present": account_report["audit_protected"],
        "active_administrators": account_report["active_administrators"],
        "local_authentication_throttle_implemented": True,
        "throttle_ledger_present": ledger.is_file(),
        "notification_job_states": jobs,
        "findings": findings,
        "outstanding_security_gaps": list(OPEN_SECURITY_GAPS),
        "phase_foundations_acceptable": (
            opportunity_report["migration_inventory_ready"]
            and account_report["ready"]
        ),
        "production_ready": False,
        "production_cutover_authorized": False,
        "sqlite_remains_authoritative": True,
        "reviewed_email_automation_enabled": False,
        "files_modified": False,
        "secrets_exported": False,
        "email_sent": False,
        "postgres_connected": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only Phase 11 development security acceptance"
    )
    parser.add_argument("--opportunities", default=str(DATABASE_PATH))
    parser.add_argument("--accounts", default=str(ACCOUNT_DATABASE))
    args = parser.parse_args()

    try:
        report = assess_phase11(args.opportunities, args.accounts)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Security acceptance failed: {type(error).__name__}")
        raise SystemExit(1) from None

    print(json.dumps(report, indent=2, sort_keys=True))
    print("No account records, backups, or notification states were changed.")
    if not report["phase_foundations_acceptable"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
