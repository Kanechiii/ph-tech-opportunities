"""Offline contract validation for the isolated, synthetic PostgreSQL rehearsal.

Inspects repository-owned SQL text only. No SQL execution, Neon connections,
SQLite access, credentials, emails, imports, or production cutover.
"""

import argparse
import json
import re
from pathlib import Path

from src.database.postgres_migration_plan import LOAD_ORDER

SQL_ROOT = Path(__file__).resolve().parents[2] / "config" / "postgres"
EXPECTED_COUNTS = {
    "opportunities": 2,
    "collection_runs": 1,
    "notification_history": 1,
    "opportunity_reviews": 2,
    "notification_jobs": 2,
    "reviewer_accounts": 1,
    "reviewer_account_audit": 1,
}
# These are fixed synthetic identifiers, never identifiers taken from a source DB.
EXPECTED_IDS = {
    "opportunities": (910001, 910003),
    "collection_runs": (920002,),
    "notification_history": (930001,),
    "opportunity_reviews": (940001, 940003),
    "notification_jobs": (950001, 950003),
    "reviewer_account_audit": (960004,),
}
EXPECTED_STATUSES = frozenset({"sent", "uncertain"})
APPROVED_TABLES = tuple(f"{schema}.{table}" for schema, table in LOAD_ORDER)


def _statements(sql):
    """Split repository-owned SQL at semicolons outside quotes and comments.

    Reject dollar-quoted blocks, nested comment ambiguity and backslash
    escapes: this reader intentionally accepts only a constrained subset.
    """
    if "$$" in sql or "/*" in sql or "\\" in sql:
        raise ValueError("Unsupported SQL syntax in rehearsal fixtures.")
    result, current, quoted = [], [], False
    for line in sql.splitlines():
        if line.lstrip().startswith("--"):
            continue
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "'":
                if quoted and i + 1 < len(line) and line[i + 1] == "'":
                    current.extend(("'", "'"))
                    i += 2
                    continue
                quoted = not quoted
            if ch == ";" and not quoted:
                piece = "".join(current).strip()
                if piece:
                    result.append(piece)
                current = []
            else:
                current.append(ch)
            i += 1
        current.append("\n")
    if quoted or "".join(current).strip():
        raise ValueError("Incomplete or unsupported SQL statement.")
    return result


def _insert_values(statement):
    """Extract tuple entries in simple INSERT ... VALUES (...) statements."""
    match = re.fullmatch(
        r"INSERT\s+INTO\s+(phtech(?:_private)?\.[a-z_]+)\s*"
        r"\(([^)]*)\)\s*VALUES\s*(.+)",
        statement.strip(), flags=re.I | re.S,
    )
    if not match:
        raise ValueError("Unsupported synthetic INSERT shape.")
    table, columns, values = match.groups()
    cols = [c.strip().lower() for c in columns.split(",")]
    if "id" not in cols and "account_id" not in cols:
        raise ValueError("No fixed primary key in rehearsal INSERT.")

    tuples, depth, quoted, buf = [], 0, False, []
    i = 0
    while i < len(values):
        ch = values[i]
        if ch == "'":
            if quoted and i + 1 < len(values) and values[i + 1] == "'":
                buf.extend(("'", "'"))
                i += 2
                continue
            quoted = not quoted
        if not quoted and ch == "(":
            if depth != 0:
                raise ValueError("Nested SQL expression unsupported.")
            depth = 1
            buf = []
        elif not quoted and ch == ")":
            if depth != 1:
                raise ValueError("Unexpected closing parenthesis.")
            tuples.append("".join(buf).strip())
            depth = 0
            buf = []
        elif depth:
            buf.append(ch)
        elif ch not in ", \r\n\t":
            raise ValueError("Unexpected characters outside SQL VALUES.")
        i += 1
    if depth or quoted or not tuples:
        raise ValueError("Invalid synthetic tuples.")
    return table.lower(), cols, tuples


def assess_synthetic_rehearsal(script):
    """Validate a fixed synthetic fixture before any isolated test-branch use."""
    path = Path(script)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Existing regular SQL fixture required.")

    sql = path.read_text(encoding="utf-8")
    if not sql.lstrip().startswith("--") or "SYNTHETIC DATA ONLY" not in sql:
        raise ValueError("Missing synthetic-only safety header.")
    if "seven empty tables" not in sql:
        raise ValueError("Missing empty-target contract.")

    # The Phase 10 fixture includes one DO $$ precondition. Inspect it as
    # a separate trusted block; the constrained parser handles only INSERTs.
    matches = list(re.finditer(r"INSERT\s+INTO\s+.*?;", sql, flags=re.I | re.S))
    statements = [m.group()[:-1] for m in matches]
    seen = {}
    for statement in statements:
        table, columns, rows = _insert_values(statement)
        if table not in APPROVED_TABLES or table in seen:
            raise ValueError("Unexpected or duplicate synthetic table.")
        expected_name = table.rsplit(".", 1)[1]
        id_col = "account_id" if expected_name == "reviewer_accounts" else "id"
        if columns[0] != id_col:
            raise ValueError("Synthetic primary key must be first column.")
        parsed_ids = []
        for row in rows:
            match = re.match(r"\s*(\d+)\s*,", row)
            if expected_name == "reviewer_accounts":
                if not re.match(r"\s*'synthetic_admin'\s*,", row):
                    raise ValueError("Synthetic account identifier changed.")
            elif match is None:
                raise ValueError("Synthetic primary key must be an integer literal.")
            else:
                parsed_ids.append(int(match.group(1)))
        if expected_name in EXPECTED_IDS and tuple(parsed_ids) != EXPECTED_IDS[expected_name]:
            raise ValueError("Historical synthetic IDs changed.")
        seen[table] = (columns, rows)

    if set(seen) != set(APPROVED_TABLES):
        raise ValueError("Expected seven approved synthetic tables.")
    counts = {
        table.rsplit(".", 1)[1]: len(data[1])
        for table, data in seen.items()
    }
    if counts != EXPECTED_COUNTS:
        raise ValueError("Synthetic rehearsal row counts changed.")
    jobs_columns, jobs = seen["phtech.notification_jobs"]
    status_index = jobs_columns.index("status")
    statuses = set()
    for row in jobs:
        # No commas in this repository-owned synthetic job payload.
        parts = [v.strip() for v in row.split(",")]
        if len(parts) != len(jobs_columns):
            raise ValueError("Malformed synthetic notification job.")
        statuses.add(parts[status_index].strip("'"))
    if statuses != EXPECTED_STATUSES:
        raise ValueError("Sent and uncertain synthetic states must be preserved.")

    # The existing precondition must abort on nonempty target tables.
    if "row_total <> 0" not in sql or "RAISE EXCEPTION" not in sql:
        raise ValueError("Nonempty target must be rejected.")
    return {
        "phase": 12,
        "step": 3,
        "synthetic_contract_passed": True,
        "table_counts": counts,
        "notification_states_checked": sorted(statuses),
        "source_records_read": False,
        "postgres_connected": False,
        "migration_performed": False,
        "cutover_authorized": False,
        "email_sent": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Offline synthetic SQL rehearsal gate")
    parser.add_argument("--fixture", default=str(SQL_ROOT / "003_synthetic_rehearsal.sql"))
    args = parser.parse_args()
    try:
        result = assess_synthetic_rehearsal(args.fixture)
    except (OSError, ValueError) as error:
        print("Synthetic rehearsal validation failed: " + type(error).__name__)
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
