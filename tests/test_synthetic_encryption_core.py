"""Offline-only synthetic AES-GCM authentication regression tests."""

from copy import deepcopy

import pytest

from src.database.synthetic_encryption_core import (
    MAX_SYNTHETIC_BYTES_PER_FILE, decrypt_synthetic_pair,
    encrypt_synthetic_pair,
)


@pytest.fixture
def pair():
    return {
        "opportunities.sqlite3": b"synthetic-opportunities" * 10,
        "reviewer_accounts.sqlite3": b"synthetic-accounts" * 10,
    }


@pytest.fixture
def bundle(pair):
    return encrypt_synthetic_pair(pair, "Synthetic-Only-Passphrase-2026!")


def test_round_trip_synthetic_pair(pair, bundle):
    metadata, ciphertexts = bundle
    assert decrypt_synthetic_pair(
        metadata, ciphertexts, "Synthetic-Only-Passphrase-2026!"
    ) == pair


def test_plaintext_not_visible_in_ciphertext(pair, bundle):
    meta, encrypted = bundle
    for name, payload in pair.items():
        assert encrypted[name] != payload
        assert payload not in encrypted[name]
    assert "Synthetic-Only-Passphrase" not in str(meta)


def test_wrong_passphrase_fails_without_payload_identification(bundle):
    metadata, ciphertexts = bundle
    with pytest.raises(ValueError, match="Authenticated synthetic decryption failed"):
        decrypt_synthetic_pair(metadata, ciphertexts, "Incorrect-Passphrase-2026!")


@pytest.mark.parametrize("name", [
    "opportunities.sqlite3", "reviewer_accounts.sqlite3",
])
def test_bitflip_ciphertext_fails(name, bundle):
    metadata, ciphertexts = bundle
    tampered = dict(ciphertexts)
    tampered[name] = bytes([tampered[name][0] ^ 1]) + tampered[name][1:]
    with pytest.raises(ValueError):
        decrypt_synthetic_pair(metadata, tampered, "Synthetic-Only-Passphrase-2026!")


def test_metadata_nonce_tamper_fails(bundle):
    meta, encrypted = bundle
    altered = deepcopy(meta)
    altered["files"]["opportunities.sqlite3"]["nonce_hex"] = "aa" * 12
    with pytest.raises(ValueError):
        decrypt_synthetic_pair(altered, encrypted, "Synthetic-Only-Passphrase-2026!")


def test_metadata_size_tamper_fails(bundle):
    meta, encrypted = bundle
    altered = deepcopy(meta)
    altered["files"]["opportunities.sqlite3"]["ciphertext_size"] += 1
    with pytest.raises(ValueError):
        decrypt_synthetic_pair(altered, encrypted, "Synthetic-Only-Passphrase-2026!")


def test_metadata_ciphertext_hash_tamper_fails(bundle):
    meta, encrypted = bundle
    altered = deepcopy(meta)
    altered["files"]["opportunities.sqlite3"]["ciphertext_sha256"] = "a" * 64
    with pytest.raises(ValueError):
        decrypt_synthetic_pair(altered, encrypted, "Synthetic-Only-Passphrase-2026!")


def test_metadata_algorithm_downgrade_fails(bundle):
    meta, encrypted = bundle
    altered = deepcopy(meta)
    altered["cipher"] = "AES-CBC"
    with pytest.raises(ValueError):
        decrypt_synthetic_pair(altered, encrypted, "Synthetic-Only-Passphrase-2026!")


def test_missing_payload_fails_closed(bundle):
    meta, encrypted = bundle
    altered = dict(encrypted)
    del altered["reviewer_accounts.sqlite3"]
    with pytest.raises(ValueError):
        decrypt_synthetic_pair(meta, altered, "Synthetic-Only-Passphrase-2026!")


def test_encryption_randomizes_salt_and_nonces(pair):
    first, first_ciphertext = encrypt_synthetic_pair(
        pair, "Synthetic-Only-Passphrase-2026!"
    )
    second, second_ciphertext = encrypt_synthetic_pair(
        pair, "Synthetic-Only-Passphrase-2026!"
    )
    assert first["salt_hex"] != second["salt_hex"]
    for name in pair:
        assert first["files"][name]["nonce_hex"] != second["files"][name]["nonce_hex"]
        assert first_ciphertext[name] != second_ciphertext[name]


def test_short_password_and_oversized_payload_refused(pair):
    with pytest.raises(ValueError):
        encrypt_synthetic_pair(pair, "too short")
    oversized = dict(pair)
    oversized["opportunities.sqlite3"] = b"x" * (MAX_SYNTHETIC_BYTES_PER_FILE + 1)
    with pytest.raises(ValueError):
        encrypt_synthetic_pair(oversized, "Synthetic-Only-Passphrase-2026!")


def test_input_never_modified(pair):
    before = dict(pair)
    encrypt_synthetic_pair(pair, "Synthetic-Only-Passphrase-2026!")
    assert pair == before
