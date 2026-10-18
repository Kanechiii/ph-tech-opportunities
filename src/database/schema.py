"""SQLite database foundation for PH Tech Opportunities."""

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "opportunities.sqlite3"
)

SCHEMA_VERSION = 1


SCHEMA_SQL = """
BEGIN;

CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,

    category TEXT NOT NULL DEFAULT 'unclassified'
        CHECK (
            category IN (
                'unclassified',
                'certification_voucher',
                'tech_event',
                'hackathon'
            )
        ),

    classification_status TEXT NOT NULL
        DEFAULT 'unclassified'
        CHECK (
            classification_status IN (
                'unclassified',
                'potential_match'
            )
        ),

    verification TEXT NOT NULL DEFAULT 'not_verified',
    free_status TEXT NOT NULL DEFAULT 'unknown',
    ph_eligibility TEXT NOT NULL DEFAULT 'unknown',
    deadline_status TEXT NOT NULL DEFAULT 'unknown',

    published_at TEXT,

    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (source_id, url)
);

CREATE INDEX IF NOT EXISTS idx_opportunities_category
ON opportunities (category);

CREATE INDEX IF NOT EXISTS idx_opportunities_verification
ON opportunities (verification);


CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    source_id TEXT NOT NULL,

    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,

    status TEXT NOT NULL DEFAULT 'running'
        CHECK (
            status IN (
                'running',
                'success',
                'partial',
                'failed'
            )
        ),

    items_found INTEGER NOT NULL DEFAULT 0
        CHECK (items_found >= 0),

    error_type TEXT
);

CREATE INDEX IF NOT EXISTS idx_collection_runs_source
ON collection_runs (source_id);


CREATE TABLE IF NOT EXISTS notification_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    opportunity_id INTEGER NOT NULL,

    channel TEXT NOT NULL DEFAULT 'email'
        CHECK (channel = 'email'),

    notification_type TEXT NOT NULL DEFAULT 'new_opportunity',

    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (opportunity_id)
        REFERENCES opportunities(id)
        ON DELETE CASCADE,

    UNIQUE (
        opportunity_id,
        channel,
        notification_type
    )
);

PRAGMA user_version = 1;

COMMIT;
"""


def connect_database(database_path=DATABASE_PATH):
    """Open a SQLite connection with integrity settings."""

    path = Path(database_path)

    if str(path) != ":memory:":
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    connection = sqlite3.connect(str(path))

    connection.row_factory = sqlite3.Row

    # SQLite foreign keys must be enabled per connection.
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database(database_path=DATABASE_PATH):
    """Create the initial schema without deleting existing data."""

    path = Path(database_path)
    connection = connect_database(path)

    try:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if version not in (0, SCHEMA_VERSION):
            raise RuntimeError(
                f"Unsupported database version: {version}"
            )

        connection.executescript(SCHEMA_SQL)

        return path

    finally:
        connection.close()


def get_database_tables(database_path=DATABASE_PATH):
    """Return the names of application database tables."""

    connection = connect_database(database_path)

    try:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        return [row["name"] for row in rows]

    finally:
        connection.close()


def main():
    """Initialize and inspect the local database."""

    print("=" * 55)
    print("PH TECH OPPORTUNITIES - DATABASE SETUP")
    print("=" * 55)

    try:
        path = initialize_database()
        tables = get_database_tables(path)

    except (sqlite3.Error, OSError, RuntimeError) as error:
        print(
            f"Database initialization failed: "
            f"{type(error).__name__}"
        )
        raise SystemExit(1) from None

    print(f"Database: {path}")
    print(f"Schema version: {SCHEMA_VERSION}")
    print()

    print("Tables created:")

    for table in tables:
        print(f"  - {table}")

    print()
    print("Database initialization completed.")
    print("No RSS collection or email delivery was performed.")


if __name__ == "__main__":
    main()