-- Migration: 0046_capability_expansion_day6
-- Description: Day 6 capability expansion — 10 new capabilities across web-scraping, data-pipeline,
--              infrastructure-as-code, and testing. Scraping caps mapped to proxy-callable Firecrawl/Apify.
-- Date: 2026-03-21
-- Author: Helm (rhumb-access)
-- Result: 135 capabilities, 429 mappings.

-- ============================================================
-- NEW CAPABILITIES (10)
-- ============================================================

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
-- Web scraping (proxy-executable via Firecrawl + Apify)
('scrape.extract', 'scrape', 'extract', 'Extract structured data from a web page URL', 'url, selectors?, output_format?, wait_for?', 'Extracted content as markdown, HTML, or structured JSON'),
('scrape.crawl', 'scrape', 'crawl', 'Crawl a website starting from a URL, following links to discover and extract pages', 'start_url, max_pages?, depth?, include_patterns?, exclude_patterns?', 'List of crawled pages with URLs, content, and metadata'),
('scrape.screenshot', 'scrape', 'screenshot', 'Capture a screenshot of a web page as an image', 'url, viewport_width?, viewport_height?, full_page?, format?', 'Screenshot image URL or base64-encoded image data'),
-- Data pipeline
('pipeline.sync', 'pipeline', 'sync', 'Trigger a data sync or replication job between a source and destination', 'connection_id, full_refresh?, streams?', 'Sync job ID with status, bytes synced, and records count'),
('pipeline.transform', 'pipeline', 'transform', 'Run a data transformation or dbt job against a data warehouse', 'project_id, job_id?, models?, full_refresh?', 'Transform run ID with status, models executed, and rows affected'),
('pipeline.schedule', 'pipeline', 'schedule', 'Create or update a recurring schedule for a data pipeline sync or transform', 'connection_id or job_id, cron_expression, timezone?', 'Schedule ID with next run time and frequency'),
-- Infrastructure-as-Code
('infra.plan', 'infra', 'plan', 'Generate an infrastructure change plan showing resources to create, update, or destroy', 'workspace_id or stack, config_version?', 'Plan ID with resource change summary (add/change/destroy counts)'),
('infra.deploy', 'infra', 'deploy', 'Apply an infrastructure plan or deploy a stack update to provision cloud resources', 'plan_id or workspace_id, auto_approve?, target_resources?', 'Apply run ID with status, resources provisioned, and outputs'),
-- Testing
('test.run', 'test', 'run', 'Execute a test suite or individual test against a target environment', 'project_id, test_suite?, browser?, os?, parallel?', 'Test run ID with pass/fail counts, duration, and results URL'),
('test.create_session', 'test', 'create_session', 'Create a remote browser or device testing session', 'browser, browser_version?, os?, os_version?, resolution?', 'Session ID with connection URL and capabilities')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- SERVICE MAPPINGS (37 new)
-- ============================================================

