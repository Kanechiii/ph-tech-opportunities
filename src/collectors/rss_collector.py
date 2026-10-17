"""Collect and preview announcements from an official RSS feed."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from html import unescape
import re

import feedparser


SOURCE_NAME = "GitHub Blog"
SOURCE_URL = "https://github.blog/feed/"

REQUEST_TIMEOUT = 15
MAX_FEED_SIZE = 2_000_000
MAX_RESULTS = 5


def fetch_feed(url=SOURCE_URL):
    """Download RSS data from a configured public feed."""

    if url != SOURCE_URL:
        raise ValueError("RSS source is not approved.")

    request = Request(
        url,
        headers={
            "User-Agent": "PHTechOpportunities/0.1 RSS Reader",
            "Accept": (
                "application/rss+xml, "
                "application/atom+xml, "
                "application/xml, text/xml"
            ),
        },
    )

    try:
        with urlopen(
            request,
            timeout=REQUEST_TIMEOUT,
        ) as response:

            data = response.read(MAX_FEED_SIZE + 1)

            if len(data) > MAX_FEED_SIZE:
                raise ValueError(
                    "RSS feed exceeds the allowed size."
                )

            return data

    except (HTTPError, URLError, TimeoutError) as error:
        raise ConnectionError(
            "Unable to retrieve the RSS feed."
        ) from error


def clean_text(value):
    """Remove simple markup and normalize whitespace."""

    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    text = unescape(text)

    return " ".join(text.split())


def format_date(entry):
    """Return a normalized UTC publication date."""

    parsed_time = entry.get("published_parsed")

    if not parsed_time:
        parsed_time = entry.get("updated_parsed")

    if parsed_time:
        return datetime(
            *parsed_time[:6],
            tzinfo=timezone.utc,
        ).isoformat()

    raw_date = (
        entry.get("published")
        or entry.get("updated")
    )

    if raw_date:
        try:
            date = parsedate_to_datetime(raw_date)

            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)

            return date.astimezone(
                timezone.utc
            ).isoformat()

        except (TypeError, ValueError, IndexError):
            pass

    return None


def parse_feed(xml_data, limit=MAX_RESULTS):
    """Normalize RSS/Atom entries into dictionaries."""

    if not isinstance(xml_data, bytes):
        raise TypeError("Feed content must be bytes.")

    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("Result limit must be between 1 and 50.")

    feed = feedparser.parse(xml_data)

    if feed.bozo:
        raise ValueError("RSS data is malformed.")

    if not feed.version:
        raise ValueError("Content is not a recognized RSS/Atom feed.")

    opportunities = []

    for entry in feed.entries[:limit]:
        title = clean_text(entry.get("title"))
        link = str(entry.get("link", "")).strip()

        if not title or not link.startswith("https://"):
            continue

        opportunities.append({
            "source": SOURCE_NAME,
            "title": title,
            "url": link,
            "published_at": format_date(entry),
            "category": "unclassified",
            "verification": "not_verified",
        })

    return opportunities


def collect_rss(url=SOURCE_URL, limit=MAX_RESULTS):
    """Retrieve and parse RSS announcements."""

    xml_data = fetch_feed(url)
    return parse_feed(xml_data, limit=limit)


def main():
    """Preview collected announcements in the terminal."""

    print("=" * 55)
    print("PH TECH OPPORTUNITIES - RSS COLLECTOR")
    print("=" * 55)
    print(f"Source: {SOURCE_NAME}")
    print("Mode: Read-only collection")
    print()

    try:
        announcements = collect_rss()

    except (ConnectionError, ValueError, TypeError) as error:
        print(f"Collection failed: {error}")
        raise SystemExit(1) from None

    if not announcements:
        print("No valid announcements were found.")
        return

    print(f"Collected {len(announcements)} announcements.")
    print()

    for index, item in enumerate(announcements, start=1):
        print(f"[{index}] {item['title']}")
        print(f"Source: {item['source']}")
        print(f"URL: {item['url']}")
        print(f"Published: {item['published_at'] or 'Unknown'}")
        print(f"Category: {item['category']}")
        print(f"Verification: {item['verification']}")
        print("-" * 55)

    print("Collection completed. No email was sent.")


if __name__ == "__main__":
    main()