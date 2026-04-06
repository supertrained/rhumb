# Spec: AUD-3 Score-Audit Quarantine Policy

**Status:** Active  
**Date:** 2026-04-06  
**Owner:** Pedro  
**Scope:** `packages/api/services/score_audit_verification.py`, `packages/api/services/chain_checkpoints.py`, `scripts/publish_chain_anchor.py`

---

## Problem

Historical `score_audit_chain` rows are not all equally trustworthy.

Most rows with an explicit persisted `key_version` can be treated as verified for anchor-head selection. Some older rows cannot:
- a row may be missing `key_version`
- a row may be explicitly known to be unreconstructible from the preserved payload surface and preserved keyring

Without an explicit policy, checkpoint and anchor publication could imply that the latest observed row is also the latest verified row.

## Policy

### Verification statuses

- `verified`
  - Row has an explicit persisted `key_version`
  - No active quarantine exception applies
  - Anchor-eligible

- `unattributed_legacy`
  - Row has no persisted `key_version`
  - Not anchor-eligible as a verified head

- `unverifiable_legacy`
  - Row is explicitly quarantined because the preserved truth surface cannot reproduce the signed message
  - Not anchor-eligible as a verified head

### Head-selection rule

When publishing a checkpoint or external witness for `score_audit_chain`:

1. If the latest observed row is `verified`, anchor the latest head normally.
2. If the latest observed row is not anchor-eligible, select the latest prior `verified` row as the verified head.
3. Surface the tail honestly as a quarantined tail, including:
   - `verification_status=verified_with_quarantined_tail`
   - `head_selection_mode=latest_verified_head`
   - `latest_observed_entry_id`
   - `latest_observed_verification_status`
   - `quarantine_action=excluded_from_verified_head`
   - `quarantined_tail_count`
   - forensic-note reference when available

## Current explicit quarantine registry

### `saud_5565e543fcc248dbbe515e38103ac518`

- status: `unverifiable_legacy`
- decision: `exclude_from_verified_head`
- forensic note: `docs/specs/AUD-3-LEGACY-SCORE-AUDIT-FORENSIC-NOTE-2026-04-04.md`

## Auditability requirements

The policy must stay auditable from the same product repo that contains the witness artifacts.

That means:
- policy references emitted into checkpoints / anchor bundles must resolve inside this repo
- tests should fail if the referenced policy or forensic-note documents disappear

## Non-goals

- This policy does not silently bless unattributed legacy rows.
- This policy does not backfill historical key versions without fresh evidence.
- This policy does not claim that a quarantined latest row is harmless; it only prevents it from being mislabeled as the verified head.
