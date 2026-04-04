BEGIN;

-- Migration 0157: APM discovery expansion II (2026-04-03)
-- Rationale: live production shows the apm category at only 5 providers
-- (aspecto, elastic-apm, jaeger, lightstep, opentelemetry). APM is a high-demand
-- agent workflow category: agents monitoring production systems need direct access
-- to performance data, error traces, slow endpoints, and incident signals without
-- human-in-the-loop intermediaries.
--
-- This batch adds five real API-backed APM / observability platforms spanning
-- hosted SaaS (AppSignal, Middleware, Instana), self-hosted (SkyWalking), and
-- enterprise (AppDynamics) surfaces, with a clear first Phase 0 wedge for read-first
-- performance inspection via AppSignal.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'appsignal',
    'AppSignal',
    'apm',
    'Application performance monitoring and error tracking API for Ruby, Python, PHP, Elixir, and Node.js. Provides REST endpoints for app performance summaries, error rates, slow transactions, and alerting — all scoped per application with API key auth.',
    'https://docs.appsignal.com/api/',
    'appsignal.com'
  ),
  (
    'middleware-io',
    'Middleware',
    'apm',
    'Full-stack cloud observability platform with a public REST API for trace inspection, metric queries, alert management, service topology, and real-time infrastructure monitoring across distributed applications.',
    'https://docs.middleware.io',
    'api.middleware.io'
  ),
  (
    'instana',
    'IBM Instana',
    'apm',
    'Enterprise observability platform with a comprehensive REST API for service mapping, trace inspection, event retrieval, anomaly detection, and infrastructure monitoring across cloud-native and hybrid environments. Part of IBM Observability.',
    'https://www.ibm.com/docs/en/instana-observability/current?topic=references-api',
    'api.instana.io'
  ),
  (
    'appdynamics',
    'AppDynamics (Splunk)',
    'apm',
    'Enterprise APM platform (acquired by Splunk) with REST APIs for application performance data, business transactions, health rules, snapshots, and event streams. Supports agent-driven monitoring across Java, .NET, PHP, Node.js, and Python.',
    'https://docs.appdynamics.com/appd/24.x/latest/en/extend-splunk-appdynamics/splunk-appdynamics-apis',
    'api.appdynamics.com'
  ),
  (
    'apache-skywalking',
    'Apache SkyWalking',
    'apm',
    'Open-source APM and observability platform for distributed systems. Provides a GraphQL query protocol for service metadata, endpoint latency, traces, service topology, and SLA metrics — commonly deployed on-premises or via SkyWalking-as-a-Service offerings.',
    'https://skywalking.apache.org/docs/main/latest/en/api/query-protocol/',
    'skywalking-api.example.com'
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
    'appsignal',
    8.25,
    8.40,
    8.05,
    0.65,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"apm expansion II","phase0_assessment":"Best Phase 0 candidate in the batch. AppSignal exposes a clean REST API for application performance summaries and error metrics. Capability shape: apm.errors.list, apm.performance.summary, apm.app.list. API key only, JSON responses, application-scoped queries. Immediately useful for agents monitoring Rails/Python/PHP app health.","notes":"Strong agent workflow fit: agents can query error rate, slow transaction counts, and alert state before deciding whether to escalate or auto-remediate. Accessible credentials model with per-app token scoping."}'::jsonb,
    now()
  ),
  (
    'middleware-io',
    8.10,
    8.20,
    7.90,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"apm expansion II","phase0_assessment":"Second Phase 0 candidate. Middleware public REST API covers trace query, metric inspection, and alert state — all read-first primitives suitable for apm.trace.get, apm.metrics.query. Cloud-native positioning and modern API design.","notes":"Full-stack observability including frontend, backend, infrastructure, and logs. Useful for agents in polyglot environments that need cross-layer signal in a single API call."}'::jsonb,
    now()
  ),
  (
    'instana',
    8.05,
    8.15,
    7.80,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"apm expansion II","phase0_assessment":"Strong enterprise Resolve target for apm.service.list, apm.events.list, apm.trace.get. REST API is comprehensive and well-documented. API token auth model is clean. Best for agents embedded in IBM/enterprise stack environments.","notes":"Excellent service mapping and topology inspection capabilities. IBM acquisition adds enterprise trust but slightly narrows the addressable startup/SME market."}'::jsonb,
    now()
  ),
  (
    'appdynamics',
    7.80,
    7.90,
    7.55,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"apm expansion II","phase0_assessment":"REST API is available and well-documented but Splunk acquisition layered additional complexity onto auth and endpoint topology. apm.transaction.list and apm.health.summary are viable Resolve starting points for enterprise Java/.NET environments.","notes":"Strategically important for coverage in legacy enterprise Java shops. Splunk integration means this is increasingly a Splunk SSO / OAuth path rather than pure API key, which increases managed credential complexity."}'::jsonb,
    now()
  ),
  (
    'apache-skywalking',
    7.70,
    7.80,
    7.45,
    0.55,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"apm expansion II","phase0_assessment":"GraphQL query protocol is richly documented and covers service/endpoint/trace/topology queries well. apm.service.list and apm.endpoint.latency are clean Phase 0 starting points once a GraphQL execution path is normalized. Self-hosted and SaaS deployments vary in endpoint.","notes":"High adoption in JVM-heavy and Kubernetes environments (particularly in Asia-Pacific and China). Important catalog depth for completeness but GraphQL surface and self-hosted variability make normalization harder than SaaS-first alternatives."}'::jsonb,
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
