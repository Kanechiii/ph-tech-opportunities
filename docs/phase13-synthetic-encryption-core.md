# Synthetic AES-GCM prototype (Phase 13, step 1)

This is **an in-memory cryptographic prototype, not an encrypted backup service**. Do not pass real SQLite databases, account records, or operational backup data into these functions. No CLI, filesystem backup, restore, Neon connection, application runtime integration, or SMTP action is enabled.

The functions in `src/database/synthetic_encryption_core.py` use the reviewed AES-256-GCM and scrypt parameters with fresh random salts and nonces. They enforce a **4 MiB per synthetic payload** limit and a bounded scrypt memory limit. They validate the design envelope and require both ciphertexts to authenticate before returning plaintext bytes. The wrong passphrase, missing file, altered ciphertext, altered metadata, and downgraded algorithm all fail closed.

**AAD clarification:** Every metadata field except the `ciphertext_sha256` entries is represented in canonical authenticated additional data. Ciphertext SHA-256 cannot be included in AAD for the same ciphertext without a circular dependency; the digest is checked before AES-GCM authentication. Integrity ultimately relies on the AES-GCM tag, not the checksum. The v2 envelope is not final and requires an independent format review before publishing a file-based implementation.

**Next implementation gates:** Design a no-plaintext-on-disk backup creation path, an isolated recovery path that verifies both encrypted payloads and SQLite structure before publishing, safe Windows ACL behavior, failure cleanup and interrupted-process tests, external backup/restore drills, and a separate authorization for any use of real data. Existing v1 backups stay plaintext and untouched. SQLite stays authoritative, with manually approved reviewed-opportunity delivery only.
