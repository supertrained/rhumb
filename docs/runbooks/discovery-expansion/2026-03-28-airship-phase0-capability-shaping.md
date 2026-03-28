# Airship Phase 0 capability shaping — 2026-03-28

Owner: Pedro
Status: shipped as the next blocked-safe lane while live x402 buyer proof stays wallet-blocked and Replicate direct-control health remains untrusted

## Why this lane now

The priority order was explicit:
- telemetry MVP is already shipped
- buyer-side x402 dogfood is still blocked on recovering the funded Awal wallet identity
- Google AI callable wiring is already live and rerun-verified
- the callable weakest bucket is down to a single provider: `replicate`

But Replicate was not a clean next move. The preliminary direct-control sanity check still returned `403`, and the service-account / secret path remains shaky enough that it should not consume the loop until it is clean again.

So the correct unblocked move was the documented fallback: **advance Airship Phase 0 capability shaping now**.

## Existing product truth

Airship already entered the catalog in:
- `rhumb/packages/api/migrations/0108_push_notifications_expansion.sql`

Current discovery position:
- service slug: `airship`
- category: `push-notifications`
- score: **8.20**
- execution: **8.35**
- access readiness: **7.95**

The earlier category memo already called Airship the strongest first implementation target in push notifications. This note turns that into a concrete Resolve shape.

## What the Airship docs confirm

### Core API contract
Airship’s current API is Version 3 and requires an explicit vendor Accept header:
- `Accept: application/vnd.urbanairship+json; version=3`

It supports:
- JSON request / response bodies
- standard HTTP response codes
- operation IDs on side-effecting calls
- both immediate success and queued async acceptance semantics

### Auth options
Airship exposes multiple auth paths:
- Basic auth
- bearer auth
- OAuth 2.0 access tokens

OAuth is real and scoped, which matters for future provider-managed access patterns:
- token endpoint on `oauth2.asnapius.com` / `oauth2.asnapieu.com`
- app-scoped subjects like `sub=app:{app_key}`
- relevant scopes include:
  - `psh` for push
  - `chn` for channels
  - `nu` for named users

### Send primitive
The critical Phase 0 primitive is live and clean:
- `POST /api/push`
- returns **202 Accepted**
- response includes `operation_id` and `push_ids`

That is a good Resolve fit because the acceptance boundary is explicit and machine-readable.

### Validation primitive
Airship also exposes a push validation endpoint using the same payload shape without actually sending.
That gives us a low-risk preflight rail for contract testing and provider debugging.

### Audience model
Airship’s audience semantics are concrete enough to normalize:
- channel IDs
- named users
- tags / tag groups
- segments / lists / schedules as future extensions

That is important because it means we do **not** have to invent a fake campaign abstraction to get Phase 0 value.

## Phase 0 gate answers

### 1) Zero-config access eliminated by routing through Rhumb?
**No.**

Push delivery is not like search or scraping. The operator still needs:
- an Airship app / project
- configured mobile or open-channel delivery rails
- opted-in destination channels or named-user mappings

Rhumb cannot eliminate that setup.

### 2) Still worth a Phase 0 even without zero-config?
**Yes.**

The value is not signup elimination. The value is:
- provider-neutral send semantics
- a cleaner execution contract for agents
- shared validation + telemetry + trust surfaces
- future alternative routing across Airship / Batch / FCM / Pusher Beams

This is a strong **normalization wedge**, not a zero-config wedge.

### 3) Is the provider surface real enough for execution?
**Yes.**

The docs expose a mature, explicit API for:
- send
- validate
- channels
- named users
- tags
- schedules
- reports

This is not speculative coverage.

### 4) Can we define a safe first runtime review rail?
**Yes, but only with a dedicated internal test audience.**

Because sends have user-visible side effects, runtime verification should use:
- a dedicated internal Airship test app or workspace
- a dedicated test named user / channel
- validation-first checks before live delivery checks

### 5) Are the async semantics acceptable for Resolve?
**Yes.**

`202 Accepted` plus `operation_id` / `push_ids` is good enough for a first execution contract. Resolve can define Phase 0 success as **request accepted by provider**, not guaranteed handset delivery.

