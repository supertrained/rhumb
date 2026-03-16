-- Migration: 0023_capability_expansion_document_search
-- Description: Add document.convert, document.extract, and search.web_search capabilities
-- Date: 2026-03-16
-- Trigger: document API = 5,400/mo search demand (#2 gap after scraping)

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
-- Document expansion (5,400/mo demand)
('document.convert', 'document', 'convert', 'Convert between document formats', 'source_url or file, output_format (pdf, docx, md, txt, html)', 'Converted document URL or content'),
('document.extract', 'document', 'extract', 'Extract structured data from a document', 'document_url or file, schema? (tables, forms, entities)', 'Structured data extracted from document'),

-- Web search for agents (high demand in agent frameworks, Tavily/Exa top tools)
('search.web_search', 'search', 'web_search', 'Search the web and return structured results', 'query, num_results?, include_content?', 'Ranked web results with titles, URLs, and optional page content')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- CAPABILITY-SERVICE MAPPINGS
-- Note: Services like Tavily, Exa, Serper, CloudConvert need to be
-- added to the services table and scored before mapping here.
-- These capabilities are defined and discoverable now; service
-- mappings will be added when the services are scored.
-- ============================================================
