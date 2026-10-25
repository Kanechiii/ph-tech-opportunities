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



def _reject_symlink_ancestors(path):
    """Reject symlinks in the target path and every existing parent."""
    for entry in (path, *path.parents):
        if entry.is_symlink():
            raise ValueError("Symbolic-link paths are not permitted.")


def _bounded_regular_read(path, limit):
    """Read only a stable, single-linked regular file, within a fixed bound.

    This is defense in depth for synthetic files, not a guarantee against
    adversarial concurrent filesystem mutation on every operating system.
    """
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("Unsafe synthetic bundle entry.")
    if before.st_size > limit:
        raise ValueError("Oversized synthetic bundle entry.")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or opened.st_size > limit
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError("Unsafe synthetic bundle entry.")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        after = os.fstat(fd)
        if (len(data) > limit or len(data) != opened.st_size
                or (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
                or opened.st_size != after.st_size or after.st_nlink != 1):
            raise ValueError("Synthetic bundle entry changed during read.")
        return data
    finally:
        os.close(fd)

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
    _reject_symlink_ancestors(target)
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
    _reject_symlink_ancestors(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Invalid synthetic bundle directory.")
    entries = list(directory.iterdir())
    if {x.name for x in entries} != EXPECTED_NAMES or len(entries) != len(EXPECTED_NAMES):
        raise ValueError("Unexpected synthetic bundle contents.")
    for item in entries:
        if not item.is_file() or item.is_symlink() or not stat.S_ISREG(item.lstat().st_mode):
            raise ValueError("Unsafe synthetic bundle entry.")
    envelope_path = directory / ENVELOPE_NAME
    try:
        metadata = json.loads(
            _bounded_regular_read(envelope_path, MAX_ENVELOPE_BYTES).decode("ascii")
        )
    except (UnicodeError, ValueError) as error:
        raise ValueError("Invalid synthetic envelope.") from None

    ciphertexts = {}
    for name in sorted(REQUIRED_FILES):
        path = directory / CIPHERTEXT_NAMES[name]
        ciphertexts[name] = _bounded_regular_read(
            path, MAX_SYNTHETIC_BYTES_PER_FILE + 16
        )
    return decrypt_synthetic_pair(metadata, ciphertexts, passphrase)
