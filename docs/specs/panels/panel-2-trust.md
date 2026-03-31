# Panel 2: Trust, Observability & Governance
## Rhumb Resolve — Founding Product Specification

**Panel Composition:** Trust Systems Architects, Observability Platform Builders, Audit/Compliance Specialists, Data Governance Experts, Provider Relations Strategists, Neutrality/Marketplace Fairness Experts, SRE/Reliability Engineers

**Status:** v1 Draft — Engineering-Grade Specification  
**Scope:** All three execution layers (Raw Provider Access, Single Capability Delivery, Deterministic Composed Capabilities)

---

## Governing Principle

Every execution through Rhumb Resolve leaves a complete, tamper-evident record. Providers are never hidden. Routing decisions are always explainable. The AN Score is structurally incorruptible. Agents know exactly what happened, why it happened, who did it, and what it cost — every time, forever (within retention policy).

Trust is not a feature. It is the architecture.

---

## 1. Execution Receipt System

### 1.1 Design Philosophy

Every execution — regardless of layer — produces an **Execution Receipt**: an immutable, self-contained record of what was requested, what was executed, what was returned, and what it cost. Receipts are the atomic unit of observability in Resolve. They are the ground truth against which billing, debugging, compliance, and auditing are all reconciled.

Receipts are written synchronously at execution completion (or failure). They are never modified after creation. Amendments are new records that reference the original.

### 1.2 Core Receipt Schema

```json
{
  "$schema": "https://schemas.rhumb.ai/resolve/receipt/v1",
  "receipt_id": "rcpt_01HX4K7M9N3P5Q8R2S6T0W",
  "receipt_version": "1.0",
  "created_at": "2026-03-30T20:43:00.000Z",
  "finalized_at": "2026-03-30T20:43:02.347Z",

  "execution": {
    "execution_id": "exec_01HX4K7M9N3P5Q8R2S6T0V",
    "layer": 2,
    "layer_name": "single_capability_delivery",
    "capability_id": "cap_image_generation_text_to_image",
    "capability_version": "1.2.0",
    "status": "success",
    "attempt_number": 1,
    "total_attempts": 1
  },

  "identity": {
    "agent_id": "agent_01HX4K7M9N3P5Q8R2S6T0U",
    "agent_key_id": "key_01HX4K7M9N3P5Q8R2S6T0T",
    "workspace_id": "ws_01HX4K7M9N3P5Q8R2S6T0S",
    "org_id": "org_01HX4K7M9N3P5Q8R2S6T0R",
    "caller_ip_hash": "sha256:a1b2c3d4...",
    "request_id": "req_01HX4K7M9N3P5Q8R2S6T0Q"
  },

  "provider": {
    "provider_id": "openai",
    "provider_name": "OpenAI",
    "provider_model": "dall-e-3",
    "provider_endpoint": "https://api.openai.com/v1/images/generations",
    "credential_mode": "rhumb_managed",
    "credential_ref": "cred_rhumb_openai_pool_07",
    "provider_request_id": "prov-req-abc123xyz",
    "provider_region": "us-east-1",
    "provider_latency_ms": 2100
  },

  "routing": {
    "router_version": "2.1.4",
    "routing_strategy": "capability_optimized",
    "candidates_evaluated": 3,
    "winner_reason": "best_composite_score",
    "route_explanation_id": "rexp_01HX4K7M9N3P5Q8R2S6T0P",
    "policy_set_id": "policy_01HX4K7M9N3P5Q8R2S6T0O",
    "policy_overrides_applied": []
  },

  "timing": {
    "request_received_at": "2026-03-30T20:43:00.000Z",
    "routing_completed_at": "2026-03-30T20:43:00.041Z",
    "provider_request_sent_at": "2026-03-30T20:43:00.045Z",
    "provider_response_received_at": "2026-03-30T20:43:02.145Z",
    "normalization_completed_at": "2026-03-30T20:43:02.200Z",
    "response_sent_at": "2026-03-30T20:43:02.347Z",
    "total_latency_ms": 2347,
    "rhumb_overhead_ms": 247,
    "provider_latency_ms": 2100
  },

  "cost": {
    "currency": "USD",
    "provider_cost": 0.040,
    "rhumb_fee": 0.004,
    "total_cost": 0.044,
    "cost_breakdown": {
      "input_tokens": null,
      "output_tokens": null,
      "image_count": 1,
      "image_resolution": "1024x1024",
      "unit_cost": 0.040
    },
    "budget_impact": {
      "per_call_ceiling": 1.00,
      "per_day_consumed_before": 0.22,
      "per_day_consumed_after": 0.264,
      "per_month_consumed_before": 3.41,
      "per_month_consumed_after": 3.454
    }
  },

  "payload_hash": {
    "request_hash": "sha256:f3a9c2e1...",
    "response_hash": "sha256:b7d4e8f2...",
    "hash_algorithm": "sha256",
    "payload_stored": false,
    "payload_storage_ref": null
  },

  "error": null,

  "recipe_context": null,

  "compliance": {
    "data_residency_region": "us",
    "pii_detected": false,
    "pii_scrubbed": false,
    "gdpr_subject_id": null,
    "retention_policy_id": "ret_standard_90d",
    "retention_expires_at": "2026-06-28T20:43:02.347Z"
  },

  "integrity": {
    "receipt_hash": "sha256:9f1c3b7a...",
    "previous_receipt_hash": "sha256:2e4d6f8a...",
    "chain_sequence": 10483,
    "signed_at": "2026-03-30T20:43:02.400Z",
    "signing_key_id": "rhumb_receipt_signing_key_v3"
  }
}
```

### 1.3 Layer-Specific Receipt Extensions

**Layer 1 Extension (Raw Provider Access):**
```json
{
  "layer1_extension": {
    "raw_passthrough": true,
    "agent_specified_provider": "openai",
    "agent_specified_model": "gpt-4o",
    "rhumb_modifications": [],
    "fidelity_guarantee": "exact_passthrough",
    "normalization_applied": false
  }
}
```

**Layer 3 Extension (Deterministic Composed Capabilities):**
```json
{
  "layer3_extension": {
    "recipe_id": "recipe_content_pipeline_v2",
    "recipe_version": "2.1.0",
    "recipe_execution_id": "rexec_01HX4K7M9N3P5Q8R2S6T0N",
    "step_index": 2,
    "step_name": "image_generation",
    "total_steps": 5,
    "parent_receipt_id": null,
    "child_receipt_ids": [],
    "step_budget_ceiling": 0.10,
    "step_budget_consumed": 0.044,
    "artifact_refs": [
      {
        "artifact_id": "art_01HX4K7M9N3P5Q8R2S6T0M",
        "artifact_type": "image",
        "artifact_url": "https://artifacts.rhumb.ai/art_01HX4K7M9N3P5Q8R2S6T0M",
        "artifact_expires_at": "2026-04-30T20:43:02.347Z"
      }
    ]
  }
}
```

