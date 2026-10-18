# PH Tech Opportunities Automation

A free and open-source Python automation system designed to discover, organize, and deliver email notifications about technology opportunities available to participants in the Philippines.

The project focuses on three opportunity categories:

1. Free professional certification exam vouchers
2. Technology events, workshops, and developer meetups
3. Hackathons, coding competitions, and innovation challenges

The system is being developed incrementally using Python, Visual Studio Code, and GitHub.

> **Development status:** Phase 1 — Basic Email Automation.
>
> The current version sends sample opportunity notifications through Gmail SMTP. Automated collection of real opportunities has not yet been implemented.

## Project Objectives

The project aims to:

- Provide free email notifications about technology opportunities.
- Prioritize opportunities available to Philippine participants.
- Discover certification vouchers, technology events, and hackathons.
- Avoid paid APIs and premium automation subscriptions.
- Use authorized public sources and open-source technologies.
- Prevent duplicate notifications in future development phases.
- Support automated execution through GitHub Actions.

## Technology Stack

| Technology | Purpose | Status |
|---|---|---|
| Python 3 | Main application | Implemented |
| Gmail SMTP | Email delivery | Implemented |
| python-dotenv | Environment configuration | Implemented |
| pytest | Automated unit testing | Implemented |
| tzdata | Time zone support | Implemented |
| Git and GitHub | Version control | In progress |
| GitHub Actions | Scheduled execution | Planned |
| RSS / Atom | Opportunity collection | Planned |
| SQLite | Opportunity history | Planned |

## Current Features

### Phase 1 — Basic Email Automation

The application currently supports:

- Gmail SMTP authentication using environment variables
- TLS-secured SMTP connections
- HTML and plain-text email content
- Three sample opportunity categories
- Philippine date formatting
- Preview mode without email delivery
- Explicit email delivery using the `--send` argument
- Configuration validation
- SMTP error handling
- Automated unit testing with mocked email delivery

**Important:** Sample opportunities are fictional and are only used to test notification formatting and delivery.

### Phase 2 — GitHub Actions Automation

The project now supports GitHub-hosted workflow execution.

Implemented features:

- Python 3.14 execution on GitHub-hosted Ubuntu runners
- Automated dependency installation
- Execution of all 14 pytest unit tests
- Manual workflow execution using `workflow_dispatch`
- Safe preview execution after relevant Git pushes
- Secure Gmail credentials using GitHub Actions Secrets
- Manually authorized Gmail SMTP delivery
- Daily workflow scheduling at 8:15 AM Philippine Time
- Conditional execution of email-related workflow steps
- SMTP configuration diagnostics
- Read-only GitHub token permissions
- Workflow concurrency configuration

#### Workflow Execution Modes

| Trigger | Behavior | Email Delivery |
|---|---|---|
| Push to main | Run tests and preview | Disabled |
| Manual, send_email=false | Run tests and preview | Disabled |
| Manual, send_email=true | Run tests and send sample email | Enabled |
| Daily schedule | Run tests and preview | Disabled |

#### Daily Schedule

The workflow uses:

```yaml
schedule:
  - cron: "15 8 * * *"
    timezone: "Asia/Manila"
```

The scheduled workflow executes at approximately 8:15 AM
Philippine Time. GitHub Actions scheduling is not guaranteed
to execute at the exact minute.

Scheduled notifications remain disabled because the application
currently generates fictional sample opportunities.

#### Manual Email Testing

1. Open the repository on GitHub.
2. Select the Actions tab.
3. Open PH Tech Opportunities Automation.
4. Select Run workflow.
5. Choose the main branch.
6. Enable the send_email input.
7. Execute the workflow.
8. Verify the email in the configured Gmail inbox.

Manual email delivery uses GitHub Actions Secrets:

- SENDER_EMAIL
- SENDER_APP_PASSWORD
- RECIPIENT_EMAIL

Never expose the secret values in logs or source files.

#### Reliability and Security

The workflow uses:

- `permissions: contents: read`
- A concurrency group to limit overlapping runs
- A 10-minute job timeout
- Automated pytest checks before email execution
- Secret validation before SMTP authentication

GitHub-hosted runners are temporary. Files created during a run
must not be treated as permanent storage.

