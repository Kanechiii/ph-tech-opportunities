# Phase 13 — Synthetic encryption acceptance

**Scope:** A deliberately limited, repeatable acceptance check on hardcoded fictional byte payloads using an automatically cleaned temporary directory. The CLI `python -m src.database.phase13_acceptance` prints a minimal JSON status report only; it has no parameters that select live databases or arbitrary backup files.

The gate verifies synthetic AES-256-GCM round-trip, ciphertext-only files, wrong-passphrase rejection, destination overwrite refusal, and modified-ciphertext rejection. It additionally asserts all production and real-data authorization flags remain **false**. Synthetic tests are not proof of production safety.

## Remaining blockers before any real backup or restore

1. Integrate consistent read-only snapshots of both existing SQLite databases into separately reviewed encryption creation logic without changing originals or uploading plaintext.
2. Implement independent, isolated authenticated decryption and validate SQLite integrity, exact row-level histories and two-database recovery parity before publishing any recovered files.
3. Independently verify Windows NTFS ACLs, inherited permissions, hard links, path traversal, symlink and directory replacement races, and test a true cross-platform atomic **no-replace** publication strategy.
4. Validate interruption behavior, crash/power-loss durability, recovery from private offsite storage, and platform-specific permissions.
5. Finalize and independently review the encrypted file format, AAD canonicalization, cryptographic key handling, and passphrase recovery requirements.
6. Obtain explicit owner authorization before using operational data; protect all existing plaintext format-v1 backups and SQLite reviewer history.

**Acceptance boundary:** Step 5 concludes Phase 13's **synthetic development scope only** after owner review and successful CI. It does **not** authorize real encrypted backup creation, restoration, Neon use, PostgreSQL migration/cutover, or automated reviewed-opportunity email. Existing SQLite and account stores remain authoritative and untouched.
