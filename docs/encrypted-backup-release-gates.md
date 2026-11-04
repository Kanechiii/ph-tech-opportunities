# Encrypted backup release gates

This workstream consolidates encrypted-backup security review into one reviewable change set, using semantic branch naming and Conventional Commit PR titles without numerical phase labels.

## Delivered

- Versioned strict AES-GCM envelope and canonical AAD compatibility checks from the previous merged design PR.
- Threat model and Windows filesystem requirements.
- Read-only destination preflight: rejects existing destinations, missing parent paths and symbolic-link ancestors, without creating or touching backup files.
- Fail-closed release evidence: explicit real SQLite snapshot integrity, both encrypted payloads authenticated, independent Windows NTFS ACL verification, no-replace publication, crash/restart tests, isolated recovery, historical audit parity and secret-management review.
- Offline tests for existing-file preservation, symlink handling, unsupported and missing evidence.

## Explicitly not delivered

**The operational encrypted backup feature is not yet production-ready.** Current code does not implement real-data backup creation, a Windows ACL inspector, platform-certified atomic no-replace publication, encrypted restoration, secret recovery, or verified offsite disaster recovery. Synthetic payload testing does not prove production backup security. Do not treat positive directory preflight results as authorization. No actual SQLite data was accessed or modified by these checks.

## Required release follow-up

A future reviewable change must implement and verify real-data encryption without plaintext leakage, robust Windows directory/file ACL control, crash-safe atomic publication and independently validated isolated restoration. It must preserve the format-v1 plaintext backups, SQLite/reviewer audit histories, Neon staging and manual-only notification behavior. Do not enable production backup operations or automatic email delivery without explicit owner authorization.

## GitHub conventions

New feature branches use `feat/<semantic-topic>`, fixes use `fix/<semantic-topic>`, tests use `test/<semantic-topic>`, and documentation uses `docs/<semantic-topic>`. Use concise Conventional Commit PR titles and **Scope / Validation / Safety** descriptions with no phase/step numbering. Group all authorized work for a phase in a single reviewable PR, with CI and human review before merging. Preserve existing merged historical PRs and never auto-merge.
