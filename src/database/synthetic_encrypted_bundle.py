"""Synthetic-only encrypted bundle writer and verifier.

Only synthetic byte fixtures may be passed. No access to application data,
SQLite paths, legacy backups, CLI, cloud services or production restore.
Only ciphertext is written. The caller-provided destination must not exist.
"""

import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

from src.database.encrypted_backup_design import REQUIRED_FILES
from src.database.synthetic_encryption_core import (
    MAX_SYNTHETIC_BYTES_PER_FILE,
    decrypt_synthetic_pair,
    encrypt_synthetic_pair,
)

ENVELOPE_NAME = "envelope.json"
CIPHERTEXT_NAMES = {
    "opportunities.sqlite3": "opportunities.sqlite3.enc",
    "reviewer_accounts.sqlite3": "reviewer_accounts.sqlite3.enc",
}
EXPECTED_NAMES = frozenset({ENVELOPE_NAME, *CIPHERTEXT_NAMES.values()})
MAX_ENVELOPE_BYTES = 8192


def _exclusive_file(folder, name, contents):
    # Exclusive creation; refuse symlinks and existing files.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(folder / name, flags, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(contents)
        file.flush()
        os.fsync(file.fileno())


def write_synthetic_encrypted_bundle(destination, payloads, passphrase):
    """Write a brand-new bundle containing ciphertext only.

    Never overwrites a destination. Creates no on-disk plaintext. The only
    supported inputs are synthetic fixtures; real backup use is not approved.
    """
    target = Path(destination).absolute()
    # Fail before encryption rather than risk leaving behind partial targets.
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError("Invalid or existing synthetic bundle destination.")
    if target.parent.is_symlink():
        raise ValueError("Symlink parent not supported.")
    metadata, ciphertexts = encrypt_synthetic_pair(payloads, passphrase)
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("ascii")
    if len(encoded) > MAX_ENVELOPE_BYTES:
        raise ValueError("Synthetic envelope exceeded supported size.")
    # Stage only ciphertext in a private sibling directory; never expose a
    # partially written destination. Publish via same-filesystem rename.
    staging = Path(tempfile.mkdtemp(prefix=".phtech-synthetic-", dir=target.parent))
    published = False
    try:
        for name in sorted(REQUIRED_FILES):
            _exclusive_file(staging, CIPHERTEXT_NAMES[name], ciphertexts[name])
        _exclusive_file(staging, ENVELOPE_NAME, encoded)
        # Read back and authenticate both encrypted files before publication.
        if read_synthetic_encrypted_bundle(staging, passphrase) != payloads:
            raise ValueError("Synthetic bundle verification failed.")
        if target.exists() or target.is_symlink():
            raise ValueError("Synthetic destination appeared during staging.")
        os.rename(staging, target)
        published = True
        # On POSIX, best effort parent directory fsync for durable directory
        # entry publication. On Windows, no portable directory fsync exists.
        if os.name == "posix":
            try:
                fd = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            except OSError:
                # A durability limitation, never a reason to delete a
                # successfully published encrypted bundle.
                pass
    finally:
        if not published and staging.is_dir() and not staging.is_symlink():
            shutil.rmtree(staging)
    return target


def read_synthetic_encrypted_bundle(directory, passphrase):
    """Verify an isolated synthetic ciphertext directory, return bytes only.

    Does not write plaintext, restore SQLite, or modify existing artifacts.
    """
    directory = Path(directory).absolute()
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Invalid synthetic bundle directory.")
    entries = list(directory.iterdir())
    if {x.name for x in entries} != EXPECTED_NAMES or len(entries) != len(EXPECTED_NAMES):
        raise ValueError("Unexpected synthetic bundle contents.")
    for item in entries:
        if not item.is_file() or item.is_symlink() or not stat.S_ISREG(item.lstat().st_mode):
            raise ValueError("Unsafe synthetic bundle entry.")
    envelope_path = directory / ENVELOPE_NAME
    if envelope_path.stat().st_size > MAX_ENVELOPE_BYTES:
        raise ValueError("Oversized synthetic envelope.")
    try:
        metadata = json.loads(envelope_path.read_text(encoding="ascii"))
    except (UnicodeError, ValueError) as error:
        raise ValueError("Invalid synthetic envelope.") from None

    ciphertexts = {}
    for name in sorted(REQUIRED_FILES):
        path = directory / CIPHERTEXT_NAMES[name]
        if path.stat().st_size > MAX_SYNTHETIC_BYTES_PER_FILE + 16:
            raise ValueError("Oversized synthetic ciphertext.")
        ciphertexts[name] = path.read_bytes()
    return decrypt_synthetic_pair(metadata, ciphertexts, passphrase)
