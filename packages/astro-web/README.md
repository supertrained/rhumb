# Rhumb public website

The production Vercel project is `team-supertraineds-projects/rhumb` and builds
this Astro application using the repository-root `vercel.json`. Root package
scripts target the separate Next.js application; they do not validate this site.

Run `npm ci` and `npm run build` from `packages/astro-web`. Keep
`packages/shared/pricing.json` available when building an isolated source copy.

## GA4 production configuration

- Canonical build variable: `PUBLIC_GA_ID=G-ZSC1S01BJ5`.
- GA4 property: `527907844`; web stream: `13884978146`.
- `NEXT_PUBLIC_GA_ID` is a legacy fallback. Values must have no whitespace.
- The shared layout emits the loader only when a measurement ID is available.
- The root content security policy permits Google's documented GA4 collection
  endpoints, including regional endpoints. Advertising endpoints are separate.

The measurement ID is public configuration, not a secret. Set the canonical
variable in the Vercel project's production environment before building.

`PUBLIC_CLARITY_ID` is deliberately empty in production. Keep it empty until
Clarity ownership and collection are verified; removing it activates the legacy
`NEXT_PUBLIC_CLARITY_ID` fallback during a fresh build.

Changing project environment variables does not repair existing prebuilt
artifacts. Redeploying a deployment containing `.vercel/output` can reuse those
artifacts without rebuilding the site. Build fresh source with the production
configuration, or supply that configuration before creating new prebuilt output.

Validate the deployment before promoting it: confirm the loader uses the exact
measurement ID, its normal page-view request succeeds, and GA4 receives the
event. Confirm the custom domain points to the validated deployment. A successful
build alone is not proof of collection. Keep any known collection-gap status in
the analytics feed until end-to-end verification succeeds.
