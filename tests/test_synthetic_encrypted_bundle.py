"""Offline synthetic ciphertext bundle tests. No operational SQLite access."""

from copy import deepcopy
import json

import pytest

from src.database.synthetic_encrypted_bundle import (
    CIPHERTEXT_NAMES, ENVELOPE_NAME, EXPECTED_NAMES,
    read_synthetic_encrypted_bundle, write_synthetic_encrypted_bundle,
)

PASSWORD = "Synthetic-Only-Passphrase-2026!"
SYNTHETIC = {
    "opportunities.sqlite3": b"FAKE-OPPORTUNITY-FIXTURE" * 8,
    "reviewer_accounts.sqlite3": b"FAKE-REVIEWER-FIXTURE" * 8,
}


def _bundle(tmp_path):
    path = tmp_path / "encrypted-synthetic-only"
    write_synthetic_encrypted_bundle(path, SYNTHETIC, PASSWORD)
    return path


def test_round_trip_and_ciphertext_only_on_disk(tmp_path):
    path = _bundle(tmp_path)
    assert {p.name for p in path.iterdir()} == EXPECTED_NAMES
    for name, ciphertext_name in CIPHERTEXT_NAMES.items():
        ciphertext = (path / ciphertext_name).read_bytes()
        assert SYNTHETIC[name] not in ciphertext
        assert ciphertext != SYNTHETIC[name]
    assert read_synthetic_encrypted_bundle(path, PASSWORD) == SYNTHETIC


def test_existing_directory_never_overwritten(tmp_path):
    path = _bundle(tmp_path)
    prior = {p.name: p.read_bytes() for p in path.iterdir()}
    with pytest.raises(ValueError):
        write_synthetic_encrypted_bundle(path, SYNTHETIC, PASSWORD)
    assert {p.name: p.read_bytes() for p in path.iterdir()} == prior


def test_wrong_password_does_not_publish_plaintext(tmp_path):
    path = _bundle(tmp_path)
    with pytest.raises(ValueError, match="Authenticated synthetic decryption failed"):
        read_synthetic_encrypted_bundle(path, "Clearly-Wrong-Passphrase!")
    assert {p.name for p in path.iterdir()} == EXPECTED_NAMES


@pytest.mark.parametrize("name", sorted(CIPHERTEXT_NAMES))
def test_ciphertext_tampering_rejected(tmp_path, name):
    path = _bundle(tmp_path)
    encrypted = path / CIPHERTEXT_NAMES[name]
    raw = encrypted.read_bytes()
    encrypted.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    with pytest.raises(ValueError):
        read_synthetic_encrypted_bundle(path, PASSWORD)


def test_authenticated_metadata_tampering_rejected(tmp_path):
    path = _bundle(tmp_path)
    envelope_path = path / ENVELOPE_NAME
    envelope = json.loads(envelope_path.read_text())
    envelope["kdf_params"]["n"] = 2**14
    envelope_path.write_text(json.dumps(envelope))
    with pytest.raises(ValueError):
        read_synthetic_encrypted_bundle(path, PASSWORD)


def test_unexpected_file_rejected(tmp_path):
    path = _bundle(tmp_path)
    (path / "extra.txt").write_text("synthetic")
    with pytest.raises(ValueError, match="Unexpected synthetic bundle"):
        read_synthetic_encrypted_bundle(path, PASSWORD)


def test_missing_file_rejected(tmp_path):
    path = _bundle(tmp_path)
    (path / ENVELOPE_NAME).unlink()
    with pytest.raises(ValueError):
        read_synthetic_encrypted_bundle(path, PASSWORD)


def test_directory_symlink_rejected(tmp_path):
    path = _bundle(tmp_path)
    link = tmp_path / "link"
    try:
        link.symlink_to(path, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlink creation unavailable")
    with pytest.raises(ValueError):
        read_synthetic_encrypted_bundle(link, PASSWORD)


def test_file_symlink_rejected(tmp_path):
    path = _bundle(tmp_path)
    encrypted = path / CIPHERTEXT_NAMES["opportunities.sqlite3"]
    encrypted.unlink()
    try:
        encrypted.symlink_to(path / CIPHERTEXT_NAMES["reviewer_accounts.sqlite3"])
    except (NotImplementedError, OSError):
        pytest.skip("File symlink creation unavailable")
    with pytest.raises(ValueError):
        read_synthetic_encrypted_bundle(path, PASSWORD)


def test_source_fixture_not_modified(tmp_path):
    fixture = deepcopy(SYNTHETIC)
    _bundle(tmp_path)
    assert SYNTHETIC == fixture


def test_invalid_fixture_does_not_create_directory(tmp_path):
    target = tmp_path / "not-created"
    with pytest.raises(ValueError):
        write_synthetic_encrypted_bundle(target, {"a": b"test"}, PASSWORD)
    assert not target.exists()
