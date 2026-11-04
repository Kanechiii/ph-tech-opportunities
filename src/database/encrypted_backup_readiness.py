"""Offline encrypted backup filesystem readiness checks.

Intended for preflight and acceptance testing only. No SQLite, backup files,
Neon, reviewer accounts or email systems are read or modified. In particular,
this is NOT a substitute for operating-system ACL review.
"""

import os
import stat
from pathlib import Path

from src.database.phase14_format_contract import WINDOWS_REQUIREMENTS


def inspect_private_backup_destination(destination):
    """Fail closed on unsafe directory structure; never create directories."""
    target = Path(destination).absolute()
    checks = {
        "parent_exists": target.parent.is_dir(),
        "destination_absent": not target.exists() and not target.is_symlink(),
        "all_path_ancestors_no_symlinks": not any(
            item.is_symlink() for item in (target, *target.parents)
        ),
        "parent_regular_directory": False,
        "parent_not_world_writable": False,
        "same_filesystem_staging_feasible": False,
    }
    if checks["parent_exists"] and checks["all_path_ancestors_no_symlinks"]:
        info = target.parent.stat()
        checks["parent_regular_directory"] = stat.S_ISDIR(info.st_mode)
        # POSIX permission bits are not meaningful NTFS ACL evidence.
        checks["parent_not_world_writable"] = (
            os.name != "posix" or not bool(info.st_mode & stat.S_IWOTH)
        )
        # Staging in the same parent only establishes intended topology;
        # it does not prove atomic publication or durability.
        checks["same_filesystem_staging_feasible"] = True
    return {
        "checks": checks,
        "preflight_passed": all(checks.values()),
        "windows_required_evidence": sorted(WINDOWS_REQUIREMENTS),
        "windows_acl_approved": False,
        "atomic_noreplace_approved": False,
        "production_encryption_authorized": False,
        "operational_data_accessed": False,
    }


def assess_encrypted_backup_release(checks):
    """Check supplied acceptance attestations without granting authorization."""
    required = frozenset({
        "sqlite_consistent_snapshot",
        "encrypted_payloads_authenticated",
        "private_windows_acl_verified",
        "atomic_noreplace_tested",
        "crash_recovery_tested",
        "isolated_sqlite_recovery_verified",
        "history_parity_verified",
        "secret_management_reviewed",
    })
    if type(checks) is not dict or set(checks) != required:
        raise ValueError("Incomplete encrypted-backup readiness evidence.")
    if any(type(value) is not bool for value in checks.values()):
        raise ValueError("Readiness evidence must be explicit Boolean values.")
    return {
        "evidence_claims_complete": all(checks.values()),
        "missing_evidence": sorted(name for name, value in checks.items() if not value),
        "real_data_backup_enabled": False,
        "recovery_cutover_enabled": False,
        "production_release_approved": False,
    }
