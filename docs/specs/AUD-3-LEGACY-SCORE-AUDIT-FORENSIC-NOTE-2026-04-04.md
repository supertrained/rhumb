# AUD-3 Legacy Score-Audit Forensic Note

**Status:** Final  
**Date:** 2026-04-04  
**Owner:** Pedro  
**Scope:** `score_audit_chain` legacy tail verification

---

## Question

Can the currently anchored legacy `score_audit_chain` head be safely re-attributed to a preserved signing key version, or is the persisted row no longer reconstructible from the preserved truth surface?

## Target row

- Anchored head row: `saud_5565e543fcc248dbbe515e38103ac518`
- Persisted row fields in production:
  - `service_slug`: `stripe`
  - `old_score`: `8.1`
  - `new_score`: `8.1`
  - `change_reason`: `recalculation`
  - `created_at`: `2026-04-03T19:30:35.190409+00:00`
  - `prev_hash`: `cea54aebe81483d6f7b4bdc928b8b60a8c9aacc044f513d03c0cb1ae1f27d875`
  - `chain_hash`: `a1aaa8215369049fb485b66802cf9ad595d9867e93bfccd7cc334dcf7774ccf9`
  - `key_version`: `null`

## Method

Using the preserved Railway keyring and the live verifier logic (`build_score_audit_payload()` + `compute_chain_hmac()`):

1. Queried live `score_audit_chain` rows from production.
2. Recomputed the historical rows against preserved key versions `[0, 1]`.
3. Verified the older legacy row reproduces cleanly under key `0`.
4. Recomputed the anchored row against both preserved key versions.
5. Ran an exhaustive `old_score` / `new_score` sweep from `0.00` to `10.00` at `0.01` precision.

## Findings

1. The anchored row is not reproducible from the preserved row payload.
2. The exhaustive score sweep also produced no match.
3. The gap is sharper than “missing `key_version`”. The preserved truth surface is insufficient to reconstruct the signed message.

## Operational conclusion

Treat `saud_5565e543fcc248dbbe515e38103ac518` as a **legacy reconstruction-failure row**.

That means:
- do **not** backfill `key_version` without new evidence
- do **not** treat this row as the current verified head
- keep witnesses/checkpoints honest about a quarantined unverifiable tail

## Closure bar

This gap is closed only if one of these becomes true:
1. the row is reproducibly verified and safely backfilled with a real `key_version`, or
2. Rhumb ships explicit retirement/quarantine semantics for unverifiable historical rows and uses that truth in checkpoint / anchor publication.
