# Rhumb Resolve — Founding Product Specification

**Version:** 1.0  
**Date:** 2026-03-30  
**Author:** Pedro (Rhumb operator) — synthesized from 4 expert panels (50 experts)  
**Status:** AUTHORITATIVE — Engineering-grade founding document  
**Classification:** Internal — Pre-launch

> **Historical route-authority note (2026-04-09):** This founding spec captures the 2026-03-30 Resolve v2 target architecture. It is **not** the live route authority. The current machine-readable public contract publishes `https://api.rhumb.dev/v1` as the default `api_base` in `agent-capabilities.json`, while `packages/api/app.py` still mounts a mixed live surface with specific Resolve families under `/v2`. Use `docs/API.md` plus `agent-capabilities.json` for current integration truth, and read this document as design history plus architecture intent.

---

## Executive Summary

Rhumb Resolve is a **managed execution substrate** for AI agents. It is not an agent, not a planner, not an orchestrator. It provides three precisely-scoped layers of API surface:

1. **Layer 1 — Raw Provider Access:** Transparent credential + billing proxy to named providers
2. **Layer 2 — Single Capability Delivery:** Stable-schema capability execution with intelligent routing (primary product surface)
3. **Layer 3 — Deterministic Composed Capabilities:** Pre-compiled multi-step recipes with traceable execution (premium layer)

**What Resolve is NOT:**
- NOT an agent behind the agent
- NOT a hidden planner or open-ended orchestrator
- NOT a black-box outcome engine
- Resolve **COMPILES** workflows, it does **NOT** improvise business intent

**Current state:** 1,038 services, 415 capabilities, 92 categories, 16 callable providers, Railway deployment, Supabase DB, MCP server with 21 tools, Stripe prepaid credits + x402 USDC payments.

**This spec defines:** How to evolve from the current state to the Resolve architecture without breaking existing users, while adding Layer 1 (raw access), enhancing Layer 2 (intelligent routing + policy), and introducing Layer 3 (recipes) as a premium tier.

---

## Table of Contents

