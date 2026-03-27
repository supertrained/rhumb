# Document-processing discovery expansion — 2026-03-26

Date: 2026-03-26
Operator: Pedro / Keel runtime loop

## Why this category

Document processing is still underrepresented relative to how often agents need to ingest invoices, receipts, IDs, and semi-structured business documents. The catalog had strong generalists (AWS Textract, Google Document AI, Unstructured, LlamaParse, Reducto) but thin coverage across the modern IDP/OCR specialists that product teams actually compare during buying decisions.

## Added services

- `veryfi`
- `mindee`
- `rossum`
- `docparser`
- `parseur`

## Category read

This batch broadens the category across the main design centers inside document extraction:

- **Financial docs / receipts / invoice extraction:** Veryfi
- **API-first OCR + field extraction products:** Mindee, Docparser, Parseur
- **Enterprise intelligent document processing workflow:** Rossum

That gives Rhumb better coverage across developer-friendly extraction APIs and enterprise AP/document automation platforms.

## Phase 0 capability assessment

### Best immediate Resolve candidate: Mindee

Mindee is the cleanest first Resolve target in this batch because its productized extraction APIs already map to agent-meaningful primitives instead of requiring a bespoke schema from scratch.

Recommended first capability set:
- `document.extract_fields` → generic structured field extraction from uploaded docs
- `invoice.extract` → invoice totals, vendors, line items, dates, currencies
- `receipt.extract` → merchant, totals, taxes, payment method, purchase time
- `identity.extract_document` → passport / ID-card / driver-license field extraction where the API supports it

Why Mindee first:
- the API surface is explicit, machine-readable, and already organized around normalized document types
- it offers a practical middle ground between generic OCR and full AP workflow software
- it creates a strong bridge from document parsing into downstream accounting / expense / onboarding workflows agents actually need

### Secondary candidates

- **Veryfi:** strong follow-on for receipts, invoices, and expense workflows
- **Rossum:** compelling later candidate for enterprise invoice/AP automation and human-in-the-loop document operations
- **Docparser / Parseur:** useful for mailbox + parser automation, but more extraction-template oriented than a first normalized Resolve primitive

## Operator takeaway

Document processing is now materially broader, and Mindee stands out as the best immediate Phase 0 next step for a normalized extraction capability in Resolve.
