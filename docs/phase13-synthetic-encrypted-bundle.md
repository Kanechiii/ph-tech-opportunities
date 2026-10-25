# Phase 13 — Synthetic encrypted bundle file boundary

**Status:** development-only synthetic fixtures; no real database backups, recovery, migration, or scheduled delivery.

The in-memory authenticated encryption core is now exercised through a deliberately small, exclusive-create filesystem bundle containing only `envelope.json`, `opportunities.sqlite3.enc`, and `reviewer_accounts.sqlite3.enc`. The source data is provided as synthetic bytes by a test fixture. No production file paths are opened, plaintext payloads are never written to disk, and no restore operation is implemented.

This is **not** a secure backup product yet. The currently provisional v2 format needs external review and further hardening before production data can be used. In particular, these synthetic tests are not a substitute for OS-level Windows ACL inspection, malicious concurrent-directory mutation resistance, symbolic-link races, interrupted-process recovery, atomic directory publication and actual SQLite consistency checks. Inputs must be synthetic and the destination must not already exist. This step makes no changes to existing format-v1 authenticated plaintext backups or their legacy recovery path.

Acceptance requires full Python regression tests, dependency security checks, review of the path/symlink handling, and owner confirmation. The next step should address isolation and failure-safe publication before designing real-data encrypted backup creation and recovery. No production cutover, data migration or automatic email delivery is authorized.


## Step 3: staged ciphertext publication and failure handling

The synthetic bundle writer now encrypts in memory, writes **ciphertext only** into a private temporary sibling directory, fsyncs each file, reads back and authenticates both encrypted payloads, then renames the staged directory to the requested destination. It cleans up unpublished staging directories after simulated write, verification and rename failures. It will refuse an already-existing destination and checks again before publishing. The API remains synthetic-only: no real SQLite file, account record, archive, or recovery operation is supported.

**Limitations not yet solved:** a concurrent actor can race the final existence check; portable Python `os.rename` does not guarantee *no replacement* of an attacker-created empty destination directory on every platform. Therefore the parent directory must be under exclusive trusted ownership; the implementation is **not approved for hostile/shared directories or real backups**. Power failure durability, directory fsync on Windows, NTFS ACL verification, hard links, path traversal via intermediate symlinks, interruption before cleanup, secure erase of temporary ciphertext, and malicious filesystem mutation remain unverified. A platform-specific atomic no-replace publication primitive and comprehensive filesystem threat tests are required before operational use.

Successful synthetic CI is acceptance of this narrow development test only, never proof of secure backup confidentiality or production disaster recovery.


## Step 4: bounded synthetic reads and link checks

The synthetic reader now refuses any path containing a symbolic-link ancestor, requires each encrypted file and manifest to be a **single-linked regular file**, and reads through bounded file descriptors using `lstat`, `fstat`, inode/size comparisons, and `O_NOFOLLOW` on platforms that expose it. The check limits the amount of ciphertext and envelope data loaded into memory. New offline tests cover hard links, linked parents, oversized ciphertext and metadata, and file replacement between preliminary metadata inspection and opening.

**Residual risk:** This does not make paths or publication atomic against hostile concurrent writers. Windows security descriptors, inherited NTFS ACLs, process interruption, intermediate directory replacement, platform-specific atomic no-replace publication, and durability semantics still require independent verification. Consequently **only synthetic test fixtures are permitted**; no operational backup or recovery CLI is exposed.
