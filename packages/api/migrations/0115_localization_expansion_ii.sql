BEGIN;

-- Migration 0115: Localization discovery expansion II (2026-03-28)
-- Rationale: localization remains a high-demand operational category for
-- agent-managed product copy, docs sync, i18n export, and release workflows,
-- but the live catalog is still thin and misses several important API-backed
-- platforms across enterprise, developer-first, and self-hosted deployment
-- modes. Add 4 more services with credible programmable control surfaces and
-- note the clearest near-term Phase 0 candidates.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'smartling',
    'Smartling',
    'localization',
    'Enterprise localization platform with API coverage for authentication, projects, files, locale workflows, translation delivery, and automation around large-scale product and documentation translation programs.',
    'https://api-reference.smartling.com/',
    'api.smartling.com'
  ),
  (
    'locize',
    'locize',
    'localization',
    'Developer-first localization platform built around continuous translation, namespaces, language resource sync, machine translation workflows, and i18n content delivery for modern apps.',
    'https://locize.com/docs/introduction',
    NULL
  ),
  (
    'poeditor',
    'POEditor',
    'localization',
    'Localization management platform with a public API for projects, languages, terms, translation uploads, exports, and glossary-style translation workflows across app and marketing content.',
    'https://poeditor.com/docs/api',
    'api.poeditor.com'
  ),
  (
    'weblate',
    'Weblate',
    'localization',
    'Open-source and hosted localization platform with REST API support for projects, components, translations, repository-backed sync, and self-hosted translation operations.',
    'https://docs.weblate.org/en/latest/api.html',
    NULL
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
    'smartling',
    8.05,
    8.35,
    7.75,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"localization expansion ii","notes":"High-value enterprise localization anchor with deep file/project automation and real API coverage. Strong category inclusion now, but OAuth plus enterprise setup make it a slower first Resolve target than POEditor or locize."}'::jsonb,
    now()
  ),
  (
    'locize',
    8.25,
    8.35,
    8.15,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"localization expansion ii","notes":"Strong developer-first localization surface with continuous sync semantics and practical namespace-driven workflows. Very credible later Resolve target for localization.sync and localization.export once we prioritize the localization lane."}'::jsonb,
    now()
  ),
  (
    'poeditor',
    8.30,
    8.40,
    8.20,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"localization expansion ii","notes":"Best immediate Phase 0 candidate in this batch. POEditor publishes a clean callable API with explicit project, language, upload, and export methods that map well to localization.sync and localization.export primitives."}'::jsonb,
    now()
  ),
  (
    'weblate',
    7.95,
    8.20,
    7.55,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"localization expansion ii","notes":"Important self-hosted and open-source localization option with a real REST API and repo-backed translation workflows. Lower turnkey access readiness than SaaS peers, but strategically valuable for agent-heavy teams that want control over deployment and data residency."}'::jsonb,
    now()
  );

COMMIT;