### 1.4 Storage Strategy

**Write Path:**
- Receipts written synchronously to primary store (PostgreSQL with append-only table) before response is returned
- Async replication to cold storage (S3-compatible object store) within 60 seconds
- Receipt chain hash computed and written at finalization; previous receipt hash links to last receipt for same agent_id

**Read Path:**
- Hot tier: PostgreSQL (last 30 days, indexed by agent_id, capability_id, provider_id, created_at)
- Warm tier: S3 with Parquet files partitioned by org/date (30–365 days)
- Cold tier: S3 Glacier or equivalent (365 days+, compliance retention)

**Retention Policies:**

| Policy ID | Hot Tier | Warm Tier | Cold Tier | Total |
|-----------|----------|-----------|-----------|-------|
| `ret_standard_90d` | 30 days | 60 days | — | 90 days |
| `ret_standard_1y` | 30 days | 335 days | — | 365 days |
| `ret_compliance_7y` | 30 days | 335 days | 6 years | 7 years |
| `ret_gdpr_delete` | On request | On request | Purged | Until deletion request |

### 1.5 Agent Query API

```
GET /v1/receipts
  ?agent_id=agent_xxx           # defaults to calling agent
  &capability_id=cap_xxx        # filter by capability
  &provider_id=openai           # filter by provider
  &status=success|error|partial
  &from=2026-03-01T00:00:00Z
  &to=2026-03-31T23:59:59Z
  &layer=1|2|3
  &recipe_id=recipe_xxx
  &limit=100                    # max 1000
  &cursor=rcpt_xxx              # pagination cursor
  &include_cost=true
  &include_routing=true

GET /v1/receipts/{receipt_id}
  Returns full receipt including all extensions

GET /v1/receipts/{receipt_id}/explanation
  Returns the route explanation record

POST /v1/receipts/export
  Body: { "format": "json|csv|parquet", "filter": {...}, "destination": "download|s3_presigned" }
  Returns: export job ID and status URL
```

---

## 2. Provider Attribution Model

### 2.1 Attribution Guarantee

At every layer, in every response, the provider that executed the work is explicitly identified. There are no phantom executions. Abstraction does not mean erasure.

### 2.2 Response Headers (Always Present)

Every API response from Resolve includes:

```
X-Rhumb-Provider: openai
X-Rhumb-Provider-Model: dall-e-3
X-Rhumb-Provider-Region: us-east-1
X-Rhumb-Execution-Id: exec_01HX4K7M9N3P5Q8R2S6T0V
X-Rhumb-Receipt-Id: rcpt_01HX4K7M9N3P5Q8R2S6T0W
X-Rhumb-Layer: 2
X-Rhumb-Route-Explanation-Id: rexp_01HX4K7M9N3P5Q8R2S6T0P
X-Rhumb-Cost-Usd: 0.044
X-Rhumb-Latency-Ms: 2347
```

### 2.3 Response Body Attribution Block

All Resolve responses include a `_rhumb` metadata block:

```json
{
  "_rhumb": {
    "execution_id": "exec_01HX4K7M9N3P5Q8R2S6T0V",
    "receipt_id": "rcpt_01HX4K7M9N3P5Q8R2S6T0W",
    "layer": 2,
    "provider": {
      "id": "openai",
      "name": "OpenAI",
      "model": "dall-e-3",
      "logo_url": "https://cdn.rhumb.ai/providers/openai/logo.svg",
      "docs_url": "https://platform.openai.com/docs/api-reference",
      "provider_request_id": "prov-req-abc123xyz"
    },
    "cost_usd": 0.044,
    "latency_ms": 2347,
    "explanation_url": "https://resolve.rhumb.ai/receipts/rcpt_01HX4K7M9N3P5Q8R2S6T0W/explanation"
  }
}
```

### 2.4 Attribution in Error Messages

Provider errors are never swallowed. Error envelopes always include provider identity:

```json
{
  "error": {
    "code": "PROVIDER_RATE_LIMITED",
    "message": "Provider returned 429 Too Many Requests",
    "provider": {
      "id": "openai",
      "name": "OpenAI",
      "error_code": "rate_limit_exceeded",
      "provider_message": "Rate limit reached for model dall-e-3",
      "retry_after_seconds": 60
    },
    "rhumb_action": "attempted_fallback",
    "fallback_result": "no_eligible_fallback_provider",
    "execution_id": "exec_01HX4K7M9N3P5Q8R2S6T0V",
    "receipt_id": "rcpt_01HX4K7M9N3P5Q8R2S6T0W"
  }
}
```

### 2.5 Attribution in Billing

Every billing line item links to a receipt and names the provider:

```json
{
  "billing_line_item": {
    "line_id": "line_01HX4K7M9N3P5Q8R2S6T0L",
    "receipt_id": "rcpt_01HX4K7M9N3P5Q8R2S6T0W",
    "execution_id": "exec_01HX4K7M9N3P5Q8R2S6T0V",
    "provider_id": "openai",
    "provider_name": "OpenAI",
    "capability_id": "cap_image_generation_text_to_image",
    "provider_cost_usd": 0.040,
    "rhumb_fee_usd": 0.004,
    "total_usd": 0.044,
    "billed_at": "2026-03-30T20:43:02.347Z"
  }
}
```

---

## 3. Route Explanation Engine

### 3.1 Philosophy

Routing is not a black box. Every routing decision in Layer 2 and Layer 3 produces a complete, queryable explanation. The explanation records every candidate evaluated, every factor weighted, and the final selection rationale. Agents can audit any routing decision.

### 3.2 Route Explanation Schema

