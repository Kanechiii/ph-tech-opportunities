"""Private local reviewer account store.

Stores password verifiers, never plaintext passwords.
Does not modify opportunity reviews or send notifications.
"""

import argparse
import getpass
import sqlite3
from pathlib import Path

from src.database.schema import PROJECT_ROOT
from src.reviewer_auth import (
    ACCOUNT_ID_PATTERN,
    ReviewerAccount,
    authorize_reviewer,
    hash_password,
)

ACCOUNT_DATABASE = (
    PROJECT_ROOT / "data" / "reviewer_accounts.sqlite3"
)


def initialize_accounts(path=ACCOUNT_DATABASE):
    """Explicitly initialize an account-only SQLite database."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reviewer_accounts (
                account_id TEXT PRIMARY KEY,
                role TEXT NOT NULL
                    CHECK (role IN (
                        'administrator', 'reviewer', 'viewer'
                    )),
                password_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
                    CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    return path


def bootstrap_administrator(
    account_id,
    password,
    path=ACCOUNT_DATABASE,
):
    """Create the first administrator only when store is empty."""

    if (
        not isinstance(account_id, str)
        or ACCOUNT_ID_PATTERN.fullmatch(account_id) is None
    ):
        raise ValueError("Invalid account ID.")

    # Validate and hash before starting the transaction.
    password_verifier = hash_password(password)

    path = initialize_accounts(path)

    connection = sqlite3.connect(path)

    try:
        connection.execute("BEGIN IMMEDIATE")

        count = connection.execute(
            "SELECT COUNT(*) FROM reviewer_accounts"
        ).fetchone()[0]

        if count != 0:
            raise PermissionError(
                "Account store already initialized."
            )

        connection.execute(
            """
            INSERT INTO reviewer_accounts (
                account_id, role, password_hash, active
            )
            VALUES (?, 'administrator', ?, 1)
            """,
            (account_id, password_verifier),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return account_id


def load_account(account_id, path=ACCOUNT_DATABASE):
    """Load an account from existing local storage, read-only."""

    if not isinstance(account_id, str):
        return None

    path = Path(path)

    if not path.is_file():
        return None

    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA query_only = ON")

        row = connection.execute(
            """
            SELECT account_id, role, password_hash, active
            FROM reviewer_accounts
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()

        if row is None:
            return None

        return ReviewerAccount(
            account_id=row["account_id"],
            role=row["role"],
            password_hash=row["password_hash"],
            active=bool(row["active"]),
        )

    finally:
        connection.close()


def check_permission(
    account_id,
    password,
    action,
    path=ACCOUNT_DATABASE,
):
    """Check credentials against the stored account and role."""

    account = load_account(account_id, path)

    if account is None:
        return False

    return authorize_reviewer(
        account,
        password,
        action,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Local reviewer account administration"
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    bootstrap = commands.add_parser("bootstrap")
    bootstrap.add_argument("account_id")

    check = commands.add_parser("check")
    check.add_argument("account_id")
    check.add_argument(
        "action",
        choices=(
            "read_opportunities",
            "read_reviews",
            "approve_opportunity",
            "reject_opportunity",
            "manage_reviewers",
        ),
    )

    args = parser.parse_args()

    if args.command == "bootstrap":
        password = getpass.getpass("New administrator password: ")
        confirm = getpass.getpass("Confirm password: ")

        if password != confirm:
            raise SystemExit("Passwords do not match.")

        try:
            bootstrap_administrator(args.account_id, password)
        except ValueError as error:
            raise SystemExit(
                f"Bootstrap failed: {error}"
            ) from None

        except PermissionError as error:
            raise SystemExit(
                f"Bootstrap failed: {error}"
            ) from None

        except sqlite3.Error:
            raise SystemExit(
                "Bootstrap failed: Account database error."
            ) from None

        print("Initial administrator created locally.")
        print("No opportunity database changes.")
        return

    password = getpass.getpass("Account password: ")

    try:
        allowed = check_permission(
            args.account_id,
            password,
            args.action,
        )
    except (ValueError, sqlite3.Error):
        allowed = False

    print("Authorized." if allowed else "Access denied.")

    if not allowed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()