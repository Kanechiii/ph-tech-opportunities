# PH Tech Opportunities Automation

A free, open-source Python project that collects and classifies public technology announcements for people in the Philippines. It focuses on **free certification exam vouchers, technology events, and hackathons**.

**Status:** Phases 1–6 complete; Phase 7 security hardening in progress. **Development system, not production-ready.** Scheduled collection is enabled; reviewed-opportunity email delivery remains manual-only.

## Features

- Approved RSS/Atom feeds, configured in `config/sources.yaml` (currently GitHub Blog and Python Insider).
- Keyword-based candidate classification; **not** independent verification of cost, availability, or Philippine eligibility.
- SQLite persistence at `data/opportunities.sqlite3`, with collection history, append-only review records, and notification queue.
- Advisory quality scoring and possible cross-source duplicate detection; **no automatic merging**.
- Deduplicated notification jobs: `pending`, `sending`, `sent`, `failed`, `uncertain`.
- Consistent atomic SQLite snapshots and validated restoration from GitHub Actions artifacts.
- Local, explicitly confirmed Gmail SMTP sending for reviewed opportunities; ambiguous submissions are **not** automatically retried.
- Local reviewer accounts with password-based authorization enforced for approval and rejection through `record_review()`.
- Read-only storage-readiness and database-health checks.

## Setup (Windows / VS Code)

From the existing project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit your local `.env` only if you intend to run a manual Gmail test. Never commit credentials. Gmail SMTP uses STARTTLS on port 587. For normal previews and tests, no Gmail credentials are required.

## Common commands

| Task | Command |
|---|---|
| Run all tests | `python -m pytest -v` |
| Preview sample email (fictional examples) | `python -m src.main` |
| Preview public RSS announcements | `python -m src.collectors.source_registry` |
| Collect and store announcements locally | `python -m src.database.collection_service` |
| Show stored opportunities | `python -m src.database.storage` |
| Inspect review history | `python -m src.database.review_service history 1` |
| Inspect notification jobs | `python -m src.database.notification_queue` |
| Preview one pending, reviewed job | `python -m src.notification_delivery preview 1` |
| Assess candidate quality (read only) | `python -m src.collectors.opportunity_quality` |
| Check storage migration readiness (read only) | `python -m src.database.storage_readiness` |
| Check both databases before future migration | `python -m src.database.migration_preflight` |
| Audit database health (read only) | `python -m src.database.health_audit` |
| Validate local SQLite | `python -m src.database.snapshot validate` |
| Create validated SQLite backup | `python -m src.database.snapshot backup` |

Replace example opportunity or job IDs with actual IDs. The quality analyzer scores hints, not verified opportunities. Do **not** approve an opportunity solely to make a demo work.

### Optional manual delivery

Only for a genuinely checked and approved opportunity already in a **pending** notification job:

```powershell
$env:ENABLE_REVIEWED_EMAIL_DELIVERY = "YES"
python -m src.notification_delivery send JOB_ID
Remove-Item Env:\ENABLE_REVIEWED_EMAIL_DELIVERY
```

The command requires an interactive local terminal and a further `SEND JOB_ID` confirmation. **It is not authenticated reviewer authorization.** The older `python -m src.main --send` path separately sends *fictional test examples* and should only be used deliberately.

## GitHub Actions and recovery

The workflow in `.github/workflows/automation.yml` runs tests and previews on relevant pushes, and performs scheduled collection at **8:15 AM Asia/Manila**. Hosted SQLite state is restored and backed up using the `ph-tech-sqlite` artifact (configured for 90-day retention, subject to GitHub limits). Push runs do not replace the hosted snapshot.

Manual workflow input `send_email=true` is for the **legacy fictional SMTP test**; keep it `false` for normal collection and database preservation. Scheduled reviewed-opportunity email delivery is **disabled**.

Artifacts are **not permanent private database hosting**. Before any restore or migration, preserve a validated independent backup; do not bootstrap a new database when recoverable history exists. Do not reset `sent` or `uncertain` jobs, because an SMTP message might already have been accepted.

## Security and limitations

- Review approval and rejection require a valid local reviewer account and appropriate permissions. Direct database access, account-store tampering, and historical pre-authentication reviews remain security limitations.
- SQLite on your computer and SQLite inside GitHub artifacts are separate copies; delivery state is not automatically synchronized.
- GitHub artifacts from this public repository must be treated as potentially readable by others. Do not store passwords, personal notes, or sensitive reviewer identities in them.
- Cross-source duplicates are advisory matches; existing rows and review history must not be automatically merged.
- No private PostgreSQL migration has occurred. The existing **SQLite schema version 3** remains authoritative.
- Gmail submission success does not guarantee inbox receipt, and an ambiguous SMTP outcome must not be retried automatically.
- Official listing legitimacy, fees, eligibility, and deadlines still require manual verification.

## Local Reviewer Accounts

Reviewer account storage is available in
`data/reviewer_accounts.sqlite3`, separate from opportunity history.

Create the initial administrator:

```powershell
python -m src.reviewer_accounts bootstrap local_admin
```

Check permissions:

```powershell
python -m src.reviewer_accounts check local_admin approve_opportunity
```

Approval and rejection require authenticated local reviewer accounts. Administrator-authorized role and status changes have a private append-only audit trail. Password verifiers remain outside GitHub. Login rate limiting, secure account recovery, and protection against direct database tampering are not yet implemented.

## Development milestones

| Phase | Completed scope |
|---|---|
| 1 | Python foundation and Gmail SMTP test sender |
| 2 | GitHub Actions testing, scheduling, and secrets |
| 3 | RSS collection, source allowlist, and classification |
| 4 | SQLite collection persistence and snapshot restoration |
| 5 | Review history, eligibility checks, notification queue, and manual delivery |
| 6 | Atomic backups, storage preparation, reviewer-auth design, quality analysis, and health audit |
| 7 (final verification) | Authenticated reviews, account revocation, audit integrity, two-database migration preflight, and security regression tests |
**No extra services, paid APIs, or automatic reviewed-email delivery are required to run this project.**

Licensed under the [MIT License](LICENSE).