```json
{
  "$schema": "https://schemas.rhumb.ai/resolve/route-explanation/v1",
  "explanation_id": "rexp_01HX4K7M9N3P5Q8R2S6T0P",
  "execution_id": "exec_01HX4K7M9N3P5Q8R2S6T0V",
  "receipt_id": "rcpt_01HX4K7M9N3P5Q8R2S6T0W",
  "capability_id": "cap_image_generation_text_to_image",
  "created_at": "2026-03-30T20:43:00.041Z",
  "routing_duration_ms": 41,

  "winner": {
    "provider_id": "openai",
    "provider_name": "OpenAI",
    "model": "dall-e-3",
    "composite_score": 0.847,
    "selection_reason": "highest_composite_score_within_policy"
  },

  "candidates": [
    {
      "provider_id": "openai",
      "provider_name": "OpenAI",
      "model": "dall-e-3",
      "eligible": true,
      "composite_score": 0.847,
      "factors": {
        "an_score": {
          "value": 0.89,
          "weight": 0.20,
          "weighted_contribution": 0.178,
          "source": "an_score_v4_published_2026_03_01"
        },
        "availability": {
          "value": 0.999,
          "weight": 0.30,
          "weighted_contribution": 0.300,
          "p99_uptime_30d": 0.9991
        },
        "estimated_cost_usd": {
          "value": 0.040,
          "normalized_score": 0.72,
          "weight": 0.25,
          "weighted_contribution": 0.180,
          "cost_rank": 2
        },
        "latency_p50_ms": {
          "value": 1800,
          "normalized_score": 0.75,
          "weight": 0.15,
          "weighted_contribution": 0.113,
          "latency_rank": 1
        },
        "credential_mode_preference": {
          "value": "rhumb_managed",
          "score": 1.0,
          "weight": 0.10,
          "weighted_contribution": 0.100,
          "note": "Agent policy prefers rhumb_managed"
        }
      },
      "policy_checks": {
        "pinned": false,
        "denied": false,
        "region_allowed": true,
        "data_residency_compliant": true,
        "cost_ceiling_ok": true
      }
    },
    {
      "provider_id": "stability_ai",
      "provider_name": "Stability AI",
      "model": "stable-diffusion-xl",
      "eligible": true,
      "composite_score": 0.721,
      "factors": {
        "an_score": { "value": 0.81, "weight": 0.20, "weighted_contribution": 0.162 },
        "availability": { "value": 0.992, "weight": 0.30, "weighted_contribution": 0.298 },
        "estimated_cost_usd": { "value": 0.018, "normalized_score": 1.0, "weight": 0.25, "weighted_contribution": 0.250 },
        "latency_p50_ms": { "value": 3200, "normalized_score": 0.41, "weight": 0.15, "weighted_contribution": 0.062 },
        "credential_mode_preference": { "value": "byo", "score": 0.5, "weight": 0.10, "weighted_contribution": 0.050 }
      },
      "policy_checks": {
        "pinned": false,
        "denied": false,
        "region_allowed": true,
        "data_residency_compliant": true,
        "cost_ceiling_ok": true
      }
    },
    {
      "provider_id": "midjourney_api",
      "provider_name": "Midjourney",
      "model": "v6",
      "eligible": false,
      "ineligibility_reason": "AGENT_DENY_LIST",
      "composite_score": null,
      "factors": null,
      "policy_checks": {
        "denied": true,
        "deny_reason": "Agent policy denies midjourney_api for this workspace"
      }
    }
  ],

  "policy_applied": {
    "policy_set_id": "policy_01HX4K7M9N3P5Q8R2S6T0O",
    "active_rules": [
      { "rule_id": "rule_deny_midjourney", "type": "deny_list", "matched": true, "provider": "midjourney_api" },
      { "rule_id": "rule_prefer_rhumb_managed", "type": "credential_preference", "matched": true }
    ]
  },

  "human_summary": "OpenAI (DALL-E 3) selected over 2 other candidates. Midjourney excluded by deny list. OpenAI won on composite score (0.847) driven by strong availability (99.9%) and highest AN Score (0.89) among eligible providers. Stability AI was cheaper ($0.018 vs $0.040) but lost on latency and AN Score."
}
```

### 3.3 Explanation Surfacing

| Channel | Content | Availability |
|---------|---------|-------------|
| Response headers | `X-Rhumb-Route-Explanation-Id` + link | Every request, v1 |
| Response body `_rhumb` block | `explanation_url` field | Every request, v1 |
| Receipt field | `routing.route_explanation_id` | Every receipt, v1 |
| Dashboard | Visual routing breakdown with factor weights | v1 |
| API endpoint | `GET /v1/receipts/{receipt_id}/explanation` | v1 |
| Streaming | `X-Rhumb-Route-Explanation-Id` in SSE header | v2 |

---

## 4. Policy Enforcement Framework

### 4.1 Policy Architecture

Policies are evaluated synchronously before any routing decision. Policy evaluation is the first gate — providers that fail policy are excluded from the candidate pool entirely before scoring. Policy enforcement is deterministic and logged.

### 4.2 Complete Policy Schema

```json
{
  "$schema": "https://schemas.rhumb.ai/resolve/policy/v1",
  "policy_set_id": "policy_01HX4K7M9N3P5Q8R2S6T0O",
  "name": "Production Safety Policy",
  "version": "3.1",
  "scope": {
    "workspace_id": "ws_01HX4K7M9N3P5Q8R2S6T0S",
    "applies_to": ["all_capabilities"],
    "capability_overrides": []
  },
  "created_at": "2026-03-01T00:00:00Z",
  "updated_at": "2026-03-28T12:00:00Z",
  "updated_by": "agent_01HX4K7M9N3P5Q8R2S6T0U",

  "provider_controls": {
    "pin": [
      {
        "rule_id": "rule_pin_anthropic_text",
        "capability_pattern": "cap_text_*",
        "provider_id": "anthropic",
        "reason": "Compliance requirement: all text generation via Anthropic",
        "override_allowed": false
      }
    ],
    "deny": [
      {
        "rule_id": "rule_deny_midjourney",
        "provider_id": "midjourney_api",
        "reason": "Licensing concerns",
        "capability_pattern": "*"
      }
    ],
    "prefer": [
      {
        "rule_id": "rule_prefer_rhumb_managed",
        "credential_mode": "rhumb_managed",
        "score_boost": 0.05,
        "reason": "Operational simplicity preference"
      }
    ],
    "allow_only": null
  },

  "cost_controls": {
    "per_call": {
      "ceiling_usd": 1.00,
      "action_on_breach": "block",
      "warn_at_usd": 0.80
    },
    "per_day": {
      "ceiling_usd": 50.00,
      "action_on_breach": "block",
      "warn_at_usd": 40.00,
      "reset_at_utc_hour": 0
    },
    "per_month": {
      "ceiling_usd": 500.00,
      "action_on_breach": "block",
      "warn_at_usd": 400.00
    },
    "per_recipe": {
      "default_ceiling_usd": 5.00,
      "recipe_overrides": {
        "recipe_content_pipeline_v2": { "ceiling_usd": 2.00 }
      }
    },
    "per_capability": {
      "cap_image_generation_text_to_image": { "ceiling_usd": 0.10 }
    }
  },

  "region_controls": {
    "allowed_provider_regions": ["us-east-1", "us-west-2", "eu-west-1"],
    "denied_provider_regions": ["cn-*", "ru-*"],
    "require_region_match": false,
    "data_residency": {
      "enabled": true,
      "allowed_regions": ["us", "eu"],
      "pii_handling": "block_if_outside_region",
      "compliance_standard": "GDPR"
    }
  },

  "approval_controls": {
    "default_mode": "auto_approve",
    "rules": [
      {
        "rule_id": "rule_manual_approve_high_cost",
        "trigger": "cost_per_call_exceeds_usd",
        "threshold": 0.50,
        "mode": "manual_approve",
        "approval_timeout_seconds": 300,
        "timeout_action": "block",
        "notify_channels": ["webhook_slack_alerts"]
      },
      {
        "rule_id": "rule_threshold_approve_recipe",
        "trigger": "recipe_total_cost_exceeds_usd",
        "threshold": 2.00,
        "mode": "threshold_approve",
        "auto_approve_below": 2.00,
        "manual_require_above": 5.00
      },
      {
        "rule_id": "rule_manual_new_provider",
        "trigger": "first_use_of_provider",
        "mode": "manual_approve",
        "approval_timeout_seconds": 86400,
        "timeout_action": "block"
      }
    ]
  },

  "retry_controls": {
    "max_retries": 3,
    "retry_same_provider": false,
    "retry_with_fallback": true,
    "retry_on": ["PROVIDER_TIMEOUT", "PROVIDER_RATE_LIMITED", "PROVIDER_SERVER_ERROR"],
    "no_retry_on": ["PROVIDER_AUTH_ERROR", "POLICY_BLOCKED", "BUDGET_EXCEEDED"]
  }
}
```

