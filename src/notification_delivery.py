"""Explicitly controlled delivery of reviewed opportunities.

Preview is read-only. Real sending is local and manually authorized.
No scheduled or unattended delivery is supported by this module.
"""

import argparse
import os
import sys
from html import escape

from dotenv import load_dotenv

from src.database.schema import DATABASE_PATH
from src.database.storage import get_opportunity
from src.database.review_service import get_latest_review
from src.database.notification_queue import (
    get_job,
    claim_notification,
    finish_attempt,
)
from src.notification_policy import assess_notification_policy
from src.email_sender import get_email_config, send_email


CATEGORY_LABELS = {
    "certification_voucher": "Certification Voucher",
    "tech_event": "Technology Event",
    "hackathon": "Hackathon",
}


def prepare_notification(job_id, database_path=DATABASE_PATH):
    """Prepare content only for a currently eligible pending job."""

    if type(job_id) is not int or job_id < 1:
        raise ValueError("Invalid notification job ID.")

    job = get_job(job_id, database_path)

    if job is None:
        raise ValueError("Notification job not found.")

    if job["status"] != "pending":
        raise ValueError(
            f"Notification job is not pending: {job['status']}"
        )

    opportunity = get_opportunity(
        job["opportunity_id"], database_path
    )

    if opportunity is None:
        raise ValueError("Opportunity record not found.")

    review = get_latest_review(
        job["opportunity_id"], database_path
    )

    assessment = assess_notification_policy(
        opportunity, review
    )

    if not assessment["policy_passed"]:
        raise ValueError(
            "Opportunity does not meet the current review policy."
        )

    category = CATEGORY_LABELS[opportunity["category"]]
    title = opportunity["title"]
    url = opportunity["url"]
    evidence = review["evidence_url"]

    subject = f"PH Tech Opportunity: {title}"

    text_body = "\n".join([
        "PH TECH OPPORTUNITIES",
        "",
        "Manually reviewed opportunity",
        "",
        f"Category: {category}",
        f"Title: {title}",
        f"Official announcement: {url}",
        f"Review evidence: {evidence}",
        "",
        "Review findings at the recorded review time:",
        "Cost: Confirmed free",
        "Philippine eligibility: Confirmed",
        "Availability: Confirmed open",
        "",
        "Availability and terms may change.",
        "Check the official announcement before registering.",
    ])

    html_body = f"""
    <html lang="en">
    <body style="font-family:Arial,sans-serif;line-height:1.6">
      <h2>PH Tech Opportunities</h2>
      <p><strong>Manually reviewed opportunity</strong></p>
      <p><strong>Category:</strong> {escape(category)}</p>
      <h3>{escape(title)}</h3>
      <p>
        <a href="{escape(url, quote=True)}">
          Official announcement
        </a>
      </p>
      <p>
        <a href="{escape(evidence, quote=True)}">
          Review evidence
        </a>
      </p>
      <p>Review findings at the recorded review time:</p>
      <ul>
        <li>Cost: Confirmed free</li>
        <li>Philippine eligibility: Confirmed</li>
        <li>Availability: Confirmed open</li>
      </ul>
      <p>
        Availability and terms may change.
        Check the official announcement before registering.
      </p>
    </body>
    </html>
    """

    return {
        "job_id": job_id,
        "opportunity_id": opportunity["id"],
        "subject": subject,
        "text_body": text_body,
        "html_body": html_body,
    }


def deliver_notification(
    job_id,
    database_path=DATABASE_PATH,
    *,
    authorized=False,
    sender=None,
    config_validator=None,
):
    """Submit one explicitly authorized pending job.

    Any exception after claim is considered ambiguous.
    The module never automatically retries such a job.
    """

    if authorized is not True:
        raise PermissionError("Explicit authorization is required.")

    # Preview and validate the latest review before credentials.
    message = prepare_notification(job_id, database_path)

    if sender is None:
        sender = send_email

    if config_validator is None:
        config_validator = get_email_config

    # No claim or SMTP operation if configuration is invalid.
    config_validator()

    # Claim atomically; claim_notification rechecks eligibility.
    token = claim_notification(job_id, database_path)

    if token is None:
        raise RuntimeError(
            "Job could not be claimed. "
            "Its status or review may have changed."
        )

    try:
        result = sender(
            subject=message["subject"],
            text_body=message["text_body"],
            html_body=message["html_body"],
        )

    except Exception:
        # We cannot safely infer whether SMTP accepted the email.
        try:
            finish_attempt(
                job_id, token, "uncertain", database_path
            )
        except Exception:
            # A stale sending claim will later be quarantined.
            pass

        raise RuntimeError(
            "Delivery outcome uncertain. Do not retry automatically."
        ) from None

    if result is not True:
        finish_attempt(
            job_id, token, "uncertain", database_path
        )
        raise RuntimeError(
            "SMTP submission was not positively confirmed."
        )

    if not finish_attempt(
        job_id, token, "sent", database_path
    ):
        raise RuntimeError(
            "SMTP reported success, but recording it failed. "
            "Inspect the job before taking further action."
        )

    return {
        "job_id": job_id,
        "status": "sent",
        "message": "SMTP submission reported success",
    }


def main():
    """Local-only CLI: preview or interactively authorize a send."""

    parser = argparse.ArgumentParser(
        description="Reviewed opportunity email delivery"
    )

    commands = parser.add_subparsers(
        dest="command", required=True
    )

    preview_parser = commands.add_parser("preview")
    preview_parser.add_argument("job_id", type=int)

    send_parser = commands.add_parser("send")
    send_parser.add_argument("job_id", type=int)

    args = parser.parse_args()

    if args.command == "preview":
        try:
            content = prepare_notification(args.job_id)
        except (ValueError, TypeError) as error:
            print(f"Preview unavailable: {error}")
            raise SystemExit(1) from None

        print("=" * 55)
        print("REVIEWED OPPORTUNITY EMAIL PREVIEW")
        print("=" * 55)
        print(f"Job ID: {content['job_id']}")
        print(f"Subject: {content['subject']}")
        print()
        print(content["text_body"])
        print()
        print("No email sent. No queue state changed.")
        return

    # Explicitly prohibit hosted or noninteractive execution.
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        raise SystemExit(
            "Reviewed opportunity delivery is disabled in GitHub Actions."
        )

    if not sys.stdin.isatty():
        raise SystemExit(
            "Sending requires an interactive local terminal."
        )

    if os.getenv("ENABLE_REVIEWED_EMAIL_DELIVERY") != "YES":
        raise SystemExit(
            "Set ENABLE_REVIEWED_EMAIL_DELIVERY=YES "
            "for the current local terminal session."
        )

    try:
        content = prepare_notification(args.job_id)
    except (ValueError, TypeError) as error:
        print(f"Delivery blocked: {error}")
        raise SystemExit(1) from None

    print("=" * 55)
    print("REVIEWED OPPORTUNITY DELIVERY CONFIRMATION")
    print("=" * 55)
    print(content["text_body"])
    print()
    print("This action may send one REAL email.")

    confirmation = input(
        f"Type SEND {args.job_id} to authorize: "
    ).strip()

    if confirmation != f"SEND {args.job_id}":
        print("Canceled. Nothing was sent.")
        return

    load_dotenv()

    try:
        result = deliver_notification(
            args.job_id,
            authorized=True,
        )
    except Exception as error:
        print(f"Delivery stopped: {error}")
        raise SystemExit(1) from None

    print(result["message"])
    print("Queue status: sent")


if __name__ == "__main__":
    main()