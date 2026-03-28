# Discovery expansion — document processing II

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop

## Why this category

Document processing is still a high-demand operational category for agents, but Rhumb's live catalog depth remains thin relative to how often agents need to ingest business documents.

Current live category counts before this batch:
- `document-processing`: **5** providers
- versus adjacent categories like `pdf-processing`: **6**, `search`: **14**, `workflow-automation`: **12**, and `email`: **34**

That gap matters because agent workflows increasingly need to:
- extract structured data from invoices, receipts, and bank statements
- parse underwriting, onboarding, and AP/AR documents
- normalize OCR-heavy business inputs into downstream automations
- bridge unstructured files into CRM, ERP, accounting, and compliance systems

## Added services

### 1. Mindee
- Slug: `mindee`
- Score: **8.35**
- Execution: **8.55**
- Access readiness: **8.10**
- Why it made the cut:
  - clean API posture with prebuilt document models and custom extraction paths
  - strongest immediate Phase 0 candidate in the batch
  - especially strong for invoice, receipt, and ID-style extraction contracts

### 2. Rossum
- Slug: `rossum`
- Score: **8.20**
- Execution: **8.40**
- Access readiness: **7.95**
- Why it made the cut:
  - mature enterprise document-automation API with ingestion + validation flows
  - valuable catalog depth for invoice-centric and operations-heavy document pipelines

### 3. Veryfi
- Slug: `veryfi`
- Score: **8.10**
- Execution: **8.25**
- Access readiness: **7.95**
- Why it made the cut:
  - clear bookkeeping-oriented extraction surface for receipts, invoices, and statements
  - strong fit for finance and operations agents that need structured outputs fast

### 4. Docsumo
- Slug: `docsumo`
- Score: **7.95**
- Execution: **8.10**
- Access readiness: **7.75**
- Why it made the cut:
  - real intelligent-document-processing API with extraction plus workflow rails
  - broadens the category beyond generic parsers and cloud hyperscaler OCR

## Phase 0 capability assessment

### Services with accessible APIs
All four added services expose accessible API surfaces.

The strongest Resolve candidates are:
1. **Mindee**
2. **Veryfi**
3. **Rossum**

Docsumo is also a credible future target, but its workflow-heavy posture makes it a slightly less surgical first normalization wedge than Mindee or Veryfi.

### Candidate capability shapes
- `document.extract_fields`
- `invoice.extract`
- `receipt.extract`
- `id_document.extract`
- `document.classify`

### Best initial Phase 0 wedge
The cleanest first move is:
- `document.extract_fields`
- `invoice.extract`

Why:
- they are immediately valuable across AP, underwriting, and document-ops workflows
- they map cleanly onto real provider APIs without inventing a fake universal workflow abstraction first
- they keep Rhumb focused on the honest, reusable normalization layer: upload document → extract structured fields → return provider-backed outputs
- **Mindee** looks like the best first implementation target because its docs and prebuilt extraction models appear easiest to normalize without bluffing over provider-specific details

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0112_document_processing_expansion_ii.sql`

## Verdict

Document processing remains underweight relative to demand. This batch improves Rhumb's discovery surface materially, and **Mindee is now the clearest next Phase 0 candidate** if the company wants to deepen structured document extraction beyond the current parser-heavy mix.
