"""Phase 10 Step 4: read-only PostgreSQL migration planning.

Never connects to PostgreSQL or exports rows. Performs deterministic SQLite
inventories and prepares parametrized insert SQL for later synthetic testing.
A separate, explicitly authorized Step 5 will implement writes/cutover.
"""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from src.database.cutover_readiness import (
    OPPORTUNITY_TABLES,
    ACCOUNT_TABLES,
    compare_database_tables,
)
from src.database.migration_preflight import inspect_accounts
from src.database.storage_readiness import inspect_storage


# Explicit, stable load order preserves foreign keys without rewriting IDs.
LOAD_ORDER = (
    ("phtech", "opportunities"),
    ("phtech", "collection_runs"),
    ("phtech", "notification_history"),
    ("phtech", "opportunity_reviews"),
    ("phtech", "notification_jobs"),
    ("phtech_private", "reviewer_accounts"),
    ("phtech_private", "reviewer_account_audit"),
)

PRIMARY_KEYS = {
    "opportunities": "id",
    "collection_runs": "id",
    "notification_history": "id",
    "opportunity_reviews": "id",
    "notification_jobs": "id",
    "reviewer_accounts": "account_id",
    "reviewer_account_audit": "id",
}


def _existing_file(path):
    candidate = Path(path).resolve(strict=True)
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError("Source must be an existing regular SQLite file.")
    return candidate


def _readonly_connection(path):
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    return connection


def _table_fingerprint(connection, table):
    """Hash canonical, ordered records without exposing sensitive fields."""
    pk = PRIMARY_KEYS[table]
    columns = [
        r["name"] for r in connection.execute(
            f'PRAGMA table_info("{table}")'
        )
    ]
    if not columns or pk not in columns:
        raise ValueError("Missing migration table or primary key.")

    digest = hashlib.sha256()
    count = 0
    for row in connection.execute(
        f'SELECT * FROM "{table}" ORDER BY "{pk}"'
    ):
        payload = json.dumps(
            [row[col] for col in columns],
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
        count += 1
    return {"rows": count, "sha256": digest.hexdigest(), "columns": columns}


def build_migration_plan(local_opportunities, local_accounts, hosted_opportunities):
    """Fail closed on structural problems and unresolved notification states.

    The plan is an inventory, not a migration permit. Divergence is reported
    without choosing one history or exporting account credentials.
    """
    paths = {
        "local": _existing_file(local_opportunities),
        "accounts": _existing_file(local_accounts),
        "hosted": _existing_file(hosted_opportunities),
    }
    if len(set(paths.values())) != 3:
        raise ValueError("Three separate SQLite source files are required.")

    local = inspect_storage(paths["local"])
    hosted = inspect_storage(paths["hosted"])
    accounts = inspect_accounts(paths["accounts"])

    blockers = []
    if not local["migration_inventory_ready"]:
        blockers.append("local_opportunities_invalid")
    if not hosted["migration_inventory_ready"]:
        blockers.append("hosted_opportunities_invalid")
    if not accounts["ready"]:
        blockers.append("reviewer_accounts_invalid")

    for label, report in (("local", local), ("hosted", hosted)):
        states = report["notification_job_states"]
        if states.get("sending", 0) or states.get("uncertain", 0):
            blockers.append(f"{label}_ambiguous_delivery")

    comparisons = None
    if local["migration_inventory_ready"] and hosted["migration_inventory_ready"]:
        comparisons = compare_database_tables(
            paths["local"], paths["hosted"], OPPORTUNITY_TABLES
        )
        if not all(comparisons.values()):
            blockers.append("histories_diverged")

    inventories = {}
    if not blockers or blockers == ["histories_diverged"]:
        # Fingerprints include no raw rows, IDs, password hashes or tokens.
        for name, path, tables in (
            ("local", paths["local"], OPPORTUNITY_TABLES),
            ("hosted", paths["hosted"], OPPORTUNITY_TABLES),
            ("accounts", paths["accounts"], ACCOUNT_TABLES),
        ):
            with _readonly_connection(path) as conn:
                inventories[name] = {
                    table: _table_fingerprint(conn, table)
                    for table in tables
                }

    # A successful Step 4 inventory never grants permission to move real data.
    return {
        "inventory_complete": not any(b.endswith("_invalid") for b in blockers),
        "blockers": blockers,
        "opportunity_table_matches": comparisons,
        "tables": inventories,
        "target_table_order": [f"{schema}.{table}" for schema, table in LOAD_ORDER],
        "postgres_import_authorized": False,
        "cutover_authorized": False,
        "files_modified": False,
        "records_exported": False,
        "credentials_exported": False,
        "email_sent": False,
    }


def parameterized_insert(table, columns):
    """Build an INSERT template, never SQL-quote user-provided identifiers.

    Columns are validated against a trusted hardcoded allowlist at call time
    by the future importer. This function has no database side effects.
    """
    known = set(PRIMARY_KEYS)
    if table not in known or not columns:
        raise ValueError("Unknown migration table or empty columns.")

    # SQL identifiers come from SQLite schemas: validate strictly and
    # compare actual columns with the approved static name allowlist.
    allowed = {
        "opportunities": (
            "id source_id url title category classification_status verification "
            "free_status ph_eligibility deadline_status published_at first_seen_at last_seen_at"
        ).split(),
        "collection_runs": (
            "id source_id started_at finished_at status items_found error_type"
        ).split(),
        "notification_history": (
            "id opportunity_id channel notification_type sent_at"
        ).split(),
        "opportunity_reviews": (
            "id opportunity_id decision method reviewer_id evidence_url free_confirmed "
            "ph_confirmed open_confirmed reviewed_at"
        ).split(),
        "notification_jobs": (
            "id opportunity_id channel notification_type status attempt_count claim_token "
            "claimed_at created_at updated_at sent_at last_error_type"
        ).split(),
        "reviewer_accounts": (
            "account_id role password_hash active created_at"
        ).split(),
        "reviewer_account_audit": (
            "id actor_id target_id action old_value new_value changed_at"
        ).split(),
    }[table]
    if list(columns) != allowed:
        raise ValueError("Migration schema column mismatch.")

    schema = "phtech_private" if table in ACCOUNT_TABLES else "phtech"
    quoted = ", ".join(f'"{c}"' for c in allowed)
    placeholders = ", ".join(["%s"] * len(allowed))
    return f'INSERT INTO "{schema}"."{table}" ({quoted}) VALUES ({placeholders})'


def main():
    parser = argparse.ArgumentParser(
        description="Read-only, zero-export PostgreSQL migration plan"
    )
    parser.add_argument("--local-opportunities", required=True)
    parser.add_argument("--local-accounts", required=True)
    parser.add_argument("--hosted-opportunities", required=True)
    args = parser.parse_args()

    try:
        report = build_migration_plan(
            args.local_opportunities, args.local_accounts,
            args.hosted_opportunities,
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Migration planning failed: {type(error).__name__}")
        raise SystemExit(1) from None

    print(json.dumps(report, indent=2, sort_keys=True))
    print("Only read-only fingerprints were calculated; no import occurred.")
    if report["blockers"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
