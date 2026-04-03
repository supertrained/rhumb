BEGIN;

-- Migration 0153: Design discovery expansion (2026-04-03)
-- Rationale: live production still shows the design category at only four
-- providers (Framer, Lunacy, Penpot, Sketch API) despite design automation,
-- template rendering, and image generation being high-demand agent primitives.
-- Agents need programmatic image/template generation for email personalization,
-- social content, report rendering, brand-consistent assets, and visual workflow
-- output. This batch adds five API-backed design and image generation platforms
-- that fill the most accessible first-wave Resolve wedge in the category.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'canva',
    'Canva',
    'design',
    'Cloud-based design platform with APIs for template management, design creation, exporting, brand kit access, and automated design workflow via the Canva Platform API.',
    'https://www.canva.com/developers/docs/',
    'api.canva.com'
  ),
  (
    'bannerbear',
    'Bannerbear',
    'design',
    'Automated image and video generation platform with APIs for template-driven image creation, text/image layers, collections, signed URLs, and webhook-driven production rendering.',
    'https://developers.bannerbear.com/',
    'sync.api.bannerbear.com'
  ),
  (
    'placid',
    'Placid',
    'design',
    'Template-based image and PDF generation API with support for dynamic text, image, and layer substitution across web, social, email, and document output formats.',
    'https://placid.app/developers',
    'api.placid.app'
  ),
  (
    'frontify',
    'Frontify',
    'design',
    'Brand management and design system platform with APIs for assets, guidelines, libraries, templates, and brand-consistent content delivery for enterprise design workflows.',
    'https://developer.frontify.com/',
    'app.frontify.com'
  ),
  (
    'photoroom',
    'PhotoRoom',
    'design',
    'AI-powered image editing API covering background removal, background generation, product photo enhancement, outpainting, and scene creation for automated visual production.',
    'https://www.photoroom.com/api',
    'sdk.photoroom.com'
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
    'bannerbear',
    8.55,
    8.70,
    8.35,
    0.70,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"design expansion","phase0_assessment":"Best immediate Resolve candidate in the batch. Bannerbear exposes a clean synchronous image generation API (POST /v2/images) with template, layer overrides, and metadata semantics that map directly to a design.template.render primitive.","notes":"Extremely accessible: API key only, synchronous endpoint option, explicit layer override model. Best fit for agent workflows that need brand-consistent generated images in email, content, and report automation."}'::jsonb,
    now()
  ),
  (
    'placid',
    8.45,
    8.55,
    8.25,
    0.68,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"design expansion","phase0_assessment":"Strong second Resolve candidate for design.template.render using Placid POST /renders. Very similar to Bannerbear in structure: template slug, dynamic layer values, format control, and a PDF generation path that Bannerbear does not cover.","notes":"Good for teams who need both image and PDF output from templates. Slightly lighter API surface than Bannerbear but well-suited for document and social template automation."}'::jsonb,
    now()
  ),
  (
    'canva',
    8.35,
    8.45,
    8.15,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"design expansion","phase0_assessment":"Credible Resolve target for design.export and design.template.list once the OAuth complexity is addressed. Canva Platform API exposes designs, brand kits, and exports, but the auth path (OAuth 2.0 with user consent) is heavier than Bannerbear or Placid for a first managed provider.","notes":"Category-defining platform. Important catalog inclusion. Best as a second-wave Resolve target after simpler key-auth template providers are normalized."}'::jsonb,
    now()
  ),
  (
    'photoroom',
    8.25,
    8.40,
    8.05,
    0.65,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"design expansion","phase0_assessment":"Strong candidate for image.edit.background_remove via POST https://sdk.photoroom.com/v1/segment. Single-purpose, API-key only, well-documented. Useful orthogonal capability to template rendering — more useful for product photo automation than design template workflows.","notes":"Best non-template-rendering design wedge in the batch. Extremely high demand for product photography automation, ecommerce image pipelines, and content asset cleanup."}'::jsonb,
    now()
  ),
  (
    'frontify',
    8.10,
    8.20,
    7.90,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"design expansion","phase0_assessment":"Good enterprise catalog depth for brand asset management via GraphQL API. Useful for design.asset.list and design.brand_kit.get workflows, but GraphQL adds normalization complexity versus the REST-first Bannerbear/Placid surface.","notes":"Strategically important for enterprise brand and design system workflows. Better as a later Resolve target when a GraphQL execution path is supported."}'::jsonb,
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