-- scrape.extract → firecrawl (CALLABLE), apify (CALLABLE), bright-data, zenrows, oxylabs
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('scrape.extract', 'firecrawl', '{byo,rhumb_managed}', 'bearer', 'POST /v1/scrape', 'PROXY-CALLABLE — live credential. Returns markdown + structured data.'),
('scrape.extract', 'apify', '{byo,rhumb_managed}', 'bearer', 'POST /v2/acts/{actorId}/runs', 'PROXY-CALLABLE — live credential. Actor-based web extraction.'),
('scrape.extract', 'bright-data', '{byo}', 'bearer', 'POST /datasets/trigger', 'Web Scraper IDE + structured data delivery'),
('scrape.extract', 'zenrows', '{byo}', 'api_key', 'GET /v1/?url={url}', 'Anti-bot bypass, headless browser rendering'),
('scrape.extract', 'oxylabs', '{byo}', 'basic', 'POST /v1/queries', 'Enterprise web scraping with residential proxies')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- scrape.crawl → firecrawl (CALLABLE), apify (CALLABLE), bright-data, zenrows
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('scrape.crawl', 'firecrawl', '{byo,rhumb_managed}', 'bearer', 'POST /v1/crawl', 'PROXY-CALLABLE — site crawl with link following + markdown output'),
('scrape.crawl', 'apify', '{byo,rhumb_managed}', 'bearer', 'POST /v2/acts/apify~web-scraper/runs', 'PROXY-CALLABLE — Apify Web Scraper actor for multi-page crawl'),
('scrape.crawl', 'bright-data', '{byo}', 'bearer', 'POST /datasets/trigger', 'Site crawl with residential proxy rotation'),
('scrape.crawl', 'zenrows', '{byo}', 'api_key', 'GET /v1/?url={url}', 'Sequential page crawl with anti-bot bypass')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- scrape.screenshot → firecrawl (CALLABLE), apify (CALLABLE), browserless
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('scrape.screenshot', 'firecrawl', '{byo,rhumb_managed}', 'bearer', 'POST /v1/scrape (screenshot option)', 'PROXY-CALLABLE — screenshot via scrape with formats[]=screenshot'),
('scrape.screenshot', 'apify', '{byo,rhumb_managed}', 'bearer', 'POST /v2/acts/apify~screenshot-url/runs', 'PROXY-CALLABLE — dedicated screenshot actor'),
('scrape.screenshot', 'browserless', '{byo}', 'bearer', 'POST /screenshot', 'Headless Chrome screenshot service')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- pipeline.sync → airbyte, fivetran, stitch, meltano
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('pipeline.sync', 'airbyte', '{byo}', 'bearer', 'POST /v1/connections/sync', 'Open-source ELT, 300+ connectors'),
('pipeline.sync', 'fivetran', '{byo}', 'bearer', 'POST /v1/connectors/{connector_id}/sync', 'Managed ELT, 400+ connectors'),
('pipeline.sync', 'stitch', '{byo}', 'bearer', 'POST /v4/sources/{source_id}/sync', 'Simple ETL, Talend-backed'),
('pipeline.sync', 'meltano', '{byo}', 'bearer', 'POST /api/v1/pipelines/{id}/run', 'Open-source DataOps, Singer-based connectors')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- pipeline.transform → dbt-cloud, airbyte, fivetran
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('pipeline.transform', 'dbt-cloud', '{byo}', 'bearer', 'POST /api/v2/accounts/{accountId}/jobs/{jobId}/run/', 'SQL-based data transformation, CI/CD for analytics'),
('pipeline.transform', 'airbyte', '{byo}', 'bearer', 'POST /v1/connections/sync (with transformations)', 'Airbyte transformations via dbt integration'),
('pipeline.transform', 'fivetran', '{byo}', 'bearer', 'POST /v1/dbt/transformations/{id}/trigger', 'Fivetran dbt integration for post-sync transforms')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- pipeline.schedule → airbyte, fivetran, dbt-cloud
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('pipeline.schedule', 'airbyte', '{byo}', 'bearer', 'PUT /v1/connections/{connectionId}/schedule', 'Cron or interval-based sync scheduling'),
('pipeline.schedule', 'fivetran', '{byo}', 'bearer', 'PATCH /v1/connectors/{connector_id}', 'Sync frequency: 1min to 24h intervals'),
('pipeline.schedule', 'dbt-cloud', '{byo}', 'bearer', 'POST /api/v2/accounts/{accountId}/jobs/', 'dbt job scheduling with cron expressions')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- infra.plan → terraform-cloud, pulumi-cloud, spacelift
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('infra.plan', 'terraform-cloud', '{byo}', 'bearer', 'POST /api/v2/runs', 'Terraform plan via workspace run, shows resource changes'),
('infra.plan', 'pulumi-cloud', '{byo}', 'bearer', 'POST /api/stacks/{org}/{project}/{stack}/preview', 'Pulumi preview showing resource diff'),
('infra.plan', 'spacelift', '{byo}', 'bearer', 'POST /graphql (triggerRun)', 'Spacelift proposed run for IaC plan')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- infra.deploy → terraform-cloud, pulumi-cloud, argocd, spacelift
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('infra.deploy', 'terraform-cloud', '{byo}', 'bearer', 'POST /api/v2/runs/{run_id}/actions/apply', 'Terraform apply — provision infrastructure from plan'),
('infra.deploy', 'pulumi-cloud', '{byo}', 'bearer', 'POST /api/stacks/{org}/{project}/{stack}/update', 'Pulumi update to provision stack resources'),
('infra.deploy', 'argocd', '{byo}', 'bearer', 'POST /api/v1/applications/{name}/sync', 'GitOps-driven Kubernetes deployment'),
('infra.deploy', 'spacelift', '{byo}', 'bearer', 'POST /graphql (confirmRun)', 'Spacelift confirmed run for IaC deploy')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- test.run → browserstack, lambdatest, cypress-cloud, k6
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('test.run', 'browserstack', '{byo}', 'basic', 'POST /automate/builds', 'Cloud browser testing, 3000+ device/browser combos'),
('test.run', 'lambdatest', '{byo}', 'basic', 'POST /automation/api/v1/builds', 'Cross-browser testing with HyperExecute'),
('test.run', 'cypress-cloud', '{byo}', 'bearer', 'POST /runs', 'Cypress test parallelization + dashboard'),
('test.run', 'k6', '{byo}', 'bearer', 'POST /loadtests/v2/runs', 'Grafana k6 Cloud — load + performance testing')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- test.create_session → browserstack, lambdatest, sauce-labs
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('test.create_session', 'browserstack', '{byo}', 'basic', 'POST /wd/hub/session', 'WebDriver session on cloud browsers'),
('test.create_session', 'lambdatest', '{byo}', 'basic', 'POST /wd/hub/session', 'Remote WebDriver session with 3000+ environments'),
('test.create_session', 'sauce-labs', '{byo}', 'basic', 'POST /wd/hub/session', 'Enterprise testing cloud, real device farm')
ON CONFLICT (capability_id, service_slug) DO NOTHING;
