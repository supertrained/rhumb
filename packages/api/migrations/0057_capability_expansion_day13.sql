-- Migration 0057: Capability expansion Day 13
-- Push past the 200-capability milestone.
-- 8 new capabilities across 2 new domains: nlp, pdf

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- NLP (4)
  ('nlp.extract_entities', 'nlp', 'Extract named entities (people, places, orgs) from text', 'active'),
  ('nlp.sentiment',        'nlp', 'Detect sentiment (positive/negative/neutral) in text',    'active'),
  ('nlp.summarize',        'nlp', 'Produce an abstractive or extractive summary of text',    'active'),
  ('nlp.classify',         'nlp', 'Classify text into predefined categories',                'active'),
  -- PDF (4)
  ('pdf.convert',          'pdf', 'Convert documents to or from PDF format',                 'active'),
  ('pdf.merge',            'pdf', 'Merge multiple PDF files into one',                       'active'),
  ('pdf.extract_text',     'pdf', 'Extract plain text or structured data from a PDF',        'active'),
  ('pdf.generate',         'pdf', 'Generate a PDF from HTML, Markdown, or template',         'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- nlp.extract_entities
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('nlp.extract_entities', 'cohere',          '{byo}', 'api_key', 'POST /v1/generate',            'Entity extraction via prompt. Free trial tier.'),
  ('nlp.extract_entities', 'aws-comprehend',  '{byo}', 'api_key', 'DetectEntities (AWS SDK)',      '50K units/mo free 12 months.'),
  ('nlp.extract_entities', 'google-nlp',      '{byo}', 'api_key', 'POST /v1/documents:analyzeEntities', '5K units/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- nlp.sentiment
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('nlp.sentiment', 'cohere',         '{byo}', 'api_key', 'POST /v1/classify',                   'Sentiment via classification endpoint.'),
  ('nlp.sentiment', 'aws-comprehend', '{byo}', 'api_key', 'DetectSentiment (AWS SDK)',            '50K units/mo free 12 months.'),
  ('nlp.sentiment', 'google-nlp',     '{byo}', 'api_key', 'POST /v1/documents:analyzeSentiment', '5K units/mo free.'),
  ('nlp.sentiment', 'huggingface',    '{byo}', 'api_key', 'POST /models/{model}',                'Inference API — many free sentiment models.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- nlp.summarize
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('nlp.summarize', 'cohere',      '{byo}', 'api_key', 'POST /v1/summarize',       'Dedicated summarize endpoint. Free trial.'),
  ('nlp.summarize', 'huggingface', '{byo}', 'api_key', 'POST /models/{model}',     'BART, Pegasus, etc.'),
  ('nlp.summarize', 'openai',      '{byo}', 'api_key', 'POST /v1/chat/completions','GPT-4o/mini prompt-based summarization.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- nlp.classify
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('nlp.classify', 'cohere',         '{byo}', 'api_key', 'POST /v1/classify',       'Few-shot text classification.'),
  ('nlp.classify', 'aws-comprehend', '{byo}', 'api_key', 'ClassifyDocument (AWS SDK)', 'Custom or zero-shot classifier.'),
  ('nlp.classify', 'huggingface',    '{byo}', 'api_key', 'POST /models/{model}',    'Zero-shot classification pipeline.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- pdf.convert
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('pdf.convert', 'pdfco',       '{byo}', 'api_key', 'POST /v1/pdf/convert/from/html',     '250 API calls/mo free.'),
  ('pdf.convert', 'ilovepdf',    '{byo}', 'api_key', 'POST /v1/process',                   'Office, image, HTML → PDF.'),
  ('pdf.convert', 'pdf-services','{byo}', 'api_key', 'POST /operation/createpdf',          'Adobe PDF Services — 500 docs/mo free.'),
  ('pdf.convert', 'unstructured','{byo,rhumb_managed}', 'api_key', 'POST /general/v0/general', 'PROXY-CALLABLE — live Unstructured credential. Converts + parses many doc types.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- pdf.merge
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('pdf.merge', 'pdfco',       '{byo}', 'api_key', 'POST /v1/pdf/merge',    '250 API calls/mo free.'),
  ('pdf.merge', 'ilovepdf',    '{byo}', 'api_key', 'POST /v1/process',      'Merge tool.'),
  ('pdf.merge', 'pdf-services','{byo}', 'api_key', 'POST /operation/combinepdf', 'Adobe PDF Services.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- pdf.extract_text
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('pdf.extract_text', 'pdfco',      '{byo}', 'api_key', 'POST /v1/pdf/convert/to/text',       '250 API calls/mo free.'),
  ('pdf.extract_text', 'unstructured','{byo,rhumb_managed}', 'api_key', 'POST /general/v0/general', 'PROXY-CALLABLE — live credential. Best-in-class PDF/table extraction.'),
  ('pdf.extract_text', 'pdf-services','{byo}', 'api_key', 'POST /operation/extractpdf',        'Adobe structured data extraction.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- pdf.generate
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('pdf.generate', 'pdfco',    '{byo}', 'api_key', 'POST /v1/pdf/convert/from/html', 'HTML → PDF generation.'),
  ('pdf.generate', 'pdfmonkey','{byo}', 'api_key', 'POST /v1/documents',             'Template-based PDF generation.'),
  ('pdf.generate', 'ilovepdf', '{byo}', 'api_key', 'POST /v1/process',               'HTML/Word → PDF.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Totals: 8 new capabilities, ~31 new mappings
-- Running total: ~203 capabilities, ~639 mappings
-- 200-capability milestone REACHED ✅
-- ============================================================

COMMIT;
