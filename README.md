# PH Tech Opportunities Automation

A free, open-source Python project that collects and classifies public technology announcements for people in the Philippines. It focuses on **free certification exam vouchers, technology events, and hackathons**.

**Status:** **Phases 1–12 complete within their approved development scopes.** Phase 13 has **not started**. **Not production-ready.** SQLite remains authoritative; scheduled collection/previews are enabled, while reviewed-opportunity email delivery remains **manual-only**. No real-data PostgreSQL migration, backend cutover, or automatic reviewed-opportunity delivery has been approved.

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
- Local persistent reviewer login throttling (five failures trigger a 15-minute lockout); review authorization consistency and account-audit safeguards.
- Read-only source-history reconciliation, synthetic PostgreSQL migration-contract checks, offline backend activation guards, and final production-readiness reports.
- Strict **design-only** AES-256-GCM encrypted-backup envelope specification; **actual encrypted backup/recovery is not yet implemented**.

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
| Back up both local databases | `python -m src.database.local_backup --destination "PATH" --authenticate` |
| Test authenticated isolated recovery | `python -m src.database.local_recovery --backup "BACKUP_PATH" --destination "NEW_RECOVERY_PATH" --authenticate` |
| Compare database pairs before cutover | `python -m src.database.cutover_readiness --candidate-opportunities "PATH" --candidate-accounts "PATH"` |

Recovery drills never replace live databases. New authenticated backups use a separate passphrase to protect manifest integrity, not confidentiality. Older unsigned backups remain supported in legacy mode; use `--authenticate` for new backups and recovery drills. Store passphrases securely and protect all backup files from unauthorized access.

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

Approval and rejection require authenticated local reviewer accounts. Administrator-authorized role and status changes have a private append-only audit trail. Password verifiers remain outside GitHub. Local per-account login throttling is implemented; secure account recovery, session management, Windows ACL review, and protection against direct database tampering remain incomplete.

## Development roadmap

**Completed:** Phases 1–12 within their bounded development and safety scopes. **Phase 13 is in progress** (synthetic in-memory encryption prototype under review). Completion **does not mean production readiness**.

| Phase | Status | Delivered scope |
|---|---|---|
| 1 — Local foundation | Complete | Python project, environment setup, Gmail SMTP test sender |
| 2 — GitHub Actions | Complete | CI, secrets, scheduled preview/collection, manual-only test email |
| 3 — Opportunity discovery | Complete | RSS/Atom sources, allowlist, keyword classification, unverified labeling |
| 4 — SQLite persistence | Complete | History, duplicate detection, durable workflow snapshot handling |
| 5 — Verification and notifications | Complete | Manual reviews, evidence history, queue, safe manual delivery |
| 6 — Reliability foundations | Complete | Atomic snapshots, storage research, reviewer auth design, quality scoring, health audit |
| 7 — Reviewer enforcement | Complete | Local reviewer accounts, authorized reviews, role/status auditing, migration preflight |
| 8 — Backup and cutover checks | Complete | Authenticated **plaintext** two-DB backups, isolated recovery, reconciliation and fail-closed checks |
| 9 — Open-source readiness | Complete | Protected branch review, security reporting, dependency audits, contribution guidance |
| 10 — PostgreSQL staging foundation | Complete | Seven-table schema/roles, isolated **synthetic-only** rehearsal, migration inventory and acceptance |
| 11 — Security hardening foundations | Complete | Local credential throttle, review authorization serialization, audit/confidentiality checks |
| 12 — Production-readiness foundations | Complete | Source-history gate, **encryption design only**, offline migration/runtime safety checks, synthetic recovery, final blockers report |

### Remaining work — not started or not approved

These are **remaining workstreams, not completed or authorized production deployment actions**:

| Priority | Proposed work | Required result |
|---|---|---|
| Current (Phase 13 in progress) | Encrypted backups and independent recovery | Synthetic in-memory AES-GCM prototype under review; file-based encrypted backup, isolated decryption/restore and recovery drills remain unimplemented |
| Critical | Source reconciliation and migration | Resolve local/hosted SQLite divergence, preserve append-only histories and `sent`/`uncertain` jobs; verify real-data import only after separate authorization |
| Critical | PostgreSQL application adapter | Least-privilege runtime integration, credential rotation, consistency validation, rollback drills and explicit cutover approval |
| High | Authentication and file security | Reviewer account recovery/session defenses, Windows ACL checks, tamper-resistant storage boundaries |
| High | Delivery authorization and operations | Resolve uncertain SMTP outcomes without duplicate sends; audit, observability, alerting, and hosted recovery |
| Medium | Philippine opportunity coverage | Expand reviewed sources for vouchers, events and hackathons |

**Safety boundary:** Do not auto-resolve ambiguous deliveries; modify original review/account audits; upload private SQLite files; treat Neon staging as production; switch runtime backends; or enable scheduled reviewed-opportunity email delivery without separate explicit authorization.

### Pull request conventions

Use **Conventional Commits** titles: `type(scope): concise description`. PR descriptions should briefly cover **Scope / Validation / Safety**. Assignment and phase labels are **manual and optional**; no workflow automatically assigns owners or applies phase labels. Existing historical pull requests and commits are retained for provenance.

**No extra services, paid APIs, or automatic reviewed-email delivery are required to run this project.**

Licensed under the [MIT License](LICENSE).

## Open-source contributions

Read the [contribution guidelines](CONTRIBUTING.md) before opening a pull request.

This project is MIT-licensed and welcomes reproducible bug reports, documentation improvements, tests, and narrowly scoped pull requests. Before submitting changes, run `python -m pytest -v`. Pull requests to `main` run the test job automatically; they do not send reviewed-opportunity emails or replace hosted SQLite snapshots. Keep credentials and any real SQLite or backup files out of issues, commits, and CI artifacts.

For a potential vulnerability, follow [the private reporting guidance](.github/SECURITY.md) rather than sharing exploit details in a public issue. Public source code and successful tests do not imply production readiness.
