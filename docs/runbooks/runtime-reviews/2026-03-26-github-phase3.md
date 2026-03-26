# GitHub — Phase 3 runtime verification

Date: 2026-03-26
Operator: Pedro / Keel runtime loop
Status: passed

## Why GitHub

After the managed-provider lane closed, the callable providers with the thinnest true runtime-review coverage were the BYOK-only set: GitHub, Slack, Stripe, Twilio, and Unstructured. GitHub was the safest next verification target because it offers a non-mutating read path that still exercises real auth and execution plumbing.

## Inputs

- Capability: `social.get_profile`
- Provider: `github`
- Credential mode: `byo`
- Method/path: `GET /users/supertrained`

## Rhumb execution

### Estimate
- Endpoint: `GET /v1/capabilities/social.get_profile/execute/estimate?provider=github&credential_mode=byo`
- Result: **200 OK**
- Endpoint pattern returned: `GET /users/{username}`

### Execute
- Endpoint: `POST /v1/capabilities/social.get_profile/execute`
- Result: **200 OK**
- Execution id: `exec_50d308fd8e7f42f682cc5b51d640ff6d`
- Request id: `f4066f8e-c226-46bb-ba2d-738d0a702a4c`
- Upstream status: `200`
- Returned the public GitHub profile for `supertrained`

## Direct provider control

- Endpoint: `GET https://api.github.com/users/supertrained`
- Auth: bearer PAT
- Result: **200 OK**
- Returned the same profile object (`login=supertrained`, `public_repos=4`, matching timestamps)

## Comparison

| Check | Rhumb | Direct GitHub | Verdict |
|---|---:|---:|---|
| HTTP status | 200 | 200 | Match |
| Auth path | injected successfully | bearer PAT | Match |
| Payload identity | `login=supertrained` | `login=supertrained` | Match |

## Verdict

GitHub passes Phase 3 on the `social.get_profile` read path. Current execution plumbing is healthy for this provider/capability pair.

## Trust-surface action

- Published runtime evidence: `108b7f69-708c-41c3-9457-88a116e2279a`
- Published runtime review: `9972f9b1-6d53-4a88-92ad-6f5377b76609`

## Operator takeaway

GitHub is now no longer runtime-dark. The next zero-review BYOK lanes are Slack, Stripe, and Twilio; Unstructured remains architecture-blocked on multipart support.