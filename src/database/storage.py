"""Opportunity storage and duplicate detection using SQLite."""

from src.database.schema import (
    DATABASE_PATH,
    connect_database,
)


# Fields stored in the opportunities table.
OPPORTUNITY_FIELDS = (
    "source_id",
    "url",
    "title",
    "category",
    "classification_status",
    "verification",
    "free_status",
    "ph_eligibility",
    "deadline_status",
    "published_at",
)

# Fields that can be modified after discovery.
EDITABLE_FIELDS = frozenset({
    "title",
    "category",
    "classification_status",
    "verification",
    "free_status",
    "ph_eligibility",
    "deadline_status",
    "published_at",
})


def validate_opportunity(opportunity):
    """Validate and normalize a collected opportunity."""

    if not isinstance(opportunity, dict):
        raise TypeError("Opportunity must be a dictionary.")

    for field in ("source_id", "url", "title"):
        value = opportunity.get(field)

        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Invalid required field: {field}")

    if not opportunity["url"].strip().startswith("https://"):
        raise ValueError("Opportunity URL must use HTTPS.")

    record = {
        "source_id": opportunity["source_id"].strip(),
        "url": opportunity["url"].strip(),
        "title": opportunity["title"].strip(),
        "category": opportunity.get(
            "category", "unclassified"
        ),
        "classification_status": opportunity.get(
            "classification_status", "unclassified"
        ),
        "verification": opportunity.get(
            "verification", "not_verified"
        ),
        "free_status": opportunity.get(
            "free_status", "unknown"
        ),
        "ph_eligibility": opportunity.get(
            "ph_eligibility", "unknown"
        ),
        "deadline_status": opportunity.get(
            "deadline_status", "unknown"
        ),
        "published_at": opportunity.get("published_at"),
    }

    # Ensure optional values are safe for SQLite storage.
    for field in OPPORTUNITY_FIELDS:
        value = record[field]

        if field == "published_at" and value is None:
            continue

        if not isinstance(value, str):
            raise ValueError(f"Invalid field type: {field}")

    return record


def save_opportunity(
    opportunity,
    database_path=DATABASE_PATH,
):
    """Insert or update an opportunity without duplication.

    Returns the opportunity ID and whether it was newly created.
    """

    record = validate_opportunity(opportunity)
    connection = connect_database(database_path)

    try:
        # Serialize the lookup and write transaction.
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            """
            SELECT *
            FROM opportunities
            WHERE source_id = ? AND url = ?
            """,
            (record["source_id"], record["url"]),
        ).fetchone()

        values = tuple(
            record[field] for field in OPPORTUNITY_FIELDS
        )

        if existing is None:
            placeholders = ", ".join(
                "?" for _ in OPPORTUNITY_FIELDS
            )
            columns = ", ".join(OPPORTUNITY_FIELDS)

            cursor = connection.execute(
                f"""
                INSERT INTO opportunities ({columns})
                VALUES ({placeholders})
                """,
                values,
            )

            opportunity_id = cursor.lastrowid
            created = True

        else:
            opportunity_id = existing["id"]
            created = False

            # An RSS refresh is not a verification action.
            # Unknown values must not erase existing decisions.
            protected_defaults = {
                "verification": "not_verified",
                "free_status": "unknown",
                "ph_eligibility": "unknown",
                "deadline_status": "unknown",
            }

            for field, default in protected_defaults.items():
                if (
                    record[field] == default
                    and existing[field] != default
                ):
                    record[field] = existing[field]

            # Preserve an existing publication date when
            # the refreshed feed entry has no date.
            if record["published_at"] is None:
                record["published_at"] = existing["published_at"]
                
            connection.execute(
                """
                UPDATE opportunities
                SET
                    title = ?,
                    category = ?,
                    classification_status = ?,
                    verification = ?,
                    free_status = ?,
                    ph_eligibility = ?,
                    deadline_status = ?,
                    published_at = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    record["title"],
                    record["category"],
                    record["classification_status"],
                    record["verification"],
                    record["free_status"],
                    record["ph_eligibility"],
                    record["deadline_status"],
                    record["published_at"],
                    opportunity_id,
                ),
            )

        connection.commit()

        return {
            "id": opportunity_id,
            "created": created,
            "status": "created" if created else "updated",
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_opportunity(
    opportunity_id,
    database_path=DATABASE_PATH,
):
    """Retrieve one opportunity by its database ID."""

    connection = connect_database(database_path)

    try:
        row = connection.execute(
            """
            SELECT *
            FROM opportunities
            WHERE id = ?
            """,
            (opportunity_id,),
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def opportunity_exists(
    source_id,
    url,
    database_path=DATABASE_PATH,
):
    """Check whether the same source and URL are stored."""

    connection = connect_database(database_path)

    try:
        row = connection.execute(
            """
            SELECT 1
            FROM opportunities
            WHERE source_id = ? AND url = ?
            LIMIT 1
            """,
            (source_id, url),
        ).fetchone()

        return row is not None

    finally:
        connection.close()


def list_opportunities(
    database_path=DATABASE_PATH,
    limit=20,
):
    """Return recently discovered opportunities."""

    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")

    connection = connect_database(database_path)

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM opportunities
            ORDER BY first_seen_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def update_opportunity(
    opportunity_id,
    changes,
    database_path=DATABASE_PATH,
):
    """Update explicitly allowed fields on an existing record."""

    if not isinstance(changes, dict) or not changes:
        raise ValueError("Changes must be a nonempty dictionary.")

    if not set(changes).issubset(EDITABLE_FIELDS):
        raise ValueError("Attempt to update a protected field.")

    for field, value in changes.items():
        if field == "published_at" and value is None:
            continue

        if not isinstance(value, str):
            raise ValueError(f"Invalid field type: {field}")

        if field != "published_at" and not value.strip():
            raise ValueError(f"Field cannot be empty: {field}")

    # Column names come exclusively from EDITABLE_FIELDS.
    assignments = ", ".join(
        f"{field} = ?" for field in changes
    )

    connection = connect_database(database_path)

    try:
        cursor = connection.execute(
            f"""
            UPDATE opportunities
            SET {assignments},
                last_seen_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (*changes.values(), opportunity_id),
        )

        connection.commit()

        return cursor.rowcount > 0

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def main():
    """Display stored opportunities without changing data."""

    print("=" * 55)
    print("PH TECH OPPORTUNITIES - DATABASE STORAGE")
    print("=" * 55)

    records = list_opportunities()

    print(f"Stored opportunities: {len(records)}")
    print()

    if not records:
        print("No stored opportunities yet.")
        print("RSS integration begins in Phase 4 Step 3.")
        return

    for record in records:
        print(f"ID: {record['id']}")
        print(f"Title: {record['title']}")
        print(f"Category: {record['category']}")
        print(f"Source: {record['source_id']}")
        print(f"URL: {record['url']}")
        print(f"First seen: {record['first_seen_at']}")
        print(f"Last seen: {record['last_seen_at']}")
        print("-" * 55)


if __name__ == "__main__":
    main()