### 4.3 Policy Evaluation Order

```
1. Parse incoming request
2. Load effective policy set (workspace + capability-level overrides)
3. Evaluate deny list → remove ineligible candidates immediately
4. Evaluate pin rules → if pin matches, force single candidate
5. Evaluate region/data residency → remove non-compliant candidates
6. Evaluate approval controls → if manual approval required, pause execution
7. Evaluate cost controls → pre-flight budget check against per-call ceiling
8. Score remaining candidates (routing engine)
9. Apply prefer rules as score modifiers
10. Select winner
11. Post-execution: update budget counters, check day/month ceilings
12. Write receipt with policy_set_id and active rules
```

### 4.4 Approval Flow (v1)

Manual approval creates a pending execution:

```
POST /v1/capabilities/{capability_id}/execute
→ 202 Accepted (pending_approval)

{
  "execution_id": "exec_pending_xxx",
  "status": "pending_approval",
  "approval_required": {
    "reason": "cost_per_call_exceeds_threshold",
    "estimated_cost_usd": 0.72,
    "threshold_usd": 0.50,
    "approval_url": "https://resolve.rhumb.ai/approvals/appr_xxx",
    "expires_at": "2026-03-30T21:43:00Z"
  }
}

POST /v1/approvals/{approval_id}/approve
POST /v1/approvals/{approval_id}/deny
GET  /v1/approvals?status=pending&agent_id=xxx
```

---

## 5. AN Score Integration

### 5.1 Structural Separation Architecture

The AN Score is computed by a structurally independent scoring service with no write access to the routing database. This is not a runtime config — it is an architectural boundary enforced at the data layer.

```
┌─────────────────────────────────────────────────────────────┐
│                     RHUMB RESOLVE                           │
│                                                             │
│  ┌───────────────────┐       ┌─────────────────────────┐   │
│  │   ROUTING ENGINE  │       │   AN SCORING SERVICE    │   │
│  │                   │       │                         │   │
│  │  - Reads AN Score │◄──────│  - Reads provider data  │   │
│  │    from read-only │  RO   │  - Computes score       │   │
│  │    score cache    │       │  - Writes to score DB   │   │
│  │  - NO write to    │       │  - NO access to routing │   │
│  │    score DB       │       │    DB or decisions      │   │
│  │  - NO commercial  │       │  - NO commercial data   │   │
│  │    data access    │       │    except as disclosed  │   │
│  └───────────────────┘       └─────────────────────────┘   │
│           │                             │                   │
│           ▼                             ▼                   │
│  ┌────────────────┐           ┌──────────────────────┐      │
│  │  ROUTING DB    │           │   SCORE DB           │      │
│  │  (write)       │           │   (write)            │      │
│  │                │           │   Score cache (RO)   │      │
│  └────────────────┘           └──────────────────────┘      │
│                                          │                  │
│                              ┌──────────────────────┐      │
│                              │  COMMERCIAL DB       │      │
│                              │  (partnership data)  │      │
│                              │  SEPARATE INSTANCE   │      │
│                              │  NO JOIN TO SCORE DB │      │
│                              └──────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 AN Score Components (v1)

The AN Score is a composite 0.0–1.0 score across four independently measured dimensions:

```json
{
  "an_score_record": {
    "score_id": "anscore_01HX4K7M9N3P5Q8R2S6T0K",
    "provider_id": "openai",
    "published_at": "2026-03-01T00:00:00Z",
    "valid_until": "2026-04-01T00:00:00Z",
    "composite_score": 0.89,
    "dimensions": {
      "api_stability": {
        "score": 0.92,
        "weight": 0.25,
        "methodology": "breaking_change_frequency_90d",
        "evidence_url": "https://trust.rhumb.ai/evidence/openai/api_stability_2026_03"
      },
      "pricing_transparency": {
        "score": 0.85,
        "weight": 0.25,
        "methodology": "pricing_page_clarity_audit + change_notice_days",
        "evidence_url": "https://trust.rhumb.ai/evidence/openai/pricing_transparency_2026_03"
      },
      "data_handling": {
        "score": 0.91,
        "weight": 0.25,
        "methodology": "tos_analysis + opt_out_availability + dpa_quality",
        "evidence_url": "https://trust.rhumb.ai/evidence/openai/data_handling_2026_03"
      },
      "agent_treatment": {
        "score": 0.88,
        "weight": 0.25,
        "methodology": "rate_limit_fairness + error_quality + agent_specific_docs",
        "evidence_url": "https://trust.rhumb.ai/evidence/openai/agent_treatment_2026_03"
      }
    },
    "change_from_previous": +0.02,
    "change_reason": "Improved API versioning policy announced 2026-02-15",
    "scorer_id": "rhumb_scoring_engine_v4",
    "external_auditor": "pending_v2",
    "commercial_relationship": {
      "has_revenue_share": false,
      "has_preferred_partner_status": false,
      "disclosure": "No commercial relationship between Rhumb and OpenAI as of this scoring date"
    }
  }
}
```

### 5.3 Firewall Between Commercial Relationships and Scoring

**Enforcement mechanisms:**

1. **Database-level**: AN Score DB has no foreign keys or joins to the partner/commercial DB. IAM roles for the scoring service explicitly deny access to any commercial table.

2. **Process-level**: The scoring team (or automated scoring pipeline) has no access to commercial agreements or partner contracts. Commercial team has read-only access to published scores, same as public.

3. **Audit-level**: Every score change creates an immutable audit event. Score changes co-occurring with commercial changes within 30 days trigger an automatic flag for external review.

4. **Publication**: Scores are published publicly at `https://trust.rhumb.ai/scores/{provider_id}` before being loaded into the routing score cache. Any discrepancy between published score and cached score triggers an alert.

