"""Transactional notification queue. No SMTP operations."""

from datetime import datetime, timezone
from uuid import uuid4

from src.database.schema import DATABASE_PATH, connect_database
from src.notification_policy import assess_notification_policy


def _eligible(connection, opportunity_id):
    """Check the latest recorded review and current opportunity."""

    opportunity = connection.execute(
        "SELECT * FROM opportunities WHERE id = ?",
        (opportunity_id,),
    ).fetchone()

    if opportunity is None:
        return False

    review = connection.execute(
        """
        SELECT decision, method, reviewer_id,
               evidence_url, reviewed_at
        FROM opportunity_reviews
        WHERE opportunity_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (opportunity_id,),
    ).fetchone()

    result = assess_notification_policy(
        dict(opportunity),
        dict(review) if review else None,
    )
    return result["policy_passed"]


def enqueue_notification(
    opportunity_id,
    database_path=DATABASE_PATH,
):
    """Queue one eligible opportunity, without sending email."""

    if type(opportunity_id) is not int or opportunity_id < 1:
        raise ValueError("Invalid opportunity ID.")

    connection = connect_database(database_path)

    try:
        connection.execute("BEGIN IMMEDIATE")

        if not _eligible(connection, opportunity_id):
            raise ValueError("Opportunity is not review-eligible.")

        cursor = connection.execute(
            """
            INSERT INTO notification_jobs (opportunity_id)
            VALUES (?)
            ON CONFLICT(
                opportunity_id, channel, notification_type
            ) DO NOTHING
            """,
            (opportunity_id,),
        )

        row = connection.execute(
            """
            SELECT * FROM notification_jobs
            WHERE opportunity_id = ?
              AND channel = 'email'
              AND notification_type = 'new_opportunity'
            """,
            (opportunity_id,),
        ).fetchone()

        connection.commit()

        return {
            "id": row["id"],
            "created": cursor.rowcount == 1,
            "status": row["status"],
        }

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_job(job_id, database_path=DATABASE_PATH):
    """Retrieve a queue record by ID."""

    connection = connect_database(database_path)
    try:
        row = connection.execute(
            "SELECT * FROM notification_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def list_jobs(database_path=DATABASE_PATH, limit=20):
    """Inspect recent queue records without modifying them."""

    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid queue limit.")

    connection = connect_database(database_path)
    try:
        rows = connection.execute(
            """
            SELECT * FROM notification_jobs
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def claim_notification(job_id, database_path=DATABASE_PATH):
    """Atomically reserve a pending job.

    This only reserves a job. It never contacts SMTP.
    """

    token = uuid4().hex
    connection = connect_database(database_path)

    try:
        connection.execute("BEGIN IMMEDIATE")

        job = connection.execute(
            "SELECT * FROM notification_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

        if job is None or job["status"] != "pending":
            connection.rollback()
            return None

        if not _eligible(connection, job["opportunity_id"]):
            connection.rollback()
            return None

        cursor = connection.execute(
            """
            UPDATE notification_jobs
            SET status = 'sending',
                claim_token = ?,
                claimed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                attempt_count = attempt_count + 1
            WHERE id = ? AND status = 'pending'
            """,
            (token, job_id),
        )

        connection.commit()

        return token if cursor.rowcount == 1 else None

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def finish_attempt(
    job_id,
    claim_token,
    outcome,
    database_path=DATABASE_PATH,
):
    """Record the result of a claimed delivery attempt.

    'failed' is only for confirmed pre-submission failures.
    'uncertain' means delivery might have occurred.
    """

    if outcome not in ("sent", "failed", "uncertain"):
        raise ValueError("Invalid delivery outcome.")

    if not isinstance(claim_token, str) or not claim_token:
        raise ValueError("Claim token is required.")

    connection = connect_database(database_path)

    try:
        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.execute(
            """
            UPDATE notification_jobs
            SET status = ?,
                claim_token = NULL,
                updated_at = CURRENT_TIMESTAMP,
                sent_at = CASE
                    WHEN ? = 'sent' THEN CURRENT_TIMESTAMP
                    ELSE sent_at
                END,
                last_error_type = CASE
                    WHEN ? = 'failed' THEN 'pre_submission_failure'
                    WHEN ? = 'uncertain' THEN 'ambiguous_delivery'
                    ELSE NULL
                END
            WHERE id = ?
              AND status = 'sending'
              AND claim_token = ?
            """,
            (outcome, outcome, outcome, outcome,
             job_id, claim_token),
        )

        connection.commit()
        return cursor.rowcount == 1

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def retry_failed(job_id, database_path=DATABASE_PATH):
    """Explicitly requeue only a definitive failed attempt."""

    connection = connect_database(database_path)

    try:
        connection.execute("BEGIN IMMEDIATE")

        job = connection.execute(
            "SELECT * FROM notification_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

        if (
            job is None
            or job["status"] != "failed"
            or not _eligible(connection, job["opportunity_id"])
        ):
            connection.rollback()
            return False

        cursor = connection.execute(
            """
            UPDATE notification_jobs
            SET status = 'pending',
                claim_token = NULL,
                claimed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'failed'
            """,
            (job_id,),
        )

        connection.commit()
        return cursor.rowcount == 1

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def quarantine_stale_claims(
    database_path=DATABASE_PATH,
    minutes=30,
):
    """Mark abandoned sending attempts uncertain, never retry."""

    if type(minutes) is not int or minutes < 1:
        raise ValueError("Minutes must be a positive integer.")

    connection = connect_database(database_path)

    try:
        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.execute(
            """
            UPDATE notification_jobs
            SET status = 'uncertain',
                claim_token = NULL,
                updated_at = CURRENT_TIMESTAMP,
                last_error_type = 'abandoned_attempt'
            WHERE status = 'sending'
              AND claimed_at <= datetime('now', ?)
            """,
            (f"-{minutes} minutes",),
        )

        connection.commit()
        return cursor.rowcount

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main():
    """Read-only queue preview."""

    print("PH TECH OPPORTUNITIES - NOTIFICATION QUEUE")
    print("Mode: Read-only preview; SMTP delivery disabled")

    for job in list_jobs():
        print(
            f"Job {job['id']}: opportunity "
            f"{job['opportunity_id']} - {job['status']}"
        )


if __name__ == "__main__":
    main()