"""SQLite database foundation for PH Tech Opportunities."""

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "opportunities.sqlite3"
)

SCHEMA_VERSION = 3


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

MIGRATION_1_TO_2 = """
BEGIN IMMEDIATE;

CREATE TABLE opportunity_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    opportunity_id INTEGER NOT NULL,
    decision TEXT NOT NULL
        CHECK (decision IN ('approved', 'rejected')),

    method TEXT NOT NULL DEFAULT 'manual'
        CHECK (method = 'manual'),

    reviewer_id TEXT NOT NULL
        CHECK (length(trim(reviewer_id)) > 0),

    evidence_url TEXT NOT NULL
        CHECK (length(trim(evidence_url)) > 0),

    free_confirmed INTEGER NOT NULL DEFAULT 0
        CHECK (free_confirmed IN (0, 1)),

    ph_confirmed INTEGER NOT NULL DEFAULT 0
        CHECK (ph_confirmed IN (0, 1)),

    open_confirmed INTEGER NOT NULL DEFAULT 0
        CHECK (open_confirmed IN (0, 1)),

    reviewed_at TEXT NOT NULL,

    FOREIGN KEY (opportunity_id)
        REFERENCES opportunities(id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_reviews_opportunity
ON opportunity_reviews (opportunity_id, id DESC);

CREATE TRIGGER protect_review_updates
BEFORE UPDATE ON opportunity_reviews
BEGIN
    SELECT RAISE(ABORT, 'Review history is append-only');
END;

CREATE TRIGGER protect_review_deletes
BEFORE DELETE ON opportunity_reviews
BEGIN
    SELECT RAISE(ABORT, 'Review history is append-only');
END;

PRAGMA user_version = 2;

COMMIT;
"""

MIGRATION_2_TO_3 = """
BEGIN IMMEDIATE;

CREATE TABLE notification_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL,
    channel TEXT NOT NULL DEFAULT 'email'
        CHECK (channel = 'email'),
    notification_type TEXT NOT NULL DEFAULT 'new_opportunity',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending', 'sending', 'sent',
                'failed', 'uncertain'
            )
        ),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    claim_token TEXT,
    claimed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TEXT,
    last_error_type TEXT,

    FOREIGN KEY (opportunity_id)
        REFERENCES opportunities(id) ON DELETE RESTRICT,

    UNIQUE (opportunity_id, channel, notification_type)
);

CREATE INDEX idx_notification_jobs_status
ON notification_jobs (status, created_at);

PRAGMA user_version = 3;

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
    """Initialize or migrate SQLite through schema version 3."""

    path = Path(database_path)
    connection = connect_database(path)

    try:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if version not in (0, 1, 2, SCHEMA_VERSION):
            raise RuntimeError(
                f"Unsupported database version: {version}"
            )

        if version == 0:
            connection.executescript(SCHEMA_SQL)
            version = 1

        if version == 1:
            connection.executescript(MIGRATION_1_TO_2)
            version = 2

        if version == 2:
            connection.executescript(MIGRATION_2_TO_3)

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