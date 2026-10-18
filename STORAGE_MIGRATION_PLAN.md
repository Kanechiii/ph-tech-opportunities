# Phase 6 — Storage Migration Plan

Status: Preparation only
Current authoritative database: SQLite schema version 3
Provisional future provider: Neon PostgreSQL

## Objectives

Establish one private, remotely accessible database as the
authoritative source for opportunities, reviews, collection history,
and notification state.

Retain the existing SQLite database and backups until a migration
has passed reconciliation and rollback testing.

## Current SQLite Tables

1. opportunities
2. collection_runs
3. notification_history
4. opportunity_reviews
5. notification_jobs

## Migration Rules

- Never import directly into production tables without validation.
- Never overwrite or delete the original SQLite file.
- Preserve all existing primary keys and foreign-key relationships.
- Preserve the order and content of append-only review history.
- Preserve notification statuses and attempt counts.
- Never requeue sent, sending, or uncertain notifications during import.
- Prevent concurrent writes during the final cutover.
- Use an explicit one-writer cutover strategy.
- Keep a validated pre-migration backup.
- Never place PostgreSQL credentials in Git.

## PostgreSQL Schema Design Requirements

- Replace SQLite-specific SQL with PostgreSQL-compatible SQL.
- Preserve unique constraints for opportunities and notifications.
- Use TIMESTAMPTZ for canonical event timestamps where appropriate.
- Translate review-history triggers to PostgreSQL safely.
- Keep notification claiming atomic.
- Enforce least-privilege database access.
- Reconcile sequences after preserving imported integer IDs.
- Test all existing application behavior against a disposable database.

## Reconciliation

Before declaring a hosted database authoritative, compare:

- Opportunity record count and unique source/URL keys
- Collection-run count
- Notification-history count
- Manual-review count and per-opportunity ordering
- Notification-job count
- Counts for pending, sending, sent, failed, and uncertain states
- Referential integrity
- Selected full-record checksums using canonical serialization

Matching counts alone are insufficient.

## Cutover and Rollback

1. Create an independently validated SQLite backup.
2. Stop scheduled collection and all database writers temporarily.
3. Export a consistent snapshot.
4. Import into a separate PostgreSQL staging schema.
5. Run reconciliation and integration tests.
6. Configure a single authoritative database connection.
7. Verify controlled reads and writes before enabling normal collection.
8. Keep reviewed email delivery disabled.
9. Retain SQLite backups for rollback.

Never revert to an older database while email delivery is active.
Doing so could lose sent-state information and cause duplicates.

## Credentials

- Use a separate, least-privileged database role for the application.
- Keep connection strings outside Git.
- Use TLS for database connections.
- Store GitHub Actions credentials only in protected secrets.
- Never print full connection URLs or passwords in logs.
- Rotate credentials if they are accidentally exposed.

## Free-Tier Limitations

Provider limits, inactivity policies, backup guarantees,
and availability can change.

Maintain independent backups even after migration.

## Phase 6 Step 2 Boundary

This step only evaluates the provider and checks SQLite readiness.

No PostgreSQL tables have been created by this project.
No data has been imported.
No database cutover has occurred.
SQLite remains authoritative.
Scheduled reviewed-email delivery remains disabled.