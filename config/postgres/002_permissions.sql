-- Phase 10 Step 3: privilege design. Apply ONLY to a disposable Neon child
-- branch after 001_schema.sql. Do not create login roles or passwords.
-- Neon roles created using the Console/API have elevated neon_superuser
-- membership; least-privilege group roles must instead be created with SQL.
BEGIN;

-- Future applications get dedicated LOGIN roles later, after verification.
CREATE ROLE phtech_collector NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE phtech_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE phtech_reviewer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

-- Private account data is intentionally inaccessible to these roles.
GRANT CONNECT ON DATABASE phtech_staging
    TO phtech_collector, phtech_reader, phtech_reviewer;
GRANT USAGE ON SCHEMA phtech
    TO phtech_collector, phtech_reader, phtech_reviewer;

GRANT SELECT ON phtech.opportunities,
    phtech.collection_runs,
    phtech.notification_history,
    phtech.opportunity_reviews,
    phtech.notification_jobs
    TO phtech_reader;

-- Collector can add/update discovered opportunities and append collection
-- runs, but cannot alter reviews, account credentials, or delivery history.
GRANT SELECT, INSERT ON phtech.opportunities,
    phtech.collection_runs TO phtech_collector;
GRANT UPDATE (title, category, classification_status,
    verification, free_status, ph_eligibility,
    deadline_status, published_at, last_seen_at)
    ON phtech.opportunities TO phtech_collector;
GRANT UPDATE (finished_at, status, items_found, error_type)
    ON phtech.collection_runs TO phtech_collector;
GRANT USAGE, SELECT ON SEQUENCE
    phtech.opportunities_id_seq, phtech.collection_runs_id_seq
    TO phtech_collector;

-- Reviewer role has read access plus append-only reviews. The role itself
-- does NOT authenticate a human reviewer. Future application code must
-- authenticate and authorize users before issuing SQL.
GRANT SELECT ON phtech.opportunities,
    phtech.collection_runs,
    phtech.notification_history,
    phtech.opportunity_reviews,
    phtech.notification_jobs TO phtech_reviewer;
GRANT INSERT ON phtech.opportunity_reviews TO phtech_reviewer;
GRANT USAGE, SELECT ON SEQUENCE phtech.opportunity_reviews_id_seq
    TO phtech_reviewer;

-- Owner retains all migration rights. No runtime role receives CREATE,
-- DELETE, TRUNCATE, UPDATE on immutable histories, or access to credentials.
COMMIT;
