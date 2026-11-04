# Encrypted backup security specification — Phase 14, Step 1

**Status:** proposed format freeze and design acceptance only. No real backup, decryption, CLI, migration, or cutover is authorized. This step must not access or modify existing operational SQLite histories, reviewer accounts, format-v1 backups, Neon staging, or email delivery.

## Threat model

Assets: both SQLite database histories, reviewer password verifiers, review/audit trails, notification states, backup passphrases and cryptographic keys. Defend against copied backup bundles, ciphertext/manifest tampering, plaintext backup leakage, path manipulation (symlink/reparse point, hard links), unauthorized local readers, concurrent directory replacement, crash-truncated writes, and unverified recovery. Preserve ambiguous `sending`/`uncertain` delivery states. A leaked or weak passphrase, compromised running host, malware, and attacker-controlled account databases remain outside the guarantees of password-based backup encryption. Require private, independently verified offsite recovery and separately audited NTFS access controls.

## Version-2 envelope — format-review candidate

The existing synthetic implementation uses the `phtech-encrypted-backup-v2` envelope. The following representation is pinned **for design review**, not certified as an operational format:

- Exactly one `envelope.json`, plus `opportunities.sqlite3.enc` and `reviewer_accounts.sqlite3.enc`. No other entries.
- JSON schema is strict: `format`, `cipher`, `kdf`, `kdf_params`, `salt_hex`, `files`. Reject unknown fields, duplicates and algorithm downgrade. Canonical JSON: ASCII, sorted keys, compact separators `,` and `:`; no whitespace or newline in canonical AAD.
- `AES-256-GCM`, 32-byte key, fresh random 96-bit nonce per payload and **never reuse a nonce under one key**. Each encrypted payload contains ciphertext with the appended 16-byte GCM tag.
- `scrypt`: N=32768, r=8, p=1, dklen=32, with new random 16-byte salt per bundle. Bound KDF resource use and payload sizes before doing expensive cryptography. Passphrase length and recovery policy need independent review.
- The canonical AAD includes `format`, `cipher`, `kdf`, `kdf_params`, `salt_hex`, and for both filenames `nonce_hex` and `ciphertext_size`. **It intentionally excludes `ciphertext_sha256`** because a ciphertext digest cannot also be authenticated AAD for the same ciphertext without circularity. Before decrypting, check the SHA-256 ciphertext digest; GCM verifies authenticity. SHA-256 alone must never count as authentication.
- Authenticate **both** ciphertexts before returning any plaintext. Reject truncated tags, missing or extra files, wrong passphrase, altered metadata, nonce reuse and unsupported format versions. Strictly separate legacy authenticated *plaintext* v1 recovery; never silently upgrade or reinterpret its files.
- The current synthetic 4 MiB payload bound is **not** a production backup sizing decision. Operational limits, streaming/chunking and crash durability remain to be designed and reviewed.

## Windows filesystem requirements — mandatory independent evidence

Before operational use, verify all of the following in actual Windows tests:
1. Private destination parent owned by the authorized reviewer process; no untrusted writers, and explicitly verified NTFS DACL/owner/SID behavior.
2. Audit inherited ACLs, deny unintended users/groups, verify directory and encrypted-file permissions after creation and after recovery, and reject reparse points throughout paths.
3. Refuse hardlinks and non-regular entries; use no-follow and handle-based validation where available. Resolve and defend against intermediate directory substitution, including network/removable shares.
4. Ensure **atomic no-replace** publication on Windows and POSIX; simple `os.rename` and a preflight existence check are **insufficient** for adversarial concurrency. Never overwrite a destination or source. Require safe, tested failure cleanup.
5. Validate interruption, restart and crash consistency, including fsync/FlushFileBuffers and directory-entry durability constraints. Avoid plaintext temporary files and never claim secure deletion on general filesystems.
6. Explicitly isolate decryption and verify SQLite integrity, data parity, reviewer audit histories, and all notification job states before publishing recovered files.
7. Inspect backups in private/offsite storage, verify restore drills and recovery-key handling; no GitHub Actions artifact should be assumed private durable hosting.

## Acceptance gates and excluded effects

Phase 14 Step 1 acceptance requires documented threat coverage, a canonical AAD contract regression check against the existing synthetic code, a fail-closed checklist of Windows gates, full Python tests, dependency audit and owner review. All such checks are **design evidence only**. They do not prove NTFS permissions, protect against hostile filesystem races, enable live backups, restore databases, change Neon or authorize scheduled reviewed-opportunity email.
