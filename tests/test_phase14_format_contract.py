"""Offline contract tests with fictional encrypted data only."""

from copy import deepcopy

import pytest

from src.database.phase14_format_contract import (
    WINDOWS_REQUIREMENTS, canonical_aad_v2, windows_security_review,
)
from src.database.synthetic_encryption_core import (
    _aad, encrypt_synthetic_pair,
)

FAKE_PAIR = {
    "opportunities.sqlite3": b"TEST-ONLY-OPPORTUNITIES",
    "reviewer_accounts.sqlite3": b"TEST-ONLY-REVIEWERS",
}
FAKE_PASSWORD = "Testing-Only-Phase14-Secret-2026!"


@pytest.fixture
def envelope():
    return encrypt_synthetic_pair(FAKE_PAIR, FAKE_PASSWORD)[0]


def test_canonical_v2_aad_matches_existing_synthetic_crypto(envelope):
    assert canonical_aad_v2(envelope) == _aad(envelope)
    assert b"ciphertext_sha256" not in canonical_aad_v2(envelope)


def test_checksum_changes_do_not_change_canonical_aad(envelope):
    altered = deepcopy(envelope)
    altered["files"]["opportunities.sqlite3"]["ciphertext_sha256"] = "f" * 64
    assert canonical_aad_v2(altered) == canonical_aad_v2(envelope)


@pytest.mark.parametrize("field,value", [
    ("cipher", "AES-CBC"),
    ("kdf", "PBKDF2"),
    ("format", "old-plaintext-format"),
])
def test_unsupported_algorithms_are_rejected(envelope, field, value):
    altered = deepcopy(envelope)
    altered[field] = value
    with pytest.raises(ValueError):
        canonical_aad_v2(altered)


def test_mutated_authenticated_metadata_changes_aad(envelope):
    altered = deepcopy(envelope)
    altered["files"]["opportunities.sqlite3"]["nonce_hex"] = "aa" * 12
    assert canonical_aad_v2(altered) != canonical_aad_v2(envelope)


def test_unknown_manifest_fields_rejected(envelope):
    altered = deepcopy(envelope)
    altered["unapproved_field"] = True
    with pytest.raises(ValueError):
        canonical_aad_v2(altered)


def test_windows_evidence_requires_exact_boolean_keys():
    with pytest.raises(ValueError):
        windows_security_review({})
    with pytest.raises(ValueError):
        windows_security_review({**dict.fromkeys(WINDOWS_REQUIREMENTS, False), "extra": True})
    with pytest.raises(ValueError):
        windows_security_review(dict.fromkeys(WINDOWS_REQUIREMENTS, 1))


def test_windows_review_stays_unauthorized_even_when_all_claims_true():
    result = windows_security_review(dict.fromkeys(WINDOWS_REQUIREMENTS, True))
    assert result["evidence_claims_complete"] is True
    assert result["independently_verified"] is False
    assert result["operational_backups_authorized"] is False
    assert result["recovery_authorized"] is False
    assert result["unverified_requirements"] == []


def test_windows_missing_gate_is_reported_without_authorization():
    evidence = dict.fromkeys(WINDOWS_REQUIREMENTS, True)
    evidence["atomic_noreplace_publication_verified"] = False
    result = windows_security_review(evidence)
    assert result["evidence_claims_complete"] is False
    assert result["unverified_requirements"] == ["atomic_noreplace_publication_verified"]
    assert result["operational_backups_authorized"] is False
