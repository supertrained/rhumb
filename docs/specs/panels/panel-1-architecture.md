# Panel 1: Product Architecture & API Design
## Rhumb Resolve — Founding Product Specification

**Panel:** 14 experts — API gateway architects, developer tools PMs, platform API designers, schema architects, DX specialists, multi-tenant SaaS architects, capability modeling experts, protocol designers

**Status:** v1.0 — Authoritative  
**Date:** 2026-03-30

---

## Executive Summary

Rhumb Resolve is a **managed execution substrate** — not an agent, not a planner, not an orchestrator. It provides three precisely-scoped layers of API surface:

1. **Raw Provider Access** — transparent credential+billing proxy to named providers
2. **Single Capability Delivery** — stable-schema capability execution with intelligent routing
3. **Deterministic Composed Capabilities** — pre-compiled multi-step recipes with traceable execution

Every layer returns the same execution receipt format. Every error uses the same envelope. Every call produces a traceable audit trail. The API is opinionated about schema stability, transparent about routing decisions, and explicit about what it will and won't do.

This document is the engineering specification. It is buildable as written.

---

## 1. Three-Layer API Surface

### 1.1 URL Namespacing

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

### 1.2 Universal Request Headers

All endpoints accept these headers:

```
Authorization: Bearer {api_key}              # Required
X-Rhumb-Version: 2026-03-30                  # Optional: date-pinned API version
X-Rhumb-Idempotency-Key: {uuid}              # Optional: idempotent retry key
X-Rhumb-Agent-Id: {agent_identifier}         # Optional: agent identity for audit
X-Rhumb-Budget-Token: {budget_token}         # Optional: per-call budget override
Content-Type: application/json
```

### 1.3 Layer 1 — Raw Provider Access

#### Endpoint: Execute on Named Provider

```
POST /v2/providers/{provider_id}/execute
```

**Path Parameters:**
- `provider_id` — Rhumb provider identifier (e.g., `openai`, `anthropic`, `twilio`, `sendgrid`)

**Query Parameters:**
- `dry_run=true` — Validate and price without executing (default: false)

**Request Body:**

```json
{
  "capability": "chat.completions",
  "parameters": {
    "model": "gpt-4o",
    "messages": [
      {"role": "user", "content": "Summarize the following: ..."}
    ],
    "max_tokens": 500,
    "temperature": 0.7
  },
  "credential_mode": "rhumb_managed",
  "policy": {
    "timeout_ms": 30000,
    "max_cost_usd": 0.10
  }
}
```

**Response (200 OK):**

```json
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
      "object": "chat.completion",
      "choices": [
        {
          "message": {"role": "assistant", "content": "Here is the summary..."},
          "finish_reason": "stop"
        }
      ],
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

**curl example:**

```bash
curl -X POST https://api.rhumb.dev/v2/providers/openai/execute \
  -H "Authorization: Bearer rk_live_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "capability": "chat.completions",
    "parameters": {
      "model": "gpt-4o",
      "messages": [{"role": "user", "content": "Hello world"}]
    },
    "credential_mode": "rhumb_managed"
  }'
```

#### Endpoint: List Available Providers

```
GET /v2/providers
```

**Query Parameters:**
- `capability=chat.completions` — Filter providers by capability
- `credential_mode=byo` — Filter by credential mode availability
- `status=healthy` — Filter by health status

**Response (200 OK):**

```json
{
  "providers": [
    {
      "id": "openai",
      "display_name": "OpenAI",
      "status": "healthy",
      "capabilities": ["chat.completions", "embeddings", "image.generation", "audio.transcription"],
      "credential_modes": ["byo", "rhumb_managed"],
      "regions": ["us-east-1", "eu-west-1"],
      "rate_limits": {
        "requests_per_minute": 500,
        "tokens_per_minute": 80000
      }
    }
  ],
  "total": 16,
  "page": 1,
  "per_page": 50
}
```

**curl example:**

```bash
curl https://api.rhumb.dev/v2/providers?capability=chat.completions \
  -H "Authorization: Bearer rk_live_abc123"
```

---

### 1.4 Layer 2 — Single Capability Delivery

#### Endpoint: Execute Capability

```
POST /v2/capabilities/{capability_id}/execute
```

**Path Parameters:**
- `capability_id` — Rhumb capability identifier (e.g., `send_email`, `transcribe_audio`, `generate_image`)

**Request Body:**

```json
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
    "retry": {
      "max_attempts": 3,
      "backoff": "exponential",
      "backoff_base_ms": 500
    },
    "fallback": "next_available"
  },
  "credential_mode": "rhumb_managed",
  "idempotency_key": "send-report-user-42-2026-03-30"
}
```

**Response (200 OK):**

```json
{
  "receipt_id": "rcpt_02HY0L3N4O5P6Q7R8S9T0U1V2W",
  "layer": 2,
  "capability": {
    "id": "send_email",
    "version": "1.2.0",
    "normalized": true
  },
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
    "provider_health_scores": {
      "sendgrid": 0.99,
      "mailgun": 0.97,
      "postmark": 0.98
    },
    "selected_reason": "policy_preference_match"
  },
  "executed_at": "2026-03-30T20:42:01.000Z"
}
```

**curl example:**

```bash
curl -X POST https://api.rhumb.dev/v2/capabilities/send_email/execute \
  -H "Authorization: Bearer rk_live_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "to": "user@example.com",
      "subject": "Hello",
      "body": "This is a test"
    },
    "credential_mode": "rhumb_managed"
  }'
```

#### Endpoint: List Capabilities

```
GET /v2/capabilities
```

**Query Parameters:**
- `category=communication` — Filter by category slug
- `provider=sendgrid` — Filter by supporting provider
- `version=stable` — Filter by stability tier (stable|beta|deprecated)
- `q=email` — Full-text search
- `page=1&per_page=50`

**Response (200 OK):**

```json
{
  "capabilities": [
    {
      "id": "send_email",
      "name": "Send Email",
      "version": "1.2.0",
      "category": "communication",
      "stability": "stable",
      "description": "Send a transactional or marketing email via the best available provider",
      "providers": ["sendgrid", "mailgun", "postmark", "ses"],
      "credential_modes": ["byo", "rhumb_managed"],
      "pricing_hint": {
        "estimated_cost_usd": 0.0001,
        "pricing_model": "per_call",
        "free_tier_included": false
      },
      "docs_url": "https://docs.rhumb.dev/capabilities/send_email"
    }
  ],
  "total": 415,
  "categories": 92,
  "page": 1,
  "per_page": 50
}
```

**curl example:**

```bash
curl "https://api.rhumb.dev/v2/capabilities?category=communication&version=stable" \
  -H "Authorization: Bearer rk_live_abc123"
```

#### Endpoint: Get Capability Schema

```
GET /v2/capabilities/{capability_id}
```

Returns the full capability contract including parameter schema, response schema, and provider details.

**curl example:**

```bash
curl https://api.rhumb.dev/v2/capabilities/send_email \
  -H "Authorization: Bearer rk_live_abc123"
