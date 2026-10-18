# Phase 6 — Authenticated Reviewer Authorization

Status: Design and authentication foundation
Enforcement status: NOT YET INTEGRATED
Current SQLite schema: Version 3

## Purpose

Prevent unauthorized opportunity approvals, rejections,
and reviewer administration.

The existing reviewer_id text field is not authenticated.

## Roles

| Role | Permissions |
|---|---|
| administrator | Read, approve, reject, manage reviewer accounts |
| reviewer | Read, approve, reject |
| viewer | Read only |

Email delivery requires a separate authorization mechanism.

## Authentication Design

Password verification uses hashlib.scrypt with:

- Unique random salts
- Fixed work parameters
- Constant-time derived-key comparison
- No plaintext password storage

The module is standalone. It does not yet establish a trusted
identity or authenticate against the production review service.

## Trusted Identity Store Requirements

A future private authoritative datastore must provide:

- Unique, immutable account identifiers
- Unique login identifiers
- Salted password verifiers
- Administrative role assignment
- Active and suspended account states
- Credential rotation and account recovery
- Login rate limiting and audit records
- Protected database access

Role values must be loaded from trusted storage and must never
be accepted directly from untrusted request arguments.

## Review Service Integration Requirements

Before reviewer authorization can be considered enforced:

1. Replace arbitrary reviewer_id acceptance with a trusted
   authenticated principal.
2. Validate active account status and current permissions
   inside the authoritative review-writing operation.
3. Preserve the append-only opportunity_reviews audit history.
4. Associate each new review with the authenticated account ID.
5. Ensure a failed authorization causes no database changes.
6. Test privilege revocation, suspended accounts, and concurrent
   review decisions.
7. Avoid logging or persisting plaintext passwords.
8. Prevent other exposed write operations from bypassing reviews.

Historical reviews must remain intact. Do not retroactively
claim their reviewer labels were authenticated.

## Local CLI Security Requirements

The future command-line integration should:

- Request passwords using getpass rather than command arguments.
- Never print passwords or password hashes.
- Avoid storing reusable credentials in process environment
  variables unnecessarily.
- Require fresh authentication for sensitive review actions.
- Avoid unattended review approval from GitHub Actions.

## Session and Authorization Security

For any future web interface:

- Use short-lived server-managed authenticated sessions.
- Protect sessions against theft and replay.
- Check authorization on the server for every write.
- Enforce authorization against the current account role.
- Apply appropriate CSRF, rate limiting, and audit safeguards.
- Never expose privileged database credentials to browsers.

## PostgreSQL Migration Considerations

A future private PostgreSQL backend should define trusted reviewer
accounts and review audit relationships.

Migration must preserve all existing SQLite opportunity IDs,
review history, notification jobs, and foreign-key relationships.

Authentication must not depend on unverified reviewer_id fields
from older records.

## Threats and Limitations

The current ReviewerAccount dataclass can be constructed by Python
callers. It is not a tamper-proof security token.

The scrypt hashing helper is a foundation, not complete identity
management. Its password policy does not replace rate limiting,
breached-password checks, or credential recovery.

Anyone with direct write access to a local SQLite file may bypass
application-level checks. Database access must be protected as part
of the final architecture.

## Step 3 Boundary

This step does not:

- Modify the SQLite schema
- Create real reviewer accounts
- Store actual passwords
- Enable reviewer login in the CLI
- Require authentication in record_review()
- Enable automatic notification delivery
- Migrate data to PostgreSQL

The review-writing path remains legacy and unauthenticated until
an explicit, tested integration is performed.