### Part I: Expert Panel Reports
- [Panel 1: Product Architecture & API Design](#part-i-panel-1-product-architecture--api-design)
- [Panel 2: Trust, Observability & Governance](#part-i-panel-2-trust-observability--governance)
- [Panel 3: Economics, Billing & Scaling](#part-i-panel-3-economics-billing--scaling)
- [Panel 4: Adversarial, Failure Modes & Edge Cases](#part-i-panel-4-adversarial-failure-modes--edge-cases)

### Part II: Unified Synthesis
1. [Complete API Specification](#1-complete-api-specification)
2. [Capability Contract Standard](#2-capability-contract-standard)
3. [Recipe Standard](#3-recipe-standard)
4. [Provider Adapter Standard](#4-provider-adapter-standard)
5. [Policy Control Specification](#5-policy-control-specification)
6. [Execution Receipt Specification](#6-execution-receipt-specification)
7. [Pricing and Billing Specification](#7-pricing-and-billing-specification)
8. [Trust and Neutrality Specification](#8-trust-and-neutrality-specification)
9. [Security and Abuse Specification](#9-security-and-abuse-specification)
10. [90-Day Implementation Plan](#10-90-day-implementation-plan)
11. [Decision Register](#11-decision-register)
12. [Open Questions](#12-open-questions)

---

# Part I: Expert Panel Reports

The following sections are the direct output from four expert panels, each comprising domain specialists who contributed engineering-grade specifications for their area.

---

## Part I, Panel 1: Product Architecture & API Design

*14 experts: API gateway architects, developer tools PMs, platform API designers, schema architects, DX specialists, multi-tenant SaaS architects, capability modeling experts, protocol designers*

### 1.1 Three-Layer API Surface

**URL Namespacing:**

```
Base URL: https://api.rhumb.dev

Layer 1 (Raw Provider):     /v2/providers/{provider_id}/execute
Layer 2 (Capability):       /v2/capabilities/{capability_id}/execute
Layer 3 (Recipe):           /v2/recipes/{recipe_id}/execute

Discovery:                  /v2/capabilities
                            /v2/providers
                            /v2/recipes

Policy:                     /v2/policy
Receipt/Trace:              /v2/receipts/{receipt_id}
Health:                     /v2/health
```

**Universal Request Headers:**

```
Authorization: Bearer {api_key}              # Required
X-Rhumb-Version: 2026-03-30                  # Optional: date-pinned API version
X-Rhumb-Idempotency-Key: {uuid}              # Optional: idempotent retry key
X-Rhumb-Agent-Id: {agent_identifier}         # Optional: agent identity for audit
X-Rhumb-Budget-Token: {budget_token}         # Optional: per-call budget override
Content-Type: application/json
```

#### Layer 1 — Raw Provider Access

**Endpoint:** `POST /v2/providers/{provider_id}/execute`

```json
// Request
{
  "capability": "chat.completions",
  "parameters": {
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Summarize the following: ..."}],
    "max_tokens": 500,
    "temperature": 0.7
  },
  "credential_mode": "rhumb_managed",
  "policy": {
    "timeout_ms": 30000,
    "max_cost_usd": 0.10
  }
}

// Response (200 OK)
{
  "receipt_id": "rcpt_01HX9K2M3N4P5Q6R7S8T9U0V1W",
  "layer": 1,
  "provider": {
    "id": "openai",
    "display_name": "OpenAI",
    "capability_used": "chat.completions"
  },
  "result": {
    "raw": {
      "id": "chatcmpl-abc123",
      "choices": [{"message": {"role": "assistant", "content": "Here is the summary..."}, "finish_reason": "stop"}],
      "usage": {"prompt_tokens": 120, "completion_tokens": 85, "total_tokens": 205}
    }
  },
  "cost": {
    "provider_cost_usd": 0.00205,
    "rhumb_fee_usd": 0.0002,
    "total_usd": 0.00225,
    "credits_deducted": 0.00225
  },
  "latency": {
    "total_ms": 1247,
    "provider_ms": 1198,
    "rhumb_overhead_ms": 49
  },
  "executed_at": "2026-03-30T20:42:00.000Z"
}
```

```bash
curl -X POST https://api.rhumb.dev/v2/providers/openai/execute \
  -H "Authorization: Bearer rk_live_abc123" \
  -H "Content-Type: application/json" \
  -d '{"capability":"chat.completions","parameters":{"model":"gpt-4o","messages":[{"role":"user","content":"Hello world"}]},"credential_mode":"rhumb_managed"}'
```

#### Layer 2 — Single Capability Delivery

**Endpoint:** `POST /v2/capabilities/{capability_id}/execute`

```json
// Request
{
  "parameters": {
    "to": "user@example.com",
    "subject": "Your report is ready",
    "body": "Please find attached...",
    "from_name": "Acme Corp"
  },
  "policy": {
    "provider_preference": ["sendgrid", "mailgun"],
    "provider_deny": ["mailchimp"],
    "max_cost_usd": 0.01,
    "timeout_ms": 10000,
    "retry": {"max_attempts": 3, "backoff": "exponential", "backoff_base_ms": 500},
    "fallback": "next_available"
  },
  "credential_mode": "rhumb_managed",
  "idempotency_key": "send-report-user-42-2026-03-30"
}

// Response (200 OK)
{
  "receipt_id": "rcpt_02HY0L3N4O5P6Q7R8S9T0U1V2W",
  "layer": 2,
  "capability": {"id": "send_email", "version": "1.2.0", "normalized": true},
  "provider": {
    "id": "sendgrid",
    "display_name": "SendGrid",
    "selection_reason": "preferred_by_policy",
    "alternatives_considered": ["mailgun", "postmark"]
  },
  "result": {
    "normalized": {
      "status": "delivered",
      "message_id": "msg_01HX9K2M3N4P5Q6R",
      "delivered_at": "2026-03-30T20:42:01.000Z"
    }
  },
  "cost": {
    "provider_cost_usd": 0.0001,
    "rhumb_fee_usd": 0.00005,
    "total_usd": 0.00015,
    "credits_deducted": 0.00015
  },
  "latency": {
    "total_ms": 342,
    "provider_ms": 290,
    "normalization_ms": 12,
    "routing_ms": 8,
    "rhumb_overhead_ms": 52
  },
  "routing": {
    "candidates_evaluated": 3,
    "policy_applied": true,
    "selected_reason": "policy_preference_match"
  },
  "executed_at": "2026-03-30T20:42:01.000Z"
}
```

```bash
curl -X POST https://api.rhumb.dev/v2/capabilities/send_email/execute \
  -H "Authorization: Bearer rk_live_abc123" \
  -H "Content-Type: application/json" \
  -d '{"parameters":{"to":"user@example.com","subject":"Hello","body":"This is a test"},"credential_mode":"rhumb_managed"}'
```

#### Layer 3 — Recipe Execution

**Endpoint:** `POST /v2/recipes/{recipe_id}/execute`

```json
// Request
{
  "inputs": {
    "audio_url": "https://storage.example.com/meeting-recording.mp3",
    "recipient_email": "team@example.com",
    "summary_length": "short"
  },
  "policy": {
    "max_total_cost_usd": 0.50,
    "timeout_ms": 120000,
    "approval_mode": "auto",
    "on_step_failure": "halt_and_report"
  },
  "credential_mode": "rhumb_managed"
}

// Response (200 OK — synchronous for short recipes)
{
  "receipt_id": "rcpt_03HZ1M4O5P6Q7R8S9T0U1V2W3X",
  "layer": 3,
  "recipe": {"id": "transcribe_and_summarize_and_email", "version": "2.1.0", "steps_total": 3, "steps_completed": 3},
  "status": "completed",
  "result": {
    "outputs": {
      "transcript": "The meeting covered Q1 targets...",
      "summary": "Team aligned on three priorities for Q1...",
      "email_sent": true,
      "email_message_id": "msg_02HY0L3N4O5P6Q"
    },
    "artifacts": {
      "transcript_artifact_id": "art_01HX9K2",
      "summary_artifact_id": "art_01HX9K3"
    }
  },
  "steps": [
    {"step_id": "transcribe", "capability_id": "transcribe_audio", "provider_used": "deepgram", "status": "completed", "cost_usd": 0.0240, "latency_ms": 8420, "artifact_id": "art_01HX9K2"},
    {"step_id": "summarize", "capability_id": "summarize_text", "provider_used": "anthropic", "status": "completed", "cost_usd": 0.0180, "latency_ms": 2100, "artifact_id": "art_01HX9K3"},
    {"step_id": "notify", "capability_id": "send_email", "provider_used": "sendgrid", "status": "completed", "cost_usd": 0.0001, "latency_ms": 290}
  ],
  "cost": {"total_usd": 0.0421, "rhumb_fee_usd": 0.0042, "grand_total_usd": 0.0463, "credits_deducted": 0.0463},
  "latency": {"total_ms": 10850, "step_ms": 10810, "orchestration_ms": 40},
  "executed_at": "2026-03-30T20:42:00.000Z",
  "completed_at": "2026-03-30T20:42:10.850Z"
}
```

**Long-running recipes return 202 Accepted:**

```json
{
  "receipt_id": "rcpt_04HA2N5P6Q7R8S9T0U1V2W3X4Y",
  "status": "running",
  "poll_url": "https://api.rhumb.dev/v2/receipts/rcpt_04HA2N5P6Q7R8S9T0U1V2W3X4Y",
  "estimated_duration_ms": 45000
}
```

#### Discovery & Management Endpoints

```
GET  /v2/capabilities                    # List capabilities (filterable by category, provider, q)
GET  /v2/capabilities/{capability_id}    # Get capability schema
GET  /v2/providers                       # List providers (filterable by capability, status)
GET  /v2/recipes                         # List recipes (filterable by category, stability)
GET  /v2/recipes/{recipe_id}             # Get recipe schema
GET  /v2/receipts/{receipt_id}           # Get execution receipt
GET  /v2/policy                          # Get current policy
PUT  /v2/policy                          # Replace policy
PATCH /v2/policy                         # Partial update
DELETE /v2/policy                        # Reset to defaults
```

### 1.2 Capability Contract Schema

The canonical JSON Schema for defining a Rhumb capability:

```json
{
  "$schema": "https://schema.rhumb.dev/capability/v1",
  "id": "send_email",
  "name": "Send Email",
  "version": "1.2.0",
  "category": "communication",
  "subcategory": "email",
  "stability": "stable",
  "description": "Send a transactional or marketing email via the best available provider.",
  "tags": ["email", "notification", "transactional"],
  
  "parameters": {
    "type": "object",
    "required": ["to", "subject", "body"],
    "properties": {
      "to": {"type": "string", "format": "email"},
      "to_name": {"type": "string", "maxLength": 255},
      "from": {"type": "string", "format": "email"},
      "from_name": {"type": "string", "maxLength": 255},
      "subject": {"type": "string", "maxLength": 998},
      "body": {"type": "string"},
      "body_format": {"type": "string", "enum": ["text", "html"], "default": "text"},
      "reply_to": {"type": "string", "format": "email"},
      "attachments": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["filename", "content", "content_type"],
          "properties": {
            "filename": {"type": "string"},
            "content": {"type": "string", "description": "Base64-encoded content"},
            "content_type": {"type": "string"}
          }
        }
      }
    },
    "additionalProperties": false
  },
  
  "response": {
    "type": "object",
    "required": ["status", "message_id"],
    "properties": {
      "status": {"type": "string", "enum": ["queued", "delivered", "failed"]},
      "message_id": {"type": "string"},
      "delivered_at": {"type": "string", "format": "date-time"},
      "provider_message_id": {"type": "string"}
    }
  },
  
  "provider_requirements": {
    "minimum_providers": 1,
    "providers": [
      {"provider_id": "sendgrid", "tier": "preferred", "capabilities_required": ["mail.send"]},
      {"provider_id": "mailgun", "tier": "standard", "capabilities_required": ["messages"]},
      {"provider_id": "postmark", "tier": "standard", "capabilities_required": ["email"]},
      {"provider_id": "ses", "tier": "fallback", "capabilities_required": ["SendEmail"], "notes": "Requires BYO credentials"}
    ]
  },
  
  "credential_modes": {"supported": ["byo", "rhumb_managed", "agent_vault"], "default": "rhumb_managed"},
  
  "pricing_hints": {
    "pricing_model": "per_call",
    "estimated_cost_usd": {"min": 0.00005, "max": 0.001, "typical": 0.0001},
    "cost_factors": ["attachment_size_bytes"]
  },
  
  "rate_limit_metadata": {
    "default_limits": {"requests_per_second": 10, "requests_per_minute": 300, "requests_per_day": 10000},
    "burst_allowed": true,
    "burst_multiplier": 2.0,
    "rate_limit_scope": "per_api_key"
  },
  
  "idempotency": {"supported": true, "key_field": "idempotency_key", "window_seconds": 86400},
  "timeouts": {"default_ms": 10000, "max_ms": 30000, "min_ms": 1000},
  
  "changelog": [
    {"version": "1.2.0", "date": "2026-02-15", "changes": ["Added attachment support", "Added reply_to field"]},
    {"version": "1.0.0", "date": "2025-12-01", "changes": ["Initial stable release"]}
  ]
}
```

### 1.3 Recipe Definition Schema

```json
{
  "$schema": "https://schema.rhumb.dev/recipe/v1",
  "recipe_id": "transcribe_and_summarize_and_email",
  "name": "Transcribe, Summarize & Email",
  "version": "2.1.0",
  "category": "productivity",
  "stability": "stable",
  "tier": "premium",
  
  "inputs": {
    "type": "object",
    "required": ["audio_url", "recipient_email"],
    "properties": {
      "audio_url": {"type": "string", "format": "uri"},
      "recipient_email": {"type": "string", "format": "email"},
      "summary_length": {"type": "string", "enum": ["short", "medium", "long"], "default": "medium"},
      "email_subject": {"type": "string", "default": "Meeting Summary"}
    }
  },
  
  "outputs": {
    "type": "object",
    "properties": {
      "transcript": {"type": "string"},
      "summary": {"type": "string"},
      "email_sent": {"type": "boolean"},
      "email_message_id": {"type": "string"}
    }
  },
  
  "steps": [
    {
      "step_id": "transcribe",
      "capability_id": "transcribe_audio",
      "capability_version": "^2.0.0",
      "depends_on": [],
      "parameters": {"audio_url": {"$ref": "inputs.audio_url"}, "language": "en", "format": "text"},
      "outputs_captured": {"transcript_text": "result.transcript"},
      "artifact_capture": {"enabled": true, "artifact_key": "transcript_artifact", "ttl_hours": 168},
      "failure_mode": {"on_failure": "halt", "retries": 2, "retry_backoff": "exponential", "retry_base_ms": 1000},
      "budget": {"max_cost_usd": 0.10, "timeout_ms": 60000}
    },
    {
      "step_id": "summarize",
      "capability_id": "summarize_text",
      "capability_version": "^1.0.0",
      "depends_on": ["transcribe"],
      "parameters": {"text": {"$ref": "steps.transcribe.outputs.transcript_text"}, "length": {"$ref": "inputs.summary_length"}},
      "outputs_captured": {"summary_text": "result.summary"},
      "artifact_capture": {"enabled": true, "artifact_key": "summary_artifact", "ttl_hours": 168},
      "failure_mode": {"on_failure": "halt", "retries": 1},
      "budget": {"max_cost_usd": 0.05, "timeout_ms": 30000}
    },
    {
      "step_id": "notify",
      "capability_id": "send_email",
      "capability_version": "^1.0.0",
      "depends_on": ["summarize"],
      "parameters": {"to": {"$ref": "inputs.recipient_email"}, "subject": {"$ref": "inputs.email_subject"}, "body": {"$ref": "steps.summarize.outputs.summary_text"}},
      "failure_mode": {"on_failure": "continue", "retries": 3, "notes": "Email failure is non-fatal"},
      "budget": {"max_cost_usd": 0.01, "timeout_ms": 15000}
    }
  ],
  
  "dag": {
    "edges": [{"from": "transcribe", "to": "summarize"}, {"from": "summarize", "to": "notify"}],
    "critical_path": ["transcribe", "summarize", "notify"]
  },
  
  "budget": {"max_total_cost_usd": 0.50, "per_step_budgets_enforced": true, "on_budget_exceeded": "halt_current_step"},
  "timeout": {"total_ms": 120000, "per_step_timeout_enforced": true},
  "idempotency": {"supported": true, "window_seconds": 3600}
}
```

### 1.4 Provider Adapter Interface

**Registration Schema:**
```json
{
  "$schema": "https://schema.rhumb.dev/adapter/v1",
  "adapter_id": "sendgrid",
  "display_name": "SendGrid",
  "version": "3.0.0",
  "base_url": "https://api.sendgrid.com",
  "auth": {"methods": ["api_key"], "primary_method": "api_key", "api_key_header": "Authorization", "api_key_prefix": "Bearer"},
  "capabilities_supported": [
    {"rhumb_capability_id": "send_email", "rhumb_capability_version": "^1.0.0", "provider_endpoint": "POST /mail/send", "adapter_handler": "handlers/send_email.js"}
  ],
  "health_check": {"endpoint": "GET /user/profile", "expected_status": 200, "timeout_ms": 5000, "check_interval_seconds": 60},
  "rate_limits": {"global": {"requests_per_second": 100, "requests_per_day": 100000}},
  "error_mapping": {
    "400": {"rhumb_code": "INVALID_PARAMETERS", "retryable": false},
    "401": {"rhumb_code": "CREDENTIAL_INVALID", "retryable": false},
    "429": {"rhumb_code": "RATE_LIMITED", "retryable": true},
    "500": {"rhumb_code": "PROVIDER_ERROR", "retryable": true},
    "503": {"rhumb_code": "PROVIDER_UNAVAILABLE", "retryable": true}
  }
}
```

**Handler Contract (TypeScript):**
```typescript
interface CapabilityHandler {
  buildRequest(params: Record<string, unknown>, credentials: InjectedCredentials, context: ExecutionContext): ProviderRequest;
  normalizeResponse(raw: ProviderResponse, context: ExecutionContext): NormalizedResult;
  mapError(error: ProviderError, context: ExecutionContext): RhumbError;
  computeCost(response: ProviderResponse, context: ExecutionContext): CostBreakdown | null;
}

interface InjectedCredentials {
  mode: "byo" | "rhumb_managed" | "agent_vault";
  api_key?: string;
  oauth_token?: string;
  // Credentials are never logged or returned to caller
}
```

### 1.5 Error Envelope Design

Every error response uses the same envelope across all three layers:

```json
{
  "error": {
    "code": "PROVIDER_ERROR",
    "category": "provider",
    "message": "The provider returned an internal server error",
    "detail": "SendGrid API returned HTTP 500...",
    "retryable": true,
    "retry_after_ms": 2000,
    "receipt_id": "rcpt_01HX9K2M3N4P5Q6R",
    "provider": {
      "id": "sendgrid",
      "http_status": 500,
      "provider_error_code": "from_address_not_verified",
      "provider_message": "The from address does not match a verified Sender Identity"
    },
    "request_id": "req_01HX9K2M3N4P5Q6R7S8T",
    "docs_url": "https://docs.rhumb.dev/errors/PROVIDER_ERROR",
    "timestamp": "2026-03-30T20:42:01.234Z"
  }
}
```

**Error Code Registry:**

| Code | Category | HTTP | Retryable | Description |
|------|----------|------|-----------|-------------|
| `INVALID_PARAMETERS` | client | 400 | No | Schema validation failed |
| `MISSING_REQUIRED_FIELD` | client | 400 | No | Required parameter absent |
| `CAPABILITY_NOT_FOUND` | client | 404 | No | Capability ID does not exist |
| `PROVIDER_NOT_FOUND` | client | 404 | No | Provider ID does not exist |
| `RECIPE_NOT_FOUND` | client | 404 | No | Recipe ID does not exist |
| `CREDENTIAL_INVALID` | auth | 401 | No | API key invalid or expired |
| `CREDENTIAL_MISSING` | auth | 401 | No | Authorization header absent |
| `PERMISSION_DENIED` | auth | 403 | No | API key lacks required permission |
| `BUDGET_EXCEEDED` | policy | 402 | No | Call would exceed cost ceiling |
| `RATE_LIMITED` | policy | 429 | Yes | Rhumb-level rate limit hit |
| `PROVIDER_RATE_LIMITED` | provider | 429 | Yes | Provider rate limit hit |
| `APPROVAL_REQUIRED` | policy | 202 | N/A | Call requires manual approval |
| `PROVIDER_ERROR` | provider | 502 | Yes | Provider returned 5xx |
| `PROVIDER_UNAVAILABLE` | provider | 503 | Yes | Provider health check failing |
| `NO_PROVIDER_AVAILABLE` | routing | 503 | Yes | All providers unavailable |
| `PROVIDER_TIMEOUT` | provider | 504 | Yes | Provider did not respond |
| `NORMALIZATION_ERROR` | internal | 500 | No | Response normalization failed |
| `RECIPE_STEP_FAILED` | recipe | 422 | Partial | Recipe step(s) failed |
| `RECIPE_BUDGET_EXCEEDED` | recipe | 402 | No | Recipe cost exceeded budget |
| `TIMEOUT` | infra | 504 | Yes | Overall request timeout |
| `INTERNAL_ERROR` | internal | 500 | Yes | Rhumb internal error |

**Partial Success (HTTP 207 Multi-Status)** for recipes with mixed step results — includes per-step status and error details.

### 1.6 Versioning Strategy

**Capabilities:** Semver with strict breaking change rules. Breaking changes → new major version → 90-day deprecation window → `X-Rhumb-Deprecation` header.

**API Surface:** Date-based versioning via `X-Rhumb-Version: 2026-03-30`. Date-pinned versions honored for 2 years.

**Provider Adapters:** Semver. Patch bumps transparent; minor bumps for normalization behavior changes.

### 1.7 Migration Path

The existing `/v1/capabilities/{id}/execute` endpoint maps to Layer 2 in the new architecture.

**v1 Compatibility Layer:** `/v1/` preserved indefinitely. v1 requests translated to v2 internally, responses translated back to v1 shape. Zero agent action required.

**Progressive Migration:**
1. Phase 1 (Month 1): v2 gateway behind existing `/v1/` — transparent, no client changes
2. Phase 2 (Month 2): `/v2/` endpoints published; Layer 1 available in beta
3. Phase 3 (Month 3-4): Layer 3 recipes available in beta
4. Phase 4 (Month 6): v1 enters soft deprecation with 12-month notice
5. Phase 5 (Month 18): v1 returns 410 Gone with redirect

**Header opt-in:** `X-Rhumb-API: v2` on `/v1/` requests returns full v2 response shape.

### 1.8 MCP Tool Interface

12 MCP tools consolidated from current 17, organized by layer:

| Tool | Layer | Tier |
|------|-------|------|
| `rhumb_execute` | 2 | All |
| `rhumb_list_capabilities` | 2 | All |
| `rhumb_get_capability` | 2 | All |
| `rhumb_get_receipt` | all | All |
| `rhumb_get_policy` | all | All |
| `rhumb_update_policy` | all | All |
| `rhumb_get_balance` | all | All |
| `rhumb_raw_execute` | 1 | Standard+ |
| `rhumb_list_providers` | 1 | Standard+ |
| `rhumb_recipe_execute` | 3 | Premium |
| `rhumb_list_recipes` | 3 | Premium |
| `rhumb_get_recipe` | 3 | Premium |

**TypeScript SDK reference:**
```typescript
import { RhumbClient } from "@rhumb/sdk";
const rhumb = new RhumbClient({ apiKey: process.env.RHUMB_API_KEY });

// Layer 2
const result = await rhumb.capabilities.execute("send_email", {
  parameters: { to: "user@example.com", subject: "Hello", body: "World" },
  policy: { maxCostUsd: 0.01 }
});

// Layer 1
const rawResult = await rhumb.providers.execute("openai", {
  capability: "chat.completions",
  parameters: { model: "gpt-4o", messages: [...] }
});

// Layer 3
const recipeResult = await rhumb.recipes.execute("transcribe_and_summarize", {
  inputs: { audioUrl: "https://...", recipientEmail: "..." }
});
```

---

## Part I, Panel 2: Trust, Observability & Governance

*12 experts: Trust systems architects, observability builders, audit/compliance specialists, data governance experts, provider relations strategists, neutrality/marketplace fairness experts, SRE/reliability engineers*

### 2.1 Execution Receipt System

Every execution produces an immutable, self-contained receipt. Receipts are the atomic unit of observability — the ground truth for billing, debugging, compliance, and auditing.

**Core Receipt Schema:**
```json
{
  "$schema": "https://schemas.rhumb.ai/resolve/receipt/v1",
  "receipt_id": "rcpt_01HX4K7M9N3P5Q8R2S6T0W",
  "receipt_version": "1.0",
  "created_at": "2026-03-30T20:43:00.000Z",
  "execution": {
    "execution_id": "exec_01HX4K7M9N3P5Q8R2S6T0V",
    "layer": 2,
    "capability_id": "cap_image_generation_text_to_image",
    "capability_version": "1.2.0",
    "status": "success",
    "attempt_number": 1
  },
  "identity": {
    "agent_id": "agent_01HX4K7M",
    "agent_key_id": "key_01HX4K7M",
    "workspace_id": "ws_01HX4K7M",
    "caller_ip_hash": "sha256:a1b2c3d4..."
  },
  "provider": {
    "provider_id": "openai",
    "provider_name": "OpenAI",
    "provider_model": "dall-e-3",
    "credential_mode": "rhumb_managed",
    "provider_region": "us-east-1",
    "provider_latency_ms": 2100
  },
  "routing": {
    "router_version": "2.1.4",
    "candidates_evaluated": 3,
    "winner_reason": "best_composite_score",
    "route_explanation_id": "rexp_01HX4K7M"
  },
  "timing": {
    "total_latency_ms": 2347,
    "rhumb_overhead_ms": 247,
    "provider_latency_ms": 2100
  },
  "cost": {
    "currency": "USD",
    "provider_cost": 0.040,
    "rhumb_fee": 0.004,
    "total_cost": 0.044
  },
  "payload_hash": {
    "request_hash": "sha256:f3a9c2e1...",
    "response_hash": "sha256:b7d4e8f2..."
  },
  "integrity": {
    "receipt_hash": "sha256:9f1c3b7a...",
    "previous_receipt_hash": "sha256:2e4d6f8a...",
    "chain_sequence": 10483,
    "signing_key_id": "rhumb_receipt_signing_key_v3"
  }
}
```

**Storage Tiers:** Hot (PostgreSQL, 30 days) → Warm (S3 Parquet, 30-365 days) → Cold (Glacier, compliance retention).

**Retention Policies:**
| Policy | Total Retention |
|--------|----------------|
| `ret_standard_90d` | 90 days |
| `ret_standard_1y` | 365 days |
| `ret_compliance_7y` | 7 years |
| `ret_gdpr_delete` | Until deletion request |

### 2.2 Provider Attribution Model

**Guarantee:** At every layer, in every response, the provider that executed the work is explicitly identified. Abstraction does not mean erasure.

**Response Headers (always present):**
```
X-Rhumb-Provider: openai
X-Rhumb-Provider-Model: dall-e-3
X-Rhumb-Provider-Region: us-east-1
X-Rhumb-Receipt-Id: rcpt_01HX4K7M
X-Rhumb-Layer: 2
X-Rhumb-Cost-Usd: 0.044
```

**Response body `_rhumb` block:** Every response includes provider identity, logo URL, docs URL, cost, latency, and explanation link.

**Attribution in errors:** Provider errors are never swallowed — error envelopes always include provider identity and raw provider error message.

### 2.3 Route Explanation Engine

Every routing decision produces a complete, queryable explanation:

```json
{
  "explanation_id": "rexp_01HX4K7M",
  "winner": {"provider_id": "openai", "composite_score": 0.847, "selection_reason": "highest_composite_score_within_policy"},
  "candidates": [
    {
      "provider_id": "openai",
      "eligible": true,
      "composite_score": 0.847,
      "factors": {
        "an_score": {"value": 0.89, "weight": 0.20, "weighted_contribution": 0.178},
        "availability": {"value": 0.999, "weight": 0.30, "weighted_contribution": 0.300},
        "estimated_cost_usd": {"normalized_score": 0.72, "weight": 0.25, "weighted_contribution": 0.180},
        "latency_p50_ms": {"normalized_score": 0.75, "weight": 0.15, "weighted_contribution": 0.113},
        "credential_mode_preference": {"score": 1.0, "weight": 0.10, "weighted_contribution": 0.100}
      },
      "policy_checks": {"pinned": false, "denied": false, "region_allowed": true, "cost_ceiling_ok": true}
    }
  ],
  "human_summary": "OpenAI (DALL-E 3) selected over 2 other candidates. Midjourney excluded by deny list. OpenAI won on composite score driven by strong availability (99.9%) and highest AN Score (0.89)."
}
```

### 2.4 AN Score Integration

**Structural Separation Architecture:**

The AN Score is computed by a structurally independent service with NO write access to the routing database and NO access to commercial data.

```
ROUTING ENGINE ──(reads)──> SCORE CACHE (read-only snapshot)
AN SCORING SERVICE ──(writes)──> SCORE DB ──(refreshes)──> SCORE CACHE
COMMERCIAL SERVICE ──(separate DB)──> COMMERCIAL DB (no join to SCORE DB)
```

**AN Score Dimensions (0.0-1.0):**
- API Stability (25%): Breaking change frequency
- Pricing Transparency (25%): Pricing clarity + change notice
- Data Handling (25%): ToS analysis + opt-out availability
- Agent Treatment (25%): Rate limit fairness + error quality

**Firewalls:**
1. Database-level: No foreign keys between Score DB and Commercial DB
2. Process-level: Scoring pipeline has no access to commercial agreements
3. Audit-level: Score changes co-occurring with commercial changes within 30 days trigger auto-flag
4. Publication: Scores published publicly before loaded into routing cache

### 2.5 SLA Framework

| Metric | Layer 1 | Layer 2 | Layer 3 |
|--------|---------|---------|---------|
| Availability | 99.9% | 99.9% | 99.5% |
| Rhumb Overhead P50 | <25ms | <50ms | <100ms |
| Rhumb Overhead P99 | <100ms | <200ms | <500ms |
| Error Rate (Rhumb-caused) | <0.1% | <0.5% | <1.0% |
| Receipt Write Success | 99.99% | 99.99% | 99.99% |
| Policy Evaluation Correctness | 100% | 100% | 100% |

**Graceful Degradation (4 levels):** Level 0 (Normal) → Level 1 (Route explanations delayed) → Level 2 (Score cache stale) → Level 3 (Receipt writes failing, execution blocked) → Level 4 (Routing DB unavailable, Layer 1 only).

### 2.6 Incident Response

**Auto-detection triggers:** Provider error spike (>20% in 5min), total outage (<1% success), recipe failure cascade (>30%), cost spike (3x vs prior week), receipt write failure (>0.1%), routing latency spike (P99 >500ms).

**Circuit breakers:** Per-provider, per-capability. States: CLOSED → OPEN (blocking) → HALF_OPEN (probing) → CLOSED.

**Escalation:** P1 (15min response), P2 (1hr), P3 (4hr), P4 (24hr).

---

## Part I, Panel 3: Economics, Billing & Scaling

*12 experts: Usage-based billing architects, API marketplace operators, fintech billing specialists, infrastructure economists, pricing strategists, payment systems architects (x402/crypto), managed service operators*

### 3.1 Pricing Model Per Layer

**Layer 1 — Raw Provider Access:**
```
agent_charge = provider_cost + max($0.0002, provider_cost × 0.08)
```
Target margin: 8-12%. This is the trust anchor, not the revenue engine.

**Layer 2 — Single Capability Delivery:**
```
agent_charge = provider_cost + capability_base_fee + (0.12 × provider_cost)
```

| Tier | Base Fee | Examples |
|------|----------|---------|
| T1 | $0.0005 | Geocoding, weather, currency rates |
| T2 | $0.0015 | Sentiment, classification, entity extraction |
| T3 | $0.0040 | Summarization, translation, moderation |
| T4 | $0.0080 | Completion, chat, structured generation |
| T5 | $0.0200 | Image generation, audio synthesis |
| T6 | $0.0350 | OCR+extract, transcribe+diarize |

Target margin: 18-28%.

**Layer 3 — Recipes:**
```
agent_charge = recipe_execution_fee + sum(step_charges_at_L2_rates) + (0.15 × sum(step_charges))
```

| Recipe Class | Steps | Execution Fee |
|-------------|-------|---------------|
| RC1 | 2-3 | $0.010 |
| RC2 | 4-6 | $0.025 |
| RC3 | 7-12 | $0.060 |
| RC4 | 13-25 | $0.150 |
| RC5 | 26+ | $0.250 |

Target margin: 35-55%.

### 3.2 Cost Accounting

**Cost Event Schema:** Every billable action produces a `CostEvent` with tenant, agent, execution, step, provider, provider cost (microdollars), Rhumb fee, budget checkpoint status.

**Three-tier storage:** Redis (sub-ms budget enforcement) → PostgreSQL (durable ledger) → Daily rollups (invoicing/analytics).

**Budget checkpoints at three granularities:** Pre-execution estimation, mid-execution step gates, post-execution reconciliation.

### 3.3 Billing Pipeline

**Payment methods (v1):**
- **Prepaid credits (Stripe):** $10/$50/$200/$500 packages. Credits tracked as integer microdollars (1 USD = 1B microdollars). FIFO expiry (12 months).
- **x402 USDC:** Per-call inline payment for permissionless agent billing.
- **Enterprise invoicing:** Manual CSV export + net-30 (v1 basic; automated in v2).

**Deferred to v2:** Subscription tiers, automated enterprise invoicing.

### 3.4 Margin Analysis

| Layer | Target Gross Margin | Revenue Driver |
|-------|-------------------|----------------|
| Layer 1 | 8-12% | Volume |
| Layer 2 | 18-28% | Routing intelligence + reliability |
| Layer 3 | 35-55% | Orchestration + artifact management |

### 3.5 Scaling Economics

| Scale | Monthly Revenue | Monthly Gross Margin | Margin % |
|-------|----------------|---------------------|----------|
| 100 agents | $5,685 | $1,305 | 23% |
| 1K agents | $56,850 | $18,510 | 33% |
| 10K agents | $568,500 | $214,600 | 38% |

**Key driver:** Margin improves through provider volume discounts, infrastructure amortization, and routing optimization.

### 3.6 x402 Integration

**Per-call flow:** Agent request → 402 Payment Required → Agent pays USDC on Base L2 → Re-sends with X-PAYMENT header → Rhumb verifies → Executes → Returns result.

**Recipe flow (v1):** Single upfront payment for estimated total; refund difference on completion.

**Settlement:** Hot wallet → Treasury wallet (daily sweep >$500) → Operating account (weekly >$5,000) via Coinbase/Circle.

**Custody (v1):** Self-custody with 2-of-3 Gnosis Safe multisig.

### 3.7 Budget Enforcement

**Budget hierarchy:** Organization → Tenant → Agent → Capability/Recipe overrides.

**Exhaustion modes:** `hard_stop` (default), `soft_stop` (human-in-the-loop), `overdraft` (trusted enterprise), `queue` (v2 deferred).

**Overdraft tiers:** Tier 0 (new, $0) → Tier 1 ($5, >30 days) → Tier 2 ($25, >90 days) → Tier 3 ($500+, enterprise contract).

### 3.8 Regulatory Considerations

- **Prepaid credits:** Non-transferable, Rhumb-only redemption → likely closed-loop exemption from MTL
- **USDC:** Use licensed payment processor layer; sweep to USD immediately; transaction monitoring above $1K/mo
- **KYC thresholds:** None <$3K; basic $3K-$10K; enhanced >$10K; full business KYC for enterprise
- **Float:** Negligible at <1K agents; material at 10K+ → sweep to money market (v2)

---

## Part I, Panel 4: Adversarial, Failure Modes & Edge Cases

*12 experts: Security researchers, abuse/fraud specialists, reliability engineers, legal/compliance advisors, competitive strategists, prompt injection specialists, cost-attack researchers*

### 4.1 Abuse Vectors Per Layer

**Layer 1 risks:** Credential stuffing via Rhumb proxy (HIGH/CRITICAL), rate limit evasion via account multiplication (HIGH), identity obscuration (MEDIUM).

**Layer 2 risks:** Routing manipulation to game cost (MEDIUM), capability parameter injection (HIGH).

**Layer 3 risks:** Infinite loop recipes (MEDIUM/CRITICAL), fork bomb via parallel fan-out (HIGH/CRITICAL), recursive recipe calls (MEDIUM).

**Mitigations:** Per-agent rate limits, anomaly detection, strict schema validation, DAG enforcement at compile time, max fan-out declarations, recipe nesting depth limit (3), execution step ceiling (100).

### 4.2 Cost Amplification Attacks

**Attack:** Recipe with fan-out step: 1 request → 10,000 provider calls. Cost multiplier up to 10,000x.

**Mitigations:**
1. Pre-execution cost estimation MANDATORY for fan-out recipes
2. Worst-case estimation using declared max fan-out
3. Explicit confirmation if estimate >10% of account balance
4. Hard per-execution cost ceiling
5. Fraud velocity detection: flag >5x normal hourly spend

### 4.3 Provider Failure Cascading

**Failure taxonomy:** STEP_ERROR_RECOVERABLE, STEP_ERROR_PERMANENT, STEP_TIMEOUT, STEP_INVALID_OUTPUT, STEP_BUDGET_EXCEEDED, PROVIDER_UNAVAILABLE, PARTIAL_EXECUTION, EXECUTION_ABANDONED.

**Decision matrix:** Completed steps → artifacts preserved. Failed step → retry per policy → fallback → FAILED_PERMANENT. Blocked downstream steps → CANCELLED_UPSTREAM_FAILURE.

**Compensating transactions:** Declared explicitly per-step, not automatic. Classification: A (irreversible delivery), B (reversible creation), C (financial), D (state mutation), E (read-only).

### 4.4 Prompt Injection Across Composed Steps

**Vectors:** String interpolation, JSON field escape, URL construction injection, tool-call syntax in data fields.

**Mitigations:** Content firewall at every step transition, typed data mappings only, no raw interpolation, parameterized construction for URLs and JSON, step outputs classified as UNTRUSTED_DATA until validated.

### 4.5 Idempotency & Retries

**Key format:** `rhumb_idk_{execution_id}_{step_id}_{attempt}_{capability}`

**Side effect taxonomy:** CLASS_A (irreversible delivery → retry ONCE), CLASS_B (reversible creation → idempotent retry), CLASS_C (financial → NEVER auto-retry), CLASS_D (state mutation → conditional), CLASS_E (read-only → freely retryable).

### 4.6 Provider ToS Compliance

**Three tiers:** Tier 1 (safe for all credential modes — explicit aggregator programs), Tier 2 (BYO only — ambiguous ToS), Tier 3 (prohibited — explicit anti-proxy terms).

**90-day review cycle** for all 16 provider ToS. Legal review required for new providers.

### 4.7 Kill Switch & Circuit Breaker Hierarchy

**L1:** Per-agent kill switch (abuse/compromise)
**L2:** Per-provider circuit breaker (error rate/latency spike)
**L3:** Per-recipe kill switch (cost runaway/harmful output)
**L4:** Global kill switch (security breach — requires two-person authorization: Tom + engineering lead)

**Recovery:** Per-provider automated via probe/half-open. Global requires incident post-mortem → phased restoration (read-only first, financial last) → two-person sign-off.

### 4.8 Risk Register Summary

| Risk | Likelihood | Impact | Launch Requirement |
|------|-----------|--------|-------------------|
| Layer 1 credential stuffing | HIGH | CRITICAL | Required |
| Recipe fork bomb / cost amplification | HIGH | CRITICAL | Required (DAG enforcement) |
| Prompt injection cross-step | HIGH | HIGH | Required |
| Double-charge on retry | HIGH | HIGH | Required (idempotency keys) |
| Money transmission (credits) | HIGH | CRITICAL | Required (legal structure) |
| AN Score routing corruption | LOW | CRITICAL | Required (architectural) |
| Vault credential extraction | LOW | CRITICAL | Required (HSM/KMS) |
| Provider competitive retaliation | MEDIUM | HIGH | Monitoring + diversification |

---

# Part II: Unified Synthesis

---

## 1. Complete API Specification

The complete API is defined in Panel 1, Section 1.1-1.5 above. Summary of endpoints:

**Execution:**
| Method | Path | Layer | Description |
|--------|------|-------|-------------|
| POST | `/v2/providers/{id}/execute` | 1 | Execute on named provider |
| POST | `/v2/capabilities/{id}/execute` | 2 | Execute capability (Rhumb routes) |
| POST | `/v2/recipes/{id}/execute` | 3 | Execute compiled recipe |

**Discovery:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v2/providers` | List providers |
| GET | `/v2/capabilities` | List capabilities |
| GET | `/v2/capabilities/{id}` | Get capability schema |
| GET | `/v2/recipes` | List recipes |
| GET | `/v2/recipes/{id}` | Get recipe schema |

**Observability:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v2/receipts/{id}` | Get execution receipt |
| GET | `/v2/receipts/{id}/explanation` | Get routing explanation |
| GET | `/v2/receipts` | Query receipts (filterable) |

**Policy:**
| Method | Path | Description |
|--------|------|-------------|
| GET/PUT/PATCH/DELETE | `/v2/policy` | CRUD on execution policy |
| POST | `/v2/approvals/{id}/approve` | Approve pending execution |
| POST | `/v2/approvals/{id}/deny` | Deny pending execution |

**Trust & Audit:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v2/trust/summary` | Agent trust summary |
| GET | `/v2/trust/providers` | Provider distribution |
| GET | `/v2/trust/costs` | Cost breakdown |
| GET | `/v2/trust/reliability` | Reliability metrics |
| POST | `/v2/audit/export` | Export audit trail |

**Billing:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v2/billing/credits/purchase` | Purchase credits (Stripe) |
| GET | `/v2/billing/balance` | Get credit balance |
| POST | `/v2/billing/estimate` | Pre-execution cost estimate |

**Public (no auth):**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v2/scores/{provider_id}` | Published AN Score |
| GET | `/v2/scores/{provider_id}/history` | AN Score change log |

**Compatibility:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/capabilities/{id}/execute` | Legacy endpoint (maps to Layer 2) |

---

## 2. Capability Contract Standard

Defined in Panel 1, Section 1.2. The canonical schema includes:

- **Identity:** id, name, version, category, subcategory, stability, tags
- **Interface:** parameters (JSON Schema), response (JSON Schema)
- **Providers:** provider_requirements with tier assignments (preferred/standard/fallback)
- **Credentials:** supported modes (byo/rhumb_managed/agent_vault) with default
- **Economics:** pricing_hints (min/max/typical cost, pricing model, cost factors)
- **Operations:** rate_limit_metadata, idempotency support, timeouts
- **History:** changelog with version-by-version changes

All 415 existing capabilities will be migrated to this schema format during the v2 rollout.

---

## 3. Recipe Standard

Defined in Panel 1, Section 1.3. The canonical schema includes:

- **Identity:** recipe_id, name, version, category, stability, tier
- **Interface:** inputs (JSON Schema), outputs (JSON Schema)
- **Steps:** Array of step definitions, each containing:
  - Capability reference with version pin (`^2.0.0` semver range)
  - Dependencies (DAG edges)
  - Parameter mapping using `$ref` syntax between steps and recipe inputs
  - Artifact capture configuration
  - Per-step failure mode (halt/continue) with retry policy
  - Per-step budget (max cost + timeout)
- **DAG:** Explicit edge list + critical path
- **Budget:** Max total cost, per-step enforcement, budget-exceeded behavior
- **Security:** DAG must be acyclic (enforced at compile time), max fan-out per step, max nesting depth (3), max steps per execution (100)

---

## 4. Provider Adapter Standard

Defined in Panel 1, Section 1.4. The canonical interface:

- **Registration:** adapter_id, base_url, auth configuration, supported capabilities with provider endpoints, health check endpoint, rate limits, error mapping
- **Handler contract:** `buildRequest`, `normalizeResponse`, `mapError`, `computeCost` — each with typed interfaces
- **Credentials:** `InjectedCredentials` — injected server-side, never returned to callers, never logged
- **Health:** Periodic health checks with configurable interval; health status feeds routing decisions

All 16 current providers will be migrated to this adapter format.

---

## 5. Policy Control Specification

Defined across Panel 1 (Section 1.5) and Panel 2 (Section 2.4). Complete policy surface:

**Provider Controls:**
- `pin`: Force specific provider for capability patterns (overrideable flag)
- `deny`: Block specific providers globally or per-capability
- `prefer`: Score boost for preferred providers/credential modes
- `allow_only`: Restrict to named providers only

**Cost Controls:**
- `per_call`: Ceiling + action on breach (block/warn)
- `per_day`: Ceiling + reset UTC hour
- `per_month`: Ceiling
- `per_recipe`: Default + per-recipe overrides
- `per_capability`: Per-capability cost limits

**Region Controls:**
- Allowed/denied provider regions
- Data residency requirements
- PII handling policy

**Approval Controls:**
- `auto_approve`: Default — all executions proceed
- `manual_approve`: Requires human approval before execution
- `threshold_approve`: Auto below threshold, manual above
- Approval webhook URL + timeout + timeout action

**Retry Controls:**
- Max retries, backoff strategy, retry-on/no-retry-on error codes
- Retry same provider vs. fallback to next

**Policy evaluation order:** Parse → Load effective policy → Deny list → Pin rules → Region/residency → Approval → Cost ceiling → Score candidates → Prefer rules → Select → Execute → Update budgets.

---

## 6. Execution Receipt Specification

Defined in Panel 2, Section 2.1. Every execution produces an immutable, chain-hashed receipt containing:

- **Execution identity:** receipt_id, execution_id, layer, capability, status
- **Agent identity:** agent_id, key_id, workspace_id, IP hash
- **Provider attribution:** provider_id, model, region, credential_mode, latency
- **Routing:** candidates evaluated, winner reason, explanation_id
- **Timing:** Full latency breakdown (auth, routing, credential injection, provider, normalization, receipt write)
- **Cost:** Provider cost, Rhumb fee, total, budget impact
- **Integrity:** Receipt hash, chain hash, sequence number, signing key ID
- **Compliance:** Data residency region, PII detected, retention policy

**Layer-specific extensions:**
- Layer 1: raw_passthrough flag, fidelity guarantee
- Layer 3: recipe_id, step_index, step_name, step budget consumed, artifact references

---

## 7. Pricing and Billing Specification

Defined in Panel 3. Summary:

**Pricing formulas:**
- Layer 1: `provider_cost + max($0.0002, provider_cost × 0.08)`
- Layer 2: `provider_cost + tier_base_fee + (0.12 × provider_cost)`
- Layer 3: `execution_fee + sum(step_charges) + (0.15 × sum(step_charges))`

**Payment methods (v1):**
1. Prepaid Stripe credits (integer microdollar ledger, FIFO expiry)
2. x402 USDC inline payments (Base L2)
3. Manual enterprise invoicing (net-30)

**Budget enforcement:** Redis for sub-ms checks, PostgreSQL as source of truth, reservation pattern for recipes.

**Revenue recognition (ASC 606):** Credits are deferred revenue; recognized on execution. Partial execution prorated.

**Float management:** Negligible <1K agents; sweep to money market at 10K+ (v2).

---

## 8. Trust and Neutrality Specification

Defined in Panel 2, Sections 2.3-2.5 and Panel 4, Section 4.8.

**Core principle:** Neutrality is the moat. The AN Score must be published, auditable, and incorruptible.

**Structural guarantees:**
1. AN Score service is a separate deployable with its own DB and no access to commercial data
2. Routing engine reads scores from a read-only cache; cannot write to Score DB
3. Commercial DB is a separate instance with no joins to Score DB
4. Score changes are immutable audit events with chain hashing
5. Commercial relationship proximity check: score changes co-occurring with commercial changes within 30 days trigger auto-flag
6. Scores published publicly before loaded into routing cache

**Neutrality corruption prevention:**
- No revenue share deals that influence routing weight (hard policy boundary)
- Volume commitments disclosed in transparency report
- Quarterly external routing audit comparing decisions to AN Score predictions
- Red line: >2% systematic routing deviation triggers investigation; >40% provider concentration per capability triggers review

**Public transparency:**
- Scores published at `https://trust.rhumb.ai/scores/`
- Methodology at `https://trust.rhumb.ai/methodology/`
- Evidence links per dimension
- Annual external audit of scoring methodology (quarterly in v2)

---

## 9. Security and Abuse Specification

Defined in Panel 4. Summary of launch-critical controls:

**Authentication:** Two-level auth (account API key + agent JWT). Agent tokens scope-bound, short-lived (1hr), IP-bindable.

**Credential security:** AES-256-GCM encryption at rest, per-account keys in KMS, inject-only pattern (agents never see raw credentials), all vault access logged.

**Recipe safety:**
- DAG must be acyclic (compile-time enforcement)
- Max fan-out per step (declared at definition time, enforced at runtime)
- Max nesting depth: 3
- Max steps per execution: 100
- Max runtime: 300 seconds
- Content firewall at every step transition (prompt injection prevention)

**Idempotency:** Rhumb-generated keys (`rhumb_idk_{execution_id}_{step_id}_{attempt}_{capability}`), 24-hour window, collision returns cached result.

**Kill switches:** 4-level hierarchy — agent (abuse), provider (circuit breaker), recipe (cost/harm), global (two-person auth required).

**Monitoring:** Per-agent call/cost/error rates (1-minute windows), per-provider error/latency, per-recipe cost vs estimate, vault access anomalies, routing distribution vs population baseline.

---

## 10. 90-Day Implementation Plan

### Days 1-30: Foundation Layer

**Why this first:** Layer 2 is the existing product surface and where all current agents live. Upgrading the execution engine, adding the v2 API gateway with v1 compatibility, and implementing receipts + policy enforcement is the foundation everything else depends on.

| Week | Deliverable | Justification |
|------|-------------|---------------|
| 1-2 | **v2 API Gateway** — Deploy v2 routing engine behind existing `/v1/` path. All existing traffic transparently routes through v2 internals. Zero client-side changes required. | Validates the new architecture under real production load without breaking existing agents. |
| 1-2 | **Execution Receipt System** — Append-only PostgreSQL table with chain hashing, receipt write on every execution. | Receipts are the ground truth for trust, billing, and debugging. Cannot ship any other feature without them. |
| 2-3 | **Error Envelope Standardization** — All error responses use the canonical envelope with codes, retry hints, and provider attribution. | Agent reliability depends on predictable, actionable errors. |
| 3-4 | **Policy Engine v1** — Account-level policy CRUD (`/v2/policy`), deny lists, cost ceilings (per-call, per-day, per-month), basic provider preference. | Policy enforcement is the primary differentiator vs raw API calls. Must be in place before Layer 1 opens. |
| 3-4 | **Budget Enforcement** — Redis-backed budget checks, pre-execution cost estimation, hard stop on ceiling breach. | Required for any serious agent deployment. |
| 4 | **v2 Endpoint Publication** — Publish `/v2/capabilities/{id}/execute` alongside `/v1/`. Update MCP tools to v2 schema. Existing agents unaffected. | Makes v2 available for opt-in without forcing migration. |

**Day 30 checkpoint:** v2 gateway running in production with v1 compat. Receipts being written. Policy enforcement active. Budget checks working. Zero regression on existing agents.

### Days 31-60: Layer 1 + Trust + Billing

**Why this second:** Layer 1 (raw provider access) is quick to ship because it requires no routing intelligence — it's a pass-through proxy with credentials, billing, and observability. The trust dashboard and billing pipeline upgrades are the platform-level infrastructure that makes Layer 2 valuable.

| Week | Deliverable | Justification |
|------|-------------|---------------|
| 5-6 | **Layer 1 — Raw Provider Access** — `/v2/providers/{id}/execute` endpoint, provider listing, 8% + floor pricing. | Escape hatch for agents who need exact provider control. Also validates the provider adapter interface with the simplest possible use case. |
| 5-6 | **Provider Attribution** — `_rhumb` block in every response, `X-Rhumb-Provider` headers, attribution in error messages. | Fulfills the "abstraction ≠ erasure" promise. |
| 6-7 | **Route Explanation Engine** — Explanation generation on every Layer 2 execution, `GET /v2/receipts/{id}/explanation` endpoint. | Transparency is the core product value. Agents need to know why a provider was chosen. |
| 7-8 | **AN Score Integration** — Structural separation of scoring service, score cache, composite score feeding into routing. | Neutrality architecture must be in place before any commercial partnerships. |
| 7-8 | **Billing Pipeline Upgrade** — x402 per-call payment flow, improved credit purchase UX, billing event stream. | x402 enables permissionless agent billing — critical for the autonomous agent use case. |
| 8 | **Trust Dashboard API** — `/v2/trust/summary`, `/v2/trust/providers`, `/v2/trust/costs`, `/v2/trust/reliability`. | Agents need visibility into their execution history, reliability, and spend. |

**Day 60 checkpoint:** Layers 1 and 2 fully operational. Route explanations available. AN Score structurally separated and feeding routing. x402 payments working. Trust API live.

### Days 61-90: Layer 3 + Security + Polish

**Why this third:** Layer 3 (recipes) is the premium product but requires the most complex engineering (multi-step orchestration, DAG execution, partial failure handling, artifact capture). Building it on top of proven Layer 1/2 infrastructure reduces risk.

| Week | Deliverable | Justification |
|------|-------------|---------------|
| 9-10 | **Recipe Execution Engine** — DAG validator (compile-time cycle detection), step-level execution with budget enforcement, artifact capture, parameter mapping between steps. | Core Layer 3 infrastructure. |
| 9-10 | **Recipe Safety Controls** — Max fan-out enforcement, nesting depth limit, content firewall at step transitions, idempotency key system. | Panel 4 identified recipes as the highest-risk attack surface. Safety controls must ship alongside the feature. |
| 10-11 | **Recipe API Surface** — `/v2/recipes/{id}/execute`, listing, schema endpoints. Recipe MCP tools. | Makes Layer 3 available to agents. |
| 11-12 | **Circuit Breakers & Kill Switches** — Per-provider circuit breakers, per-agent/recipe/global kill switches with two-person auth for global. | Operational safety for production deployment at scale. |
| 11-12 | **Audit Trail** — Append-only audit log, 15 event types, export API, chain-hash verification. | Compliance infrastructure for SOC2 preparation. |
| 12 | **SDK & Documentation** — TypeScript SDK v1, updated MCP server (`rhumb-mcp@2.0.0`), API documentation, migration guide. | Without SDK and docs, the platform doesn't ship — agents can't use what they can't understand. |

**Day 90 checkpoint:** All three layers operational. Recipe execution with safety controls. Circuit breakers active. Audit trail logging. SDK and documentation complete. Ready for controlled beta.

### Post-Day 90 (Deferred)

| Item | Target |
|------|--------|
| Python/Go SDKs | Month 4 |
| Subscription tiers | Month 4-5 |
| Automated enterprise invoicing | Month 4-5 |
| Approval gate webhooks | Month 5 |
| Recipe authoring API (agent-created recipes) | Month 6 |
| Streaming execution results (SSE) | Month 6 |
| Payment channels for Layer 3 (x402 Option B) | Month 6-8 |
| Public recipe marketplace | Month 9+ |
| External quarterly AN Score audit | Month 6+ |

---

## 11. Decision Register

| # | Decision | Rationale | Alternatives Considered | Minority View |
|---|----------|-----------|------------------------|---------------|
| D1 | **Three layers, not two.** Layer 1 exists as escape hatch + trust anchor. | Agents need raw provider access for capabilities Rhumb hasn't normalized yet, and for debugging. Layer 1 also validates our billing/observability infra at the simplest level. | Two layers (skip Layer 1, always route). | "Layer 1 cannibalizes Layer 2 margin." True, but the trust anchor it provides drives Layer 2 adoption. An agent that can always escape is an agent willing to use routing. |
| D2 | **Recipes are compiled, not generated.** Resolve does NOT improvise. | Open-ended orchestration makes Resolve an agent-behind-the-agent, destroying the trust thesis. Compiled recipes are auditable, deterministic, and bounded. | LLM-powered recipe generation at request time. | "Compiled recipes limit flexibility." Yes. That's the point. Flexibility is the agent's job; reliability is Resolve's. |
| D3 | **v1 compatibility forever.** Not just a migration period. | The cost of maintaining a translation layer is lower than the cost of breaking existing agents. Trust is built by never forcing migration. | 18-month sunset. | "Forever is too long — increases tech debt." Accept the tech debt as the cost of trust. |
| D4 | **AN Score structurally separated from routing.** Not just process-separated — architecturally separated (separate DB, separate service, separate IAM). | Process separation can be overridden by management. Architectural separation requires code changes and deploys to violate. | Policy-based separation. | "Over-engineered for a 16-provider catalog." Correct for today; catastrophically wrong at 100+ providers. Build the right architecture now. |
| D5 | **No revenue share deals that influence routing.** Hard boundary. | The moment routing is influenced by commercial incentives, the AN Score is worthless. This is existential. | "Revenue share is free margin." Free margin that destroys the only thing that makes Rhumb worth trusting. |
| D6 | **Prepaid credits, not subscriptions, for v1.** | Usage-based billing aligns with agent usage patterns (bursty, unpredictable). Subscriptions add committed revenue but complicate proration and the credit interaction. | Subscription tiers from day one. | "Subscriptions are revenue-predictable." True; revisit when ARR > $50K. |
| D7 | **x402 USDC as first-class payment method.** | Enables truly autonomous agent billing without Stripe accounts. Natural fit for permissionless agents. | USDC deferred to v2. | "Regulatory complexity." Mitigated by using Base L2 + licensed processor + sweep to USD. Worth the complexity for the agent autonomy story. |
| D8 | **Date-pinned API versioning with 2-year guarantee.** | Schema stability is the product. Agents build on stable schemas — breaking changes are production incidents. | Semver URL versioning (`/v2/`, `/v3/`). | "2 years is too long." For an infrastructure layer that agents depend on? 2 years is the minimum. |
| D9 | **DAG-only recipes (no cycles, no conditionals in v1).** | Cycles create unbounded execution. Conditionals add complexity that isn't justified until we see real usage patterns. | Conditional branching in v1. | "No conditionals limits recipe expressiveness." True; add conditional steps in v1.1 after observing actual recipe usage. |
| D10 | **Two-person auth for global kill switch.** | Single-person kill switch is itself a risk vector. Two-person auth prevents rogue shutdowns and forces coordination. | Single-person emergency authority. | "Slows emergency response." Acceptable tradeoff — P1 response time is 15 minutes, not 15 seconds. Two people can coordinate in 15 minutes. |
| D11 | **Content firewall at every step transition in recipes.** | Prompt injection across composed steps is a HIGH likelihood, HIGH impact risk. Sanitization at every boundary is the only reliable defense. | Trust step outputs. | "False positives will block legitimate content." Yes — accept false positives at launch, tune over time. Blocking legitimate content is recoverable; prompt injection is not. |
| D12 | **Layer 3 deferred to Days 61-90.** | Layer 3 requires proven Layer 1/2 infrastructure. Building it first increases risk of cascading failures. | Ship all layers simultaneously. | "Delays premium revenue." Correct. But shipping broken recipes destroys trust permanently. 60 days of proven Layer 2 is worth the delay. |

---

## 12. Open Questions

These questions need real-world signal — they cannot be decided from the spec alone.

| # | Question | What We Need | Decision Deadline |
|---|----------|-------------|------------------|
| Q1 | **What's the right AN Score weight in routing?** Currently set at 20% of composite score. Should it be higher (agents want neutrality) or lower (agents want price/speed)? | Agent feedback from first 50 users on whether they care about AN Score in routing or just as a published metric. | Day 60 |
| Q2 | **Should agents be able to create their own recipes?** v1 recipes are Rhumb-curated. Agents may want custom composition. | Observe how agents use Layer 2 sequentially — if patterns emerge, productize as recipe authoring API. | Day 90 |
| Q3 | **Is 8% the right Layer 1 markup?** Too high = agents bypass Rhumb. Too low = unsustainable. | A/B test with first 20 agents. Track Layer 1 adoption rate vs perceived value. | Day 45 |
| Q4 | **Do agents actually use approval gates?** Manual approval mode is expensive to build. If no one uses it, defer. | Survey first 30 agents on whether their orchestrators would ever pause for human approval. | Day 30 |
| Q5 | **How aggressive should content firewalls be at step transitions?** Too aggressive = false positives kill recipe reliability. Too lax = injection risk. | Deploy with aggressive defaults, measure false positive rate, tune down. Track blocked-but-legitimate content. | Day 75 (after recipe launch) |
| Q6 | **Should Layer 3 support parallel step execution in v1?** Currently spec allows it, but adds orchestration complexity. | If first 10 recipes are all sequential, defer parallel to v1.1. If fan-out patterns appear immediately, prioritize. | Day 70 |
| Q7 | **What's the right maximum credit balance?** $500 at launch for MTL safe harbor. Enterprise may need more. | Legal counsel on per-state stored value thresholds. Monitor enterprise demand signals. | Day 30 |
| Q8 | **Should Rhumb offer provider-level SLA guarantees?** Current spec explicitly excludes provider availability from Rhumb SLAs. Agents may want end-to-end guarantees. | Measure actual provider uptime for first 90 days. If P99 availability across providers is >99.5%, consider offering composite SLA. | Day 90 |
| Q9 | **How much should Rhumb invest in recipe DSL tooling?** Recipes are JSON — should there be a visual editor, a DSL compiler, or just raw JSON? | Observe friction in recipe creation. If most recipes are copy-modify patterns, a template library may suffice. | Month 4 |
| Q10 | **Is Base L2 the right chain for x402?** Base is cheap and fast today. If gas costs rise or better alternatives emerge, should Rhumb be multi-chain? | Monitor Base L2 gas costs over 90 days. Track agent USDC wallet distribution (Base vs other chains). | Day 90 |
| Q11 | **Provider feedback loops — how transparent?** Current spec shares anonymized aggregate metrics. Providers may want more detail. | Start with aggregate only. Listen to provider requests. Expand only if it strengthens the relationship without compromising agent privacy. | Month 4 |
| Q12 | **When should Rhumb hire its first human?** Tom's board-level authority. But the spec implies engineering work that may exceed what Pedro can ship solo with AI agents. | Assess velocity at Day 30 and Day 60 milestones. If behind schedule, escalate to Tom with specific hire request. | Day 60 |

---

## Appendix A: What Ships in v1 vs What's Deferred

### ✅ v1 (Ship within 90 days)

- Layer 1 + Layer 2 execution endpoints
- Layer 3 recipe execution (basic — sequential + simple DAG)
- v1 compatibility layer at `/v1/`
- Capability discovery and schema endpoints
- Standard error envelope (21 error codes)
- Execution receipts with chain hashing
- Account-level policy (deny lists, cost ceilings, provider preference, approval modes)
- Per-call policy overrides
- Budget enforcement (Redis + PostgreSQL)
- Route explanation engine
- AN Score structural separation + integration
- Provider attribution in all responses
- Idempotency keys
- x402 USDC per-call payments
- Prepaid credits via Stripe
- Circuit breakers per provider
- Kill switches (4 levels)
- Content firewall at recipe step transitions
- DAG enforcement (compile-time cycle detection)
- 12 MCP tools
- TypeScript SDK
- Date-pinned API versioning
- Trust dashboard API (basic)
- Audit trail (append-only, chain-hashed)
- Basic enterprise invoicing (manual CSV)

### 🔜 Deferred to v1.1 (Months 4-6)

- Budget tokens (delegated spending envelopes)
- Conditional branching in recipes
- Recipe authoring API (agent-created recipes)
- Approval gate webhooks
- Artifact storage and retrieval API
- Python and Go SDKs
- Subscription tiers
- Automated enterprise invoicing
- Provider cost change detection + automated repricing
- Overdraft with risk scoring
- Webhook on completion/failure

### 🔭 Deferred to v2+ (Months 6-12+)

- Agent identity federation (cross-agent trust)
- Public recipe marketplace
- Custom adapter registration by third parties
- Streaming execution results (SSE)
- Real-time observability dashboard
- Payment channels for Layer 3 (x402 Option B)
- External quarterly AN Score audit
- Multi-currency support
- EU regulatory compliance (PSD2/MiCA)
- Float management + interest sweep

---

## Appendix B: Design Principles (Non-Negotiable)

1. **Schema stability is the product.** Agents build on stable schemas. Breaking changes are treated as production incidents.

2. **Every execution is traceable.** No black boxes. Every routing decision, every cost, every provider choice is recorded and retrievable.

3. **Credentials never leak.** Credentials are injected server-side and never returned to callers, logged in plaintext, or included in receipts.

4. **Errors are actionable.** Every error includes: is it retryable? When? From which layer? What provider caused it? Where are the docs?

5. **Policy is explicit.** Routing decisions are explained in receipts. Agents know why a provider was chosen.

6. **Resolve compiles, it does not improvise.** Layer 3 recipes are declared workflows — not open-ended planners. If a workflow isn't pre-compiled into a recipe, it's Layer 2 territory.

7. **v1 compat is permanent infrastructure.** The migration cost to abandon v1 users is higher than the cost of maintaining a compat layer.

8. **Abstraction is not erasure.** Providers are always visible, always attributed, always credited. Rhumb adds a layer but never removes one.

9. **Neutrality is structural, not procedural.** AN Score integrity is enforced architecturally (separate services, DBs, IAM) — not by policy documents that can be ignored.

10. **Trust compounds.** Every correct receipt, every transparent routing decision, every honest error message compounds the trust that makes agents choose Rhumb over alternatives.

---

## Appendix C: Full Panel Reports

The complete, unabridged panel reports are available at:

- `rhumb/docs/specs/panels/panel-1-architecture.md` (59KB)
- `rhumb/docs/specs/panels/panel-2-trust.md` (52KB)
- `rhumb/docs/specs/panels/panel-3-economics.md` (52KB)
- `rhumb/docs/specs/panels/panel-4-adversarial.md` (53KB)

Total panel output: 216KB of engineering-grade specification.

---

*This is a founding document. Build from it. Ship from it. Everything that follows — sprints, PRDs, architecture docs, test plans — traces back to this spec.*

*Resolve doesn't improvise. Neither does its spec.*
