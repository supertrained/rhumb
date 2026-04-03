BEGIN;

-- Migration 0154: Subscription billing discovery expansion (2026-04-03)
-- Rationale: live production still shows subscription-billing at only five
-- providers (Chargebee, Lago, Orb Billing, Recurly, RevenueCat) despite
-- subscription state, invoice state, entitlement timing, and customer billing
-- context being recurring operator needs for product, support, finance, and
-- agent-mediated SaaS workflows.
--
-- This batch deepens the category with API-backed platforms that expose clean
-- subscription/customer/invoice/admin surfaces and strengthens the next honest
-- Resolve wedge around read-first subscription inspection.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'lemonsqueezy',
    'Lemon Squeezy',
    'subscription-billing',
    'Merchant-of-record subscription platform with APIs for products, variants, customers, subscriptions, orders, license keys, and recurring billing operations for software businesses.',
    'https://docs.lemonsqueezy.com/api',
    'api.lemonsqueezy.com'
  ),
  (
    'rebilly',
    'Rebilly',
    'subscription-billing',
    'Recurring billing and payments platform with APIs for customers, plans, subscriptions, invoices, transactions, dunning, and lifecycle automation across SaaS and digital commerce.',
    'https://www.rebilly.com/docs/api',
    'api.rebilly.com'
  ),
  (
    'zuora',
    'Zuora',
    'subscription-billing',
    'Enterprise subscription management platform with APIs for accounts, subscriptions, catalog, invoices, usage, amendments, and recurring revenue operations.',
    'https://developer.zuora.com/',
    'rest.zuora.com'
  ),
  (
    'chargeover',
    'ChargeOver',
    'subscription-billing',
    'Subscription billing and invoicing platform with APIs for customers, subscriptions, invoices, payments, plans, and recurring revenue workflows for SMB and midmarket teams.',
    'https://developer.chargeover.com/api/',
    'api.chargeover.com'
  ),
  (
    'billsby',
    'Billsby',
    'subscription-billing',
    'Recurring billing platform with APIs for plans, customers, subscriptions, usage, and subscription lifecycle events oriented around SaaS and membership businesses.',
    'https://docs.billsby.com/reference/introduction',
    'public.billsby.com'
  )
ON CONFLICT (slug) DO NOTHING;

INSERT INTO scores (
  service_slug,
  aggregate_recommendation_score,
  execution_score,
  access_readiness_score,
  confidence,
  tier,
  tier_label,
  probe_metadata,
  calculated_at
)
VALUES
  (
    'lemonsqueezy',
    8.50,
    8.60,
    8.30,
    0.70,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"subscription-billing expansion","phase0_assessment":"Best immediate Resolve candidate in the batch because Lemon Squeezy exposes a clean API-key REST surface for customers, subscriptions, orders, and license artifacts that maps directly to subscription.list/get and customer.get workflows.","notes":"Very strong fit for read-first billing context in SaaS support, entitlement debugging, renewal monitoring, and agent-assisted revenue ops without the setup heaviness of the larger enterprise billing suites."}'::jsonb,
    now()
  ),
  (
    'rebilly',
    8.35,
    8.50,
    8.05,
    0.67,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"subscription-billing expansion","phase0_assessment":"Strong follow-on Resolve target for subscription.get/list, invoice.list, and customer.get because Rebilly exposes broad recurring billing primitives on a modern API surface with strong operational depth.","notes":"Strategically useful for SaaS and digital commerce teams that need subscription and invoice truth in the same execution lane, though the wider payment surface makes it slightly noisier than Lemon Squeezy for a first narrow billing wedge."}'::jsonb,
    now()
  ),
  (
    'zuora',
    8.20,
    8.35,
    7.85,
    0.65,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"subscription-billing expansion","phase0_assessment":"High-value enterprise Resolve target for subscription.get, account.get, and invoice.list once the simpler SaaS-first billing rails are normalized. Rich operational primitives are present, but auth and product-surface complexity are heavier than Lemon Squeezy or Rebilly.","notes":"Important enterprise coverage because Zuora remains a real system of record for recurring revenue ops, amendments, invoicing, and subscription state management."}'::jsonb,
    now()
  ),
  (
    'chargeover',
    8.05,
    8.15,
    7.95,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"subscription-billing expansion","phase0_assessment":"Credible midmarket Resolve target for customer.get, subscription.list, and invoice.list with a straightforward REST posture and clear recurring-billing semantics.","notes":"Useful SMB-to-midmarket category depth beyond the best-known billing platforms, especially for operator workflows that need invoice and subscriber truth without a full enterprise revenue stack."}'::jsonb,
    now()
  ),
  (
    'billsby',
    7.95,
    8.05,
    7.80,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"subscription-billing expansion","phase0_assessment":"Worth indexing now because it exposes real subscription, customer, and plan APIs, even though Lemon Squeezy and Rebilly are cleaner first normalization targets.","notes":"Useful category breadth for SaaS recurring revenue workflows with enough API surface to support later subscription-state inspection and lifecycle automation."}'::jsonb,
    now()
  )
ON CONFLICT (service_slug) DO UPDATE SET
  aggregate_recommendation_score = EXCLUDED.aggregate_recommendation_score,
  execution_score = EXCLUDED.execution_score,
  access_readiness_score = EXCLUDED.access_readiness_score,
  confidence = EXCLUDED.confidence,
  tier = EXCLUDED.tier,
  tier_label = EXCLUDED.tier_label,
  probe_metadata = EXCLUDED.probe_metadata,
  calculated_at = EXCLUDED.calculated_at;

COMMIT;
