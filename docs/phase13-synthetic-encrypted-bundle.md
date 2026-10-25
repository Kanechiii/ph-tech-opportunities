# Phase 13 — Synthetic encrypted bundle file boundary

**Status:** development-only synthetic fixtures; no real database backups, recovery, migration, or scheduled delivery.

The in-memory authenticated encryption core is now exercised through a deliberately small, exclusive-create filesystem bundle containing only `envelope.json`, `opportunities.sqlite3.enc`, and `reviewer_accounts.sqlite3.enc`. The source data is provided as synthetic bytes by a test fixture. No production file paths are opened, plaintext payloads are never written to disk, and no restore operation is implemented.

This is **not** a secure backup product yet. The currently provisional v2 format needs external review and further hardening before production data can be used. In particular, these synthetic tests are not a substitute for OS-level Windows ACL inspection, malicious concurrent-directory mutation resistance, symbolic-link races, interrupted-process recovery, atomic directory publication and actual SQLite consistency checks. Inputs must be synthetic and the destination must not already exist. This step makes no changes to existing format-v1 authenticated plaintext backups or their legacy recovery path.

Acceptance requires full Python regression tests, dependency security checks, review of the path/symlink handling, and owner confirmation. The next step should address isolation and failure-safe publication before designing real-data encrypted backup creation and recovery. No production cutover, data migration or automatic email delivery is authorized.
