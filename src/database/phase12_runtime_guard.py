"""Phase 12 Step 4: offline fail-closed application backend configuration gate.

Pure validation only; no environment access, credential inspection, sockets,
database connections, state mutations, or email. SQLite remains authoritative.
Future PostgreSQL deployment requires a separately reviewed runtime adapter,
history reconciliation, credential policy, and explicit cutover authorization.
"""

from collections.abc import Mapping

from src.database.postgres_integration_gate import inspect_connection_target

_ALLOWED_KEYS = frozenset({
    "storage_backend",
    "postgres_inspection_url",
    "postgres_runtime_enabled",
    "postgres_import_enabled",
    "production_cutover_enabled",
    "reviewed_email_automation_enabled",
})
_FORBIDDEN_SWITCHES = (
    "postgres_runtime_enabled",
    "postgres_import_enabled",
    "production_cutover_enabled",
    "reviewed_email_automation_enabled",
)


def assess_application_backend(settings):
    """Require explicit offline-only SQLite runtime settings.

    Optional staging URL metadata can be examined only when all runtime
    activation switches remain strictly False. Never return a URL or secret.
    """
    if not isinstance(settings, Mapping) or set(settings) - _ALLOWED_KEYS:
        raise ValueError("Unsupported storage configuration keys.")

    for key in _FORBIDDEN_SWITCHES:
        if settings.get(key, False) is not False:
            raise PermissionError("Unsupported application activation requested.")

    if settings.get("storage_backend", "sqlite") != "sqlite":
        raise PermissionError("PostgreSQL application runtime is not authorized.")

    inspection_requested = "postgres_inspection_url" in settings
    if inspection_requested:
        info = inspect_connection_target(
            settings["postgres_inspection_url"], operation="read"
        )
        if info["connected"] or not info["read_only_requested"]:
            raise ValueError("PostgreSQL inspection must be offline and read-only.")

    return {
        "configuration_accepted": True,
        "runtime_backend": "sqlite",
        "staging_metadata_inspected_offline": inspection_requested,
        "postgres_runtime_enabled": False,
        "postgres_import_enabled": False,
        "production_cutover_authorized": False,
        "reviewed_email_automation_enabled": False,
        "network_connected": False,
        "database_modified": False,
        "secrets_exported": False,
        "email_sent": False,
    }
