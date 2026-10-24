"""Phase 12 Step 2: strict metadata contract for a FUTURE encrypted backup.

DESIGN ONLY. Does not encrypt/decrypt data, derive keys, read backup files,
load credentials, change existing backup formats or authorize restoration.
Unknown fields are rejected to avoid algorithm-downgrade ambiguity.
"""

import re

FORMAT = "phtech-encrypted-backup-v2"
CIPHER = "AES-256-GCM"
KDF = "scrypt"
N, R, P = 2**15, 8, 1
REQUIRED_FILES = frozenset({
    "opportunities.sqlite3", "reviewer_accounts.sqlite3",
})
HEX = re.compile(r"^[0-9a-f]+$")


def _hex_bytes(value, length):
    return (type(value) is str and len(value) == length * 2
            and HEX.fullmatch(value) is not None)


def validate_encryption_envelope(meta):
    """Validate non-secret envelope metadata, not an authenticity proof.

    The eventual decryptor must authenticate *every* metadata field as
    canonical AAD before releasing any plaintext to an isolated directory.
    Never infer that this validator proves a backup is safe to restore.
    """
    if type(meta) is not dict or set(meta) != {
        "format", "cipher", "kdf", "kdf_params", "salt_hex", "files"
    }:
        raise ValueError("Invalid encrypted-backup envelope.")
    if meta["format"] != FORMAT or meta["cipher"] != CIPHER or meta["kdf"] != KDF:
        raise ValueError("Unsupported encrypted-backup algorithm.")
    if meta["kdf_params"] != {"n": N, "r": R, "p": P, "dklen": 32}:
        raise ValueError("Unapproved key derivation parameters.")
    if not _hex_bytes(meta["salt_hex"], 16):
        raise ValueError("Invalid key derivation salt.")

    files = meta["files"]
    if type(files) is not dict or set(files) != REQUIRED_FILES:
        raise ValueError("Encrypted backup must contain exactly two databases.")
    nonces = set()
    for filename in sorted(REQUIRED_FILES):
        file_info = files[filename]
        if type(file_info) is not dict or set(file_info) != {
            "nonce_hex", "ciphertext_sha256", "ciphertext_size"
        }:
            raise ValueError("Invalid encrypted file metadata.")
        nonce = file_info["nonce_hex"]
        if not _hex_bytes(nonce, 12) or nonce in nonces:
            raise ValueError("Invalid or reused AES-GCM nonce.")
        nonces.add(nonce)
        if not _hex_bytes(file_info["ciphertext_sha256"], 32):
            raise ValueError("Invalid ciphertext checksum.")
        if type(file_info["ciphertext_size"]) is not int or not (
            16 <= file_info["ciphertext_size"] <= 512 * 1024 * 1024
        ):
            raise ValueError("Invalid encrypted file size.")
    return {
        "envelope_structure_valid": True,
        "authenticated_decryption_performed": False,
        "safe_to_restore": False,
        "legacy_backup_rewritten": False,
        "key_material_exported": False,
        "production_cutover_authorized": False,
    }