### 5.4 Score Change Audit Trail

```json
{
  "score_change_event": {
    "event_id": "scevt_01HX4K7M9N3P5Q8R2S6T0J",
    "provider_id": "openai",
    "dimension": "api_stability",
    "old_score": 0.87,
    "new_score": 0.92,
    "composite_old": 0.87,
    "composite_new": 0.89,
    "changed_at": "2026-03-01T00:00:00Z",
    "scorer_id": "rhumb_scoring_engine_v4",
    "trigger": "scheduled_monthly_rescore",
    "evidence_diff": "api_stability: 0 breaking changes in 90d window (prev: 1)",
    "commercial_change_proximity_check": {
      "commercial_changes_in_30d": false,
      "auto_flag_triggered": false
    },
    "immutable_hash": "sha256:3c7f9a1b..."
  }
}
```

### 5.5 Public Score Publication

Scores are published monthly at `https://trust.rhumb.ai/scores/` with:
- Provider-by-provider breakdown (JSON + human-readable)
- Methodology documentation
- Evidence links for each dimension
- Change history (12 months)
- Commercial relationship disclosures
- Score computation reproducibility guide

API: `GET /v1/scores/{provider_id}` returns current score (public, no auth required)  
API: `GET /v1/scores/{provider_id}/history` returns 12-month change log

---

## 6. Audit Trail Design

### 6.1 Audit Event Schema

```json
{
  "$schema": "https://schemas.rhumb.ai/resolve/audit/v1",
  "audit_id": "audit_01HX4K7M9N3P5Q8R2S6T0I",
  "event_type": "CAPABILITY_EXECUTED",
  "event_version": "1.0",
  "occurred_at": "2026-03-30T20:43:02.400Z",
  "recorded_at": "2026-03-30T20:43:02.450Z",

  "actor": {
    "type": "agent",
    "agent_id": "agent_01HX4K7M9N3P5Q8R2S6T0U",
    "workspace_id": "ws_01HX4K7M9N3P5Q8R2S6T0S",
    "org_id": "org_01HX4K7M9N3P5Q8R2S6T0R",
    "ip_hash": "sha256:a1b2c3d4..."
  },

  "action": {
    "verb": "execute",
    "resource_type": "capability",
    "resource_id": "cap_image_generation_text_to_image",
    "outcome": "success"
  },

  "context": {
    "execution_id": "exec_01HX4K7M9N3P5Q8R2S6T0V",
    "receipt_id": "rcpt_01HX4K7M9N3P5Q8R2S6T0W",
    "provider_id": "openai",
    "layer": 2,
    "cost_usd": 0.044
  },

  "integrity": {
    "event_hash": "sha256:7a3c9f1b...",
    "chain_hash": "sha256:2b4d6e8f...",
    "sequence_number": 84721,
    "immutable": true
  }
}
```

**Audit Event Types (v1):**

| Event Type | Trigger |
|------------|---------|
| `CAPABILITY_EXECUTED` | Any successful or failed execution |
| `POLICY_EVALUATED` | Policy check run before routing |
| `POLICY_BLOCKED` | Execution blocked by policy |
| `APPROVAL_REQUESTED` | Manual approval gate triggered |
| `APPROVAL_GRANTED` | Approval granted |
| `APPROVAL_DENIED` | Approval denied |
| `BUDGET_WARNING` | Budget threshold crossed |
| `BUDGET_BLOCKED` | Budget ceiling hit |
| `PROVIDER_FALLBACK` | Fallback to secondary provider |
| `POLICY_UPDATED` | Policy set modified |
| `CREDENTIAL_USED` | Credential accessed for execution |
| `AN_SCORE_UPDATED` | Provider AN Score changed |
| `RECEIPT_EXPORTED` | Audit export generated |
| `GDPR_DELETION_REQUESTED` | Data deletion request received |
| `GDPR_DELETION_COMPLETED` | Data deletion confirmed |

### 6.2 Immutability Guarantees

Audit records are written to an **append-only** table with row-level deletion disabled at the database role level. Each record includes a chained hash (event_hash includes hash of previous event in sequence). A separate process verifies chain integrity hourly and alerts on breaks.

**v1**: Append-only PostgreSQL with chain hashing  
**v2 (deferred)**: Write to immutable log service (AWS CloudTrail-equivalent or dedicated audit ledger)

### 6.3 Retention

| Data Class | Retention | Legal Basis |
|------------|-----------|-------------|
| Execution receipts | 90 days (standard) / 7 years (compliance) | SOC2, financial audit |
| Audit events | 3 years minimum | SOC2 CC7.2 |
| Policy change history | 7 years | Compliance |
| AN Score change history | Indefinite (public record) | Transparency |
| GDPR-scoped records | Until deletion request + 30 days | GDPR Art. 17 |

### 6.4 Export API

```
POST /v1/audit/export
Content-Type: application/json

{
  "format": "json",              // json | csv | parquet | jsonl
  "filter": {
    "from": "2026-03-01T00:00:00Z",
    "to": "2026-03-31T23:59:59Z",
    "event_types": ["CAPABILITY_EXECUTED", "POLICY_BLOCKED"],
    "agent_id": "agent_xxx",
    "provider_id": "openai"
  },
  "destination": "download",     // download | s3_presigned | webhook
  "include_receipt_details": true
}

Response: 202 Accepted
{
  "export_job_id": "expjob_01HX4K7M9N3P5Q8R2S6T0H",
  "status": "queued",
  "estimated_records": 4821,
  "status_url": "https://resolve.rhumb.ai/audit/exports/expjob_xxx"
}
```

### 6.5 Compliance Coverage

**SOC2 Type II:**
- CC6.1 (Access Controls): Audit log of all API key uses
- CC7.2 (System Monitoring): All executions and anomalies logged
- CC9.2 (Change Management): Policy changes with before/after state
- A1.2 (Capacity): Budget enforcement and ceiling events

**GDPR:**
- Art. 5 (Data Minimization): IP stored as hash only; payload stored only on explicit opt-in
- Art. 13/14 (Transparency): Audit export available on demand
- Art. 17 (Right to Erasure): GDPR deletion API with 30-day SLA, receipt anonymization
- Art. 20 (Data Portability): Export in JSON and CSV

**GDPR Deletion API:**
```
POST /v1/compliance/gdpr/deletion-request
{ "subject_id": "agent_xxx", "scope": "all_personal_data" }

GET /v1/compliance/gdpr/deletion-request/{request_id}
→ { "status": "pending|in_progress|completed", "completed_at": "..." }
```

---

## 7. SLA Framework

### 7.1 Layer SLA Targets

