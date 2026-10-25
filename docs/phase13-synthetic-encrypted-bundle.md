# Phase 13 — Synthetic encrypted bundle file boundary

**Status:** development-only synthetic fixtures; no real database backups, recovery, migration, or scheduled delivery.

The in-memory authenticated encryption core is now exercised through a deliberately small, exclusive-create filesystem bundle containing only `envelope.json`, `opportunities.sqlite3.enc`, and `reviewer_accounts.sqlite3.enc`. The source data is provided as synthetic bytes by a test fixture. No production file paths are opened, plaintext payloads are never written to disk, and no restore operation is implemented.

This is **not** a secure backup product yet. The currently provisional v2 format needs external review and further hardening before production data can be used. In particular, these synthetic tests are not a substitute for OS-level Windows ACL inspection, malicious concurrent-directory mutation resistance, symbolic-link races, interrupted-process recovery, atomic directory publication and actual SQLite consistency checks. Inputs must be synthetic and the destination must not already exist. This step makes no changes to existing format-v1 authenticated plaintext backups or their legacy recovery path.

Acceptance requires full Python regression tests, dependency security checks, review of the path/symlink handling, and owner confirmation. The next step should address isolation and failure-safe publication before designing real-data encrypted backup creation and recovery. No production cutover, data migration or automatic email delivery is authorized.


## Step 3: staged ciphertext publication and failure handling

The synthetic bundle writer now encrypts in memory, writes **ciphertext only** into a private temporary sibling directory, fsyncs each file, reads back and authenticates both encrypted payloads, then renames the staged directory to the requested destination. It cleans up unpublished staging directories after simulated write, verification and rename failures. It will refuse an already-existing destination and checks again before publishing. The API remains synthetic-only: no real SQLite file, account record, archive, or recovery operation is supported.

**Limitations not yet solved:** a concurrent actor can race the final existence check; portable Python `os.rename` does not guarantee *no replacement* of an attacker-created empty destination directory on every platform. Therefore the parent directory must be under exclusive trusted ownership; the implementation is **not approved for hostile/shared directories or real backups**. Power failure durability, directory fsync on Windows, NTFS ACL verification, hard links, path traversal via intermediate symlinks, interruption before cleanup, secure erase of temporary ciphertext, and malicious filesystem mutation remain unverified. A platform-specific atomic no-replace publication primitive and comprehensive filesystem threat tests are required before operational use.

Successful synthetic CI is acceptance of this narrow development test only, never proof of secure backup confidentiality or production disaster recovery.


## Step 4: descriptor-bound synthetic file validation

The bundle reader now bounds ciphertext/envelope data while reading, verifies that opened descriptors refer to regular files, and compares pre-open, post-open, and post-read file identities. It refuses symbolic-link entries, missing entries, oversized files, nonregular files and simulated file substitution. On platforms implementing `O_NOFOLLOW`, final-path symlink following is denied at `os.open`; on Windows the available checks are only best-effort and do not prove race-free behavior.

**Security boundary:** This is not safe for adversarially writable parent directories and not a replacement for Windows secure handle flags, ACL verification, intermediate-path checks, atomic no-replace publication, interruption cleanup, or trusted private backup storage. No operational SQLite or reviewer-account file has been opened. Existing format-v1 backups and SMTP safeguards are untouched. A future step must address platform-specific filesystem primitives and controlled synthetic end-to-end recovery before any real-data use.