Scheduled workflows in inactive public repositories may be
automatically disabled by GitHub after 60 days of inactivity.

#### Current Limitations

- Real opportunity collection is not implemented.
- Scheduled runs do not send email.
- Repeated manual runs can send identical test notifications.
- Persistent opportunity tracking is not implemented.
- Opportunity-level duplicate detection is not implemented.
- Source failure monitoring is not yet implemented.

These limitations will be addressed during subsequent phases.

#### Phase 2 Acceptance Criteria

- GitHub Actions workflow executes successfully.
- All 14 pytest tests pass.
- Preview mode executes without sending email.
- Manual email delivery works using GitHub Secrets.
- Push-triggered executions skip email delivery.
- A daily Philippine Time schedule is configured.
- Credentials are excluded from the repository.
- Existing application files remain functional.

### Phase 3 — RSS Opportunity Collection

The system now retrieves technology announcements from approved
public RSS feeds and classifies possible technology opportunities.

#### Implemented Features

- RSS and Atom feed parsing using feedparser
- Centralized YAML source configuration
- An explicit allowlist of approved feed URLs
- Multi-source collection with independent error handling
- Configurable source enable/disable controls
- Configurable result limits per source
- Normalized announcement records
- UTC publication date formatting
- Rule-based opportunity classification
- Keyword-based detection of certification voucher announcements
- Keyword-based detection of technology events
- Keyword-based detection of hackathons
- Preservation of original source URLs
- Explicit unverified classification results
- Terminal previews of collected announcements
- GitHub Actions RSS collection previews
- Automated testing using mocked RSS data

#### Configured RSS Sources

| Source | Feed URL | Purpose |
|---|---|---|
| GitHub Blog | https://github.blog/feed/ | Developer and technology announcements |
| Python Insider | https://blog.python.org/rss.xml | Python ecosystem announcements |

These feeds are general technology announcement sources.
They are not guaranteed to contain free certification vouchers,
Philippine events, or hackathon announcements.

#### Running RSS Collection

To execute the configured RSS collectors locally:

```powershell
python -m src.collectors.source_registry
```

To run the original single-source RSS collector:

```powershell
python -m src.collectors.rss_collector
```

To demonstrate the classifier independently:

```powershell
python -m src.collectors.opportunity_classifier
```

No Gmail notification is sent by these commands.

### Phase 4 — Persistence Reliability and Recovery

#### SQLite Persistence

The application stores normalized RSS announcements in SQLite.

The local database is located at:

`data/opportunities.sqlite3`

The database contains:

- `opportunities` — Discovered announcements and classification records
- `collection_runs` — Collection history and failure status
- `notification_history` — Reserved for future notification deduplication

The database is ignored by Git and is not committed to the repository.

#### GitHub Actions Persistence

GitHub-hosted runners are temporary.

The scheduled workflow preserves SQLite data through
validated GitHub Actions artifacts named:

`ph-tech-sqlite`

A successful hosted collection:

1. Finds the latest available SQLite snapshot.
2. Restores and validates the database.
3. Collects and stores classified RSS announcements.
4. Creates a validated SQLite backup.
5. Uploads a new workflow artifact.

The first hosted database must be initialized manually using
the `bootstrap_database` workflow input.

Automatic email notifications remain disabled.

#### Failed Collection Handling

If RSS collection fails:

- The persistent collection step fails.
- No new database snapshot should be uploaded.
- The workflow reports the failure.
- Previous successfully uploaded artifacts remain available
  until expiration or deletion.

A failing source must not be mistaken for zero new opportunities.

If snapshot restoration fails, persistent collection does not
continue and a new snapshot is not created automatically.

#### SQLite Integrity Validation

Validate the existing local database:

```powershell
python -m src.database.snapshot validate
```

Create a validated local backup:

```powershell
python -m src.database.snapshot backup
```

Validate the backup:

```powershell
python -c "from src.database.snapshot import validate_database; validate_database('data/snapshot_upload/opportunities.sqlite3'); print('Snapshot OK')"
```

#### Recovering From a Missing or Damaged Artifact

1. Open GitHub Actions and locate the latest successful
   workflow run that contains the `ph-tech-sqlite` artifact.
2. Download the artifact to a secure local folder.
3. Validate its SQLite contents before restoring.
4. Preserve any existing local database before replacing it.
5. Do not bootstrap a new hosted database while a recoverable
   historical snapshot may still exist.