| Metric | Layer 1 | Layer 2 | Layer 3 | Measurement |
|--------|---------|---------|---------|-------------|
| Availability | 99.9% | 99.9% | 99.5% | Calendar month, excl. provider |
| API Latency P50 (Rhumb overhead only) | <25ms | <50ms | <100ms | Rolling 7-day |
| API Latency P99 (Rhumb overhead only) | <100ms | <200ms | <500ms | Rolling 7-day |
| Routing Decision Time P99 | N/A | <75ms | <150ms | Rolling 7-day |
| Error Rate (Rhumb-caused) | <0.1% | <0.5% | <1.0% | Rolling 24h |
| Receipt Write Success | 99.99% | 99.99% | 99.99% | Calendar month |
| Policy Evaluation Correctness | 100% | 100% | 100% | Zero tolerance |

Note: Provider latency and provider availability are excluded from Rhumb SLAs. They are tracked and reported but Rhumb does not warrant external provider uptime.

### 7.2 Graceful Degradation

```
┌─────────────────────────────────────────────────────────────┐
│                    DEGRADATION LEVELS                       │
│                                                             │
│  LEVEL 0 (Normal): Full feature set, all SLAs active       │
│                                                             │
│  LEVEL 1 (Degraded): Route explanation generation delayed  │
│    → Receipts still written; explanation async             │
│    → Response headers still include execution_id          │
│    → Explanation available within 30s                      │
│                                                             │
│  LEVEL 2 (Impaired): Score cache stale (>1h)               │
│    → Routing continues with last-known scores              │
│    → Explanation includes "score_freshness: stale"        │
│    → Alert fired to ops                                    │
│                                                             │
│  LEVEL 3 (Emergency): Receipt write failing                 │
│    → Execution BLOCKED until receipt write recovers        │
│    → Agent receives INTERNAL_ERROR with retry guidance     │
│    → Escalation P1 immediately                             │
│                                                             │
│  LEVEL 4 (Fallback Mode): Routing DB unavailable           │
│    → Layer 1 continues (direct passthrough, no routing)    │
│    → Layer 2/3 suspended; returns 503 with retry-after    │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 SLA Monitoring

```json
{
  "sla_monitor_config": {
    "availability_check_interval_seconds": 30,
    "latency_window_minutes": 60,
    "error_rate_window_minutes": 15,
    "alert_channels": ["pagerduty", "slack_ops", "status_page"],
    "thresholds": {
      "availability_warn": 0.999,
      "availability_critical": 0.995,
      "p99_latency_warn_ms": 150,
      "p99_latency_critical_ms": 200,
      "error_rate_warn": 0.003,
      "error_rate_critical": 0.005
    }
  }
}
```

**Status Page:** `https://status.rhumb.ai` — public real-time status for all layers

### 7.4 SLA Breach Remediation

| Breach | SLA Credit | Trigger | Process |
|--------|-----------|---------|---------|
| <99.9% availability (Layer 2) | 10% monthly credit | Monthly | Automatic via billing |
| <99.5% availability (Layer 3) | 10% monthly credit | Monthly | Automatic via billing |
| P1 incident >1h | 25% monthly credit | Per incident | Manual credit |
| Receipt loss | Investigation + full refund of affected executions | Per event | Manual |

**v1**: Credits applied manually on request  
**v2 (deferred)**: Automatic credit calculation and application

---

## 8. Provider Relationship Preservation

### 8.1 Design Principle

Abstraction is not erasure. Rhumb adds a layer but never removes a layer. Provider identity, branding, and capability-specific features must remain fully accessible to agents. The goal is to make providers more accessible and more trustworthy, not to commoditize them into interchangeability.

### 8.2 Provider Branding in Responses

Every Resolve response exposes the full provider identity:

```json
{
  "_rhumb": {
    "provider": {
      "id": "openai",
      "name": "OpenAI",
      "display_name": "OpenAI GPT-4o",
      "logo_url": "https://cdn.rhumb.ai/providers/openai/logo.svg",
      "brand_color": "#10A37F",
      "homepage_url": "https://openai.com",
      "docs_url": "https://platform.openai.com/docs",
      "model": "gpt-4o",
      "model_card_url": "https://openai.com/research/gpt-4o",
      "provider_request_id": "chatcmpl-abc123",
      "provider_latency_ms": 847
    }
  }
}
```

### 8.3 Provider-Specific Feature Passthrough

Providers have unique features that Resolve must not strip. Feature passthrough works as follows:

**Layer 1**: 100% passthrough. All provider-specific parameters are forwarded as-is. No normalization.

**Layer 2**: Normalized output + `provider_native` passthrough field. If a provider returns model-specific metadata (e.g., OpenAI's `usage.prompt_tokens`, Anthropic's `stop_reason`), it appears in `provider_native`:

```json
{
  "result": { ... normalized output ... },
  "_rhumb": { ... attribution block ... },
  "provider_native": {
    "id": "chatcmpl-abc123",
    "model": "gpt-4o",
    "usage": {
      "prompt_tokens": 150,
      "completion_tokens": 300,
      "total_tokens": 450
    },
    "finish_reason": "stop",
    "system_fingerprint": "fp_abc123"
  }
}
```

**Layer 3**: Each step's `provider_native` block is preserved in the step-level receipt. Agents can inspect per-step provider metadata via the recipe execution API.

### 8.4 Provider Feedback Loops

Providers receive anonymized quality signals about their performance within Rhumb:

- Aggregate success/error rates per capability (no agent-level data)
- P50/P99 latency distributions
- Fallback trigger rates (how often agents fell back away from their provider)
- AN Score change notifications (before publication)

**v1**: Manual sharing via provider dashboard (read-only portal)  
**v2 (deferred)**: Provider-facing API for programmatic access to their own metrics

### 8.5 Provider Dashboard Concept

```
Provider Portal: https://providers.rhumb.ai

Metrics (30/90/365 day windows):
- Total executions via Rhumb
- Success rate
- Average latency (Rhumb-measured)
- Fallback rate (outbound + inbound)
- Current AN Score + dimension breakdown
- AN Score history
- Top capabilities used

Provider can:
- View and contest AN Score dimension evidence
- Update documentation/changelog links
- Flag capability schema changes (advance notice)
- See (aggregated, anonymous) agent feedback
```

---

## 9. Neutrality Guardrails

### 9.1 Structural Separation (Code Level)

The AN Scoring service is a **separate deployable** with its own codebase, database credentials, and deployment pipeline. It does not share a process, container, or database connection with the routing engine.

```
Repository structure:
rhumb-resolve/
  routing-engine/          # reads score cache (read-only credentials)
  scoring-service/         # writes scores (separate DB user, no routing access)
  commercial-service/      # manages partnerships (no score DB access)
  score-cache/             # read-only snapshot, refreshed hourly by scoring-service
```

