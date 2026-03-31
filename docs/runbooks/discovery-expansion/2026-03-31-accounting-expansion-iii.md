# Discovery expansion — accounting III

Date: 2026-03-31
Owner: Pedro / Keel runtime review loop

## Why this category

Live production catalog depth for `accounting` is still only **5** providers:
- `bill`
- `freshbooks`
- `netsuite`
- `quickbooks`
- `zoho-books`

That is still too thin for a high-demand operational category agents repeatedly need for:
- listing invoices and outstanding balances
- reading customer and vendor records
- reviewing bills, expenses, and payment status
- reconciling finance data across CRM, payroll, and banking systems
- generating bookkeeping support workflows and operator summaries
- powering invoice-aware, budget-aware, and revenue-adjacent automation

So the honest Mission 2 move was to deepen accounting instead of inventing another shallow category.

## Added services

### 1. FreeAgent
- Slug: `freeagent`
- Score: **8.15**
- Execution: **8.25**
- Access readiness: **8.00**
- Why it made the cut:
  - clean API surface for contacts, invoices, bills, bank transactions, projects, and expenses
  - strongest immediate Phase 0 target in the batch for read-first accounting workflows

### 2. Sage Intacct
- Slug: `sage-intacct`
- Score: **8.10**
- Execution: **8.20**
- Access readiness: **7.95**
- Why it made the cut:
  - broad finance-system coverage across AP, AR, GL, vendors, customers, and purchasing
  - strategically important enterprise accounting anchor for future Resolve depth

### 3. Microsoft Dynamics 365 Business Central
- Slug: `business-central`
- Score: **8.05**
- Execution: **8.15**
- Access readiness: **7.90**
- Why it made the cut:
  - explicit API objects for customers, vendors, invoices, journals, and companies
  - important mid-market ERP/accounting bridge with strong operator relevance

### 4. MYOB
- Slug: `myob`
- Score: **7.85**
- Execution: **7.95**
- Access readiness: **7.70**
- Why it made the cut:
  - practical SMB accounting API for contacts, invoices, bills, tax codes, and accounts
  - broadens the category beyond US-first finance stacks

### 5. Odoo Accounting
- Slug: `odoo-accounting`
- Score: **7.75**
- Execution: **7.85**
- Access readiness: **7.60**
- Why it made the cut:
  - broad partner, invoice, payment, and journal-entry surface through Odoo's external APIs
  - useful ERP-adjacent depth for finance automation and internal-tool workflows

## Phase 0 capability assessment

All five additions expose accessible APIs and are viable Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **FreeAgent**
2. **Business Central**
3. **Sage Intacct**
4. **MYOB**

### Candidate capability shapes
- `invoice.list`
- `invoice.read`
- `customer.list`
- `vendor.list`
- `bill.list`
- `payment.list`

### Best initial Phase 0 wedge
The cleanest first move is:
- `invoice.list`
- `invoice.read`
- `customer.list`
- `bill.list`

Why:
- these are common cross-provider finance reads with obvious operator value
- they normalize cleanly before taking on multi-step write flows
- they support agent workflows around collections, reconciliation, procurement, and status reporting
- **FreeAgent** is the best first provider target because it exposes explicit invoice/contact/bill primitives without the heaviest enterprise setup friction

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0131_accounting_expansion_iii.sql`

## Verdict

Accounting was still underweight in the live catalog. This batch adds five more real API-backed providers and sharpens the next honest Resolve wedge around **invoice/customer/bill reads**, with **FreeAgent** as the clearest first provider target.
