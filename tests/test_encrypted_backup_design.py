"""Synthetic contract tests. Does not perform encryption or touch real backups."""

from copy import deepcopy

import pytest

from src.database.encrypted_backup_design import (
    CIPHER, FORMAT, KDF, N, R, P, validate_encryption_envelope,
)


@pytest.fixture
def envelope():
    return {
        "format": FORMAT,
        "cipher": CIPHER,
        "kdf": KDF,
        "kdf_params": {"n": N, "r": R, "p": P, "dklen": 32},
        "salt_hex": "a1" * 16,
        "files": {
            "opportunities.sqlite3": {
                "nonce_hex": "b2" * 12,
                "ciphertext_sha256": "c3" * 32,
                "ciphertext_size": 100,
            },
            "reviewer_accounts.sqlite3": {
                "nonce_hex": "d4" * 12,
                "ciphertext_sha256": "e5" * 32,
                "ciphertext_size": 200,
            },
        },
    }


def test_valid_structure_never_authorizes_restore(envelope):
    result = validate_encryption_envelope(envelope)
    assert result["envelope_structure_valid"]
    assert not result["authenticated_decryption_performed"]
    assert not result["safe_to_restore"]
    assert not result["production_cutover_authorized"]


@pytest.mark.parametrize("field,value", [
    ("format", "plaintext-v1"),
    ("cipher", "AES-CBC"),
    ("kdf", "pbkdf2"),
    ("kdf_params", {"n": 1024, "r": R, "p": P, "dklen": 32}),
    ("salt_hex", "bad"),
])
def test_disallow_downgrades(envelope, field, value):
    bad = deepcopy(envelope)
    bad[field] = value
    with pytest.raises(ValueError):
        validate_encryption_envelope(bad)


def test_unknown_metadata_rejected(envelope):
    bad = deepcopy(envelope)
    bad["extra_field"] = "ignored?"
    with pytest.raises(ValueError):
        validate_encryption_envelope(bad)


def test_missing_account_database_rejected(envelope):
    bad = deepcopy(envelope)
    del bad["files"]["reviewer_accounts.sqlite3"]
    with pytest.raises(ValueError):
        validate_encryption_envelope(bad)


def test_reused_nonce_rejected(envelope):
    bad = deepcopy(envelope)
    bad["files"]["reviewer_accounts.sqlite3"]["nonce_hex"] = "b2" * 12
    with pytest.raises(ValueError, match="nonce"):
        validate_encryption_envelope(bad)


def test_invalid_checksum_or_size_rejected(envelope):
    for field, value in (
        ("ciphertext_sha256", "1234"),
        ("ciphertext_size", -1),
        ("ciphertext_size", True),
    ):
        bad = deepcopy(envelope)
        bad["files"]["opportunities.sqlite3"][field] = value
        with pytest.raises(ValueError):
            validate_encryption_envelope(bad)


def test_input_envelope_never_modified(envelope):
    initial = deepcopy(envelope)
    result = validate_encryption_envelope(envelope)
    assert envelope == initial
    assert not result["key_material_exported"]
    assert not result["legacy_backup_rewritten"]


def test_unexpected_file_metadata_rejected(envelope):
    bad = deepcopy(envelope)
    bad["files"]["opportunities.sqlite3"]["plaintext_path"] = "secret"
    with pytest.raises(ValueError):
        validate_encryption_envelope(bad)
