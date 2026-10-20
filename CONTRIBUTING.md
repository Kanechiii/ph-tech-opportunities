# Contributing to PH Tech Opportunities Automation

Thank you for helping improve this free, open-source project. It is currently **development software, not production-ready**. Reviewed-opportunity email delivery is manual-only.

## Get started

1. Fork the repository and clone your fork, or clone the public repository to review it.
2. Use a supported Python interpreter and create a virtual environment: `py -m venv .venv` on Windows.
3. Install dependencies with `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` on Windows.
4. Run `.\.venv\Scripts\python.exe -m pip check` and `.\.venv\Scripts\python.exe -m pytest -v`.
5. Preview fictional examples safely with `.\.venv\Scripts\python.exe -m src.main`. **Do not** use `--send` for contribution testing.

GitHub Actions also runs the `Test Python Application` check on pull requests, plus dependency-security checks. All required checks must pass before a pull request is merged.

## Pull requests

- Open a focused feature branch; do not commit directly to protected `main`.
- Describe the behavior being changed, why it is needed, how it was tested, and whether it changes database schemas, persisted state, review authorization, SMTP behavior, or GitHub Actions permissions.
- Include offline regression tests for application behavior changes; do not require paid APIs or network access in ordinary tests.
- Keep documentation and code consistent. Do not bypass required checks or leave review conversations unresolved.
- Do not automatically merge Dependabot updates; verify compatibility and security findings per PR.

## Data and security

Never commit or upload `.env`, real credentials or tokens, real SQLite databases, database snapshots, reviewer account files, backup passphrases, local backup manifests, private data, or operational logs containing sensitive information.

Use synthetic fixtures and temporary directories for tests. Do not replace existing storage, change `sent`/`uncertain` notification job history, enable unattended reviewed-opportunity email delivery, or run migrations as a side effect of a pull request.

Report security issues privately following [the security policy](.github/SECURITY.md). Never share exploit details or secrets in a public issue.

## Scope

The current system collects and classifies publicly available announcements; classification is not proof that a voucher, event, or hackathon is free, open, genuine, or available in the Philippines. Keep this distinction clear in documentation and user-facing output.

By contributing, you agree that your contributions are made available under the repository's [MIT License](LICENSE).
