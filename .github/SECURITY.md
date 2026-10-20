# Security policy

This project is open-source development software and has no production-supported release yet. The `main` branch is the maintained development branch.

## Report a vulnerability privately

Please use the repository's **Security** tab and **Report a vulnerability** if private vulnerability reporting is enabled. If that option is unavailable, open a public issue **requesting a private reporting channel only**; do not include exploit details, credentials, database content, personal information, or logs containing secrets.

Do not submit production database files, `.env` files, Gmail app passwords, backup passphrases, or private reviewer data in issues or pull requests.

## Scope and limitations

The repository currently contains a development-grade SQLite application. GitHub Actions artifacts are not a private or durable database, and HMAC-authenticated local backups are not encrypted. Reviewed-opportunity email delivery is manual-only. Please review the README's security and limitations section before running this application with real data.

Security fixes should be reviewed and tested before disclosure or release.
