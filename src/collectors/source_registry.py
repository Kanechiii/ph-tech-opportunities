"""Configuration and orchestration for approved RSS sources."""

from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "sources.yaml"

# Security allowlist: adding a new feed requires code review.
APPROVED_SOURCES = {
    "github_blog": {
        "name": "GitHub Blog",
        "url": "https://github.blog/feed/",
    },
    "python_insider": {
        "name": "Python Insider",
        "url": "https://blog.python.org/rss.xml",
    },
}

APPROVED_FEED_URLS = frozenset(
    source["url"] for source in APPROVED_SOURCES.values()
)


def load_sources(config_path=DEFAULT_CONFIG):
    """Read and validate the YAML source configuration."""

    path = Path(config_path)

    try:
        with path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

    except (OSError, yaml.YAMLError) as error:
        raise ValueError(
            "Unable to load source configuration."
        ) from error

    if not isinstance(config, dict):
        raise ValueError("Source configuration must be a mapping.")

    if config.get("version") != 1:
        raise ValueError("Unsupported source configuration version.")

    sources = config.get("sources")

    if not isinstance(sources, list):
        raise ValueError("Sources must be a list.")

    seen_ids = set()
    validated = []

    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Each source must be a mapping.")

        source_id = source.get("id")

        if source_id not in APPROVED_SOURCES:
            raise ValueError(
                "Source ID is not approved."
            )

        if source_id in seen_ids:
            raise ValueError(
                "Duplicate source ID detected."
            )

        seen_ids.add(source_id)

        approved = APPROVED_SOURCES[source_id]

        if source.get("name") != approved["name"]:
            raise ValueError(
                f"Invalid source name for {source_id}."
            )

        if source.get("url") != approved["url"]:
            raise ValueError(
                f"Invalid source URL for {source_id}."
            )

        enabled = source.get("enabled")

        if type(enabled) is not bool:
            raise ValueError(
                f"Invalid enabled setting for {source_id}."
            )

        limit = source.get("max_results")

        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError(
                f"Invalid max_results for {source_id}."
            )

        validated.append({
            "id": source_id,
            "name": approved["name"],
            "url": approved["url"],
            "enabled": enabled,
            "max_results": limit,
        })

    return validated


def collect_all_sources(config_path=DEFAULT_CONFIG):
    """Collect from every enabled source independently."""

    # Import here to avoid a circular import.
    from src.collectors.rss_collector import collect_rss

    sources = load_sources(config_path)

    announcements = []
    errors = []

    for source in sources:
        if not source["enabled"]:
            continue

        print(f"Checking: {source['name']}")

        try:
            items = collect_rss(
                url=source["url"],
                limit=source["max_results"],
            )

            for item in items:
                # The individual feed parser has a default
                # source label; replace it with the registry label.
                item["source"] = source["name"]
                item["source_id"] = source["id"]

            announcements.extend(items)

            print(f"  Collected: {len(items)}")

        except (ConnectionError, ValueError, TypeError) as error:
            errors.append({
                "source_id": source["id"],
                "error_type": type(error).__name__,
            })

            print(
                f"  Failed: {type(error).__name__}"
            )

    return announcements, errors


def main():
    """Run the multi-source RSS preview."""

    print("=" * 55)
    print("PH TECH OPPORTUNITIES - SOURCE REGISTRY")
    print("=" * 55)

    try:
        announcements, errors = collect_all_sources()

    except ValueError as error:
        print(f"Configuration error: {error}")
        raise SystemExit(1) from None

    print()
    print(f"Total announcements: {len(announcements)}")
    print(f"Failed sources: {len(errors)}")
    print()

    for index, item in enumerate(announcements, start=1):
        print(f"[{index}] {item['title']}")
        print(f"Source: {item['source']}")
        print(f"URL: {item['url']}")
        print(f"Published: {item['published_at'] or 'Unknown'}")
        print(f"Verification: {item['verification']}")
        print("-" * 55)

    print("Preview completed. No email was sent.")

    if errors:
        print("Some sources could not be collected.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()