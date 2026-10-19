"""Verified independent backups of both local SQLite databases.

Creates new backup folders only. Never restores databases,
modifies sources, uploads files, or sends email.
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.database.schema import DATABASE_PATH, PROJECT_ROOT
from src.database.snapshot import validate_database
from src.database.storage_readiness import inspect_storage
from src.database.migration_preflight import inspect_accounts
from src.reviewer_accounts import ACCOUNT_DATABASE


def file_hash(path):
    """Calculate SHA-256 without loading the whole file."""

    digest = hashlib.sha256()

    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)

    return digest.hexdigest()


def copy_sqlite(source_path, destination_path):
    """Use SQLite's online backup API for a consistent copy."""

    source_path = Path(source_path)
    destination_path = Path(destination_path)

    source = sqlite3.connect(
        source_path.resolve().as_uri() + "?mode=ro",
        uri=True,
    )
    destination = None

    try:
        destination = sqlite3.connect(destination_path)
        source.backup(destination)
        destination.close()
        destination = None

    finally:
        if destination is not None:
            destination.close()
        source.close()


def create_local_backup(
    destination,
    opportunity_path=DATABASE_PATH,
    account_path=ACCOUNT_DATABASE,
):
    """Create a new, validated two-database backup directory."""

    destination = Path(destination).resolve()
    opportunity_path = Path(opportunity_path).resolve()
    account_path = Path(account_path).resolve()

    if destination.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError(
            "Backup destination must be outside the project."
        )

    if opportunity_path == account_path:
        raise ValueError("Source databases must be different.")

    if destination.exists():
        raise FileExistsError(
            "Backup destination already exists."
        )

    if not opportunity_path.is_file():
        raise ValueError("Opportunity database does not exist.")

    if not account_path.is_file():
        raise ValueError("Reviewer database does not exist.")

    if not inspect_storage(opportunity_path)[
        "migration_inventory_ready"
    ]:
        raise ValueError("Opportunity database validation failed.")

    if not inspect_accounts(account_path)["ready"]:
        raise ValueError("Reviewer database validation failed.")

    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = Path(tempfile.mkdtemp(
        prefix=".ph-tech-backup-",
        dir=destination.parent,
    ))

    try:
        opportunity_copy = temporary / "opportunities.sqlite3"
        account_copy = temporary / "reviewer_accounts.sqlite3"

        copy_sqlite(opportunity_path, opportunity_copy)
        copy_sqlite(account_path, account_copy)

                # Validate the actual backup files, not just sources.
        validate_database(opportunity_copy)

        account_result = inspect_accounts(account_copy)

        if not account_result["ready"]:
            raise ValueError(
                "Reviewer backup validation failed: "
                f"integrity_ok={account_result['integrity_ok']}, "
                f"missing_tables={account_result['missing_tables']}, "
                f"audit_protected={account_result['audit_protected']}, "
                f"active_administrators="
                f"{account_result['active_administrators']}, "
                f"invalid_accounts={account_result['invalid_accounts']}"
            )

        manifest = {
            "format_version": 1,
            "created_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "files": {
                "opportunities.sqlite3": {
                    "sha256": file_hash(opportunity_copy),
                    "size_bytes": opportunity_copy.stat().st_size,
                },
                "reviewer_accounts.sqlite3": {
                    "sha256": file_hash(account_copy),
                    "size_bytes": account_copy.stat().st_size,
                },
            },
        }

        manifest_path = temporary / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # Publish only after both copies are validated.
        if destination.exists():
            raise FileExistsError(
                "Backup destination already exists."
            )

        os.rename(temporary, destination)

        return {
            "destination": str(destination),
            "files": sorted(manifest["files"]),
            "verified": True,
            "sources_modified": False,
            "email_sent": False,
        }

    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser(
        description="Create verified local database backups"
    )

    parser.add_argument(
        "--destination",
        required=True,
        help="New private backup folder outside the project",
    )

    args = parser.parse_args()

    try:
        result = create_local_backup(args.destination)

    except (
        ValueError,
        FileExistsError,
        OSError,
        sqlite3.Error,
    ) as error:
        print(
            f"Backup failed: {type(error).__name__}: {error}"
        )
        raise SystemExit(1) from None

    print("PH TECH OPPORTUNITIES - LOCAL BACKUP")
    print(json.dumps(result, indent=2))
    print("Keep this backup in a private, secure location.")


if __name__ == "__main__":
    main()