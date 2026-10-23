"""Phase 10 Step 6: offline PostgreSQL integration and cutover guard.

Does not establish a network connection, read secrets from the environment,
alter SQLite or PostgreSQL, or authorize a production cutover.
"""

from urllib.parse import parse_qs, urlsplit


PRIVILEGED_ROLE_SUFFIXES = ("_owner",)
TEST_DATABASE = "phtech_staging"
PROHIBITED_JOB_STATES = ("sending", "uncertain")


def inspect_connection_target(url, *, operation="read"):
    """Validate target metadata without returning any URL or credentials.

    This is a config preflight, NOT TLS verification or authorization.
    It is intentionally limited to staging read-only inspections.
    """
    if type(url) is not str or not url:
        raise ValueError("A PostgreSQL connection URL is required.")
    if operation != "read":
        raise ValueError("Only read-only inspection is currently supported.")

    try:
        parsed = urlsplit(url)
        port = parsed.port
        hostname = parsed.hostname
        username = parsed.username
    except ValueError as error:
        raise ValueError("Malformed PostgreSQL target.") from error

    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError("PostgreSQL URL required.")
    if not hostname or not username or port not in (None, 5432):
        raise ValueError("Invalid PostgreSQL connection metadata.")

    # The staging target must be an actual Neon endpoint, not a host chosen
    # from a user-controlled suffix (e.g. attacker.neon.tech.example.com).
    if not hostname.endswith(".neon.tech"):
        raise ValueError("Only the Neon staging endpoint is allowed.")
    if hostname.endswith("-pooler.neon.tech") or "-pooler." in hostname:
        raise ValueError("Direct endpoint required for staging checks.")

    database = parsed.path.lstrip("/")
    if database != TEST_DATABASE or "/" in database:
        raise ValueError("Unexpected target database.")
    if username.endswith(PRIVILEGED_ROLE_SUFFIXES) or username in (
        "postgres", "neon_superuser", "phtech_staging_owner"
    ):
        raise ValueError("Owner/admin credentials are prohibited.")

    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get("sslmode") != ["verify-full"]:
        raise ValueError("TLS certificate hostname verification required.")
    if query.get("channel_binding") not in (None, ["require"]):
        raise ValueError("Channel binding must not be disabled.")

    return {
        "configuration_valid": True,
        "database": TEST_DATABASE,
        "read_only_requested": True,
        "owner_credentials_rejected": True,
        "tls_verified_by_network": False,
        "connected": False,
        "credentials_exported": False,
    }


def assess_storage_cutover(*, local_report, destination_reviewed=False):
    """Fail closed until a future authorized release has reconciled sources.

    This never changes runtime storage, job status, or user permissions.
    """
    if not isinstance(local_report, dict):
        raise ValueError("Explicit migration inventory report required.")

    blockers = []
    for issue in local_report.get("blockers") or []:
        blockers.append("source_" + str(issue)[:80])

    if local_report.get("inventory_complete") is not True:
        blockers.append("source_inventory_incomplete")
    if local_report.get("opportunity_table_matches") is None or not all(
        local_report["opportunity_table_matches"].values()
    ):
        blockers.append("unreconciled_opportunity_histories")
    if not destination_reviewed:
        blockers.append("destination_reconciliation_not_reviewed")

    # This method intentionally NEVER grants cutover: explicit future
    # human authorization and deployment-specific controls are missing.
    blockers.append("cutover_requires_separate_authorization")

    return {
        "blockers": sorted(set(blockers)),
        "cutover_authorized": False,
        "postgres_runtime_enabled": False,
        "sqlite_backend_remains_authoritative": True,
        "reviewed_email_automation_enabled": False,
        "records_exported": False,
        "records_modified": False,
        "email_sent": False,
    }
