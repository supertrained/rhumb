BEGIN;

-- Migration 0138: Agent-payments discovery expansion (2026-03-31)
-- Rationale: live production still shows agent-payments as an underrepresented
-- category despite growing demand for programmable spend, virtual cards,
-- approval rails, transaction receipts, and wallet-adjacent controls that
-- agents can use safely.
-- Add five more API-backed providers that deepen the category around virtual
-- card issuance, spend controls, transaction visibility, and programmable
-- payment program management.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'lithic',
    'Lithic',
    'agent-payments',
    'Card issuing infrastructure with APIs for virtual and physical cards, authorizations, spend controls, events, balances, and programmable payment workflows.',
    'https://docs.lithic.com/docs/welcome',
    'api.lithic.com'
  ),
  (
    'stripe-issuing',
    'Stripe Issuing',
    'agent-payments',
    'Programmable card issuing platform from Stripe with APIs for cards, cardholders, authorizations, disputes, spending controls, and commercial card program management.',
    'https://docs.stripe.com/issuing',
    'api.stripe.com'
  ),
  (
    'marqeta',
    'Marqeta',
    'agent-payments',
    'Modern card issuing and payments platform with REST APIs for users, cards, funding controls, authorizations, tokenization, and transaction lifecycle management.',
    'https://www.marqeta.com/docs/core-api/introduction',
    'api.marqeta.com'
  ),
  (
    'highnote',
    'Highnote',
    'agent-payments',
    'Embedded payments platform with APIs for issuing cards, acquiring payments, unified ledger operations, program management, and real-time spend controls.',
    'https://docs.highnote.com/',
    'api.highnote.com'
  ),
  (
    'unit',
    'Unit',
    'agent-payments',
    'Banking and card infrastructure API covering accounts, cards, payments, customers, and transaction workflows for programmable spend and embedded-finance operations.',
    'https://www.unit.co/docs/api/',
    'api.s.unit.sh'
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
    'lithic',
    8.35,
    8.55,
    8.10,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"agent-payments expansion","notes":"Best immediate Phase 0 candidate in the batch. Lithic exposes explicit card, authorization, spend-limit, and transaction primitives that map cleanly to virtual_card.create/list and transaction.list for agent-controlled spend workflows."}'::jsonb,
    now()
  ),
  (
    'stripe-issuing',
    8.20,
    8.35,
    8.00,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"agent-payments expansion","notes":"Strong second Phase 0 candidate with mature cards, cardholders, authorizations, and disputes APIs. Excellent operational fit for agent spend programs, though regional availability and Stripe account setup make access slightly heavier than Lithic."}'::jsonb,
    now()
  ),
  (
    'marqeta',
    8.10,
    8.25,
    7.90,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"agent-payments expansion","notes":"Category heavyweight with broad card-program coverage across users, cards, funding controls, and transaction management. High execution potential, but enterprise implementation weight is a bit heavier than the cleanest first-wave target."}'::jsonb,
    now()
  ),
  (
    'highnote',
    8.05,
    8.20,
    7.85,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"agent-payments expansion","notes":"Promising modern platform with issuing, acquiring, webhooks, and unified-ledger abstractions. Strong later Resolve target once the first normalized card and transaction primitives are landed."}'::jsonb,
    now()
  ),
  (
    'unit',
    7.95,
    8.00,
    7.80,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"agent-payments expansion","notes":"Useful breadth addition because Unit unifies cards, accounts, and payments in one API. Valuable for programmable spend operations, but broader banking scope makes it a slightly noisier first normalization target than Lithic or Stripe Issuing."}'::jsonb,
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