If all hosted artifacts have expired or been deleted, the
workflow cannot automatically reconstruct the previous history.

A new bootstrap creates a new database history, not a recovery
of the original database.

#### Artifact Retention

GitHub Actions artifacts have limited retention.

The configured retention is 90 days, subject to repository
and organization policies.

Artifacts are not permanent backups.

If the project is inactive for an extended period, or if
artifact storage becomes unavailable, historical records may
be lost unless they were backed up elsewhere.

GitHub Actions artifact storage quotas and billing limits
also apply.

#### Data Privacy

Workflow artifacts may be downloaded by users with repository
read access.

For a public repository, treat artifact snapshots as
potentially publicly accessible.

Only public, non-sensitive RSS-derived information should be
stored in the current hosted database.

Do not store passwords, personal contact details, access tokens,
or private verification notes in uploaded snapshots.

#### Duplicate Detection Limitations

The current database identifies duplicate announcements using:

`source_id + exact URL`

The same opportunity published using different URLs, tracking
parameters, or different sources may still produce multiple rows.

The system does not yet use persistent notification history to
prevent repeated real email delivery.

#### Operational Checklist

After scheduled runs, review:

- Python test results
- RSS collection warnings
- SQLite collection status
- Successful snapshot backup creation
- Successful artifact upload
- Missing or expired snapshot warnings
- Unexpected database growth

A green workflow does not independently prove that every
source returned new, valid opportunities.

#### Phase 4 Limitations

- Hosted persistence depends on expiring workflow artifacts.
- GitHub Actions artifacts are not a transactional database service.
- Cross-source opportunity deduplication is not implemented.
- Automatic opportunity emails remain disabled.
- Source eligibility, cost, and deadlines are not verified.
- A permanent off-platform backup strategy is not implemented.
- Historical collection runs have limited timing precision.
- The database is intended for public RSS-derived data only.

#### Source Configuration

Approved sources are configured in:

`config/sources.yaml`

Each source contains:

- A unique source identifier
- An official source name
- An approved RSS URL
- An enabled or disabled setting
- A maximum result count

Source IDs and URLs are validated against the allowlist in:

`src/collectors/source_registry.py`

Adding new websites requires reviewing their data access
permissions and updating the approved source registry.

#### Opportunity Categories

The classifier recognizes:

| Category | Description |
|---|---|
| certification_voucher | Possible certification examination promotions |
| tech_event | Possible technology workshops, webinars, and meetups |
| hackathon | Possible coding competitions and hackathons |
| unclassified | Announcements without qualifying keyword matches |

#### Verification Status

Classification does not establish that an opportunity is
legitimate, free, currently available, or open to Philippine
participants.

Current records use:

- verification: not_verified
- free_status: unknown
- ph_eligibility: unknown
- deadline_status: unknown

Verification and filtering will be expanded in later phases.

#### GitHub Actions Integration

The workflow runs the RSS classifier during:

- Relevant pushes to the main branch
- Daily scheduled preview executions
- Manually triggered preview-only runs

RSS collection executes separately from email delivery.

Temporary feed failures produce workflow warnings without
automatically failing the existing Python test pipeline.

Scheduled email delivery remains disabled.

#### Automated Testing

The project currently includes 46 automated tests.

Run the complete test suite:

```powershell
python -m pytest -v
```

RSS-related tests use mocked network responses and do not
require actual internet access.

#### Current Limitations

- Only approved RSS feed endpoints are supported.
- Classification relies on keywords rather than semantic AI.
- Current classification examines announcement titles.
- Matches may include false positives or miss relevant items.
- Free status, deadlines, and PH eligibility are not verified.
- Opportunity records are not stored persistently.
- Duplicate tracking is not implemented.
- RSS collection failures require inspection of workflow logs.
- Real opportunity notifications are not sent automatically.

Persistent tracking and duplicate prevention are planned
for Phase 4.

#### Legal and Ethical Collection

The system uses publisher-provided RSS endpoints and avoids
paid platform APIs.

Additional sources must be reviewed for applicable terms,
access permissions, usage restrictions, and rate limits.

The system does not attempt to bypass authentication,
CAPTCHAs, paywalls, or other access controls.