```

---

### 1.5 Layer 3 — Recipe Execution

#### Endpoint: Execute Recipe

```
POST /v2/recipes/{recipe_id}/execute
```

**Path Parameters:**
- `recipe_id` — Rhumb recipe identifier (e.g., `enrich_and_email_lead`, `transcribe_and_summarize`)

**Request Body:**

```json
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
```

**Response (200 OK — synchronous for short recipes):**

```json
{
  "receipt_id": "rcpt_03HZ1M4O5P6Q7R8S9T0U1V2W3X",
  "layer": 3,
  "recipe": {
    "id": "transcribe_and_summarize_and_email",
    "version": "2.1.0",
    "steps_total": 3,
    "steps_completed": 3
  },
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
    {
      "step_id": "transcribe",
      "capability_id": "transcribe_audio",
      "provider_used": "deepgram",
      "status": "completed",
      "cost_usd": 0.0240,
      "latency_ms": 8420,
      "artifact_id": "art_01HX9K2"
    },
    {
      "step_id": "summarize",
      "capability_id": "summarize_text",
      "provider_used": "anthropic",
      "status": "completed",
      "cost_usd": 0.0180,
      "latency_ms": 2100,
      "artifact_id": "art_01HX9K3"
    },
    {
      "step_id": "notify",
      "capability_id": "send_email",
      "provider_used": "sendgrid",
      "status": "completed",
      "cost_usd": 0.0001,
      "latency_ms": 290
    }
  ],
  "cost": {
    "total_usd": 0.0421,
    "rhumb_fee_usd": 0.0042,
    "grand_total_usd": 0.0463,
    "credits_deducted": 0.0463
  },
  "latency": {
    "total_ms": 10850,
    "step_ms": 10810,
    "orchestration_ms": 40
  },
  "executed_at": "2026-03-30T20:42:00.000Z",
  "completed_at": "2026-03-30T20:42:10.850Z"
}
```

**Response for long-running recipes (202 Accepted):**

```json
{
  "receipt_id": "rcpt_04HA2N5P6Q7R8S9T0U1V2W3X4Y",
  "status": "running",
  "poll_url": "https://api.rhumb.dev/v2/receipts/rcpt_04HA2N5P6Q7R8S9T0U1V2W3X4Y",
  "estimated_duration_ms": 45000,
  "webhook_registered": false
}
```

**curl example:**

```bash
curl -X POST https://api.rhumb.dev/v2/recipes/transcribe_and_summarize_and_email/execute \
  -H "Authorization: Bearer rk_live_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "audio_url": "https://storage.example.com/recording.mp3",
      "recipient_email": "team@example.com"
    },
    "credential_mode": "rhumb_managed"
  }'
```

#### Endpoint: List Recipes

```
GET /v2/recipes
```

**curl example:**

```bash
curl "https://api.rhumb.dev/v2/recipes?category=productivity" \
  -H "Authorization: Bearer rk_live_abc123"
```

#### Endpoint: Get Recipe Schema

```
GET /v2/recipes/{recipe_id}
```

Returns full recipe definition including DAG visualization, step details, input/output schemas.

---

### 1.6 Shared Endpoints

#### Poll Receipt / Async Status

```
GET /v2/receipts/{receipt_id}
```

**curl example:**

```bash
curl https://api.rhumb.dev/v2/receipts/rcpt_04HA2N5P6Q7R8 \
  -H "Authorization: Bearer rk_live_abc123"