### 6) What is the cleanest first audience abstraction?
**Named user + explicit channel / tag targeting.**

That gives us:
- one-to-one targeting (`push_notification.send_to_user`)
- group/topic-style targeting (`push_topic.publish`)
- raw send flexibility (`push_notification.send`)

### 7) What should we avoid in Phase 0?
Avoid starting with:
- full campaign / automation orchestration
- device registration flows
- schedule builders
- experimentation / A/B abstractions
- broad segment authoring

Those are real later surfaces, but they are not the first wedge.

## Recommended Resolve capability mapping

### 1) `push_notification.send`
**Airship mapping:** `POST /api/push`

Recommended normalized inputs:
- `message` / `alert`
- `device_types`
- one audience selector:
  - `channel_ids`
  - `named_user_id`
  - `tag`
  - `tag_group`
- optional provider payload overrides for platform-specific fields
- optional `validate_only`

Phase 0 success contract:
- Rhumb returns accepted state when Airship returns `202`
- capture `operation_id`
- capture `push_ids`
- do not overclaim delivery completion

### 2) `push_notification.send_to_user`
**Airship mapping:** same `POST /api/push`, but normalized around `named_user_id`

Why it matters:
- cleaner operator mental model than “build an audience object”
- strong fit for transactional agent workflows
- maps directly onto Airship named-user fanout semantics

Minimal normalized inputs:
- `named_user_id`
- `message`
- `device_types`
- optional metadata / deep-link fields

### 3) `push_topic.publish`
**Airship mapping:** same `POST /api/push`, but use tags / tag groups as the target primitive

Important normalization note:
Airship does **not** have a native “topic” abstraction in the same way some other providers do. The safest Rhumb mapping is:
- `topic` => tag value
- `topic_group` => Airship tag group

Do **not** silently assume an implicit default tag group in Phase 0. Make the group explicit so we avoid provider-specific magic.

## Recommended first execution slice

### Slice A — validation-first contract proof
Ship first if we want the lowest-risk provider wiring proof:
- use Airship validation to prove payload construction
- verify auth, headers, audience shaping, and error handling
- no end-user-visible side effect

### Slice B — controlled live send proof
Ship second once a safe test audience exists:
- one dedicated internal named user or channel
- one real send through `push_notification.send_to_user`
- capture accepted response, `operation_id`, and `push_ids`
- optionally confirm downstream visibility from Airship reporting / UI if available

### Why this order
Push is side-effectful. Validation-first lets us harden the provider contract before we risk noisy live sends.

## Telemetry and trust-surface implications

If Airship becomes callable, telemetry should capture at minimum:
- provider slug
- capability id
- audience mode (`channel`, `named_user`, `tag_group`)
- device type count / mix
- validation-only vs live-send
- upstream status code
- `operation_id`
- request latency
- credential mode

Trust-surface note:
For push providers, the first public runtime-backed review should explicitly state whether the proof was:
- validation-only, or
- real accepted send to a controlled internal audience

Do not blur those.

## Risks / blockers

### Still needed before execution wiring
- an internal Airship credential set
- a dedicated test app / workspace if not already available
- at least one controlled destination audience

### Product risk
Push APIs are easy to over-normalize. If we hide too much audience detail, we create a fake abstraction and lose operator trust.

### Design rule
Keep Phase 0 honest:
- normalize the common send contract
- expose provider-specific audience / payload details as explicit optional fields
- never imply guaranteed delivery when the provider only confirmed acceptance

## Recommendation

**Make Airship the first push-notifications execution target.**

But do it with a strict Phase 0 shape:
1. start with `push_notification.send`
2. add `push_notification.send_to_user` as the clean transactional wrapper
3. map `push_topic.publish` only through explicit Airship tag-group semantics
4. define success as provider acceptance, not handset delivery
5. require a dedicated internal test audience before live runtime verification

## Net

Replicate remains the last callable weakest-bucket provider, but it is not currently the cleanest lane.

**Airship is now the correct next discovery-to-execution bridge:**
- the API surface is real
- the normalization wedge is clear
- the capability mapping is concrete
- the next implementation slice can be scoped without pretending push is zero-config
