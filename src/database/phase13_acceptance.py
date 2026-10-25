"""Read-only-to-production acceptance gate for Phase 13 synthetic encryption.

Runs only on hardcoded fictional byte fixtures in a temporary directory.
No operational file arguments, CLI, imports from account stores, or network.
Reports no passphrase, plaintext, ciphertext, or database file contents.
"""

import json
import tempfile
from pathlib import Path

from src.database.synthetic_encrypted_bundle import (
    CIPHERTEXT_NAMES,
    ENVELOPE_NAME,
    read_synthetic_encrypted_bundle,
    write_synthetic_encrypted_bundle,
)

TEST_PASSPHRASE = "FAKE-testing-only-phase13-secret-2026!"
TEST_BYTES = {
    "opportunities.sqlite3": b"FAKE-OPPORTUNITIES-TEST-ONLY" * 4,
    "reviewer_accounts.sqlite3": b"FAKE-ACCOUNTS-TEST-ONLY" * 4,
}

# These explicitly remain false even if every synthetic verification passes.
UNRESOLVED_BLOCKERS = (
    "no production SQLite snapshot-to-encryption integration",
    "no file-based isolated authenticated recovery and SQLite parity validation",
    "no independently verified Windows NTFS ACLs or recovery permissions",
    "no cross-platform atomic no-replace publication against adversarial races",
    "no demonstrated interruption, crash-durability, or external offsite recovery",
    "no production key management, supported format freeze, or independent review",
)


def assess_synthetic_encryption():
    """Exercise temporary fictional payloads; never claim production readiness."""
    outcomes = {
        "synthetic_round_trip": False,
        "on_disk_ciphertext_only": False,
        "wrong_passphrase_rejected": False,
        "ciphertext_tampering_rejected": False,
        "existing_destination_preserved": False,
    }
    with tempfile.TemporaryDirectory(prefix="phtech-synthetic-acceptance-") as tmp:
        root = Path(tmp)
        destination = root / "fictional-bundle"
        write_synthetic_encrypted_bundle(
            destination, TEST_BYTES, TEST_PASSPHRASE
        )
        outcomes["synthetic_round_trip"] = (
            read_synthetic_encrypted_bundle(destination, TEST_PASSPHRASE)
            == TEST_BYTES
        )
        encrypted_bytes = [
            (destination / encrypted).read_bytes()
            for encrypted in CIPHERTEXT_NAMES.values()
        ]
        folder_entries = {p.name for p in destination.iterdir()}
        outcomes["on_disk_ciphertext_only"] = (
            folder_entries == {ENVELOPE_NAME, *CIPHERTEXT_NAMES.values()}
            and all(
                value not in blob
                for value in TEST_BYTES.values()
                for blob in encrypted_bytes
            )
        )
        try:
            read_synthetic_encrypted_bundle(
                destination, "INCORRECT-testing-only-secret-2026!"
            )
        except ValueError:
            outcomes["wrong_passphrase_rejected"] = True

        try:
            write_synthetic_encrypted_bundle(
                destination, TEST_BYTES, TEST_PASSPHRASE
            )
        except ValueError:
            outcomes["existing_destination_preserved"] = (
                read_synthetic_encrypted_bundle(destination, TEST_PASSPHRASE)
                == TEST_BYTES
            )

        damaged = destination / CIPHERTEXT_NAMES["opportunities.sqlite3"]
        raw = damaged.read_bytes()
        damaged.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        try:
            read_synthetic_encrypted_bundle(destination, TEST_PASSPHRASE)
        except ValueError:
            outcomes["ciphertext_tampering_rejected"] = True

    return {
        "gate": "phase13-synthetic-acceptance",
        "checks": outcomes,
        "all_synthetic_checks_passed": all(outcomes.values()),
        "operational_encrypted_backup_enabled": False,
        "real_sqlite_access_performed": False,
        "restoration_authorized": False,
        "production_ready": False,
        "production_cutover_authorized": False,
        "reviewed_email_automation_enabled": False,
        "outstanding_production_blockers": list(UNRESOLVED_BLOCKERS),
    }


if __name__ == "__main__":
    print(json.dumps(assess_synthetic_encryption(), indent=2, sort_keys=True))
