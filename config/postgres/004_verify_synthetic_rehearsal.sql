-- Read-only verification. Run ONLY on the isolated synthetic test branch.
-- Any failed assertion raises an error; do not alter the source to force success.
DO $$
BEGIN
 IF (SELECT COUNT(*) FROM phtech.opportunities) <> 2
 OR (SELECT COUNT(*) FROM phtech.collection_runs) <> 1
 OR (SELECT COUNT(*) FROM phtech.notification_history) <> 1
 OR (SELECT COUNT(*) FROM phtech.opportunity_reviews) <> 2
 OR (SELECT COUNT(*) FROM phtech.notification_jobs) <> 2
 OR (SELECT COUNT(*) FROM phtech_private.reviewer_accounts) <> 1
 OR (SELECT COUNT(*) FROM phtech_private.reviewer_account_audit) <> 1
 THEN RAISE EXCEPTION 'Unexpected synthetic row counts'; END IF;

 IF NOT EXISTS (
   SELECT 1 FROM phtech.notification_jobs
   WHERE id=950001 AND status='sent' AND sent_at='2026-01-03 12:00:00'
 ) OR NOT EXISTS (
   SELECT 1 FROM phtech.notification_jobs
   WHERE id=950003 AND status='uncertain'
   AND last_error_type='ambiguous_delivery'
 ) THEN RAISE EXCEPTION 'Original notification outcomes not preserved'; END IF;

 IF NOT EXISTS (
   SELECT 1 FROM phtech.opportunities
   WHERE id=910001 AND source_id='synthetic_source'
   AND first_seen_at='2026-01-01 10:01:00'
 ) OR NOT EXISTS (
   SELECT 1 FROM phtech.opportunities
   WHERE id=910003 AND last_seen_at='2026-01-02 10:02:00'
 ) THEN RAISE EXCEPTION 'Historical identifiers or timestamps changed'; END IF;

 IF has_schema_privilege('phtech_collector','phtech_private','USAGE')
 OR has_schema_privilege('phtech_reviewer','phtech_private','USAGE')
 OR has_table_privilege('phtech_collector',
      'phtech.opportunity_reviews','INSERT')
 OR NOT has_table_privilege('phtech_reviewer',
      'phtech.opportunity_reviews','INSERT')
 THEN RAISE EXCEPTION 'Least-privilege grants unexpected'; END IF;

 IF NOT EXISTS (
   SELECT 1 FROM pg_roles WHERE rolname='phtech_collector'
   AND rolcanlogin=false
 ) OR NOT EXISTS (
   SELECT 1 FROM pg_roles WHERE rolname='phtech_reviewer'
   AND rolcanlogin=false
 ) THEN RAISE EXCEPTION 'Expected NOLOGIN roles absent'; END IF;
END $$;

SELECT 'synthetic_rehearsal_passed' AS check_result,
       (SELECT count(*) FROM phtech.opportunities) AS opportunities,
       (SELECT count(*) FROM phtech.notification_jobs WHERE status='sent') AS sent,
       (SELECT count(*) FROM phtech.notification_jobs WHERE status='uncertain') AS uncertain;
