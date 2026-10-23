"""Offline authorization-consistency tests with isolated SQLite fixtures."""

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.database.storage import save_opportunity
from src.database.review_service import record_review, get_review_history
from src.reviewer_accounts import bootstrap_administrator, change_account_access
from src.reviewer_throttle import attempts_path


PASSWORD = "Offline-Step11-Secure-Password-2026!"


@pytest.fixture
def sources(tmp_path):
    opportunities = tmp_path / "opportunities.sqlite3"
    accounts = tmp_path / "reviewer_accounts.sqlite3"
    initialize_database(opportunities)
    item = save_opportunity({
        "source_id": "synthetic",
        "url": "https://example.invalid/review",
        "title": "Synthetic workshop",
        "category": "tech_event",
        "classification_status": "potential_match",
    }, opportunities)
    bootstrap_administrator("test_admin", PASSWORD, accounts)
    return opportunities, accounts, item["id"]


def review(sources, **kwargs):
    opportunities, accounts, id_ = sources
    return record_review(
        id_, "approved", "https://example.invalid/evidence",
        reviewer_id="test_admin", reviewer_password=PASSWORD,
        free_confirmed=True, ph_confirmed=True, open_confirmed=True,
        database_path=opportunities, account_database_path=accounts,
        **kwargs,
    )


def test_review_commits_with_current_admin_permission(sources):
    result = review(sources)
    assert result["decision"] == "approved"
    assert len(get_review_history(sources[2], sources[0])) == 1


def test_account_revocation_cannot_commit_during_review(monkeypatch, sources):
    """Emulate revocation exactly after authentication but before writing."""
    import src.database.review_service as mod

    real_check = mod.check_permission
    tested = []

    def checked(*args, **kwargs):
        assert real_check(*args, **kwargs) is True
        competing = sqlite3.connect(sources[1], timeout=0)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                competing.execute("BEGIN IMMEDIATE")
            tested.append(True)
        finally:
            competing.close()
        return True

    monkeypatch.setattr(mod, "check_permission", checked)
    review(sources)
    assert tested == [True]
    assert len(get_review_history(sources[2], sources[0])) == 1


def test_deactivated_admin_cannot_approve(sources):
    with sqlite3.connect(sources[1]) as db:
        db.execute("UPDATE reviewer_accounts SET active=0 WHERE account_id='test_admin'")
    with pytest.raises(PermissionError, match="denied"):
        review(sources)
    assert get_review_history(sources[2], sources[0]) == []


def test_demoted_admin_cannot_approve(sources):
    with sqlite3.connect(sources[1]) as db:
        db.execute("UPDATE reviewer_accounts SET role='viewer' WHERE account_id='test_admin'")
    with pytest.raises(PermissionError, match="denied"):
        review(sources)
    assert get_review_history(sources[2], sources[0]) == []


def test_failure_does_not_append_history_or_modify_opportunity(sources):
    with pytest.raises(PermissionError):
        record_review(
            sources[2], "approved", "https://example.invalid/evidence",
            reviewer_id="test_admin", reviewer_password="wrong",
            free_confirmed=True, ph_confirmed=True, open_confirmed=True,
            database_path=sources[0], account_database_path=sources[1],
        )
    assert get_review_history(sources[2], sources[0]) == []
    with sqlite3.connect(sources[0]) as db:
        assert db.execute(
            "SELECT verification FROM opportunities WHERE id=?", (sources[2],)
        ).fetchone()[0] == "not_verified"


def test_lock_state_failure_denies_review(sources):
    attempts_path(sources[1]).mkdir()
    with pytest.raises(PermissionError):
        review(sources)
    assert get_review_history(sources[2], sources[0]) == []


def test_admin_revocation_still_preserves_audit(sources):
    with sqlite3.connect(sources[1]) as db:
        db.execute(
            "INSERT INTO reviewer_accounts(account_id,role,password_hash,active)"
            " SELECT 'synthetic_reviewer','reviewer',password_hash,1"
            " FROM reviewer_accounts WHERE account_id='test_admin'"
        )
    assert change_account_access(
        "test_admin", PASSWORD, "synthetic_reviewer",
        role="viewer", path=sources[1]
    )
    with sqlite3.connect(sources[1]) as db:
        assert db.execute(
            "SELECT count(*) FROM reviewer_account_audit"
        ).fetchone()[0] == 1
