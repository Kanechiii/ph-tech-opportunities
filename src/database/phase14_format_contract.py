"""Review-only format and filesystem contract; no real-data access."""

import json

from src.database.encrypted_backup_design import REQUIRED_FILES, validate_encryption_envelope

WINDOWS_REQUIREMENTS = frozenset({
    "private_parent",
    "ntfs_owner_acl_verified",
    "inherited_permissions_audited",
    "reparse_and_hardlinks_rejected",
    "atomic_noreplace_publication_verified",
    "interruption_durability_verified",
    "isolated_recovery_permissions_verified",
})


def canonical_aad_v2(meta):
    """Return the v2 authenticated fields; exclude ciphertext digests."""
    validate_encryption_envelope(meta)
    fields = {
        "format": meta["format"],
        "cipher": meta["cipher"],
        "kdf": meta["kdf"],
        "kdf_params": meta["kdf_params"],
        "salt_hex": meta["salt_hex"],
        "files": {
            name: {
                "nonce_hex": meta["files"][name]["nonce_hex"],
                "ciphertext_size": meta["files"][name]["ciphertext_size"],
            }
            for name in sorted(REQUIRED_FILES)
        },
    }
    return json.dumps(
        fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")


def windows_security_review(evidence):
    """Assess claimed evidence only; never authorize operational backup."""
    if type(evidence) is not dict or set(evidence) != WINDOWS_REQUIREMENTS:
        raise ValueError("Incomplete Windows security evidence.")
    if any(type(value) is not bool for value in evidence.values()):
        raise ValueError("Windows evidence values must be Boolean.")
    return {
        "evidence_claims_complete": all(evidence.values()),
        "unverified_requirements": sorted(
            name for name, passed in evidence.items() if not passed
        ),
        "independently_verified": False,
        "operational_backups_authorized": False,
        "recovery_authorized": False,
    }
