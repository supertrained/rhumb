# Round 12 — Metering + Billing Pipeline (WU 2.3)

> **Kickoff Date:** 2026-03-08
> **Round:** 12 (cb-r012)
> **Work Unit:** 2.3 — Metering + Billing Pipeline
> **Predecessor:** Round 11 (Agent Identity System) — COMPLETE ✅
> **Status:** READY FOR KICKOFF
> **Execution Model:** Codex 5.3 xhigh (backend implementation)

## Overview

Implement call metering, spend caps, billing aggregation, and Stripe integration. This round consumes usage data from Round 11's agent identity system (per-agent per-service usage tracking) and builds the financial layer on top of the Access Layer infrastructure.

**Key dependencies from Rounds 10–11:**
- Usage events table: `agent_usage_events` (agent_id, service, result, created_at) ✅
- Agent identity: `agents` table with rate_limit_qpm, organization_id ✅
- Admin routes: `/v1/admin/agents/{agent_id}` ✅
- Proxy router: validates agent → records usage ✅

**Deliverables this round:**
1. Usage metering engine (count, latency, success/fail aggregation)
2. Spend cap enforcement (per-agent spend limits, alerts)
3. Free tier quota (1,000 calls/month per operator)
4. Billing aggregation (monthly invoice generation)
5. Stripe integration (one-click payment, subscription management)
6. Admin dashboard (usage reports, spend trends, billing history)
7. 25+ integration tests

**Success criteria:**
- All tests passing (25+)
- Metering correctly tracks calls + latency + success rates
- Spend cap alerts trigger before overage
- Free tier quota enforced (1,000 calls/month, rollover behavior)
- Stripe Subscription + PaymentIntent integrations working
- Admin dashboard shows usage trends, billing history, forecast
- Type-check clean, linting clean
- Zero regressions from Rounds 10–11 (205 tests still passing)

## High-Level Architecture

7 modules: usage_metering.py, spend_cap.py, free_tier_quota.py, billing_aggregation.py, stripe_integration.py, admin_billing.py, 0006_metering_billing.sql

**Tests target:** 25+ integration tests (metering, spend cap, free tier, invoicing, Stripe, admin routes, E2E flows)

**Supabase schema:**
- agent_usage_events table (extended from R11)
- invoices table (new)
- organizations table (add Stripe + billing fields)

**Estimated execution time:** 20 hours on Codex 5.3 xhigh

**Branch:** feat/r12-metering-billing
**Expected completion:** 2026-03-09 evening OR 2026-03-10 morning

## Success Metrics
- 25+ tests passing (target exceeded acceptable)
- Spend cap enforced correctly
- Free tier quota enforced
- Stripe integration working
- Admin dashboard functional
- 0 regressions (230+ total tests)