**Database IAM:**
- `routing_engine` role: `SELECT` on `score_cache` only; no access to `scoring_db` or `commercial_db`
- `scoring_service` role: `SELECT/INSERT/UPDATE` on `scoring_db`; no access to `commercial_db` write tables
- `commercial_service` role: full access to `commercial_db`; `SELECT` on `score_cache` (same as public)

### 9.2 Decision Audit Requirements

Every routing decision that uses AN Score must log:
1. The AN Score value at time of decision
2. The score's `published_at` timestamp
3. Whether the score was the decisive factor or a tiebreaker
4. The `score_cache_freshness_seconds` at decision time

This enables retroactive auditing: "Was routing biased toward Provider X during a period when Rhumb had a commercial agreement with Provider X?"

### 9.3 Conflict of Interest Policy

**Prohibited:**
- Commercial team cannot request score changes or re-scores
- Scoring team cannot see or be told about commercial relationships during scoring
- Score publication cannot be delayed for commercial reasons
- AN Score cannot be a factor in commercial contract negotiations with providers

**Required:**
- Any Rhumb employee who learns of a conflict between scoring and commercial must report to designated compliance officer
- Score changes that affect a top-10 revenue provider require secondary review by a second scorer
- External audit of scoring methodology minimum annually (v2 target: quarterly)

### 9.4 External Audit Mechanism

**v1**: Annual methodology audit by independent third party; results published at `https://trust.rhumb.ai/audits/`

**v2 (deferred)**: 
- Quarterly external audits
- Continuous monitoring by external firm with access to score change audit trail
- Bug bounty for evidence of score manipulation

### 9.5 Public Verifiability

The scoring methodology is fully documented and published. Any third party can independently compute a provider's AN Score using:
1. Published methodology (`https://trust.rhumb.ai/methodology/`)
2. Public provider data (APIs, docs, pricing pages, ToS)
3. Published evidence links for each dimension

Score disputes are handled via a public dispute process at `https://trust.rhumb.ai/disputes/`.

---

## 10. Incident Response Design

### 10.1 Incident Detection Triggers

Incidents are auto-detected by the following monitors:

```json
{
  "incident_triggers": [
    {
      "name": "provider_error_spike",
      "condition": "provider_error_rate_5m > 0.20",
      "severity": "P2",
      "action": ["alert_ops", "consider_circuit_break"]
    },
    {
      "name": "provider_total_outage",
      "condition": "provider_success_rate_5m < 0.01",
      "severity": "P1",
      "action": ["open_circuit_breaker", "alert_ops", "agent_notify"]
    },
    {
      "name": "recipe_step_failure_cascade",
      "condition": "recipe_step_failure_rate_5m > 0.30",
      "severity": "P2",
      "action": ["alert_ops", "pause_recipe_routing"]
    },
    {
      "name": "cost_spike",
      "condition": "hourly_cost_3x_vs_prior_week",
      "severity": "P2",
      "action": ["alert_ops", "notify_agent"]
    },
    {
      "name": "budget_ceiling_hit",
      "condition": "agent_daily_spend >= daily_ceiling",
      "severity": "P3",
      "action": ["block_executions", "notify_agent"]
    },
    {
      "name": "receipt_write_failure",
      "condition": "receipt_write_failure_rate_5m > 0.001",
      "severity": "P1",
      "action": ["block_executions", "alert_ops", "escalate_immediately"]
    },
    {
      "name": "routing_latency_spike",
      "condition": "routing_latency_p99_5m > 500ms",
      "severity": "P2",
      "action": ["alert_ops", "investigate"]
    }
  ]
}
```

### 10.2 Circuit Breaker Integration

Circuit breakers are per-provider, per-capability:

```json
{
  "circuit_breaker": {
    "provider_id": "openai",
    "capability_pattern": "cap_text_*",
    "state": "open",
    "opened_at": "2026-03-30T20:00:00Z",
    "trigger": "error_rate_threshold",
    "error_rate_at_open": 0.42,
    "half_open_after_seconds": 60,
    "close_on_success_count": 3,
    "fallback_providers": ["anthropic", "cohere"],
    "agent_notifications_sent": 847
  }
}
```

States: `closed` (normal) → `open` (blocking, routing to fallbacks) → `half_open` (testing recovery) → `closed`

### 10.3 Escalation Paths

| Severity | Response Time | Escalation |
|----------|---------------|------------|
| P1 | 15 minutes | On-call engineer → CTO |
| P2 | 1 hour | On-call engineer |
| P3 | 4 hours | Next business day |
| P4 | 24 hours | Scheduled review |

**P1 examples**: Receipt system down, routing completely unavailable, budget system failing to block  
**P2 examples**: Provider outage (has fallbacks), elevated error rates, latency degradation  
**P3 examples**: Cost spike detected, single provider slowdown, AN Score staleness  
**P4 examples**: Dashboard anomaly, non-critical export failure

### 10.4 Agent Notification Mechanisms

When an incident affects an agent's executions, they are notified via:

1. **In-response error envelope** — immediate, for current in-flight request
2. **Webhook** (if configured) — within 60 seconds of incident detection
3. **API polling** — `GET /v1/incidents?affects_agent={agent_id}&status=active`

```json
{
  "incident_notification": {
    "incident_id": "inc_01HX4K7M9N3P5Q8R2S6T0G",
    "severity": "P1",
    "title": "OpenAI API experiencing elevated error rates",
    "description": "OpenAI is returning 5xx errors at 35% rate for text generation capabilities. Fallback routing to Anthropic is active.",
    "affected_capabilities": ["cap_text_generation_*"],
    "affected_providers": ["openai"],
    "started_at": "2026-03-30T20:00:00Z",
    "estimated_resolution": null,
    "status": "investigating",
    "mitigation_active": true,
    "mitigation_description": "Auto-fallback to Anthropic Claude-3 active for affected capabilities",
    "impact_on_agent": {
      "executions_affected": 12,
      "executions_failed": 0,
      "executions_rerouted": 12,
      "cost_delta_usd": 0.18
    },
    "status_page_url": "https://status.rhumb.ai/incidents/inc_xxx"
  }
}
```

### 10.5 Post-Incident Reporting

Every P1/P2 incident produces a post-mortem within 48 hours:

