"""Private local reviewer account store.

Stores password verifiers, never plaintext passwords.
Does not modify opportunity reviews or send notifications.
"""

import argparse
import getpass
import sqlite3
from pathlib import Path

from src.database.schema import PROJECT_ROOT
from src.reviewer_throttle import authorize_with_throttle
from src.reviewer_auth import (
    ACCOUNT_ID_PATTERN,
    ROLES,
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

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reviewer_account_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                action TEXT NOT NULL
                    CHECK (action IN ('role_changed', 'status_changed')),
                old_value TEXT NOT NULL,
                new_value TEXT NOT NULL,
                changed_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        connection.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                protect_account_audit_updates
            BEFORE UPDATE ON reviewer_account_audit
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Account audit history is append-only'
                );
            END
            """
        )

        connection.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                protect_account_audit_deletes
            BEFORE DELETE ON reviewer_account_audit
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Account audit history is append-only'
                );
            END
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

    return authorize_with_throttle(
        account, account_id, password, action, path
    )

def change_account_access(
    actor_id,
    actor_password,
    target_id,
    *,
    role=None,
    active=None,
    path=ACCOUNT_DATABASE,
):
    """Change a stored account with administrator authorization.

    Only one field may change per call. All checks, updates,
    and audit inserts use the same SQLite transaction.
    """

    if (role is None) == (active is None):
        raise ValueError("Specify exactly one account change.")

    if role is not None and role not in ROLES:
        raise ValueError("Invalid reviewer role.")

    if active is not None and type(active) is not bool:
        raise ValueError("Active status must be boolean.")

    if not (
        isinstance(actor_id, str)
        and isinstance(target_id, str)
        and ACCOUNT_ID_PATTERN.fullmatch(actor_id)
        and ACCOUNT_ID_PATTERN.fullmatch(target_id)
    ):
        raise ValueError("Invalid account identifier.")

    path = Path(path)

    if not path.is_file():
        raise PermissionError("Account store unavailable.")

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row

    try:
        # Serialize the authorization check and account update.
        connection.execute("BEGIN IMMEDIATE")

        actor_row = connection.execute(
            """
            SELECT account_id, role, password_hash, active
            FROM reviewer_accounts
            WHERE account_id = ?
            """,
            (actor_id,),
        ).fetchone()

        if actor_row is None:
            raise PermissionError("Administrator access denied.")

        actor = ReviewerAccount(
            account_id=actor_row["account_id"],
            role=actor_row["role"],
            password_hash=actor_row["password_hash"],
            active=bool(actor_row["active"]),
        )

        if not authorize_with_throttle(
            actor, actor_id, actor_password, "manage_reviewers", path
        ):
            raise PermissionError("Administrator access denied.")

        target = connection.execute(
            """
            SELECT account_id, role, active
            FROM reviewer_accounts
            WHERE account_id = ?
            """,
            (target_id,),
        ).fetchone()

        if target is None:
            raise ValueError("Target account not found.")

        field = "role" if role is not None else "active"

        old_value = target[field]
        new_value = role if role is not None else int(active)

        if old_value == new_value:
            return False

        removing_admin = (
            target["role"] == "administrator"
            and target["active"] == 1
            and (
                (field == "role" and role != "administrator")
                or (field == "active" and active is False)
            )
        )

        if removing_admin:
            admin_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM reviewer_accounts
                WHERE role = 'administrator'
                  AND active = 1
                """
            ).fetchone()[0]

            if admin_count <= 1:
                raise PermissionError(
                    "Cannot remove the last active administrator."
                )

        if field == "role":
            connection.execute(
                """
                UPDATE reviewer_accounts
                SET role = ?
                WHERE account_id = ?
                """,
                (role, target_id),
            )
            action = "role_changed"
        else:
            connection.execute(
                """
                UPDATE reviewer_accounts
                SET active = ?
                WHERE account_id = ?
                """,
                (int(active), target_id),
            )
            action = "status_changed"

        connection.execute(
            """
            INSERT INTO reviewer_account_audit (
                actor_id, target_id, action,
                old_value, new_value
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                actor_id,
                target_id,
                action,
                str(old_value),
                str(new_value),
            ),
        )

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


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