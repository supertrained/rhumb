-- Migration 0052: Capability expansion Day 8
-- 10 new capabilities across 4 domains: nlp, pdf, file, barcode
-- Continues cadence toward 200 total capabilities (~145 → ~155)

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- NLP / text intelligence (3)
  ('nlp.extract_entities', 'nlp', 'Extract named entities (people, places, orgs) from text', 'active'),
  ('nlp.sentiment',        'nlp', 'Analyze sentiment and tone of text',                      'active'),
  ('nlp.summarize',        'nlp', 'Produce an abstractive or extractive summary of text',    'active'),
  -- PDF operations (3)
  ('pdf.convert',          'pdf', 'Convert a document or web page to PDF',                   'active'),
  ('pdf.merge',            'pdf', 'Merge multiple PDF files into one',                       'active'),
  ('pdf.extract_text',     'pdf', 'Extract plain text or structured data from a PDF',        'active'),
  -- File utilities (2)
  ('file.convert',         'file', 'Convert a file from one format to another',              'active'),
  ('file.compress',        'file', 'Compress a file or archive into zip/tar/etc',            'active'),
  -- Barcode / QR (2)
  ('barcode.generate',     'barcode', 'Generate a QR code or barcode image',                 'active'),
  ('barcode.scan',         'barcode', 'Decode a barcode or QR code from an image',           'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- nlp.extract_entities
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('nlp.extract_entities', 'cohere',          '{byo}', 'api_key', 'POST /v1/classify',             'Cohere NLP. Free trial tier.'),
  ('nlp.extract_entities', 'google-nlp',      '{byo}', 'api_key', 'POST /v1/documents:analyzeEntities', 'Google Natural Language API. 5K units/mo free.'),
  ('nlp.extract_entities', 'aws-comprehend',  '{byo}', 'api_key', 'DetectEntities (AWS SDK)',       '50K units/mo free for 12 months.'),
  ('nlp.extract_entities', 'huggingface',     '{byo}', 'api_key', 'POST /models/{model}',           'Inference API, many NER models.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- nlp.sentiment
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('nlp.sentiment', 'cohere',         '{byo}', 'api_key', 'POST /v1/classify',                   'Sentiment classification.'),
  ('nlp.sentiment', 'google-nlp',     '{byo}', 'api_key', 'POST /v1/documents:analyzeSentiment', 'Google NL sentiment. 5K units/mo free.'),
  ('nlp.sentiment', 'aws-comprehend', '{byo}', 'api_key', 'DetectSentiment (AWS SDK)',            '50K units/mo free for 12 months.'),
  ('nlp.sentiment', 'meaningcloud',   '{byo}', 'api_key', 'POST /sentiment-2.1',                 '40K credits/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- nlp.summarize
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('nlp.summarize', 'cohere',      '{byo}', 'api_key', 'POST /v1/summarize',   'Cohere Summarize endpoint.'),
  ('nlp.summarize', 'huggingface', '{byo}', 'api_key', 'POST /models/facebook/bart-large-cnn', 'BART summarization.'),
  ('nlp.summarize', 'openai',      '{byo}', 'api_key', 'POST /v1/chat/completions', 'GPT-4o-mini for cost-efficient summarization.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- pdf.convert
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('pdf.convert', 'pdfco',        '{byo}', 'api_key', 'POST /v1/pdf/convert/from/doc',  'PDF.co. Free trial credits.'),
  ('pdf.convert', 'ilovepdf',     '{byo}', 'api_key', 'POST /v1/upload + process',      'iLovePDF API. Free tier.'),
  ('pdf.convert', 'pdf-services', '{byo}', 'api_key', 'POST /operation/createpdf',      'Adobe PDF Services. 500 transactions/mo free.'),
  ('pdf.convert', 'unstructured', '{byo,rhumb_managed}', 'api_key', 'POST /general/v0/general', 'PROXY-CALLABLE — live Unstructured credential. Converts many doc types.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- pdf.merge
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('pdf.merge', 'pdfco',        '{byo}', 'api_key', 'POST /v1/pdf/merge',   'Up to 10 files per request.'),
  ('pdf.merge', 'ilovepdf',     '{byo}', 'api_key', 'POST /v1/merge',       'iLovePDF merge endpoint.'),
  ('pdf.merge', 'pdf-services', '{byo}', 'api_key', 'POST /operation/combinepdf', 'Adobe PDF Services.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- pdf.extract_text
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('pdf.extract_text', 'pdfco',        '{byo}', 'api_key', 'POST /v1/pdf/convert/to/text', 'Full text extraction.'),
  ('pdf.extract_text', 'pdf-services', '{byo}', 'api_key', 'POST /operation/extractpdf',   'Structured extraction incl tables.'),
  ('pdf.extract_text', 'unstructured', '{byo,rhumb_managed}', 'api_key', 'POST /general/v0/general', 'PROXY-CALLABLE — live credential. Best-in-class OCR + chunking.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- file.convert
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('file.convert', 'cloudconvert',  '{byo}', 'api_key', 'POST /v2/jobs',   'CloudConvert. 25 free conversions/day.'),
  ('file.convert', 'zamzar',        '{byo}', 'api_key', 'POST /v1/jobs',   'Zamzar. 100 conversions/mo free.'),
  ('file.convert', 'unstructured',  '{byo,rhumb_managed}', 'api_key', 'POST /general/v0/general', 'PROXY-CALLABLE — 64+ input formats.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- file.compress
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('file.compress', 'cloudconvert', '{byo}', 'api_key', 'POST /v2/jobs (archive task)', 'ZIP/TAR creation.'),
  ('file.compress', 'zamzar',       '{byo}', 'api_key', 'POST /v1/jobs',               'Compression via conversion job.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- barcode.generate
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('barcode.generate', 'qr-server',      '{byo}', 'none',    'GET /create-qr-code/?data={data}', 'Free QR code generation API (no key).'),
  ('barcode.generate', 'goqr',           '{byo}', 'none',    'GET /api/qr?data={data}',          'GoQR.me free API.'),
  ('barcode.generate', 'barcodeapi',     '{byo}', 'api_key', 'POST /barcode/{type}/{data}',      'Barcode generation service.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- barcode.scan
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('barcode.scan', 'google-vision',   '{byo}', 'api_key', 'POST /v1/images:annotate (DOCUMENT_TEXT_DETECTION)', 'QR/barcode via Vision API.'),
  ('barcode.scan', 'aws-rekognition', '{byo}', 'api_key', 'DetectText (AWS SDK)',                               'Text/barcode detection.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Totals: 10 new capabilities, ~35 new mappings
-- Running total: ~155 capabilities, ~501 mappings
-- ============================================================

COMMIT;