```json
{
  "post_incident_report": {
    "incident_id": "inc_01HX4K7M9N3P5Q8R2S6T0G",
    "severity": "P1",
    "duration_minutes": 47,
    "detection_latency_seconds": 23,
    "started_at": "2026-03-30T20:00:00Z",
    "resolved_at": "2026-03-30T20:47:00Z",
    "timeline": [
      { "t": "+0s", "event": "First 5xx from OpenAI" },
      { "t": "+23s", "event": "Monitor triggered, circuit breaker opened" },
      { "t": "+35s", "event": "Fallback routing to Anthropic active" },
      { "t": "+60s", "event": "On-call notified" },
      { "t": "+2700s", "event": "OpenAI recovery confirmed, circuit breaker half-open" },
      { "t": "+2820s", "event": "Circuit breaker closed, normal routing restored" }
    ],
    "root_cause": "OpenAI datacenter issue in us-east-1",
    "impact": {
      "executions_affected": 847,
      "executions_failed": 0,
      "executions_rerouted": 847,
      "agent_impact": "Transparent fallback; no agent-facing failures"
    },
    "action_items": [
      { "item": "Add multi-region health check for OpenAI", "owner": "ops", "due": "2026-04-07" }
    ]
  }
}
```

---

## 11. Trust Dashboard for Agents

### 11.1 API Endpoints

```
# Execution Summary
GET /v1/trust/summary
  ?window=7d|30d|90d
  &granularity=hour|day|week
  →  Aggregate execution stats for the calling agent

# Provider Distribution
GET /v1/trust/providers
  ?window=30d
  →  Breakdown of executions per provider with success/error rates

# Cost Trends
GET /v1/trust/costs
  ?window=30d
  &group_by=capability|provider|day
  →  Cost breakdown with trend data

# Reliability Metrics
GET /v1/trust/reliability
  ?window=30d
  →  Error rates, fallback rates, latency percentiles by capability

# Route Audit
GET /v1/trust/routing
  ?capability_id=cap_xxx
  &window=7d
  →  Routing decisions for capability over window

# Receipt Feed
GET /v1/receipts
  (see Section 1.5)

# Active Incidents
GET /v1/incidents
  ?status=active|resolved
  &affects_capability=cap_xxx
  →  Incidents affecting this agent's capabilities

# Policy Evaluation Audit
GET /v1/trust/policy-audit
  ?window=7d
  →  All policy evaluations including blocks and overrides
```

### 11.2 Trust Summary Response Schema

```json
{
  "trust_summary": {
    "agent_id": "agent_01HX4K7M9N3P5Q8R2S6T0U",
    "window": "30d",
    "generated_at": "2026-03-30T20:43:00Z",

    "execution_totals": {
      "total_executions": 4821,
      "successful": 4753,
      "failed": 42,
      "partial": 26,
      "success_rate": 0.9856,
      "layer_breakdown": {
        "layer1": 124,
        "layer2": 4400,
        "layer3": 297
      }
    },

    "cost": {
      "total_usd": 87.43,
      "by_provider": {
        "openai": 52.10,
        "anthropic": 21.30,
        "stability_ai": 14.03
      },
      "daily_average_usd": 2.91,
      "trend_vs_prior_period": "+12.3%",
      "largest_single_execution_usd": 0.72
    },

    "reliability": {
      "overall_error_rate": 0.0087,
      "rhumb_error_rate": 0.0003,
      "provider_error_rate": 0.0084,
      "fallback_rate": 0.021,
      "fallback_success_rate": 0.994,
      "p50_latency_ms": 487,
      "p99_latency_ms": 2841
    },

    "provider_distribution": [
      {
        "provider_id": "openai",
        "provider_name": "OpenAI",
        "execution_count": 2847,
        "execution_share": 0.590,
        "success_rate": 0.991,
        "avg_latency_ms": 423,
        "total_cost_usd": 52.10,
        "an_score": 0.89
      },
      {
        "provider_id": "anthropic",
        "provider_name": "Anthropic",
        "execution_count": 1204,
        "execution_share": 0.250,
        "success_rate": 0.996,
        "avg_latency_ms": 612,
        "total_cost_usd": 21.30,
        "an_score": 0.94
      }
    ],

    "policy_activity": {
      "evaluations": 4821,
      "blocks": 14,
      "approvals_required": 3,
      "approvals_granted": 3,
      "approvals_denied": 0,
      "budget_warnings_triggered": 2,
      "budget_blocks_triggered": 0
    },

    "top_capabilities": [
      {
        "capability_id": "cap_text_generation_chat",
        "executions": 2100,
        "success_rate": 0.997,
        "avg_cost_usd": 0.008,
        "primary_provider": "openai"
      }
    ]
  }
}
```

### 11.3 Comparison Capabilities

Agents can compare their reliability/cost against:

1. **Historical self-comparison**: "How does my last 7 days compare to prior 7 days?"
2. **Provider comparison**: "For capability X, how do providers compare on cost, latency, and AN Score?"
3. **Capability benchmarks**: "How does my error rate for this capability compare to the platform average?" (aggregated, anonymized)

```
GET /v1/trust/compare/providers
  ?capability_id=cap_text_generation_chat
  &metrics=cost,latency,reliability,an_score
  →  Side-by-side provider comparison for this capability

GET /v1/trust/compare/self
  ?window=7d
  &vs=prior_7d
  →  My metrics this window vs prior window
```

### 11.4 Dashboard Data Model (v1 Web Interface)

The Trust Dashboard at `https://resolve.rhumb.ai/trust` exposes:

- **Overview**: Total executions, spend, success rate (7d/30d/90d toggles)
- **Provider Map**: Sankey diagram of capability → provider routing
- **Cost Timeline**: Daily spend with provider breakdown
- **Reliability Chart**: Error rate over time with incident overlays
- **Policy Audit Log**: All blocks, approvals, and overrides
- **Routing Explorer**: Per-execution routing explanation drill-down
- **AN Score Panel**: Current scores for all providers used, with history

**v1**: Read-only dashboard, data refreshed every 5 minutes  
**v2 (deferred)**: Real-time streaming updates, custom alerts, scheduled PDF exports

---

## Implementation Notes: v1 vs Deferred

### v1 (Launch-Ready)

- Full execution receipt schema and write path
- Provider attribution in all responses and error messages
- Route explanation generation and storage
- Policy enforcement: deny lists, provider pins, cost ceilings, region filters
- AN Score structural separation (separate service + DB)
- Append-only audit trail with chain hashing
- Agent query API for receipts and explanations
- Layer 1/2/3 SLA targets and monitoring
- Circuit breakers per provider
- Incident detection and agent notification via API
- Trust Summary API endpoint

### Deferred to v2

- External audit of AN Score methodology (annual → quarterly)
- Provider-facing portal and feedback API
- Automatic SLA credit calculation
- Real-time streaming receipt writes
- Immutable audit ledger (external service)
- Dashboard real-time updates
- Parquet export format
- GDPR automated deletion pipeline (v1: manual process with SLA)
- Approval webhook integrations beyond Slack
- Streaming response attribution (SSE headers)

---

*Section authored by Panel 2: Trust, Observability & Governance*  
*Rhumb Resolve Founding Product Specification*  
*Status: Engineering Draft v1 — Ready for Implementation Review*
