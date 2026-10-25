"""Synthetic-only in-memory authenticated backup encryption prototype.

Not wired to production backups, SQLite, Neon, local recovery, or any CLI.
No files, secrets or network state are read or modified. The proposed v2
envelope is validated structurally and cryptographically authenticated.

The v2 AAD encodes all metadata EXCEPT ciphertext SHA-256 values: a digest of
ciphertext cannot itself be used as AAD for that same ciphertext without a
circular dependency. Hashes are checked separately before GCM authentication.
This format is provisional until reviewed and documented as stable.
"""

import hashlib
import json
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.database.encrypted_backup_design import (
    CIPHER, FORMAT, KDF, N, P, R, REQUIRED_FILES,
    validate_encryption_envelope,
)

MAX_SYNTHETIC_BYTES_PER_FILE = 4 * 1024 * 1024
KDF_MAXMEM = 128 * 1024 * 1024


def _passphrase(value):
    if type(value) is not str or not 16 <= len(value) <= 256:
        raise ValueError("Passphrase must be between 16 and 256 characters.")
    return value


def _derive(value, salt):
    return hashlib.scrypt(
        _passphrase(value).encode("utf-8"),
        salt=salt, n=N, r=R, p=P, dklen=32, maxmem=KDF_MAXMEM,
    )


def _aad(meta):
    """Authenticate selected metadata, excluding ciphertext digests only."""
    aad_meta = {
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
    return json.dumps(aad_meta, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def encrypt_synthetic_pair(payloads, passphrase):
    """Encrypt two synthetic byte payloads entirely in memory.

    Returns an envelope and ciphertexts, not a restorable backup. Both
    payloads are required; caller must never supply private application data.
    """
    if type(payloads) is not dict or set(payloads) != REQUIRED_FILES:
        raise ValueError("Exactly two synthetic database payloads required.")
    for value in payloads.values():
        if (type(value) is not bytes or not 1 <= len(value)
                <= MAX_SYNTHETIC_BYTES_PER_FILE):
            raise ValueError("Synthetic payload size or type invalid.")

    salt = secrets.token_bytes(16)
    _passphrase(passphrase)
    meta = {
        "format": FORMAT,
        "cipher": CIPHER,
        "kdf": KDF,
        "kdf_params": {"n": N, "r": R, "p": P, "dklen": 32},
        "salt_hex": salt.hex(),
        "files": {},
    }
    for name in sorted(REQUIRED_FILES):
        meta["files"][name] = {
            "nonce_hex": secrets.token_bytes(12).hex(),
            "ciphertext_sha256": "0" * 64,
            "ciphertext_size": len(payloads[name]) + 16,
        }
    if len({m["nonce_hex"] for m in meta["files"].values()}) != 2:
        raise RuntimeError("Unexpected nonce collision; refusing encryption.")

    aad = _aad(meta)
    aes = AESGCM(_derive(passphrase, salt))
    encrypted = {}
    for name in sorted(REQUIRED_FILES):
        nonce = bytes.fromhex(meta["files"][name]["nonce_hex"])
        ciphertext = aes.encrypt(nonce, payloads[name], aad)
        encrypted[name] = ciphertext
        meta["files"][name]["ciphertext_sha256"] = hashlib.sha256(
            ciphertext
        ).hexdigest()
    validate_encryption_envelope(meta)
    return meta, encrypted


def decrypt_synthetic_pair(meta, encrypted, passphrase):
    """Authenticate *both* ciphertexts before releasing any plaintext.

    No source files are read; invalid data always raises ValueError with a
    generic error to avoid exposing which secret or payload was incorrect.
    """
    try:
        validate_encryption_envelope(meta)
        if type(encrypted) is not dict or set(encrypted) != REQUIRED_FILES:
            raise ValueError()
        for name in REQUIRED_FILES:
            value = encrypted[name]
            if (type(value) is not bytes
                    or len(value) != meta["files"][name]["ciphertext_size"]
                    or len(value) > MAX_SYNTHETIC_BYTES_PER_FILE + 16
                    or hashlib.sha256(value).hexdigest()
                    != meta["files"][name]["ciphertext_sha256"]):
                raise ValueError()
        aes = AESGCM(_derive(passphrase, bytes.fromhex(meta["salt_hex"])))
        aad = _aad(meta)
        plaintexts = {}
        for name in sorted(REQUIRED_FILES):
            plaintexts[name] = aes.decrypt(
                bytes.fromhex(meta["files"][name]["nonce_hex"]),
                encrypted[name], aad,
            )
        return plaintexts
    except (ValueError, TypeError, KeyError, InvalidTag) as error:
        raise ValueError("Authenticated synthetic decryption failed.") from None
