# Phase 12 Step 2 — encrypted backup and isolated recovery design

**Status: contract and offline tests only. No encryption, decryption, or migration is implemented in this step.**

## Scope and threat model

Existing format-v1 backups are **plaintext SQLite**, even when their manifest is protected by scrypt-HMAC. Preserve all existing backups and CLI commands unchanged. A future opt-in v2 implementation should protect opportunity histories and reviewer-account password verifiers at rest against someone who gains a copy of the backup bundle. It cannot protect data after local compromise, weak or stolen passphrases, or exposure through already-published artifacts.

## Proposed version-2 format

- Envelope format: `phtech-encrypted-backup-v2`. Exactly two database payloads: `opportunities.sqlite3` and `reviewer_accounts.sqlite3`.
- Passphrase derivation: **scrypt**, with fixed parameters N=32768, r=8, p=1, derived key length 32 bytes, and a fresh cryptographically random 16-byte salt **for each backup**. The decryptor must enforce work-factor and resource bounds before any KDF work. Consider memory/resource suitability and independent review before shipping.
- Encryption: **AES-256-GCM** using a vetted maintained crypto library; fresh unique unpredictable 96-bit nonce **per encrypted file under the derived key**, never reused. Use ciphertext + GCM tag together; reject incomplete tags.
- Bind **the full canonical envelope** (format, algorithms, parameters, salt, filenames, ciphertext metadata) as authenticated additional data (AAD). Define and independently test its byte serialization before implementation. An unauthenticated SHA-256 ciphertext checksum is useful for corruption screening **but does not authenticate the backup**.
- Do not store passphrases, encryption keys, reviewer hashes, raw rows, or original secret values in reports or logs. Do not let users select weakened algorithms or work factors.
- Both encrypted database payloads must decrypt and validate successfully before an isolated recovery directory can be published. Use an exclusive temporary destination and fail without replacing any existing directory.
- Recovery requires a manually entered passphrase; errors must not disclose whether a specific account or password exists. **Never automatically resume uncertain SMTP jobs**, rewrite timestamps/history, or authorize a PostgreSQL cutover.
- Support legacy v1 only through an explicit separate recovery path with clear plaintext warnings; never silently reinterpret v1 as encrypted or overwrite old bundles.
- On Windows, separately verify NTFS ACLs and permissions on temporary files, parent directories, recovered files, and archives; never claim secure deletion of plaintext from an ordinary filesystem.
- Add verified end-to-end ciphertext confidentiality and tamper tests, wrong-passphrase rejection, isolated recovery, failure cleanup, process interruption, and memory/resource bounds **before** enabling an encrypted-backup CLI.

## Step-2 acceptance

`src/database/encrypted_backup_design.py` checks the *shape* of proposed metadata, not the cryptographic authenticity of a bundle. It must always report `safe_to_restore=False` and `production_cutover_authorized=False`. Step 2 may be accepted as **design-only** after CI, owner review, and regression tests; it is **not** approval to create or decrypt a real encrypted backup.

All real source databases, format-v1 backups, reviewer accounts, Neon staging, GitHub Actions schedule, and manual-only reviewed email delivery remain unchanged.
