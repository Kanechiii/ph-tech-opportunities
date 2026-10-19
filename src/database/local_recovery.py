"""Safely recover a verified local backup into an isolated folder.

Never replaces live databases, sends email, or migrates storage.
"""

import argparse
import getpass
import json
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

from src.database.local_backup import (
    file_hash,
    verify_manifest_authentication,
)
from src.database.schema import PROJECT_ROOT
from src.database.storage_readiness import inspect_storage
from src.database.migration_preflight import inspect_accounts


DATABASE_FILES = (
    "opportunities.sqlite3",
    "reviewer_accounts.sqlite3",
)

BACKUP_FILES = frozenset((
    *DATABASE_FILES,
    "manifest.json",
))


def validate_backup_directory(
    backup_directory,
    *,
    authentication_password=None,
    require_authenticated=False,
):
    """Verify checksums, optional HMAC, and both SQLite schemas."""

    backup = Path(backup_directory).resolve(strict=True)

    if not backup.is_dir():
        raise ValueError("Backup path must be a directory.")

    manifest_path = backup / "manifest.json"

    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("Backup manifest is missing or unsafe.")

    # Reject unexpected content and symbolic links.
    if {item.name for item in backup.iterdir()} != BACKUP_FILES:
        raise ValueError("Unexpected backup directory contents.")

    for name in DATABASE_FILES:
        path = backup / name

        if not path.is_file() or path.is_symlink():
            raise ValueError("Backup database is missing or unsafe.")

    try:
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid backup manifest.") from error

    if (
        not isinstance(manifest, dict)
        or manifest.get("format_version") != 1
        or not isinstance(manifest.get("files"), dict)
        or set(manifest["files"]) != set(DATABASE_FILES)
    ):
        raise ValueError("Unsupported backup manifest.")

    verify_manifest_authentication(
        manifest,
        authentication_password,
        require_authenticated=require_authenticated,
    )

    for name in DATABASE_FILES:
        metadata = manifest["files"][name]

        if not isinstance(metadata, dict):
            raise ValueError("Invalid manifest file metadata.")

        expected_hash = metadata.get("sha256")
        expected_size = metadata.get("size_bytes")

        if (
            not isinstance(expected_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
            or type(expected_size) is not int
            or expected_size < 1
        ):
            raise ValueError("Invalid manifest hash or file size.")

        source = backup / name

        if source.stat().st_size != expected_size:
            raise ValueError("Backup file size mismatch.")

        if file_hash(source) != expected_hash:
            raise ValueError("Backup file hash mismatch.")

    opportunity_report = inspect_storage(
        backup / "opportunities.sqlite3"
    )

    account_report = inspect_accounts(
        backup / "reviewer_accounts.sqlite3"
    )

    if not opportunity_report["migration_inventory_ready"]:
        raise ValueError("Opportunity backup validation failed.")

    if not account_report["ready"]:
        raise ValueError("Reviewer backup validation failed.")

    return manifest


def recover_to_isolated_directory(
    backup_directory,
    destination_directory,
    *,
    authentication_password=None,
    require_authenticated=False,
):
    """Recover verified backups into an isolated directory only."""

    backup = Path(backup_directory).resolve(strict=True)
    destination = Path(destination_directory).resolve()
    project = PROJECT_ROOT.resolve()

    if destination.is_relative_to(project):
        raise ValueError(
            "Recovery destination must be outside the project."
        )

    if (
        destination == backup
        or destination.is_relative_to(backup)
        or backup.is_relative_to(destination)
    ):
        raise ValueError(
            "Recovery destination must be separate from backup."
        )

    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            "Recovery destination already exists."
        )

    # Authenticate and validate before creating recovery files.
    manifest = validate_backup_directory(
        backup,
        authentication_password=authentication_password,
        require_authenticated=require_authenticated,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = Path(tempfile.mkdtemp(
        prefix=".ph-tech-recovery-",
        dir=destination.parent,
    ))

    try:
        for name in DATABASE_FILES:
            source = backup / name
            recovered = temporary / name

            shutil.copy2(source, recovered)

            expected = manifest["files"][name]

            if (
                recovered.stat().st_size != expected["size_bytes"]
                or file_hash(recovered) != expected["sha256"]
            ):
                raise ValueError(
                    "Recovered file does not match manifest."
                )

        shutil.copy2(
            backup / "manifest.json",
            temporary / "manifest.json",
        )

        # Independently validate the recovered copies.
        recovered_opportunities = inspect_storage(
            temporary / "opportunities.sqlite3"
        )

        recovered_accounts = inspect_accounts(
            temporary / "reviewer_accounts.sqlite3"
        )

        if not recovered_opportunities["migration_inventory_ready"]:
            raise ValueError(
                "Recovered opportunity database is invalid."
            )

        if not recovered_accounts["ready"]:
            raise ValueError(
                "Recovered reviewer database is invalid."
            )

        # Refuse replacement of any existing destination.
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(
                "Recovery destination already exists."
            )

        os.rename(temporary, destination)

        return {
            "recovery_verified": True,
            "backup_authenticated": (
                "authentication" in manifest
            ),
            "destination": str(destination),
            "files": list(DATABASE_FILES),
            "opportunity_records": (
                recovered_opportunities["table_counts"]
            ),
            "reviewer_account_count": (
                recovered_accounts["account_count"]
            ),
            "source_databases_modified": False,
            "live_databases_replaced": False,
            "email_sent": False,
        }

    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser(
        description="Recover a local backup into an isolated folder"
    )

    parser.add_argument(
        "--backup",
        required=True,
        help="Existing verified backup directory",
    )

    parser.add_argument(
        "--destination",
        required=True,
        help="New recovery directory outside the project",
    )

    parser.add_argument(
        "--authenticate",
        action="store_true",
        help="Require and verify an authenticated backup",
    )

    args = parser.parse_args()

    password = None

    if args.authenticate:
        password = getpass.getpass(
            "Backup authentication passphrase: "
        )

    try:
        report = recover_to_isolated_directory(
            args.backup,
            args.destination,
            authentication_password=password,
            require_authenticated=args.authenticate,
        )

    except (
        ValueError,
        FileExistsError,
        OSError,
        sqlite3.Error,
    ) as error:
        print(
            f"Recovery failed: {type(error).__name__}: {error}"
        )
        raise SystemExit(1) from None

    print("PH TECH OPPORTUNITIES - RECOVERY DRILL")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("Live databases were not replaced.")
    print("No email was sent.")


if __name__ == "__main__":
    main()