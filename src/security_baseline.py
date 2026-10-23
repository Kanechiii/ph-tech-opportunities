"""Read-only security baseline for the current local development system.

No account authentication, live record reads, SMTP, cloud connections,
database initialization or changes. Never prints passwords or hashes.
"""

import argparse
import json
import sqlite3
from pathlib import Path

from src.database.schema import DATABASE_PATH
from src.database.migration_preflight import inspect_accounts
from src.database.storage_readiness import inspect_storage
from src.reviewer_accounts import ACCOUNT_DATABASE


LIMITATIONS = (
    "login_rate_limiting_not_implemented",
    "password_recovery_not_implemented",
    "authentication_session_management_not_implemented",
    "direct_sqlite_file_tampering_outside_app_authorization",
    "cross_database_authorization_not_atomic",
    "reviewed_email_send_requires_local_confirmation_not_reviewer_auth",
    "backup_manifest_authentication_does_not_encrypt_contents",
    "hosted_sqlite_artifact_not_private_durable_storage",
)


def inspect_security_baseline(
    opportunity_path=DATABASE_PATH,
    account_path=ACCOUNT_DATABASE,
):
    """Return account/storage structure and documented limitations only."""
    opportunities = Path(opportunity_path)
    accounts = Path(account_path)
    if (
        not opportunities.is_file()
        or not accounts.is_file()
        or opportunities.resolve() == accounts.resolve()
    ):
        raise ValueError("Two distinct existing database files required.")

    opportunity_check = inspect_storage(opportunities)
    accounts_check = inspect_accounts(accounts)

    findings = []
    if not opportunity_check["migration_inventory_ready"]:
        findings.append("opportunity_storage_integrity_not_ready")
    if not accounts_check["ready"]:
        findings.append("account_storage_integrity_not_ready")
    if not accounts_check["audit_protected"]:
        findings.append("reviewer_audit_triggers_missing")
    ambiguous = opportunity_check["notification_job_states"]
    if ambiguous.get("sending", 0) or ambiguous.get("uncertain", 0):
        findings.append("unresolved_delivery_states_present")

    return {
        "security_baseline_ready_for_further_hardening": (
            accounts_check["ready"]
            and opportunity_check["migration_inventory_ready"]
        ),
        "account_count": accounts_check["account_count"],
        "active_administrators": accounts_check["active_administrators"],
        "audit_append_only_triggers_present": accounts_check["audit_protected"],
        "opportunity_schema_version": opportunity_check["schema_version"],
        "notification_job_states": ambiguous,
        "findings": findings,
        "known_limitations": list(LIMITATIONS),
        "production_ready": False,
        "data_modified": False,
        "credentials_exported": False,
        "postgres_connected": False,
        "email_sent": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only local security baseline")
    parser.add_argument("--opportunities", default=str(DATABASE_PATH))
    parser.add_argument("--accounts", default=str(ACCOUNT_DATABASE))
    args = parser.parse_args()
    try:
        report = inspect_security_baseline(args.opportunities, args.accounts)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Security baseline failed: {type(error).__name__}")
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2, sort_keys=True))
    print("No account secrets were exported. No databases or email state changed.")
    if not report["security_baseline_ready_for_further_hardening"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
