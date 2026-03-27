# 2026-03-27 Email OTP `request-code` 500

## Summary

At approximately 2026-03-27 07:31 PT, production `POST /v1/auth/email/request-code`
returned a 500 instead of the generic success envelope. The most likely root cause is
that the email OTP schema migration was not applied in production before the API deploy.

## Evidence

- The request path calls `user_store.find_by_email()` first, but that store suppresses
  Supabase lookup errors and returns `None`, so it is unlikely to surface a raw 500.
- The next call is `EmailOtpService.request_code()`, which immediately queries
  `email_verification_codes` for throttling and active-code invalidation before email
  delivery starts.
- A missing or inaccessible `email_verification_codes` table reproduces the same 500
  envelope seen in production.
- The OTP schema exists in
  `packages/api/migrations/0103_email_otp_user_bootstrap.sql`, but before this incident
  there was no corresponding migration in `supabase/migrations/`, which is the repo's
  deploy-facing Supabase migration track.

## Most Likely Root Cause

Production did not have the `0103_email_otp_user_bootstrap` schema changes at deploy time,
especially the `email_verification_codes` table and related indexes/RLS policy.

## Immediate Remediation

1. Apply the SQL from
   `packages/api/migrations/0103_email_otp_user_bootstrap.sql`
   or `supabase/migrations/0010_email_otp_user_bootstrap.sql`
   to the production database using the production migration path.
2. Verify the schema:
   `select to_regclass('public.email_verification_codes');`
3. Verify the expected columns exist on `users`:
   `signup_method`, `email_verified_at`, `signup_ip`, `signup_subnet`, `credit_policy`,
   `risk_flags`.
4. Retry:
   `POST https://api.rhumb.dev/v1/auth/email/request-code`
   with a test inbox and confirm:
   - HTTP 200
   - envelope shape `{ "data": { "status": "ok", ... }, "error": null }`
   - a new row appears in `email_verification_codes`
   - the OTP email is delivered

## Follow-Up Guardrails

- Keep the OTP schema on the Supabase migration track as
  `supabase/migrations/0010_email_otp_user_bootstrap.sql`.
- The request-code route now logs and falls back to the generic success envelope if
  OTP storage fails before delivery, preserving the endpoint's anti-enumeration contract
  during future migration or storage regressions.
