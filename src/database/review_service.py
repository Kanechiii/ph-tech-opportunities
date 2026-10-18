"""Local manual opportunity review and evidence history.

Reviews are operator attestations, not identity authentication.
This module never sends notifications.
"""

import argparse
import getpass
from datetime import datetime, timezone

from src.database.schema import DATABASE_PATH, connect_database
from src.notification_policy import valid_https_url
from src.reviewer_accounts import (
    ACCOUNT_DATABASE,
    check_permission,
)


def record_review(
    opportunity_id,
    decision,
    evidence_url,
    reviewer_id=None,
    free_confirmed=False,
    ph_confirmed=False,
    open_confirmed=False,
    database_path=DATABASE_PATH,
    *,
    reviewer_password=None,
    account_database_path=ACCOUNT_DATABASE,
):
    """Append a review only after authenticated authorization."""

    if type(opportunity_id) is not int or opportunity_id < 1:
        raise ValueError("Invalid opportunity ID.")

    if decision not in ("approved", "rejected"):
        raise ValueError("Invalid review decision.")

    if not valid_https_url(evidence_url):
        raise ValueError("Evidence must be an HTTPS URL.")

    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise ValueError("Reviewer label is required.")

    confirmations = (
        free_confirmed,
        ph_confirmed,
        open_confirmed,
    )

    if any(type(value) is not bool for value in confirmations):
        raise ValueError("Confirmations must be boolean.")

    if decision == "approved" and not all(confirmations):
        raise ValueError(
            "Approval requires all three confirmations."
        )

    if decision == "rejected" and any(confirmations):
        raise ValueError(
            "Rejected reviews cannot contain approval confirmations."
        )

    # Never trust reviewer_id as evidence of identity.
    # The account store verifies the password and current role.
    action = (
        "approve_opportunity"
        if decision == "approved"
        else "reject_opportunity"
    )

    if not (
        isinstance(reviewer_id, str)
        and reviewer_id.strip()
        and isinstance(reviewer_password, str)
        and reviewer_password
    ):
        raise PermissionError(
            "Authenticated reviewer credentials are required."
        )

    try:
        authorized = check_permission(
            reviewer_id,
            reviewer_password,
            action,
            account_database_path,
        )
    except (ValueError, OSError):
        authorized = False

    if not authorized:
        raise PermissionError(
            "Review authorization denied."
        )

    reviewed_at = datetime.now(timezone.utc).isoformat()

    connection = connect_database(database_path)

    try:
        connection.execute("BEGIN IMMEDIATE")

        opportunity = connection.execute(
            """
            SELECT *
            FROM opportunities
            WHERE id = ?
            """,
            (opportunity_id,),
        ).fetchone()

        if opportunity is None:
            raise ValueError("Opportunity not found.")

        if decision == "approved":
            if (
                opportunity["category"] not in (
                    "certification_voucher",
                    "tech_event",
                    "hackathon",
                )
                or opportunity["classification_status"]
                != "potential_match"
            ):
                raise ValueError(
                    "Only classified candidates can be approved."
                )

        cursor = connection.execute(
            """
            INSERT INTO opportunity_reviews (
                opportunity_id,
                decision,
                method,
                reviewer_id,
                evidence_url,
                free_confirmed,
                ph_confirmed,
                open_confirmed,
                reviewed_at
            )
            VALUES (?, ?, 'manual', ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity_id,
                decision,
                reviewer_id,
                evidence_url,
                int(free_confirmed),
                int(ph_confirmed),
                int(open_confirmed),
                reviewed_at,
            ),
        )

        if decision == "approved":
            connection.execute(
                """
                UPDATE opportunities
                SET verification = 'verified',
                    free_status = 'confirmed_free',
                    ph_eligibility = 'confirmed',
                    deadline_status = 'open'
                WHERE id = ?
                """,
                (opportunity_id,),
            )

        else:
            connection.execute(
                """
                UPDATE opportunities
                SET verification = 'rejected',
                    free_status = 'unknown',
                    ph_eligibility = 'unknown',
                    deadline_status = 'unknown'
                WHERE id = ?
                """,
                (opportunity_id,),
            )

        connection.commit()

        return {
            "review_id": cursor.lastrowid,
            "opportunity_id": opportunity_id,
            "decision": decision,
            "reviewed_at": reviewed_at,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_review_history(
    opportunity_id,
    database_path=DATABASE_PATH,
):
    """Retrieve an opportunity's recorded review decisions."""

    connection = connect_database(database_path)

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM opportunity_reviews
            WHERE opportunity_id = ?
            ORDER BY id DESC
            """,
            (opportunity_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_latest_review(
    opportunity_id,
    database_path=DATABASE_PATH,
):
    """Get the most recent review in policy-compatible form."""

    history = get_review_history(
        opportunity_id,
        database_path,
    )

    if not history:
        return None

    latest = history[0]

    return {
        "decision": latest["decision"],
        "method": latest["method"],
        "reviewer_id": latest["reviewer_id"],
        "evidence_url": latest["evidence_url"],
        "reviewed_at": latest["reviewed_at"],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Local opportunity review"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    list_parser = subparsers.add_parser("history")
    list_parser.add_argument("opportunity_id", type=int)

    review_parser = subparsers.add_parser("review")
    review_parser.add_argument("opportunity_id", type=int)
    review_parser.add_argument(
        "decision",
        choices=("approved", "rejected"),
    )
    review_parser.add_argument("--evidence", required=True)
    review_parser.add_argument(
        "--reviewer",
        required=True,
        help="Existing local reviewer account ID",
    )

    args = parser.parse_args()

    if args.command == "history":
        for row in get_review_history(args.opportunity_id):
            print(
                f"Review {row['id']}: "
                f"{row['decision']} | {row['reviewed_at']}"
            )
            print(f"Evidence: {row['evidence_url']}")
        return

    print()
    print("MANUAL OPPORTUNITY REVIEW")
    print(f"Opportunity ID: {args.opportunity_id}")
    print(f"Decision: {args.decision}")
    print(f"Evidence: {args.evidence}")
    print()
    print("Inspect the official listing yourself.")
    print("The software cannot verify the evidence for you.")

    free = ph = is_open = False

    if args.decision == "approved":
        free = input(
            "Confirmed free, including required fees? [yes/no]: "
        ).strip().lower() == "yes"

        ph = input(
            "Confirmed Philippine eligibility? [yes/no]: "
        ).strip().lower() == "yes"

        is_open = input(
            "Confirmed currently open and available? [yes/no]: "
        ).strip().lower() == "yes"

        if not all((free, ph, is_open)):
            print("Approval canceled: confirmation incomplete.")
            raise SystemExit(1)

    confirmation = input(
        f"Type {args.decision.upper()} to record this decision: "
    ).strip()

    if confirmation != args.decision.upper():
        print("Review canceled. No database changes made.")
        return

    password = getpass.getpass(
        f"Password for {args.reviewer}: "
    )

    try:
        result = record_review(
            opportunity_id=args.opportunity_id,
            decision=args.decision,
            evidence_url=args.evidence,
            reviewer_id=args.reviewer,
            reviewer_password=password,
            free_confirmed=free,
            ph_confirmed=ph,
            open_confirmed=is_open,
        )

    except PermissionError:
        print("Review failed: Access denied.")
        raise SystemExit(1) from None

    except (ValueError, OSError) as error:
        print(f"Review failed: {error}")
        raise SystemExit(1) from None

    finally:
        password = None

    print(f"Review recorded: {result['review_id']}")
    print("No email was sent.")


if __name__ == "__main__":
    main()