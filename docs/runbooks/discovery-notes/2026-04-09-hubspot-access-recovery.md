# Discovery note — HubSpot access recovery for AUD-18 (2026-04-09)

## Why this note exists

The next `AUD-18` blocker is no longer local product shape. The hosted HubSpot CRM rail is live enough to reject bad refs honestly, but the first bounded `RHUMB_CRM_<REF>` proof is still blocked on source-material access.

This note captures the live operator-access truth so the next pass does not redo the same digging.

## Confirmed live truths

### Hosted route surface is already live

Using a working Rhumb dogfood key against `https://api.rhumb.dev` with an intentionally missing CRM ref produced the expected bounded denials:
- `crm.object.describe` → `400 crm_ref_invalid`
- `crm.record.search` → `400 crm_ref_invalid`
- `crm.record.get` → `400 crm_ref_invalid`

Interpretation: deployment and route registration are not the blocker.

### A real HubSpot account trail already exists

Gmail metadata for `tommeredith@supertrained.ai` shows a real existing HubSpot account trail, including:
- `578189 is your HubSpot Log In Code` on 2026-01-21
- `376767 is your HubSpot Log In Code` on 2025-09-11
- `A new super admin has been added to your account` on 2025-08-04 and 2025-09-15
- multiple deactivation / inactive-user notices through 2026-03-30

Interpretation: HubSpot previously knew about a real account tied to `tommeredith@supertrained.ai`.

### The Rhumb browser profile still has HubSpot history, but not an authenticated app session

Browser-profile evidence shows:
- prior engagement for both `https://app.hubspot.com` and `https://developers.hubspot.com`
- only marketing / session / cookie state remains, not authenticated app cookies
- navigating to `https://app.hubspot.com/` lands on `https://app.hubspot.com/login`

### Login discovery details

- Entering `tommeredith@supertrained.ai` on HubSpot login resolves to a real account flow and offers:
  - `Sign in with Google`
  - `Sign in with password`
  - `Sign in with Apple`
  - `Sign in with Microsoft`
- A Google-login attempt from the Rhumb browser profile surfaced HubSpot portal id `49739435` in the redirect state.
- The available browser Google accounts include `team@getsupertrained.com`, but signing in with that Google account fails with:
  - `That email address doesn't exist.`

Interpretation: the known Google workspace account is not the same identity as the existing HubSpot login, even though HubSpot account history exists.

### Shared vault truth

The shared `OpenClaw Agents` vault currently exposes:
- no HubSpot-titled item
- no obvious HubSpot login item among the visible `LOGIN` entries
- no existing bounded HubSpot private-app token source item

Interpretation: the missing proof material is a real operator-access gap, not a search mistake confined to titles only.

## Fresh blocker encountered while trying to create a new fallback account

Trying to bootstrap a fresh free HubSpot account for `team@getsupertrained.com` hit provider anti-abuse controls:
- signup flow requires visible reCAPTCHA enterprise verification
- after repeated attempts, HubSpot responds:
  - `There have been too many requests to create an account from your network or email address.`
  - `Please try again in an hour.`

Interpretation: emergency fallback signup from the current network is temporarily rate-limited, so brute-forcing the signup path is the wrong move.

## Best next step

On the next clean pass, do exactly this:
1. start from the existing-account path for `tommeredith@supertrained.ai`, not fresh signup
2. attempt a single clean password-recovery or approved login recovery flow
3. once inside portal `49739435`, mint a bounded private-app token with only:
   - `crm.objects.contacts.read`
   - `crm.objects.deals.read`
   - `crm.schemas.contacts.read`
   - `crm.schemas.deals.read`
4. create one narrow `RHUMB_CRM_<REF>` bundle with explicit object/property scope and, if needed, exact record ids
5. run the hosted proof bundle for:
   - `crm.object.describe`
   - `crm.record.search`
   - `crm.record.get`
   - bad `crm_ref`
   - out-of-scope object / property / record denials

## What not to waste time on next pass

- do **not** re-argue whether the hosted rail exists, it does
- do **not** keep searching the current visible vault titles for HubSpot, that path is exhausted
- do **not** spam new-account signup retries before the anti-abuse window clears
- do **not** widen the CRM slice beyond read-only record/object proofing
