BEGIN;

-- Migration 0123: Screenshots discovery expansion II (2026-03-30)
-- Rationale: the live screenshots category is still badly underrepresented even
-- though agents regularly need deterministic URL/HTML -> image capture for QA,
-- preview generation, compliance evidence, browser fallback, and visual diff
-- workflows. Add five more API-backed screenshot vendors with clear capture
-- surfaces and strong Phase 0 potential around a normalized screenshot.capture
-- capability.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'screenshotone',
    'ScreenshotOne',
    'screenshots',
    'API-first website screenshot and rendering platform with URL and HTML capture, image and PDF output, viewport controls, auth via access key, and flexible rendering options for previews, QA, and monitoring workflows.',
    'https://screenshotone.com/docs/',
    'api.screenshotone.com'
  ),
  (
    'urlbox',
    'Urlbox',
    'screenshots',
    'Screenshot and rendering API with direct render links plus sync/async JSON workflows for website screenshots, HTML-to-image and PDF, video capture, metadata extraction, and scheduled archival use cases.',
    'https://urlbox.com/docs',
    'api.urlbox.com'
  ),
  (
    'capturekit',
    'CaptureKit',
    'screenshots',
    'Capture API for website screenshots and related rendering jobs with synchronous and asynchronous modes, job polling, API-key auth, and billing tied to successful capture responses.',
    'https://docs.capturekit.dev/',
    'api.capturekit.dev'
  ),
  (
    'screenshotapi-net',
    'ScreenshotAPI.net',
    'screenshots',
    'Configurable screenshot API for websites with PNG, JPEG, WebP, PDF, video, custom CSS and JS injection, geolocation, fresh renders, and flexible GET or POST request support.',
    'https://www.screenshotapi.net/docs/',
    'api.screenshotapi.net'
  ),
  (
    'url2png',
    'URL2PNG',
    'screenshots',
    'Long-running screenshot-as-a-service with signed request URLs, viewport and full-page controls, and simple website-to-image capture for preview and archival workflows.',
    'https://www.url2png.com/docs/',
    'api.url2png.com'
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
    'screenshotone',
    8.30,
    8.45,
    8.10,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"screenshots expansion ii","notes":"Strongest Phase 0 candidate in the batch. Clear capture endpoint, explicit access-key auth, URL and HTML rendering support, and good fit for a normalized screenshot.capture capability with optional PDF output."}'::jsonb,
    now()
  ),
  (
    'urlbox',
    8.20,
    8.35,
    8.00,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"screenshots expansion ii","notes":"Very strong breadth across synchronous and asynchronous capture plus HTML-to-image/PDF and metadata extraction. Excellent second Phase 0 lane after ScreenshotOne for screenshot.capture and render-from-html variants."}'::jsonb,
    now()
  ),
  (
    'capturekit',
    8.05,
    8.15,
    7.90,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"screenshots expansion ii","notes":"Clean API-key posture with synchronous and asynchronous billing semantics and job polling. Useful category depth for repeatable capture workflows and good future parity-test potential once screenshot execution lands in Resolve."}'::jsonb,
    now()
  ),
  (
    'screenshotapi-net',
    7.90,
    8.00,
    7.75,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"screenshots expansion ii","notes":"Broad parameter surface including PNG/JPEG/WebP/PDF plus CSS/JS injection and geolocation. Valuable for category depth, though the broader feature surface creates a slightly noisier normalization target than ScreenshotOne or Urlbox."}'::jsonb,
    now()
  ),
  (
    'url2png',
    7.55,
    7.70,
    7.45,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"screenshots expansion ii","notes":"Older but still straightforward signed-URL screenshot API with viewport and full-page controls. Good long-tail catalog coverage for simple URL-to-image capture even if the surface is narrower and less modern than the leaders."}'::jsonb,
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
