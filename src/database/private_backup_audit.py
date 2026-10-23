"""Phase 11 Step 4: read-only backup confidentiality and audit safeguards.

Never opens private records, prints password verifiers, creates backups,
changes permissions or modifies SQLite/manifest files. This is an advisory
configuration audit, NOT a claim of encryption or comprehensive ACL review.
"""

import argparse
import json
import os
import sqlite3
import stat
from pathlib import Path

from src.database.migration_preflight import inspect_accounts


EXPECTED_BACKUP_FILES = frozenset({
    "opportunities.sqlite3",
    "reviewer_accounts.sqlite3",
    "manifest.json",
})


def _permissions(path):
    """Return local POSIX permission findings; Windows ACLs need native review."""
    if os.name == "nt":
        return ["windows_acl_not_verified"]
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return ["group_or_other_file_access_detected"]
    return []


def inspect_private_backup(backup_directory, reviewer_accounts):
    """Inspect manifest metadata and confidentiality without exporting rows.

    Authenticated backup manifests are integrity protection, not encryption.
    No trust is granted to an unverified manifest signature.
    """
    backup = Path(backup_directory)
    accounts = Path(reviewer_accounts)

    if not backup.is_dir() or backup.is_symlink():
        raise ValueError("Existing regular backup directory required.")
    if not accounts.is_file() or accounts.is_symlink():
        raise ValueError("Existing regular reviewer database required.")

    findings = []
    entries = list(backup.iterdir())
    if {entry.name for entry in entries} != EXPECTED_BACKUP_FILES:
        findings.append("unexpected_or_missing_backup_files")

    if any(entry.is_symlink() for entry in entries):
        findings.append("backup_symlink_detected")

    manifest_path = backup / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        findings.append("manifest_missing_or_unsafe")
        manifest = None
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            manifest = None
            findings.append("manifest_invalid")

    if not isinstance(manifest, dict) or manifest.get("format_version") != 1:
        findings.append("manifest_format_not_verified")
        signed = False
    else:
        meta = manifest.get("authentication")
        signed = isinstance(meta, dict) and meta.get("scheme") == (
            "scrypt-hmac-sha256-v1"
        )
        if not signed:
            findings.append("authenticated_manifest_not_confirmed")
        else:
            findings.append("manifest_signature_not_verified_without_passphrase")

    # Current backup layout uses unencrypted SQLite files regardless of HMAC.
    findings.append("backup_contents_not_encrypted")

    for name in EXPECTED_BACKUP_FILES:
        item = backup / name
        if item.is_file() and not item.is_symlink():
            findings.extend(_permissions(item))
    findings.extend(_permissions(backup))
    findings.extend(_permissions(accounts))

    account_report = inspect_accounts(accounts)
    if not account_report["ready"]:
        findings.append("reviewer_account_integrity_not_ready")
    if not account_report["audit_protected"]:
        findings.append("reviewer_account_audit_not_append_only")

    return {
        "audit_completed": True,
        "backup_format": "plaintext_sqlite_v1",
        "manifest_signed_metadata_present": signed,
        "manifest_signature_cryptographically_verified": False,
        "backup_encrypted": False,
        "windows_acl_verified": False,
        "reviewer_account_structure_ready": account_report["ready"],
        "account_audit_append_only_triggers_present": account_report[
            "audit_protected"
        ],
        "findings": sorted(set(findings)),
        "production_ready": False,
        "sources_modified": False,
        "backup_modified": False,
        "credentials_exported": False,
        "email_sent": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only private-backup confidentiality assessment"
    )
    parser.add_argument("--backup", required=True)
    parser.add_argument("--accounts", required=True)
    args = parser.parse_args()
    try:
        result = inspect_private_backup(args.backup, args.accounts)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Private backup audit failed: {type(error).__name__}")
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2, sort_keys=True))
    print("No backups, account records, permissions, or emails were changed.")


if __name__ == "__main__":
    main()
