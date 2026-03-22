-- Migration 0072: Capability Expansion Day 28
-- Domains: kyc, workflow, document_ai, asset
-- New capabilities: 10
-- New mappings: ~37
-- Cumulative target: ~331 capabilities / ~1147 mappings

-- ============================================================
-- DOMAIN: kyc (Know Your Customer / Identity Verification)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('kyc.verify', 'kyc.verify', 'kyc', 'Submit a KYC verification request for a customer (AML/PEP screening, ID check)', '{"type":"object","required":["customer_id","type"],"properties":{"customer_id":{"type":"string"},"type":{"type":"string","enum":["identity","aml","pep","sanctions","all"]},"given_name":{"type":"string"},"family_name":{"type":"string"},"dob":{"type":"string"},"country":{"type":"string"},"id_number":{"type":"string"}}}', '{"type":"object","properties":{"verification_id":{"type":"string"},"status":{"type":"string","enum":["pending","approved","declined","review"]},"risk_level":{"type":"string","enum":["low","medium","high"]},"checks":{"type":"array"}}}'),
  ('kyc.check_document', 'kyc.check_document', 'kyc', 'Submit a government-issued document for authenticity and data extraction', '{"type":"object","required":["customer_id","document_type","front_url"],"properties":{"customer_id":{"type":"string"},"document_type":{"type":"string","enum":["passport","drivers_license","national_id","residence_permit"]},"front_url":{"type":"string"},"back_url":{"type":"string"},"selfie_url":{"type":"string"}}}', '{"type":"object","properties":{"check_id":{"type":"string"},"status":{"type":"string"},"extracted":{"type":"object","description":"Parsed document fields"},"liveness_passed":{"type":"boolean"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- kyc.verify
  ('kyc.verify', 'persona', 'byo', 0.020, 8.2, true),
  ('kyc.verify', 'onfido', 'byo', 0.025, 8.1, false),
  ('kyc.verify', 'jumio', 'byo', 0.030, 8.0, false),
  ('kyc.verify', 'stripe-identity', 'byo', 0.015, 7.9, false),
  -- kyc.check_document
  ('kyc.check_document', 'persona', 'byo', 0.030, 8.2, true),
  ('kyc.check_document', 'onfido', 'byo', 0.035, 8.1, false),
  ('kyc.check_document', 'jumio', 'byo', 0.040, 8.0, false),
  ('kyc.check_document', 'stripe-identity', 'byo', 0.025, 7.9, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: workflow (Workflow Automation & Orchestration)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('workflow.create', 'workflow.create', 'workflow', 'Create or register a new automation workflow from a definition', '{"type":"object","required":["name"],"properties":{"name":{"type":"string"},"trigger":{"type":"object","description":"Trigger configuration (webhook, schedule, event)"},"steps":{"type":"array","description":"Ordered list of action steps"},"active":{"type":"boolean","default":false}}}', '{"type":"object","properties":{"workflow_id":{"type":"string"},"status":{"type":"string"},"webhook_url":{"type":"string"}}}'),
  ('workflow.trigger', 'workflow.trigger', 'workflow', 'Manually trigger a workflow execution with optional input payload', '{"type":"object","required":["workflow_id"],"properties":{"workflow_id":{"type":"string"},"payload":{"type":"object"},"async":{"type":"boolean","default":true}}}', '{"type":"object","properties":{"execution_id":{"type":"string"},"status":{"type":"string"},"started_at":{"type":"string"}}}'),
  ('workflow.get_status', 'workflow.get_status', 'workflow', 'Get the current status and output of a workflow execution', '{"type":"object","required":["execution_id"],"properties":{"execution_id":{"type":"string"}}}', '{"type":"object","properties":{"execution_id":{"type":"string"},"status":{"type":"string","enum":["running","succeeded","failed","cancelled"]},"output":{"type":"object"},"error":{"type":"string"},"duration_ms":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- workflow.create
  ('workflow.create', 'make', 'byo', 0.010, 7.9, true),
  ('workflow.create', 'zapier', 'byo', 0.012, 7.8, false),
  ('workflow.create', 'tray', 'byo', 0.015, 7.7, false),
  ('workflow.create', 'n8n', 'byo', 0.005, 7.6, false),
  -- workflow.trigger
  ('workflow.trigger', 'make', 'byo', 0.005, 7.9, true),
  ('workflow.trigger', 'zapier', 'byo', 0.006, 7.8, false),
  ('workflow.trigger', 'tray', 'byo', 0.008, 7.7, false),
  ('workflow.trigger', 'n8n', 'byo', 0.003, 7.6, false),
  -- workflow.get_status
  ('workflow.get_status', 'make', 'byo', 0.003, 7.9, true),
  ('workflow.get_status', 'zapier', 'byo', 0.003, 7.8, false),
  ('workflow.get_status', 'tray', 'byo', 0.004, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: document_ai (Document Intelligence & Extraction)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('document_ai.extract_entities', 'document_ai.extract_entities', 'document_ai', 'Extract structured entities (names, dates, amounts, line items) from a document', '{"type":"object","required":["document_url"],"properties":{"document_url":{"type":"string"},"document_type":{"type":"string","enum":["invoice","receipt","contract","form","general"]},"fields":{"type":"array","description":"Specific field names to extract; omit for auto-detection"}}}', '{"type":"object","properties":{"entities":{"type":"object","description":"Extracted field names and values"},"confidence":{"type":"number"},"page_count":{"type":"integer"}}}'),
  ('document_ai.classify', 'document_ai.classify', 'document_ai', 'Classify a document into a category (invoice, contract, ID, etc.)', '{"type":"object","required":["document_url"],"properties":{"document_url":{"type":"string"},"candidate_types":{"type":"array","description":"Restrict classification to these types; omit for open classification"}}}', '{"type":"object","properties":{"document_type":{"type":"string"},"confidence":{"type":"number"},"alternatives":{"type":"array"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- document_ai.extract_entities
  ('document_ai.extract_entities', 'google-documentai', 'byo', 0.015, 8.3, true),
  ('document_ai.extract_entities', 'aws-textract', 'byo', 0.010, 8.1, false),
  ('document_ai.extract_entities', 'azure-formrecognizer', 'byo', 0.012, 8.2, false),
  ('document_ai.extract_entities', 'reducto', 'byo', 0.008, 7.8, false),
  -- document_ai.classify
  ('document_ai.classify', 'google-documentai', 'byo', 0.010, 8.3, true),
  ('document_ai.classify', 'aws-textract', 'byo', 0.008, 8.1, false),
  ('document_ai.classify', 'azure-formrecognizer', 'byo', 0.009, 8.2, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: asset (Digital Asset Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('asset.upload', 'asset.upload', 'asset', 'Upload a media asset (image, video, file) to a DAM or storage service', '{"type":"object","required":["source_url"],"properties":{"source_url":{"type":"string"},"folder":{"type":"string"},"public_id":{"type":"string"},"tags":{"type":"array"},"overwrite":{"type":"boolean","default":false}}}', '{"type":"object","properties":{"asset_id":{"type":"string"},"url":{"type":"string"},"format":{"type":"string"},"bytes":{"type":"integer"},"width":{"type":"integer"},"height":{"type":"integer"}}}'),
  ('asset.transform', 'asset.transform', 'asset', 'Apply transformations (resize, crop, format convert, watermark) to an asset', '{"type":"object","required":["asset_id"],"properties":{"asset_id":{"type":"string"},"width":{"type":"integer"},"height":{"type":"integer"},"crop":{"type":"string","enum":["fill","fit","scale","crop","thumb"]},"format":{"type":"string","enum":["jpg","png","webp","avif","gif"]},"quality":{"type":"integer"},"effects":{"type":"array"}}}', '{"type":"object","properties":{"url":{"type":"string"},"format":{"type":"string"},"bytes":{"type":"integer"},"width":{"type":"integer"},"height":{"type":"integer"}}}'),
  ('asset.get_url', 'asset.get_url', 'asset', 'Get a signed or public delivery URL for a stored asset', '{"type":"object","required":["asset_id"],"properties":{"asset_id":{"type":"string"},"expiry_seconds":{"type":"integer","description":"For signed URLs; omit for permanent public URL"},"transformations":{"type":"string","description":"Inline transformation string"}}}', '{"type":"object","properties":{"url":{"type":"string"},"expires_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- asset.upload
  ('asset.upload', 'cloudinary', 'byo', 0.005, 8.4, true),
  ('asset.upload', 'imgix', 'byo', 0.004, 8.0, false),
  ('asset.upload', 'uploadcare', 'byo', 0.004, 7.7, false),
  ('asset.upload', 'bunny', 'byo', 0.003, 7.5, false),
  -- asset.transform
  ('asset.transform', 'cloudinary', 'byo', 0.004, 8.4, true),
  ('asset.transform', 'imgix', 'byo', 0.003, 8.0, false),
  ('asset.transform', 'uploadcare', 'byo', 0.003, 7.7, false),
  -- asset.get_url
  ('asset.get_url', 'cloudinary', 'byo', 0.001, 8.4, true),
  ('asset.get_url', 'imgix', 'byo', 0.001, 8.0, false),
  ('asset.get_url', 'bunny', 'byo', 0.001, 7.5, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
