"""Verified independent backups of both local SQLite databases.

Creates new backup folders only. Never restores databases,
modifies sources, uploads files, or sends email.
"""

import argparse
import getpass
import hashlib
import hmac
import json
import os
import secrets
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

AUTH_SCHEME = "scrypt-hmac-sha256-v1"


def _manifest_bytes(manifest):
    """Canonical bytes of manifest data excluding its authenticator."""

    payload = {
        key: value
        for key, value in manifest.items()
        if key != "authentication"
    }

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _derive_backup_key(password, salt):
    """Derive a separate HMAC key from the backup passphrase."""

    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )


def authenticate_manifest(manifest, password):
    """Add an HMAC authenticator without storing the passphrase."""

    if (
        type(password) is not str
        or not 16 <= len(password) <= 256
    ):
        raise ValueError(
            "Backup passphrase must contain 16 to 256 characters."
        )

    if "authentication" in manifest:
        raise ValueError("Manifest is already authenticated.")

    salt = secrets.token_bytes(16)
    key = _derive_backup_key(password, salt)

    signature = hmac.new(
        key,
        _manifest_bytes(manifest),
        hashlib.sha256,
    ).hexdigest()

    manifest["authentication"] = {
        "scheme": AUTH_SCHEME,
        "salt": salt.hex(),
        "hmac_sha256": signature,
    }

    return manifest


def verify_manifest_authentication(
    manifest,
    password=None,
    *,
    require_authenticated=False,
):
    """Verify an authenticated manifest or identify a legacy one."""

    authentication = manifest.get("authentication")

    if "authentication" in manifest and authentication is None:
        raise ValueError("Invalid backup authentication metadata.")

    if authentication is None:
        if require_authenticated:
            raise ValueError(
                "Authenticated backup required; legacy backup refused."
            )

        if password is not None:
            raise ValueError(
                "Backup has no authentication signature."
            )

        return False

    if (
        not isinstance(authentication, dict)
        or set(authentication) != {
            "scheme", "salt", "hmac_sha256"
        }
        or authentication.get("scheme") != AUTH_SCHEME
    ):
        raise ValueError("Invalid backup authentication metadata.")

    if type(password) is not str or not password:
        raise ValueError(
            "Backup authentication passphrase is required."
        )

    salt_hex = authentication["salt"]
    signature = authentication["hmac_sha256"]

    if (
        not isinstance(salt_hex, str)
        or not isinstance(signature, str)
        or len(salt_hex) != 32
        or len(signature) != 64
    ):
        raise ValueError("Invalid backup authentication metadata.")

    try:
        salt = bytes.fromhex(salt_hex)
        expected_signature = bytes.fromhex(signature)
    except ValueError as error:
        raise ValueError(
            "Invalid backup authentication metadata."
        ) from error

    actual_signature = hmac.new(
        _derive_backup_key(password, salt),
        _manifest_bytes(manifest),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(
        actual_signature,
        expected_signature,
    ):
        raise ValueError(
            "Backup authentication failed."
        )

    return True

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
    *,
    authentication_password=None,
):
    """Create a verified backup with optional manifest authentication."""

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

        if authentication_password is not None:
            authenticate_manifest(
                manifest,
                authentication_password,
            )

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
            "authenticated": (
                "authentication" in manifest
            ),
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

    parser.add_argument(
        "--authenticate",
        action="store_true",
        help="Protect manifest integrity using a backup passphrase",
    )

    args = parser.parse_args()

    password = None

    if args.authenticate:
        password = getpass.getpass(
            "New backup authentication passphrase: "
        )
        confirmation = getpass.getpass(
            "Confirm backup passphrase: "
        )

        if password != confirmation:
            raise SystemExit("Backup passphrases do not match.")

    try:
        result = create_local_backup(
            args.destination,
            authentication_password=password,
        )

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