```

#### Policy CRUD

```
GET    /v2/policy              # Get current policy
PUT    /v2/policy              # Replace policy
PATCH  /v2/policy              # Partial update
DELETE /v2/policy              # Reset to defaults
```

---

## 2. Capability Contract Schema

The canonical JSON Schema definition for a Rhumb capability:

```json
{
  "$schema": "https://schema.rhumb.dev/capability/v1",
  "id": "send_email",
  "name": "Send Email",
  "version": "1.2.0",
  "category": "communication",
  "subcategory": "email",
  "stability": "stable",
  "description": "Send a transactional or marketing email via the best available provider. Normalizes delivery status and message IDs across providers.",
  "tags": ["email", "notification", "transactional"],
  
  "parameters": {
    "type": "object",
    "required": ["to", "subject", "body"],
    "properties": {
      "to": {
        "type": "string",
        "format": "email",
        "description": "Recipient email address"
      },
      "to_name": {
        "type": "string",
        "description": "Recipient display name",
        "maxLength": 255
      },
      "from": {
        "type": "string",
        "format": "email",
        "description": "Sender email address (must be verified with provider)"
      },
      "from_name": {
        "type": "string",
        "description": "Sender display name",
        "maxLength": 255
      },
      "subject": {
        "type": "string",
        "description": "Email subject line",
        "maxLength": 998
      },
      "body": {
        "type": "string",
        "description": "Email body (plain text or HTML)"
      },
      "body_format": {
        "type": "string",
        "enum": ["text", "html"],
        "default": "text"
      },
      "reply_to": {
        "type": "string",
        "format": "email"
      },
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
      "status": {
        "type": "string",
        "enum": ["queued", "delivered", "failed"],
        "description": "Normalized delivery status"
      },
      "message_id": {
        "type": "string",
        "description": "Provider-normalized message ID"
      },
      "delivered_at": {
        "type": "string",
        "format": "date-time"
      },
      "provider_message_id": {
        "type": "string",
        "description": "Raw provider message ID for debugging"
      }
    }
  },
  
  "provider_requirements": {
    "minimum_providers": 1,
    "providers": [
      {
        "provider_id": "sendgrid",
        "tier": "preferred",
        "capabilities_required": ["mail.send"],
        "min_version": "3.0.0"
      },
      {
        "provider_id": "mailgun",
        "tier": "standard",
        "capabilities_required": ["messages"],
        "min_version": "4.0.0"
      },
      {
        "provider_id": "postmark",
        "tier": "standard",
        "capabilities_required": ["email"]
      },
      {
        "provider_id": "ses",
        "tier": "fallback",
        "capabilities_required": ["SendEmail"],
        "notes": "Requires BYO credentials due to account verification requirements"
      }
    ]
  },
  
  "credential_modes": {
    "supported": ["byo", "rhumb_managed", "agent_vault"],
    "default": "rhumb_managed",
    "notes": "BYO requires pre-verified sender domain per provider"
  },
  
  "pricing_hints": {
    "pricing_model": "per_call",
    "estimated_cost_usd": {
      "min": 0.00005,
      "max": 0.001,
      "typical": 0.0001
    },
    "cost_factors": ["attachment_size_bytes"],
    "free_tier": {
      "available": false
    }
  },
  
  "rate_limit_metadata": {
    "default_limits": {
      "requests_per_second": 10,
      "requests_per_minute": 300,
      "requests_per_day": 10000
    },
    "burst_allowed": true,
    "burst_multiplier": 2.0,
    "rate_limit_scope": "per_api_key"
  },
  
  "idempotency": {
    "supported": true,
    "key_field": "idempotency_key",
    "window_seconds": 86400,
    "notes": "Identical key + parameters within window returns cached receipt"
  },
  
  "timeouts": {
    "default_ms": 10000,
    "max_ms": 30000,
    "min_ms": 1000
  },
  
  "changelog": [
    {
      "version": "1.2.0",
      "date": "2026-02-15",
      "changes": ["Added attachment support", "Added reply_to field"]
    },
    {
      "version": "1.1.0",
      "date": "2026-01-01",
      "changes": ["Added HTML body support", "Normalized delivered_at timestamp"]
    },
    {
      "version": "1.0.0",
      "date": "2025-12-01",
      "changes": ["Initial stable release"]
    }
  ]
}
```

---

## 3. Recipe Definition Schema

The canonical JSON Schema for a Rhumb recipe (compiled multi-step workflow):

```json
{
  "$schema": "https://schema.rhumb.dev/recipe/v1",
  "recipe_id": "transcribe_and_summarize_and_email",
  "name": "Transcribe, Summarize & Email",
  "version": "2.1.0",
  "category": "productivity",
  "description": "Transcribes an audio file, generates a summary, and emails the result to a specified recipient.",
  "stability": "stable",
  "tier": "premium",
  
  "inputs": {
    "type": "object",
    "required": ["audio_url", "recipient_email"],
    "properties": {
      "audio_url": {
        "type": "string",
        "format": "uri",
        "description": "URL to the audio file to transcribe"
      },
      "recipient_email": {
        "type": "string",
        "format": "email",
        "description": "Email address to send the summary to"
      },
      "summary_length": {
        "type": "string",
        "enum": ["short", "medium", "long"],
        "default": "medium",
        "description": "Desired summary length"
      },
      "email_subject": {
        "type": "string",
        "default": "Meeting Summary"
      }
    }
  },
  
  "outputs": {
    "type": "object",
    "properties": {
      "transcript": {
        "type": "string",
        "description": "Full transcript text"
      },
      "summary": {
        "type": "string",
        "description": "Generated summary"
      },
      "email_sent": {
        "type": "boolean"
      },
      "email_message_id": {
        "type": "string"
      }
    }
  },
  
  "steps": [
    {
      "step_id": "transcribe",
      "display_name": "Transcribe Audio",
      "capability_id": "transcribe_audio",
      "capability_version": "^2.0.0",
      "depends_on": [],
      "parameters": {
        "audio_url": {"$ref": "inputs.audio_url"},
        "language": "en",
        "format": "text"
      },
      "outputs_captured": {
        "transcript_text": "result.transcript"
      },
      "artifact_capture": {
        "enabled": true,
        "artifact_key": "transcript_artifact",
        "ttl_hours": 168
      },
      "failure_mode": {
        "on_failure": "halt",
        "retries": 2,
        "retry_backoff": "exponential",
        "retry_base_ms": 1000
      },
      "budget": {
        "max_cost_usd": 0.10,
        "timeout_ms": 60000
      },
      "approval_gate": null
    },
    {
      "step_id": "summarize",
      "display_name": "Generate Summary",
      "capability_id": "summarize_text",
      "capability_version": "^1.0.0",
      "depends_on": ["transcribe"],
      "parameters": {
        "text": {"$ref": "steps.transcribe.outputs.transcript_text"},
        "length": {"$ref": "inputs.summary_length"},
        "format": "prose"
      },
      "outputs_captured": {
        "summary_text": "result.summary"
      },
      "artifact_capture": {
        "enabled": true,
        "artifact_key": "summary_artifact",
        "ttl_hours": 168
      },
      "failure_mode": {
        "on_failure": "halt",
        "retries": 1,
        "fallback_step": null
      },
      "budget": {
        "max_cost_usd": 0.05,
        "timeout_ms": 30000
      },
      "approval_gate": null
    },
    {
      "step_id": "notify",
      "display_name": "Send Email Notification",
      "capability_id": "send_email",
      "capability_version": "^1.0.0",
      "depends_on": ["summarize"],
      "parameters": {
        "to": {"$ref": "inputs.recipient_email"},
        "subject": {"$ref": "inputs.email_subject"},
        "body": {"$ref": "steps.summarize.outputs.summary_text"},
        "body_format": "text"
      },
      "outputs_captured": {
        "email_sent": "result.status == 'delivered'",
        "email_message_id": "result.message_id"
      },
      "artifact_capture": {
        "enabled": false
      },
      "failure_mode": {
        "on_failure": "continue",
        "retries": 3,
        "retry_backoff": "exponential",
        "notes": "Email failure is non-fatal — transcript and summary still captured"
      },
      "budget": {
        "max_cost_usd": 0.01,
        "timeout_ms": 15000
      },
      "approval_gate": null
    }
  ],
  
  "dag": {
    "edges": [
      {"from": "transcribe", "to": "summarize"},
      {"from": "summarize", "to": "notify"}
    ],
    "parallelizable_groups": [
      ["transcribe"]
    ],
    "critical_path": ["transcribe", "summarize", "notify"]
  },
  
  "budget": {
    "max_total_cost_usd": 0.50,
    "per_step_budgets_enforced": true,
    "on_budget_exceeded": "halt_current_step"
  },
  
  "approval_gates": {
    "mode": "auto",
    "manual_steps": [],
    "threshold_usd": null,
    "notes": "No manual approval gates in this recipe. Set mode=manual to require human approval before any step."
  },
  
  "pricing_hints": {
    "estimated_total_cost_usd": {
      "min": 0.02,
      "max": 0.30,
      "typical": 0.05
    },
    "pricing_model": "per_execution"
  },
  
  "idempotency": {
    "supported": true,
    "window_seconds": 3600
  },
  
  "timeout": {
    "total_ms": 120000,
    "per_step_timeout_enforced": true
  },
  
  "changelog": [
    {
      "version": "2.1.0",
      "date": "2026-03-01",
      "changes": ["Added artifact capture for transcript and summary", "Made email step non-fatal"]
    },
    {
      "version": "2.0.0",
      "date": "2026-01-15",
      "changes": ["Breaking: summary_length enum changed from int to string", "Added email step"]
    }
  ]
}
```

---

## 4. Provider Adapter Interface

Every provider integration in Rhumb must implement the adapter contract. This section defines the canonical interface.

### 4.1 Adapter Registration Schema

```json
{
  "$schema": "https://schema.rhumb.dev/adapter/v1",
  "adapter_id": "sendgrid",
  "display_name": "SendGrid",
  "version": "3.0.0",
  "provider_type": "api",
  "homepage": "https://sendgrid.com",
  "docs_url": "https://docs.sendgrid.com/api-reference",
  
  "base_url": "https://api.sendgrid.com",
  "api_version": "v3",
  
  "auth": {
    "methods": ["api_key", "oauth2"],
    "primary_method": "api_key",
    "api_key_header": "Authorization",
    "api_key_prefix": "Bearer",
    "oauth2_config": null
  },
  
  "capabilities_supported": [
    {
      "rhumb_capability_id": "send_email",
      "rhumb_capability_version": "^1.0.0",
      "provider_endpoint": "POST /mail/send",
      "adapter_handler": "handlers/send_email.js"
    },
    {
      "rhumb_capability_id": "get_email_stats",
      "rhumb_capability_version": "^1.0.0",
      "provider_endpoint": "GET /stats",
      "adapter_handler": "handlers/get_stats.js"
    }
  ],
  
  "health_check": {
    "endpoint": "GET /user/profile",
    "expected_status": 200,
    "timeout_ms": 5000,
    "check_interval_seconds": 60
  },
  
  "rate_limits": {
    "global": {
      "requests_per_second": 100,
      "requests_per_day": 100000
    },
    "per_capability": {
      "send_email": {
        "requests_per_second": 100
      }
    },
    "headers": {
      "remaining": "X-RateLimit-Remaining",
      "reset": "X-RateLimit-Reset",
      "limit": "X-RateLimit-Limit"
    }
  },
  
  "regions": ["us-east-1", "eu-west-1"],
  "latency_p50_ms": 180,
  "latency_p99_ms": 800,
  
  "error_mapping": {
    "400": {"rhumb_code": "INVALID_PARAMETERS", "retryable": false},
    "401": {"rhumb_code": "CREDENTIAL_INVALID", "retryable": false},
    "403": {"rhumb_code": "PERMISSION_DENIED", "retryable": false},
    "429": {"rhumb_code": "RATE_LIMITED", "retryable": true, "retry_after_header": "X-RateLimit-Reset"},
    "500": {"rhumb_code": "PROVIDER_ERROR", "retryable": true},
    "503": {"rhumb_code": "PROVIDER_UNAVAILABLE", "retryable": true}
  }
}
```

### 4.2 Capability Handler Contract

Each adapter handler must implement this interface (TypeScript):

```typescript
interface CapabilityHandler {
  // Transform normalized Rhumb parameters into provider-specific request
  buildRequest(
    params: Record<string, unknown>,
    credentials: InjectedCredentials,
    context: ExecutionContext
  ): ProviderRequest;

