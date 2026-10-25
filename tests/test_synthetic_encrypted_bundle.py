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


def test_publish_failure_removes_staging_and_never_exposes_destination(tmp_path, monkeypatch):
    import src.database.synthetic_encrypted_bundle as module

    def refuse_publish(source, destination):
        assert source.is_dir()
        assert not destination.exists()
        raise OSError("synthetic simulated publishing failure")

    monkeypatch.setattr(module.os, "rename", refuse_publish)
    target = tmp_path / "never-published"
    with pytest.raises(OSError, match="synthetic simulated"):
        write_synthetic_encrypted_bundle(target, SYNTHETIC, PASSWORD)
    assert not target.exists()
    assert not list(tmp_path.iterdir())


def test_encryption_failure_creates_no_staging_dir(tmp_path, monkeypatch):
    import src.database.synthetic_encrypted_bundle as module

    def refuse_encryption(*args):
        raise RuntimeError("synthetic encryption fault")

    monkeypatch.setattr(module, "encrypt_synthetic_pair", refuse_encryption)
    with pytest.raises(RuntimeError, match="synthetic encryption fault"):
        write_synthetic_encrypted_bundle(tmp_path / "new-target", SYNTHETIC, PASSWORD)
    assert not list(tmp_path.iterdir())


def test_file_write_fault_removes_staging_without_publishing(tmp_path, monkeypatch):
    import src.database.synthetic_encrypted_bundle as module

    original = module._exclusive_file
    calls = 0

    def faulty_write(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic disk write failure")
        return original(*args)

    monkeypatch.setattr(module, "_exclusive_file", faulty_write)
    with pytest.raises(OSError, match="synthetic disk write failure"):
        write_synthetic_encrypted_bundle(tmp_path / "bundle", SYNTHETIC, PASSWORD)
    assert not list(tmp_path.iterdir())


def test_failed_self_verification_cleans_staging(tmp_path, monkeypatch):
    import src.database.synthetic_encrypted_bundle as module

    def verification_error(*args):
        raise ValueError("synthetic self-verification failure")

    monkeypatch.setattr(module, "read_synthetic_encrypted_bundle", verification_error)
    with pytest.raises(ValueError, match="synthetic self-verification failure"):
        write_synthetic_encrypted_bundle(tmp_path / "bundle", SYNTHETIC, PASSWORD)
    assert not list(tmp_path.iterdir())


def test_concurrent_destination_creation_fails_closed(tmp_path, monkeypatch):
    import src.database.synthetic_encrypted_bundle as module

    original = module.read_synthetic_encrypted_bundle

    def competing_process(path, password):
        output = original(path, password)
        (tmp_path / "bundle").mkdir()
        (tmp_path / "bundle" / "keep.txt").write_text("external")
        return output

    monkeypatch.setattr(module, "read_synthetic_encrypted_bundle", competing_process)
    with pytest.raises(ValueError, match="destination appeared"):
        write_synthetic_encrypted_bundle(tmp_path / "bundle", SYNTHETIC, PASSWORD)
    assert (tmp_path / "bundle" / "keep.txt").read_text() == "external"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bundle"]


def test_published_bundle_is_complete(tmp_path):
    path = _bundle(tmp_path)
    assert {p.name for p in path.iterdir()} == EXPECTED_NAMES
    assert read_synthetic_encrypted_bundle(path, PASSWORD) == SYNTHETIC
    assert not any(p.name.startswith(".phtech-synthetic-") for p in tmp_path.iterdir())


def test_no_follow_reader_rejects_symlink_directly(tmp_path):
    import src.database.synthetic_encrypted_bundle as module

    original = tmp_path / "original"
    original.write_bytes(b"synthetic")
    link = tmp_path / "link"
    try:
        link.symlink_to(original)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks not supported by this environment")
    with pytest.raises(ValueError):
        module._read_regular_no_follow(link, 100)


def test_no_follow_reader_rejects_oversized_regular_file(tmp_path):
    import src.database.synthetic_encrypted_bundle as module

    original = tmp_path / "oversized"
    original.write_bytes(b"x" * 101)
    with pytest.raises(ValueError):
        module._read_regular_no_follow(original, 100)


def test_no_follow_reader_rejects_missing_file(tmp_path):
    import src.database.synthetic_encrypted_bundle as module

    with pytest.raises(ValueError):
        module._read_regular_no_follow(tmp_path / "not-there", 10)


def test_no_follow_reader_detects_path_identity_substitution(tmp_path, monkeypatch):
    import src.database.synthetic_encrypted_bundle as module

    original = tmp_path / "original"
    original.write_bytes(b"initial")
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"changed")
    real_open = module.os.open

    def swapped_open(path, flags, *args):
        if str(path) == str(original):
            original.unlink()
            replacement.rename(original)
        return real_open(path, flags, *args)

    monkeypatch.setattr(module.os, "open", swapped_open)
    with pytest.raises(ValueError, match="changed while reading"):
        module._read_regular_no_follow(original, 100)


def test_no_follow_reader_rejects_nonregular_directory(tmp_path):
    import src.database.synthetic_encrypted_bundle as module

    with pytest.raises(ValueError):
        module._read_regular_no_follow(tmp_path, 100)
