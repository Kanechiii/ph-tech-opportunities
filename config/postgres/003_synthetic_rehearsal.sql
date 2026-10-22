-- PH Tech Opportunities / Phase 10 Step 5
-- SYNTHETIC DATA ONLY. Run on a NEW disposable Neon child branch, never
-- the project's default branch. No existing source SQLite files are used.
-- Deliberately preserve legacy IDs, textual timestamps and ambiguous states.
-- The precondition requires all seven application tables to be empty.
BEGIN;

DO $$
DECLARE row_total BIGINT;
BEGIN
  SELECT
    (SELECT count(*) FROM phtech.opportunities)
  + (SELECT count(*) FROM phtech.collection_runs)
  + (SELECT count(*) FROM phtech.notification_history)
  + (SELECT count(*) FROM phtech.opportunity_reviews)
  + (SELECT count(*) FROM phtech.notification_jobs)
  + (SELECT count(*) FROM phtech_private.reviewer_accounts)
  + (SELECT count(*) FROM phtech_private.reviewer_account_audit)
  INTO row_total;
  IF row_total <> 0 THEN
    RAISE EXCEPTION 'Synthetic rehearsal requires seven empty tables';
  END IF;
END $$;

-- Deliberately use fixed, non-sequential IDs to test historical ID retention.
INSERT INTO phtech.opportunities
(id,source_id,url,title,category,classification_status,verification,
 free_status,ph_eligibility,deadline_status,published_at,
 first_seen_at,last_seen_at)
VALUES
(910001,'synthetic_source','https://example.invalid/phase10-a',
 'Synthetic workshop','tech_event','potential_match','not_verified',
 'unknown','unknown','unknown','2026-01-01T10:00:00+00:00',
 '2026-01-01 10:01:00','2026-01-01 10:02:00'),
(910003,'synthetic_source','https://example.invalid/phase10-b',
 'Synthetic hackathon','hackathon','potential_match','not_verified',
 'unknown','unknown','unknown',NULL,
 '2026-01-02 10:01:00','2026-01-02 10:02:00');

INSERT INTO phtech.collection_runs
(id,source_id,started_at,finished_at,status,items_found,error_type)
VALUES (920002,'synthetic_source','2026-01-01 10:00:00',
 '2026-01-01 10:03:00','success',2,NULL);

INSERT INTO phtech.notification_history
(id,opportunity_id,channel,notification_type,sent_at)
VALUES (930001,910001,'email','new_opportunity','2026-01-03 12:00:00');

INSERT INTO phtech.opportunity_reviews
(id,opportunity_id,decision,method,reviewer_id,evidence_url,
 free_confirmed,ph_confirmed,open_confirmed,reviewed_at)
VALUES
(940001,910001,'approved','manual','synthetic_admin',
 'https://example.invalid/synthetic-evidence',1,1,1,'2026-01-03 11:00:00'),
(940003,910003,'rejected','manual','synthetic_admin',
 'https://example.invalid/synthetic-evidence-b',0,0,0,
 '2026-01-03 11:05:00');

INSERT INTO phtech.notification_jobs
(id,opportunity_id,channel,notification_type,status,attempt_count,
 claim_token,claimed_at,created_at,updated_at,sent_at,last_error_type)
VALUES
(950001,910001,'email','new_opportunity','sent',1,NULL,
 '2026-01-03 11:30:00','2026-01-03 11:20:00',
 '2026-01-03 12:00:00','2026-01-03 12:00:00',NULL),
(950003,910003,'email','new_opportunity','uncertain',1,NULL,
 '2026-01-03 11:45:00','2026-01-03 11:25:00',
 '2026-01-03 12:10:00',NULL,'ambiguous_delivery');

-- This is intentionally an INVALID verifier, not a usable credential.
INSERT INTO phtech_private.reviewer_accounts
(account_id,role,password_hash,active,created_at)
VALUES ('synthetic_admin','administrator',
 'SYNTHETIC_INVALID_VERIFIER_DO_NOT_AUTHENTICATE',1,
 '2026-01-01 00:00:00');

INSERT INTO phtech_private.reviewer_account_audit
(id,actor_id,target_id,action,old_value,new_value,changed_at)
VALUES (960004,'synthetic_admin','synthetic_admin','role_changed',
 'reviewer','administrator','2026-01-02 00:00:00');

-- The explicit historical ID may be larger than an IDENTITY sequence.
-- Reset only on the disposable test branch, after INSERTs commit.
-- This remains no-op on other databases because the script must not run there.
SELECT setval(pg_get_serial_sequence('phtech.opportunities','id'),
  (SELECT max(id) FROM phtech.opportunities),true);
SELECT setval(pg_get_serial_sequence('phtech.collection_runs','id'),
  (SELECT max(id) FROM phtech.collection_runs),true);
SELECT setval(pg_get_serial_sequence('phtech.notification_history','id'),
  (SELECT max(id) FROM phtech.notification_history),true);
SELECT setval(pg_get_serial_sequence('phtech.opportunity_reviews','id'),
  (SELECT max(id) FROM phtech.opportunity_reviews),true);
SELECT setval(pg_get_serial_sequence('phtech.notification_jobs','id'),
  (SELECT max(id) FROM phtech.notification_jobs),true);
SELECT setval(pg_get_serial_sequence('phtech_private.reviewer_account_audit','id'),
  (SELECT max(id) FROM phtech_private.reviewer_account_audit),true);

COMMIT;