  // Transform provider response into normalized Rhumb response
  normalizeResponse(
    raw: ProviderResponse,
    context: ExecutionContext
  ): NormalizedResult;

  // Map provider errors to Rhumb error envelope
  mapError(
    error: ProviderError,
    context: ExecutionContext
  ): RhumbError;

  // Optional: compute cost from provider response metadata
  computeCost(
    response: ProviderResponse,
    context: ExecutionContext
  ): CostBreakdown | null;
}

interface InjectedCredentials {
  mode: "byo" | "rhumb_managed" | "agent_vault";
  api_key?: string;
  oauth_token?: string;
  // Credentials are never logged or returned to caller
}

interface ExecutionContext {
  receipt_id: string;
  capability_id: string;
  agent_id?: string;
  idempotency_key?: string;
  policy: PolicySnapshot;
}
```

### 4.3 Health Check Contract

```json
{
  "provider_id": "sendgrid",
  "status": "healthy",
  "checked_at": "2026-03-30T20:41:55.000Z",
  "latency_ms": 145,
  "details": {
    "api_reachable": true,
    "credentials_valid": true,
    "rate_limit_remaining": 9842,
    "rate_limit_reset_at": "2026-03-30T20:42:00.000Z"
  },
  "degraded_reason": null
}
```

### 4.4 Rate Limit Reporting

Adapters report current rate limit state after each request:

```json
{
  "provider_id": "sendgrid",
  "capability_id": "send_email",
  "limits": {
    "requests_per_second": {"limit": 100, "remaining": 87, "reset_at": "2026-03-30T20:42:01.000Z"},
    "requests_per_day": {"limit": 100000, "remaining": 97234, "reset_at": "2026-03-31T00:00:00.000Z"}
  },
  "throttle_recommended": false
}
```

---

## 5. Policy Control Surface

Policy is a first-class API object. Agents set policy at account level, per-call, or via budget tokens.

### 5.1 Policy Schema (Full)

```json
{
  "$schema": "https://schema.rhumb.dev/policy/v1",
  "policy_id": "pol_01HX9K2M3N4P5Q6R",
  "name": "Production Agent Policy",
  "created_at": "2026-03-01T00:00:00.000Z",
  "updated_at": "2026-03-30T20:00:00.000Z",
  
  "provider_routing": {
    "preference": ["anthropic", "openai"],
    "deny": ["cohere"],
    "require": [],
    "notes": "preference is ordered list; deny overrides preference; require forces inclusion"
  },
  
  "cost_ceilings": {
    "per_call_usd": 0.50,
    "per_hour_usd": 5.00,
    "per_day_usd": 25.00,
    "per_month_usd": 200.00,
    "on_ceiling_exceeded": "reject_with_error",
    "ceiling_exceeded_alternatives": ["queue", "reject_with_error", "notify_and_continue"]
  },
  
  "region_restrictions": {
    "allowed_regions": ["us-east-1", "us-west-2", "eu-west-1"],
    "denied_regions": [],
    "require_data_residency": false,
    "data_residency_region": null
  },
  
  "approval_mode": {
    "mode": "auto",
    "manual_threshold_usd": null,
    "manual_capabilities": [],
    "webhook_url": null,
    "notes": "Mode options: auto | manual | threshold. threshold requires manual_threshold_usd."
  },
  
  "retry": {
    "enabled": true,
    "max_attempts": 3,
    "backoff": "exponential",
    "backoff_base_ms": 500,
    "backoff_max_ms": 10000,
    "retry_on": ["PROVIDER_ERROR", "PROVIDER_UNAVAILABLE", "RATE_LIMITED", "TIMEOUT"],
    "do_not_retry": ["INVALID_PARAMETERS", "CREDENTIAL_INVALID", "PERMISSION_DENIED", "BUDGET_EXCEEDED"]
  },
  
  "timeouts": {
    "default_ms": 30000,
    "max_ms": 120000,
    "per_capability_overrides": {
      "transcribe_audio": 90000,
      "generate_image": 60000
    }
  },
  
  "fallback": {
    "mode": "next_available",
    "fallback_chain_max_length": 3,
    "notify_on_fallback": true,
    "notes": "Mode options: next_available | none | specific_provider. specific_provider requires fallback_provider_id."
  },
  
  "observability": {
    "store_receipts": true,
    "receipt_ttl_days": 90,
    "include_raw_provider_response": false,
    "webhook_on_completion": null,
    "webhook_on_failure": null
  },
  
  "credential_mode_default": "rhumb_managed",
  
  "rate_limit_behavior": {
    "on_rate_limit": "retry_with_backoff",
    "max_wait_ms": 5000
  }
}
```

### 5.2 Per-Call Policy Override

Any execute endpoint accepts an inline `policy` object that overrides account-level policy for that call only:

```json
{
  "parameters": {"...": "..."},
  "policy": {
    "provider_preference": ["openai"],
    "max_cost_usd": 0.05,
    "timeout_ms": 10000,
    "retry": {"max_attempts": 1},
    "approval_mode": "manual"
  }
}
```

### 5.3 Budget Tokens (v1 — deferred to v1.1)

Budget tokens are pre-issued spending envelopes that can be handed to sub-agents:

```json
{
  "budget_token": "btok_01HX9K2M3N4P5Q6R7S8T",
  "budget_usd": 1.00,
  "spent_usd": 0.00,
  "remaining_usd": 1.00,
  "expires_at": "2026-03-31T00:00:00.000Z",
  "scope": {
    "capabilities": ["send_email", "summarize_text"],
    "providers": null
  },
  "created_by": "agent_main",
  "created_at": "2026-03-30T20:00:00.000Z"
}
```

**Note:** Budget token CRUD endpoints (`POST /v2/budget-tokens`, `GET /v2/budget-tokens/{id}`) are **deferred to v1.1**. Account-level cost ceilings are v1.

---

## 6. Error Envelope Design

Every error response — across all three layers — uses the same envelope. This is non-negotiable for agent reliability.

### 6.1 Standard Error Envelope

```json
{
  "error": {
    "code": "PROVIDER_ERROR",
    "category": "provider",
    "message": "The provider returned an internal server error",
    "detail": "SendGrid API returned HTTP 500 with body: {\"errors\":[{\"message\":\"The from address does not match a verified Sender Identity\"}]}",
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

### 6.2 Error Code Registry

| Code | Category | HTTP Status | Retryable | Description |
|------|----------|-------------|-----------|-------------|
| `INVALID_PARAMETERS` | client | 400 | No | Request parameters failed schema validation |
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
| `PROVIDER_ERROR` | provider | 502 | Yes | Provider returned 5xx error |
| `PROVIDER_UNAVAILABLE` | provider | 503 | Yes | Provider health check failing |
| `NO_PROVIDER_AVAILABLE` | routing | 503 | Yes | All providers for capability unavailable |
| `PROVIDER_TIMEOUT` | provider | 504 | Yes | Provider did not respond in time |
| `NORMALIZATION_ERROR` | internal | 500 | No | Response normalization failed |
| `RECIPE_STEP_FAILED` | recipe | 422 | Partial | One or more recipe steps failed |
| `RECIPE_BUDGET_EXCEEDED` | recipe | 402 | No | Recipe total cost exceeded budget |
| `TIMEOUT` | infra | 504 | Yes | Overall request timeout exceeded |
| `INTERNAL_ERROR` | internal | 500 | Yes | Rhumb internal error |

### 6.3 Partial Success — Recipe Errors

When a recipe partially succeeds (some steps complete, others fail), the response uses HTTP 207 Multi-Status:

```json
{
  "receipt_id": "rcpt_05HB3O6Q7R8S9T0U1V2W3X4Y5Z",
  "layer": 3,
  "status": "partial_failure",
  "recipe": {
    "id": "transcribe_and_summarize_and_email",
    "steps_total": 3,
    "steps_completed": 2,
    "steps_failed": 1
  },
  "result": {
    "outputs": {
      "transcript": "The meeting covered...",
      "summary": "Team aligned on...",
      "email_sent": false,
      "email_message_id": null
    },
    "artifacts": {
      "transcript_artifact_id": "art_01HX9K2",
      "summary_artifact_id": "art_01HX9K3"
    }
  },
  "steps": [
    {"step_id": "transcribe", "status": "completed", "cost_usd": 0.024},
    {"step_id": "summarize", "status": "completed", "cost_usd": 0.018},
    {
      "step_id": "notify",
      "status": "failed",
      "cost_usd": 0.00,
      "error": {
        "code": "PROVIDER_ERROR",
        "category": "provider",
        "message": "SendGrid returned 400: from address not verified",
        "retryable": false,
        "provider": {"id": "sendgrid", "http_status": 400}
      }
    }
  ],
  "errors": [
    {
      "step_id": "notify",
      "code": "RECIPE_STEP_FAILED",
      "category": "recipe",
      "message": "Step 'notify' failed: provider returned non-retryable error",
      "retryable": false,
      "failure_mode_applied": "continue"
    }
  ],
  "cost": {
    "total_usd": 0.042,
    "credits_deducted": 0.042
  }
}
```

---

## 7. Execution Receipt / Trace Schema

Every execution — regardless of layer — produces a receipt. Receipts are immutable, stored for 90 days by default, and retrievable via `GET /v2/receipts/{receipt_id}`.

### 7.1 Full Receipt Schema

```json
{
  "$schema": "https://schema.rhumb.dev/receipt/v1",
  "receipt_id": "rcpt_01HX9K2M3N4P5Q6R7S8T9U0V1W",
  "layer": 2,
  "api_version": "2026-03-30",
  
  "identity": {
    "api_key_id": "key_abc123",
    "agent_id": "my-agent-v1",
    "account_id": "acct_01HX9K2M"
  },
  
  "request": {
    "capability_id": "send_email",
    "capability_version": "1.2.0",
    "idempotency_key": "send-report-user-42-2026-03-30",
    "parameters_hash": "sha256:a1b2c3d4e5f6...",
    "parameters_snapshot": null
  },
  
  "routing": {
    "candidates_evaluated": [
      {"provider_id": "sendgrid", "score": 0.99, "selected": true, "reason": "policy_preference_match"},
      {"provider_id": "mailgun", "score": 0.97, "selected": false, "reason": "not_preferred"},
      {"provider_id": "postmark", "score": 0.98, "selected": false, "reason": "not_preferred"}
    ],
    "provider_selected": "sendgrid",
    "selection_reason": "policy_preference_match",
    "fallback_occurred": false,
    "fallback_chain": []
  },
  
  "policy_applied": {
    "policy_id": "pol_01HX9K2M3N4P5Q6R",
    "provider_preference_enforced": true,
    "deny_list_checked": true,
    "cost_ceiling_checked": true,
    "cost_ceiling_usd": 0.50,
    "retry_attempted": false,
    "retry_count": 0,
    "approval_required": false,
    "approval_mode": "auto"
  },
  
  "execution": {
    "provider_id": "sendgrid",
    "provider_capability": "mail.send",
    "credential_mode": "rhumb_managed",
    "provider_request_id": "SG-REQ-abc123",
    "provider_http_status": 200
  },
  
  "result": {
    "status": "success",
    "normalized_response": {
      "status": "delivered",
      "message_id": "msg_01HX9K2M3N4P5Q6R",
      "delivered_at": "2026-03-30T20:42:01.000Z"
    },
    "raw_response_stored": false
  },
  
  "cost": {
    "provider_cost_usd": 0.0001,
    "rhumb_markup_usd": 0.00005,
    "total_usd": 0.00015,
    "credits_deducted": 0.00015,
    "credit_balance_after": 12.4823,
    "cost_breakdown": [
      {"component": "api_call", "usd": 0.0001}
    ]
  },
  
  "latency": {
    "total_ms": 342,
    "breakdown": {
      "auth_ms": 2,
      "routing_ms": 8,
      "credential_injection_ms": 3,
      "provider_ms": 290,
      "normalization_ms": 12,
      "receipt_write_ms": 27
    }
  },
  
  "timestamps": {
    "received_at": "2026-03-30T20:42:01.000Z",
    "routing_started_at": "2026-03-30T20:42:01.002Z",
    "provider_called_at": "2026-03-30T20:42:01.013Z",
    "provider_responded_at": "2026-03-30T20:42:01.303Z",
    "completed_at": "2026-03-30T20:42:01.342Z"
  },
  
  "steps": null,
  
  "tags": {
    "environment": "production",
    "agent_version": "1.0.0"
  }
}
```

### 7.2 Recipe Receipt Extensions

For Layer 3 receipts, `steps` contains the full step-level trace:

```json
{
  "steps": [
    {
      "step_id": "transcribe",
      "sequence": 1,
      "capability_id": "transcribe_audio",
      "provider_used": "deepgram",
      "status": "completed",
      "cost_usd": 0.0240,
      "latency_ms": 8420,
      "artifact_id": "art_01HX9K2",
      "timestamps": {
        "started_at": "2026-03-30T20:42:00.100Z",
        "completed_at": "2026-03-30T20:42:08.520Z"
      },
      "retry_count": 0,
      "policy_applied": {
        "budget_enforced": true,
        "timeout_ms": 60000
      }
    }
  ]
}
```

---

## 8. Versioning Strategy

### 8.1 Capability Versioning

Capabilities follow **semantic versioning** with strict breaking change rules.

| Change Type | Version Bump | Examples |
|-------------|--------------|---------|
| Add optional parameter | PATCH | New optional field in request |
| Add optional response field | PATCH | New field in normalized response |
| Fix normalization bug | PATCH | Correct timestamp format |
| Add required parameter | MINOR with default | New required field + default value |
| Change response field name | MAJOR | Rename `status` to `delivery_status` |
| Remove parameter | MAJOR | Drop deprecated field |
| Change parameter type | MAJOR | `number` to `string` |
| Remove response field | MAJOR | Drop normalized field |

**Breaking Change Detection:**

Rhumb runs automated schema diffing on every capability version bump. Breaking changes trigger:
1. Creation of new major version (e.g., `send_email@2.0.0`)
2. Old version enters `deprecated` stability tier
3. Deprecation warning in all responses using old version (`X-Rhumb-Deprecation` header)
4. 90-day deprecation window before old version becomes `retired`
5. Retired versions return `CAPABILITY_RETIRED` error with migration hint

```json
{
  "X-Rhumb-Deprecation": "send_email@1.2.0 is deprecated. Migrate to send_email@2.0.0 by 2026-06-30. See https://docs.rhumb.dev/migrations/send_email_v2"
}
```

### 8.2 Recipe Versioning

Recipes use the same semver rules. Recipe breaking changes:
- Any change to `inputs` schema that removes or renames a required field
- Any change to `outputs` schema that removes a field
- Any change to step DAG that alters execution order in ways that change observable behavior

Recipe versions are pinned at execution time. A recipe execution always uses the version specified in the request (or `stable` alias which resolves to latest stable).

### 8.3 API Surface Versioning

The REST API uses **date-based versioning** via:
1. URL path prefix (`/v2/`)  — major structural changes only
2. `X-Rhumb-Version: 2026-03-30` header — fine-grained date-pinned behavior

Date-pinned versions lock response shapes and behavior for that date. Rhumb guarantees:
- A date-pinned version works unchanged for **2 years** from the pin date
- After 2 years: 90-day notice period, then retirement
- Pin is per-request, per-API-key default, or account default

### 8.4 Provider Adapter Versioning

Adapters use semver. When a provider changes their API:
1. Adapter patch version bumps transparently (no agent impact)
2. If normalization behavior changes, adapter minor version bumps
3. Capability minor/major version bumps when provider changes break capability contract

**Migration Tooling (v1):**

```bash
# Check which capabilities an API key currently uses
curl https://api.rhumb.dev/v2/usage/capabilities \
  -H "Authorization: Bearer rk_live_abc123"

# Get migration hints for all deprecated capabilities in use
curl https://api.rhumb.dev/v2/deprecations \
  -H "Authorization: Bearer rk_live_abc123"
```

---

## 9. Migration Path

### 9.1 Current State

The existing API has a single execution endpoint:

```
POST /v1/capabilities/{capability_id}/execute
```

This maps to **Layer 2** in the new architecture. All 16 callable providers route through this endpoint with the existing credential modes and routing logic.

### 9.2 v1 Compatibility Layer

The `/v1/` namespace is preserved indefinitely. v1 requests are:

1. Received by the v2 gateway
2. Translated to v2 Layer 2 requests
3. Executed via the v2 execution engine
4. Response translated back to v1 shape

This is transparent to existing users. No action required from v1 consumers.

**v1 → v2 Translation Rules:**

```
/v1/capabilities/{id}/execute → /v2/capabilities/{id}/execute (Layer 2)

v1 request body:     { parameters: {}, credential_mode: "..." }
v2 internal:         { parameters: {}, credential_mode: "...", policy: {} }

v1 response:         { result: {}, cost: {}, latency_ms: N }
v2 response:         { receipt_id: "...", layer: 2, result: {}, cost: {}, latency: {} }
v1 compat layer:     strips receipt_id, steps, routing; returns v1-shaped response
```

### 9.3 Header-Based Version Negotiation

Clients opt into v2 behavior without changing the URL:

```
X-Rhumb-API: v2
```

When this header is present on a `/v1/` request, the full v2 response shape is returned. This lets existing integrations migrate incrementally.

**Progressive Migration Path:**

```
Phase 1 (v1 consumers):   /v1/capabilities/{id}/execute → works unchanged
Phase 2 (opt-in v2):      /v1/ + X-Rhumb-API: v2 header → v2 response shape
Phase 3 (migrate URL):    /v2/capabilities/{id}/execute → full v2
Phase 4 (new features):   /v2/providers/{id}/execute, /v2/recipes/{id}/execute
```

### 9.4 Phased Rollout Plan

**Phase 1 — v2 Gateway with v1 Compat (Month 1)**
- Deploy v2 routing engine behind existing `/v1/` path
- All existing traffic routes transparently through v2 internals
- No client changes required
- New `receipt_id` available in response (additive, non-breaking)
- Validate: 0 regression on existing v1 consumers

**Phase 2 — v2 URL Surface (Month 2)**
- Publish `/v2/` endpoints
- All new documentation points to `/v2/`
- v1 docs updated with migration notice and timeline
- Layer 1 (`/v2/providers/`) available in beta
- Announce to existing users via email + changelog

**Phase 3 — Layer 3 / Recipes (Month 3-4)**
- `/v2/recipes/` endpoints available in beta
- MCP tools updated to expose all three layers
- SDK released with v2 bindings

**Phase 4 — v1 Deprecation Notice (Month 6)**
- `/v1/` enters soft deprecation
- `X-Rhumb-Deprecation` header on all v1 responses
- 12-month deprecation window announced
- Migration guides published for all 415 capabilities

**Phase 5 — v1 Retirement (Month 18)**
- `/v1/` returns 410 Gone with redirect hint
- All consumers on v2

### 9.5 Backward Compatibility Guarantees

Rhumb commits to:
- v1 compatibility maintained for minimum 18 months post-v2 GA
- No breaking changes to v2 stable capabilities without 90-day notice
- Date-pinned API versions honored for 2 years

---

## 10. SDK Design / MCP Tool Interface

### 10.1 MCP Server Architecture

The Rhumb MCP server (`rhumb-mcp`) exposes the three-layer architecture as discrete tool groups. Tool availability is governed by account tier and API key permissions.

**MCP Server Configuration:**

```json
{
  "name": "rhumb",
  "version": "2.0.0",
  "description": "Rhumb Resolve — managed execution substrate for AI agents",
  "tool_groups": ["layer1_raw", "layer2_capabilities", "layer3_recipes", "management"],
  "authentication": {
    "type": "api_key",
    "header": "X-Rhumb-Api-Key"
  }
}
```

### 10.2 Layer 1 MCP Tools

#### `rhumb_raw_execute`

```json
{
  "name": "rhumb_raw_execute",
  "description": "Execute a capability directly on a named provider. Use when you need exact provider control, specific model versions, or provider-specific parameters not exposed in the normalized capability interface.",
  "inputSchema": {
    "type": "object",
    "required": ["provider_id", "capability", "parameters"],
    "properties": {
      "provider_id": {
        "type": "string",
        "description": "Rhumb provider ID (e.g., 'openai', 'anthropic', 'sendgrid')"
      },
      "capability": {
        "type": "string",
        "description": "Provider capability to invoke (e.g., 'chat.completions', 'mail.send')"
      },
      "parameters": {
        "type": "object",
        "description": "Provider-native parameters. Passed through without normalization."
      },
      "credential_mode": {
        "type": "string",
        "enum": ["byo", "rhumb_managed", "agent_vault"],
        "default": "rhumb_managed"
      },
      "policy": {
        "type": "object",
        "description": "Optional per-call policy overrides",
        "properties": {
          "max_cost_usd": {"type": "number"},
          "timeout_ms": {"type": "number"}
        }
      }
    }
  }
}
```

#### `rhumb_list_providers`

```json
{
  "name": "rhumb_list_providers",
  "description": "List available providers and their supported capabilities. Use to discover what providers are available before using rhumb_raw_execute.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "capability": {
        "type": "string",
        "description": "Filter providers by capability (e.g., 'chat.completions')"
      },
      "status": {
        "type": "string",
        "enum": ["healthy", "degraded", "all"],
        "default": "healthy"
      }
    }
  }
}
```

### 10.3 Layer 2 MCP Tools

#### `rhumb_execute`

```json
{
  "name": "rhumb_execute",
  "description": "Execute a Rhumb capability. Rhumb selects the best available provider, handles retries, normalizes the response, and returns a stable result schema. Use this for most tasks — it's the main Rhumb interface.",
  "inputSchema": {
    "type": "object",
    "required": ["capability_id", "parameters"],
    "properties": {
      "capability_id": {
        "type": "string",
        "description": "Rhumb capability ID (e.g., 'send_email', 'transcribe_audio', 'generate_image'). Use rhumb_list_capabilities to discover available capabilities."
      },
      "parameters": {
        "type": "object",
        "description": "Capability-specific parameters. See the capability schema for required and optional fields."
      },
      "policy": {
        "type": "object",
        "description": "Optional policy overrides for this call",
        "properties": {
          "provider_preference": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ordered list of preferred provider IDs"
          },
          "provider_deny": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Provider IDs to exclude"
          },
          "max_cost_usd": {"type": "number", "description": "Maximum cost for this call"},
          "timeout_ms": {"type": "number", "description": "Timeout in milliseconds"},
          "retry": {
            "type": "object",
            "properties": {
              "max_attempts": {"type": "integer"},
              "backoff": {"type": "string", "enum": ["exponential", "linear", "none"]}
            }
          }
        }
      },
      "credential_mode": {
        "type": "string",
        "enum": ["byo", "rhumb_managed", "agent_vault"],
        "default": "rhumb_managed",
        "description": "Credential mode. rhumb_managed uses Rhumb's pooled credentials; byo uses your own."
      },
      "idempotency_key": {
        "type": "string",
        "description": "Optional idempotency key. Same key + parameters within 24h returns cached result."
      }
    }
  }
}
```

#### `rhumb_list_capabilities`

```json
{
  "name": "rhumb_list_capabilities",
  "description": "Search and list available Rhumb capabilities. Returns capability IDs, descriptions, and parameter schemas. Use before rhumb_execute to discover the right capability_id.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "category": {
        "type": "string",
        "description": "Filter by category (e.g., 'communication', 'ai', 'data', 'media')"
      },
      "q": {
        "type": "string",
        "description": "Full-text search query"
      },
      "provider": {
        "type": "string",
        "description": "Filter to capabilities supported by a specific provider"
      }
    }
  }
}
```

#### `rhumb_get_capability`

```json
{
  "name": "rhumb_get_capability",
  "description": "Get the full schema for a Rhumb capability, including all parameters, response shape, and supported providers. Use before rhumb_execute when you need to know exact parameter requirements.",
  "inputSchema": {
    "type": "object",
    "required": ["capability_id"],
    "properties": {
      "capability_id": {
        "type": "string",
        "description": "Capability ID to retrieve"
      }
    }
  }
}
```

### 10.4 Layer 3 MCP Tools

#### `rhumb_recipe_execute`

```json
{
  "name": "rhumb_recipe_execute",
  "description": "Execute a compiled Rhumb recipe — a pre-declared multi-step workflow. Recipes are deterministic, auditable, and production-grade. Use when you need multi-step capability composition with guaranteed execution order, artifact capture, and partial-failure handling. Do NOT use for ad-hoc orchestration — recipes are pre-compiled, not improvised.",
  "inputSchema": {
    "type": "object",
    "required": ["recipe_id", "inputs"],
    "properties": {
      "recipe_id": {
        "type": "string",
        "description": "Rhumb recipe ID. Use rhumb_list_recipes to discover available recipes."
      },
      "inputs": {
        "type": "object",
        "description": "Recipe input parameters. Required fields vary by recipe — see recipe schema."
      },
      "policy": {
        "type": "object",
        "description": "Recipe execution policy",
        "properties": {
          "max_total_cost_usd": {"type": "number"},
          "timeout_ms": {"type": "number"},
          "approval_mode": {
            "type": "string",
            "enum": ["auto", "manual"],
            "description": "auto = execute all steps; manual = require approval before each step"
          },
          "on_step_failure": {
            "type": "string",
            "enum": ["halt_and_report", "continue", "retry_then_halt"],
            "description": "What to do when a step fails. Recipe's step-level failure_mode takes precedence."
          }
        }
      },
      "credential_mode": {
        "type": "string",
        "enum": ["byo", "rhumb_managed", "agent_vault"],
        "default": "rhumb_managed"
      }
    }
  }
}
```

#### `rhumb_list_recipes`

```json
{
  "name": "rhumb_list_recipes",
  "description": "List available Rhumb recipes. Returns recipe IDs, descriptions, input schemas, and cost estimates.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "category": {"type": "string"},
      "q": {"type": "string"},
      "stability": {
        "type": "string",
        "enum": ["stable", "beta", "all"],
        "default": "stable"
      }
    }
  }
}
```

#### `rhumb_get_recipe`

```json
{
  "name": "rhumb_get_recipe",
  "description": "Get full schema for a Rhumb recipe including step definitions, DAG structure, input/output schemas, and cost estimates.",
  "inputSchema": {
    "type": "object",
    "required": ["recipe_id"],
    "properties": {
      "recipe_id": {"type": "string"}
    }
  }
}
```

### 10.5 Management MCP Tools

#### `rhumb_get_receipt`

```json
{
  "name": "rhumb_get_receipt",
  "description": "Retrieve an execution receipt by ID. Use to check status of async operations, audit past executions, or debug failures.",
  "inputSchema": {
    "type": "object",
    "required": ["receipt_id"],
    "properties": {
      "receipt_id": {"type": "string"}
    }
  }
}
```

#### `rhumb_get_policy`

```json
{
  "name": "rhumb_get_policy",
  "description": "Get the current execution policy for this API key. Shows cost ceilings, provider preferences, retry configuration, and approval mode.",
  "inputSchema": {
    "type": "object",
    "properties": {}
  }
}
```

#### `rhumb_update_policy`

```json
{
  "name": "rhumb_update_policy",
  "description": "Update the execution policy for this API key. Supports partial updates — only fields provided are changed.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "provider_preference": {
        "type": "array",
        "items": {"type": "string"}
      },
      "provider_deny": {
        "type": "array",
        "items": {"type": "string"}
      },
      "max_cost_per_call_usd": {"type": "number"},
      "max_cost_per_day_usd": {"type": "number"},
      "retry_max_attempts": {"type": "integer"},
      "approval_mode": {
        "type": "string",
        "enum": ["auto", "manual", "threshold"]
      },
      "approval_threshold_usd": {"type": "number"}
    }
  }
}
```

#### `rhumb_get_balance`

```json
{
  "name": "rhumb_get_balance",
  "description": "Get current credit balance and recent usage summary.",
  "inputSchema": {
    "type": "object",
    "properties": {}
  }
}
```

### 10.6 MCP Tool Count and Tier Availability

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

**Total v2 MCP tools: 12** (vs 17 in `rhumb-mcp@0.8.2` — consolidated and clarified)

### 10.7 TypeScript SDK (v1 — reference)

```typescript
import { RhumbClient } from "@rhumb/sdk";

const rhumb = new RhumbClient({ apiKey: process.env.RHUMB_API_KEY });

// Layer 2 — capability execution
const result = await rhumb.capabilities.execute("send_email", {
  parameters: {
    to: "user@example.com",
    subject: "Hello",
    body: "World"
  },
  policy: { maxCostUsd: 0.01 }
});

// Layer 1 — raw provider access
const rawResult = await rhumb.providers.execute("openai", {
  capability: "chat.completions",
  parameters: { model: "gpt-4o", messages: [...] }
});

// Layer 3 — recipe execution
const recipeResult = await rhumb.recipes.execute("transcribe_and_summarize", {
  inputs: { audioUrl: "https://...", recipientEmail: "..." }
});

// Async polling
const { receiptId, pollUrl } = await rhumb.recipes.execute("long_recipe", {
  inputs: { ... }
}, { async: true });

const receipt = await rhumb.receipts.poll(receiptId, { timeoutMs: 120000 });
```

**SDK packages (deferred to v1.1):** Python, Go. Node.js SDK is v1.

---

## Appendix A: What Is and Isn't v1

### ✅ v1 (Ship with initial release)

- Layer 2 execute endpoint (`/v2/capabilities/{id}/execute`)
- Layer 1 execute endpoint (`/v2/providers/{id}/execute`)
- Capability discovery (`GET /v2/capabilities`, `GET /v2/capabilities/{id}`)
- Provider listing (`GET /v2/providers`)
- v1 compatibility layer at `/v1/`
- Standard error envelope
- Execution receipts with full trace
- Account-level policy (all knobs except budget tokens)
- Per-call policy overrides
- Rate limiting and cost ceiling enforcement
- MCP tools: all Layer 1 and Layer 2 tools + management tools
- Date-pinned API versioning (`X-Rhumb-Version`)
- Idempotency keys

### 🔜 Deferred to v1.1

- Layer 3 / Recipes (`/v2/recipes/{id}/execute`)
- Recipe MCP tools
- Budget tokens (`/v2/budget-tokens`)
- Artifact storage and retrieval API
- Webhook on completion/failure
- Python and Go SDKs
- Approval gate webhooks (manual approval mode)
- Recipe authoring API (v1 recipes are Rhumb-curated only)

### 🔭 Deferred to v2 roadmap

- Agent identity federation (cross-agent trust)
- Public recipe marketplace
- Custom adapter registration by third parties
- Streaming execution results (SSE)
- Real-time observability dashboard API

---

## Appendix B: Design Principles (Non-Negotiable)

1. **Schema stability is the product.** Agents build on stable schemas. Breaking changes are treated as production incidents.

2. **Every execution is traceable.** No black boxes. Every routing decision, every cost, every provider choice is recorded and retrievable.

3. **Credentials never leak.** Credentials are injected server-side and never returned to callers, logged in plaintext, or included in receipts.

4. **Errors are actionable.** Every error includes: is it retryable? When? From which layer? What provider caused it? Where are the docs?

5. **Policy is explicit.** Routing decisions are explained in receipts. Agents know why a provider was chosen.

6. **Resolve compiles, it does not improvise.** Layer 3 recipes are declared workflows — not open-ended planners. If a workflow isn't pre-compiled into a recipe, it's Layer 2 territory.

7. **v1 compat is permanent infrastructure.** The migration cost to abandon v1 users is higher than the cost of maintaining a compat layer. We maintain it indefinitely.
