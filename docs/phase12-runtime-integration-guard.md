# Phase 12 Step 4 — PostgreSQL application integration safeguards

**Status:** Offline configuration validation only. The application still uses SQLite, and there is no PostgreSQL runtime adapter or production cutover.

- `src/database/phase12_runtime_guard.py` accepts only an explicitly SQLite backend. Attempts to enable PostgreSQL runtime/import, production cutover, or unattended reviewed-opportunity email fail closed.
- Optional staging connection metadata is validated using the existing offline Neon target checks, without establishing a connection or exposing connection strings.
- This is a **future integration contract**, not a runtime switch: existing application paths do not invoke it automatically. No deployment or environment configuration is changed by this PR.
- Full production integration still requires an independently reviewed PostgreSQL adapter, authenticated credentials/least-privilege enforcement, local-versus-hosted immutable history reconciliation, SMTP state-preserving migration, verified backups/restore, and rollback testing.
- Never configure PostgreSQL access against the staging project's default branch as though it were production. Any real-data migration or cutover requires a separate explicit authorization.

Acceptance: full offline Python tests and dependency-security CI pass; maintain manual-only reviewed-email delivery and all existing SQLite databases, backups, reviewer accounts and audit histories unchanged.
