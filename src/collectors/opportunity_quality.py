"""Read-only opportunity relevance and duplicate analysis.

Signals are hints, not proof of availability, price, or eligibility.
Never merges records, changes reviews, or sends email.
"""

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)

from src.database.schema import DATABASE_PATH


TRACKING_PARAMETERS = frozenset({
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
})

FREE_HINTS = (
    "free",
    "no registration fee",
    "100% off",
    "fee waiver",
)

PH_HINTS = (
    "philippines",
    "filipino",
    "manila",
    "quezon city",
    "cebu",
    "davao",
)

DEADLINE_HINTS = (
    "registration",
    "apply now",
    "applications open",
    "register now",
    "deadline",
)

GENERIC_WORDS = frozenset({
    "the", "a", "an", "and", "for", "of", "to",
    "in", "on", "at", "with",
})


def normalized_title(value):
    """Normalize title text for conservative comparison."""

    if not isinstance(value, str):
        raise TypeError("Title must be text.")

    text = value.casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def canonical_url(value):
    """Produce a conservative comparison key for HTTPS URLs.

    Does not rewrite the URL stored in SQLite.
    """

    if not isinstance(value, str):
        return None

    try:
        parsed = urlsplit(value)

        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            return None

        hostname = parsed.hostname.casefold()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        if any(char.isspace() for char in hostname):
            return None

        parameters = [
            (key, val)
            for key, val in parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            if not (
                key.casefold().startswith("utm_")
                or key.casefold() in TRACKING_PARAMETERS
            )
        ]

        parameters.sort()

        path = parsed.path or "/"

        # Remove only a redundant trailing slash.
        if path != "/":
            path = path.rstrip("/")

        return urlunsplit((
            "https",
            hostname,
            path,
            urlencode(parameters),
            "",
        ))

    except ValueError:
        return None


def title_similarity(first, second):
    """Return conservative title similarity from 0 to 1."""

    a = normalized_title(first)
    b = normalized_title(second)

    words_a = [
        word for word in a.split()
        if word not in GENERIC_WORDS
    ]
    words_b = [
        word for word in b.split()
        if word not in GENERIC_WORDS
    ]

    # Short titles are too ambiguous for similarity matching.
    if len(words_a) < 4 or len(words_b) < 4:
        return 0.0

    # Compare both word overlap and character sequence.
    set_a = set(words_a)
    set_b = set(words_b)

    overlap = len(set_a & set_b) / len(set_a | set_b)

    sequence = SequenceMatcher(
        None, a, b, autojunk=False
    ).ratio()

    return round(min(overlap, sequence), 4)


def _contains_phrase(text, phrase):
    pattern = (
        r"(?<!\w)"
        + re.escape(phrase)
        + r"(?!\w)"
    )
    return re.search(pattern, text) is not None


def analyze_candidate(item):
    """Generate explainable, unverified relevance signals."""

    if not isinstance(item, dict):
        raise TypeError("Opportunity must be a dictionary.")

    title = normalized_title(item.get("title", ""))

    category = item.get("category", "unclassified")

    is_candidate = (
        item.get("classification_status") == "potential_match"
        and category in {
            "certification_voucher",
            "tech_event",
            "hackathon",
        }
    )

    signals = {
        "free_hint": any(
            _contains_phrase(title, term)
            for term in FREE_HINTS
        ),
        "philippines_hint": any(
            _contains_phrase(title, term)
            for term in PH_HINTS
        ),
        "registration_hint": any(
            _contains_phrase(title, term)
            for term in DEADLINE_HINTS
        ),
    }

    score = (
        (2 if is_candidate else 0)
        + int(signals["free_hint"])
        + int(signals["philippines_hint"])
        + int(signals["registration_hint"])
    )

    return {
        "id": item.get("id"),
        "source_id": item.get("source_id"),
        "category": category,
        "candidate": is_candidate,
        "quality_score": score,
        "review_priority": (
            "high" if score >= 4
            else "medium" if score >= 2
            else "low"
        ),
        "signals": signals,
        "requires_manual_verification": True,
        "verified_by_analyzer": False,
    }


def find_possible_duplicates(records):
    """Flag possible duplicates without modifying records.

    URL equivalents can be matched across different sources.
    Title-only matching requires same category, different
    source IDs, and a strong title similarity.
    """

    records = list(records)
    findings = []

    for index, first in enumerate(records):
        for second in records[index + 1:]:
            first_id = first.get("id")
            second_id = second.get("id")

            if (
                first_id is None
                or second_id is None
                or first_id == second_id
            ):
                continue

            url_a = canonical_url(first.get("url"))
            url_b = canonical_url(second.get("url"))

            if url_a and url_a == url_b:
                reason = "equivalent_url"
                confidence = "high"
            elif (
                first.get("source_id") != second.get("source_id")
                and first.get("category") == second.get("category")
                and first.get("category") not in (None, "unclassified")
                and title_similarity(
                    first.get("title", ""),
                    second.get("title", ""),
                ) >= 0.92
            ):
                reason = "similar_cross_source_title"
                confidence = "possible"
            else:
                continue

            findings.append({
                "first_id": first_id,
                "second_id": second_id,
                "reason": reason,
                "confidence": confidence,
                "automatically_merged": False,
            })

    return findings


def inspect_quality(database_path=DATABASE_PATH, limit=100):
    """Inspect current SQLite opportunities without writing."""

    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Limit must be between 1 and 500.")

    path = Path(database_path)

    if not path.is_file():
        raise ValueError("Database does not exist.")

    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")

        rows = connection.execute(
            """
            SELECT id, source_id, url, title,
                   category, classification_status
            FROM opportunities
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        records = [dict(row) for row in rows]

    finally:
        connection.close()

    evaluations = [
        analyze_candidate(record)
        for record in records
    ]

    duplicates = find_possible_duplicates(records)

    priority_counts = {
        "high": 0,
        "medium": 0,
        "low": 0,
    }

    for evaluation in evaluations:
        priority_counts[evaluation["review_priority"]] += 1

    return {
        "records_inspected": len(records),
        "candidate_count": sum(
            item["candidate"]
            for item in evaluations
        ),
        "priority_counts": priority_counts,
        "possible_duplicate_pairs": duplicates,
        "evaluations": evaluations,
        "database_modified": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only opportunity quality analysis"
    )
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    try:
        result = inspect_quality(limit=args.limit)
    except (ValueError, TypeError, sqlite3.Error) as error:
        print(
            "Quality analysis failed: "
            f"{type(error).__name__}"
        )
        raise SystemExit(1) from None

    print("PH TECH OPPORTUNITIES - QUALITY ANALYSIS")
    print(json.dumps(result, indent=2))
    print("No records merged, verified, or modified.")
    print("No email was sent.")


if __name__ == "__main__":
    main()