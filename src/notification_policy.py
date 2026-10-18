"""Fail-closed notification eligibility policy.

This module evaluates supplied opportunity and review data.
It does not verify external evidence, authorize reviewers,
access the database, or send emails.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit


ALLOWED_CATEGORIES = frozenset({
    "certification_voucher",
    "tech_event",
    "hackathon",
})

MAX_REVIEW_AGE = timedelta(days=7)


def valid_https_url(value):
    """Check basic HTTPS URL syntax, not website legitimacy."""

    if not isinstance(value, str):
        return False

    if not value or value != value.strip():
        return False

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname

        return (
            parsed.scheme == "https"
            and bool(hostname)
            and not any(char.isspace() for char in hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False


def valid_review_date(value, now):
    """Require an explicit, recent, timezone-aware review."""

    if not isinstance(value, str):
        return False

    try:
        reviewed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return False

    if reviewed.tzinfo is None:
        return False

    reviewed = reviewed.astimezone(timezone.utc)

    return (
        now - MAX_REVIEW_AGE <= reviewed <= now
    )


def assess_notification_policy(
    opportunity,
    review=None,
    now=None,
):
    """Evaluate readiness without authorizing email delivery.

    A passing result means the supplied fields meet the
    preliminary policy. It does not establish that the
    review is genuine, authorized, or stored in an audit log.
    """

    if not isinstance(opportunity, dict):
        raise TypeError("Opportunity must be a dictionary.")

    if review is not None and not isinstance(review, dict):
        raise TypeError("Review must be a dictionary or None.")

    if now is None:
        now = datetime.now(timezone.utc)

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Now must be timezone-aware.")

    now = now.astimezone(timezone.utc)

    reasons = []

    # Validate the basic record identity.
    if not (
        isinstance(opportunity.get("source_id"), str)
        and opportunity["source_id"].strip()
        and isinstance(opportunity.get("title"), str)
        and opportunity["title"].strip()
        and valid_https_url(opportunity.get("url"))
    ):
        reasons.append("invalid_opportunity")

    if opportunity.get("category") not in ALLOWED_CATEGORIES:
        reasons.append("unsupported_category")

    if opportunity.get("classification_status") != "potential_match":
        reasons.append("not_a_potential_match")

    if opportunity.get("verification") != "verified":
        reasons.append("not_verified")

    if opportunity.get("free_status") != "confirmed_free":
        reasons.append("free_status_unconfirmed")

    if opportunity.get("ph_eligibility") != "confirmed":
        reasons.append("ph_eligibility_unconfirmed")

    if opportunity.get("deadline_status") != "open":
        reasons.append("availability_unconfirmed")

    if review is None:
        reasons.append("review_missing")
    else:
        if (
            review.get("decision") != "approved"
            or review.get("method") != "manual"
        ):
            reasons.append("manual_approval_missing")

        reviewer_id = review.get("reviewer_id")

        if not (
            isinstance(reviewer_id, str)
            and reviewer_id.strip()
        ):
            reasons.append("reviewer_missing")

        if not valid_https_url(
            review.get("evidence_url")
        ):
            reasons.append("evidence_url_invalid")

        if not valid_review_date(
            review.get("reviewed_at"),
            now,
        ):
            reasons.append("review_date_invalid_or_stale")

    policy_passed = not reasons

    return {
        "policy_passed": policy_passed,
        "decision": (
            "preliminary_pass"
            if policy_passed
            else "blocked"
        ),
        "reasons": reasons,
        # Step 2 will introduce authoritative reviews.
        # Step 3 will introduce notification deduplication.
        # Neither capability exists in this policy module.
        "delivery_authorized": False,
    }