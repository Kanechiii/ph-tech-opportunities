"""Rule-based classification for technology opportunity announcements.

This module only detects potential opportunities.
It does not verify availability, cost, or PH eligibility.
"""

import re


# Keywords identifying certification examinations.
CERTIFICATION_TERMS = (
    "certification",
    "certified",
    "certification exam",
    "exam voucher",
    "certification voucher",
)

# Terms indicating a possible exam promotion.
VOUCHER_TERMS = (
    "voucher",
    "exam discount",
    "exam fee waiver",
    "free exam",
    "100% off",
    "exam promotion",
)

# Terms identifying organized events.
EVENT_TERMS = (
    "workshop",
    "webinar",
    "meetup",
    "conference",
    "tech event",
    "developer event",
    "bootcamp",
    "seminar",
)

# Technical context required for generic event words.
TECH_TERMS = (
    "developer",
    "software",
    "programming",
    "coding",
    "python",
    "javascript",
    "cloud",
    "aws",
    "azure",
    "cybersecurity",
    "artificial intelligence",
    "machine learning",
    "generative ai",
    "technology",
    "tech",
    "data science",
    "github",
    "google developer",
)

# Hackathon and competition signals.
HACKATHON_TERMS = (
    "hackathon",
    "buildathon",
    "coding competition",
    "code jam",
    "programming competition",
)

# Strong event indicators containing their own tech context.
EXPLICIT_TECH_EVENTS = (
    "tech event",
    "developer event",
    "developer conference",
    "coding meetup",
    "tech meetup",
    "tech conference",
)


def normalize_text(value):
    """Normalize whitespace and case."""

    if not isinstance(value, str):
        raise TypeError("Announcement text must be a string.")

    return " ".join(value.casefold().split())


def find_matches(text, keywords):
    """Find whole keywords or phrases in normalized text."""

    matches = []

    for keyword in keywords:
        pattern = (
            r"(?<!\w)"
            + re.escape(keyword.casefold())
            + r"(?!\w)"
        )

        if re.search(pattern, text):
            matches.append(keyword)

    return matches


def classify_announcement(title, description=""):
    """Classify an announcement without claiming verification."""

    if not isinstance(title, str):
        raise TypeError("Title must be a string.")

    if not isinstance(description, str):
        raise TypeError("Description must be a string.")

    combined_text = normalize_text(
        f"{title} {description}"
    )

    category = "unclassified"
    matched_terms = []

    hackathon_matches = find_matches(
        combined_text,
        HACKATHON_TERMS,
    )

    certification_matches = find_matches(
        combined_text,
        CERTIFICATION_TERMS,
    )

    voucher_matches = find_matches(
        combined_text,
        VOUCHER_TERMS,
    )

    event_matches = find_matches(
        combined_text,
        EVENT_TERMS,
    )

    tech_matches = find_matches(
        combined_text,
        TECH_TERMS,
    )

    explicit_event_matches = find_matches(
        combined_text,
        EXPLICIT_TECH_EVENTS,
    )

    # Priority 1: Explicit hackathon-related language.
    if hackathon_matches:
        category = "hackathon"
        matched_terms = hackathon_matches

    # Priority 2: Certification AND promotion terminology.
    elif certification_matches and voucher_matches:
        category = "certification_voucher"
        matched_terms = list(dict.fromkeys(
            certification_matches + voucher_matches
        ))

    # Priority 3: Technology-related event terminology.
    elif explicit_event_matches or (
        event_matches and tech_matches
    ):
        category = "tech_event"
        matched_terms = list(dict.fromkeys(
            event_matches
            + tech_matches
            + explicit_event_matches
        ))

    is_candidate = category != "unclassified"

    return {
        "category": category,
        "classification_status": (
            "potential_match"
            if is_candidate
            else "unclassified"
        ),
        "is_candidate": is_candidate,
        "matched_terms": matched_terms,
        "verification": "not_verified",
        "free_status": "unknown",
        "ph_eligibility": "unknown",
        "deadline_status": "unknown",
    }


def main():
    """Demonstrate classification with fictional examples."""

    samples = [
        "AWS Certification Exam Voucher Available",
        "Free Python Developer Workshop",
        "Philippines Student AI Hackathon",
        "Understanding New GitHub Features",
        "Introduction to Python Programming",
    ]

    print("=" * 55)
    print("PH TECH OPPORTUNITIES CLASSIFIER")
    print("=" * 55)
    print("Mode: Local demonstration - fictional samples")
    print()

    for title in samples:
        result = classify_announcement(title)

        print(f"Title: {title}")
        print(f"Category: {result['category']}")
        print(f"Status: {result['classification_status']}")
        print(f"Terms: {result['matched_terms']}")
        print(f"Verification: {result['verification']}")
        print(f"Free status: {result['free_status']}")
        print(
            f"PH eligibility: {result['ph_eligibility']}"
        )
        print("-" * 55)

    print("Classification completed. No email was sent.")


if __name__ == "__main__":
    main()