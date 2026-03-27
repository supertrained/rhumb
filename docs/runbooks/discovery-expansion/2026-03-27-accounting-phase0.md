# Discovery expansion — accounting

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop

## Why this category

Accounting is a high-demand operational category for agents, but Rhumb's current coverage is thin.

I pulled current category counts from the service catalog and found:
- `accounting`: **5** providers
- versus much deeper categories like `payments` (**22**), `analytics` (**28**), `email` (**41**), and `auth` (**43**)

That gap is too wide for a category agents routinely need for:
- invoice and bill workflows
- contact + vendor sync
- reconciliation support
- financial ops read access
- back-office automations that connect CRM, payments, and books

## Added services

### 1. Xero
- Slug: `xero`
- Score: **8.15**
- Execution: **8.40**
- Access readiness: **7.90**
- Why it made the cut:
  - major global accounting API with strong SME adoption
  - clean normalized wedge for invoices, contacts, and bills
  - best immediate Phase 0 candidate in the batch

### 2. Sage Intacct
- Slug: `sage-intacct`
- Score: **7.85**
- Execution: **8.05**
- Access readiness: **7.55**
- Why it made the cut:
  - enterprise accounting depth with mature finance workflows
  - strong long-term fit for bill/invoice/vendor primitives
  - heavier implementation surface than Xero, but strategically important

### 3. FreeAgent
- Slug: `freeagent`
- Score: **7.55**
- Execution: **7.75**
- Access readiness: **7.30**
- Why it made the cut:
  - practical SMB accounting API with solid contacts/invoices surface
  - good fit for freelancer / agency / small-ops automations

### 4. MYOB
- Slug: `myob`
- Score: **7.40**
- Execution: **7.60**
- Access readiness: **7.15**
- Why it made the cut:
  - important APAC accounting platform with real API coverage
  - expands the catalog beyond the current US-heavy accounting stack

### 5. Wave
- Slug: `wave`
- Score: **7.10**
- Execution: **6.95**
- Access readiness: **7.20**
- Why it made the cut:
  - relevant SMB / solo-operator accounting product
  - API surface is lighter and less universal than Xero or Intacct, but still worth catalog coverage

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose usable developer surfaces, but the strongest Resolve candidates are:
1. **Xero**
2. **Sage Intacct**
3. **FreeAgent**
4. **MYOB**

Wave is still useful, but its API posture is less attractive as a first normalized execution target.

### Candidate capability shapes
- `invoice.list`
- `invoice.create`
- `bill.list`
- `contact.list`
- `contact.create`

### Best initial Phase 0 wedge
The cleanest first move is:
- `invoice.list`
- `contact.list`

Why:
- read-first primitives are safer than mutating accounting records
- they have immediate operator value
- they create a strong cross-provider normalization surface
- Xero and FreeAgent especially look viable for an early comparison lane

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0102_accounting_expansion_ii.sql`

## Verdict

Accounting coverage was underweight relative to demand. This batch materially improves Rhumb's accounting discovery surface, and **Xero is now the clearest next Phase 0 accounting candidate** when the capability-expansion lane opens.