## Project Structure

```text
ph-tech-opportunities/
│
├── src/
│   ├── __init__.py
│   ├── main.py
│   └── email_sender.py
│
├── tests/
│   ├── test_email_sender.py
│   └── test_main.py
│
├── .env.example
├── .gitignore
├── requirements.txt
├── LICENSE
└── README.md
```

The local `.env` and `.venv` files are excluded from version control.

## Installation

### Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer
- Visual Studio Code
- Git
- A Gmail account supporting the selected SMTP authentication method

### 1. Clone the repository

After the GitHub repository is published:

```powershell
git clone <YOUR_REPOSITORY_URL>
cd ph-tech-opportunities
```

Replace `<YOUR_REPOSITORY_URL>` with the actual GitHub repository URL.

### 2. Create a virtual environment

```powershell
python -m venv .venv
```

### 3. Activate the environment

For Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 5. Configure environment variables

Copy the provided configuration template:

```powershell
Copy-Item .env.example .env
```

Open `.env` and provide the required values:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

SENDER_EMAIL=your_email@gmail.com
SENDER_APP_PASSWORD=your_app_password
RECIPIENT_EMAIL=recipient@gmail.com

APP_NAME=PH Tech Opportunities Automation
APP_TIMEZONE=Asia/Manila
APP_ENV=development
```

Use a Google App Password if your Gmail account supports this authentication method.

Never commit or publish the actual `.env` file.

## Running the Application

### Preview mode

Run:

```powershell
python -m src.main
```

This generates and displays the sample notification without sending an email.

### Email delivery mode

Run:

```powershell
python -m src.main --send
```

This connects to Gmail SMTP and submits the notification to the configured recipient.

## Automated Testing

Run all tests:

```powershell
python -m pytest -v
```

Phase 1 includes 14 unit tests covering:

- Environment variable validation
- SMTP port validation
- Email address validation
- Placeholder credential detection
- SMTP message construction
- Mocked SMTP authentication failures
- HTML notification generation
- Opportunity category verification
- Preview mode safety
- Email delivery execution
- Application error handling

All 14 tests passed during local Phase 1 verification.

Tests use mocked SMTP delivery and do not require sending real emails.

## Development Roadmap

- [x] Phase 1 — Basic Email Automation
- [x] Phase 2 — GitHub Actions Scheduling
- [x] Phase 3 — RSS Opportunity Collection
- [ ] Phase 4 — SQLite and Duplicate Prevention
- [ ] Phase 5 — Filtering and Validation
- [ ] Phase 6 — Certification Voucher Monitoring
- [ ] Phase 7 — Philippine Technology Event Integrations
- [ ] Phase 8 — Philippine Hackathon Monitoring
- [ ] Phase 9 — Advanced Email Notifications
- [ ] Phase 10 — Testing, Security, and Production Release

Phase 1 implementation and testing are complete. Repository publication is the remaining Phase 1 milestone.

All development phases will extend this same repository.

## Legal and Ethical Data Collection

The project follows these principles:

1. Use authorized public data sources and officially available feeds.
2. Respect applicable website terms and access restrictions.
3. Do not bypass authentication, CAPTCHAs, paywalls, or anti-bot systems.
4. Avoid unauthorized use of subscription-only APIs.
5. Apply reasonable rate limits to permitted automated requests.
6. Preserve source attribution for discovered opportunities.
7. Collect only information necessary for the application.
8. Protect email credentials and other sensitive information.

Luma and Meetup integrations will use authorized access methods where available. The project does not guarantee full platform coverage.

## Security

- Credentials are loaded from environment variables.
- Local `.env` files are excluded from Git.
- Python virtual environments are not committed.
- SMTP connections use TLS.
- Automated tests use mock email connections.
- Secrets must not appear in source code or application logs.

GitHub Actions Secrets will be introduced during Phase 2.

## Open-Source License

This project is licensed under the MIT License.

See the [LICENSE](LICENSE) file for the complete license terms.

## Disclaimer

This project is an independent open-source automation tool.

Certification providers, event organizers, and hackathon platforms are not affiliated with or responsible for this project.

Users must verify registration availability, eligibility, deadlines, and offer conditions through original official sources before participating.

The software is provided without warranty under the terms of the MIT License.