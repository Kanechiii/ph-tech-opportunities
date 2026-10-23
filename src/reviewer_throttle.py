"""Local, persistent password-attempt throttling for reviewer accounts.

Separate from the immutable reviewer account/audit history. This file contains
only account IDs, failure counters, and lock expiries (no passwords or hashes).
Any ledger access failure denies authorization. No email or cloud operations.
"""

import sqlite3
import time
from pathlib import Path

from src.reviewer_auth import (
    ACCOUNT_ID_PATTERN,
    KNOWN_ACTIONS,
    authenticate_reviewer,
    PERMISSIONS,
)

MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60


def attempts_path(accounts_path):
    """Store private authentication state alongside the existing account DB."""
    path = Path(accounts_path)
    return path.with_name(path.stem + ".auth_attempts.sqlite3")


def authorize_with_throttle(account, account_id, password, action, accounts_path,
                            *, now=None):
    """Authenticate with an atomically persisted per-account failure budget.

    Unknown users and invalid passwords consume an attempt; a valid password
    with an unauthorized action is denied without consuming an attempt.
    Locked accounts cannot authenticate before the lock expires. A ledger
    read/write error fails closed rather than allowing password guessing.
    """
    if (
        not isinstance(account_id, str)
        or ACCOUNT_ID_PATTERN.fullmatch(account_id) is None
        or not isinstance(password, str)
        or not isinstance(action, str)
        or action not in KNOWN_ACTIONS
    ):
        return False

    moment = int(time.time()) if now is None else now
    if type(moment) is not int or moment < 0:
        raise ValueError("Invalid authentication clock.")

    path = attempts_path(accounts_path)

    if path.is_symlink():
        raise PermissionError("Authentication state unavailable.")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=10)
        try:
            db.execute("PRAGMA busy_timeout = 10000")
            db.execute("""
                CREATE TABLE IF NOT EXISTS auth_attempts (
                    account_id TEXT PRIMARY KEY,
                    failed_attempts INTEGER NOT NULL
                        CHECK(failed_attempts >= 0),
                    locked_until INTEGER NOT NULL DEFAULT 0
                        CHECK(locked_until >= 0)
                )
            """)
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT failed_attempts, locked_until FROM auth_attempts "
                "WHERE account_id=?", (account_id,)
            ).fetchone()
            failed, until = (int(row[0]), int(row[1])) if row else (0, 0)

            if until > moment:
                db.commit()
                return False

            if until != 0:
                failed = 0

            authenticated = (
                account is not None
                and authenticate_reviewer(account, password)
            )
            if authenticated:
                db.execute(
                    "DELETE FROM auth_attempts WHERE account_id=?", (account_id,)
                )
                db.commit()
                return action in PERMISSIONS[account.role]

            failed += 1
            locked_until = moment + LOCK_SECONDS if failed >= MAX_FAILURES else 0
            db.execute(
                "INSERT INTO auth_attempts "
                "(account_id,failed_attempts,locked_until) VALUES (?,?,?) "
                "ON CONFLICT(account_id) DO UPDATE SET "
                "failed_attempts=excluded.failed_attempts, "
                "locked_until=excluded.locked_until",
                (account_id, failed, locked_until),
            )
            db.commit()
            return False
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except (sqlite3.Error, OSError) as error:
        raise PermissionError("Authentication state unavailable.") from error
