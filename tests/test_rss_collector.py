"""Offline tests for the first RSS collector."""

from unittest.mock import patch

import pytest

from src.collectors.rss_collector import (
    SOURCE_URL,
    clean_text,
    collect_rss,
    fetch_feed,
    parse_feed,
)


SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Technology Feed</title>
    <link>https://example.com</link>
    <description>Offline RSS test feed</description>

    <item>
      <title>Python Developer Workshop</title>
      <link>https://example.com/workshop</link>
      <description>Sample technology announcement</description>
      <pubDate>Sat, 17 Oct 2026 08:00:00 GMT</pubDate>
    </item>

    <item>
      <title>Cloud Technology News</title>
      <link>https://example.com/cloud</link>
      <description>Another test announcement</description>
      <pubDate>Fri, 16 Oct 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_parse_valid_rss():
    """Valid RSS produces normalized records."""

    items = parse_feed(SAMPLE_RSS)

    assert len(items) == 2
    assert items[0]["title"] == "Python Developer Workshop"
    assert items[0]["category"] == "unclassified"
    assert items[0]["verification"] == "not_verified"


def test_publication_date():
    """Publication dates use UTC ISO formatting."""

    items = parse_feed(SAMPLE_RSS)

    assert items[0]["published_at"] == (
        "2026-10-17T08:00:00+00:00"
    )


def test_result_limit():
    """The collector respects the maximum result count."""

    items = parse_feed(SAMPLE_RSS, limit=1)

    assert len(items) == 1


def test_invalid_limit():
    """Reject result limits outside allowed bounds."""

    with pytest.raises(ValueError):
        parse_feed(SAMPLE_RSS, limit=0)


def test_malformed_feed():
    """Reject malformed XML."""

    with pytest.raises(ValueError):
        parse_feed(b"<rss><channel><item></rss>")


def test_clean_text():
    """Basic HTML markup is removed from titles."""

    assert clean_text("<b>Hello</b>   World") == (
        "Hello World"
    )


def test_collect_with_mocked_network():
    """Collection can be tested without internet access."""

    with patch(
        "src.collectors.rss_collector.fetch_feed",
        return_value=SAMPLE_RSS,
    ) as mock_fetch:

        items = collect_rss()

        assert len(items) == 2
        mock_fetch.assert_called_once_with(SOURCE_URL)


def test_unapproved_source_rejected():
    """The initial collector rejects unknown feed URLs."""

    with pytest.raises(ValueError):
        fetch_feed("https://example.com/feed.xml")