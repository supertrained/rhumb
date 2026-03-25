# Discovery expansion — accounting (2026-03-25)

## Why this category

Accounting was effectively absent as a first-class category despite being one of the highest-demand operational surfaces for real agent work.

At run time, the catalog had **0 dedicated `accounting` services**. Some adjacent finance tools existed under `fintech`, but that does not cover the practical agent workflows developers actually need: invoices, bills, customers, vendors, payments, chart-of-accounts, reimbursements, and bookkeeping sync.

That made accounting the cleanest underrepresented category to expand this run.

## Services added

Added 5 services with initial AN scoring:
- QuickBooks
- FreshBooks
- BILL
- Zoho Books
- NetSuite

## Initial score posture

Practical launch posture:
- **QuickBooks** — `7.1` aggregate, `L3 / Ready`
- **FreshBooks** — `6.9` aggregate, `L3 / Ready`
- **BILL** — `7.2` aggregate, `L3 / Ready`
- **Zoho Books** — `7.0` aggregate, `L3 / Ready`
- **NetSuite** — `6.3` aggregate, `L4 / Established`

Interpretation:
- QuickBooks, BILL, and Zoho Books look like the strongest near-term agent integrations
- FreshBooks is solid for SMB invoicing/time-billing workflows
- NetSuite matters strategically because of enterprise demand, but integration friction is materially higher

## Phase 0 Resolve assessment

Strongest immediate Resolve-fit services:
- **QuickBooks** — broad accounting objects, clear developer docs, high demand for invoice/customer/reporting actions
- **BILL** — strong AP/AR, vendor, bill, payment, reimbursement, and webhook surfaces
- **Zoho Books** — broad REST surface with explicit org-scoped bookkeeping resources

Secondary candidate:
- **FreshBooks** — viable for invoices, clients, and payments, but narrower overall surface than QuickBooks/BILL

Lower-priority candidate:
- **NetSuite** — strategically important, but should wait until the cleaner REST/OAuth-style finance providers are mapped first

## Recommended Phase 0 capability fit

This category does **not** need a brand-new accounting mega-capability first. The right move is widening provider coverage around practical action surfaces such as:
- `invoice.create`
- `invoice.list`
- `invoice.get`
- `customer.list`
- `customer.get`
- `bill.list`
- `vendor.list`
- `payment.create`
- `expense.list`

## Recommendation

Next accounting Phase 0 pass should:
1. map **QuickBooks** first for invoice/customer/reporting primitives
2. map **BILL** second for AP/AR and vendor/payment flows
3. map **Zoho Books** third for broad SMB accounting coverage
4. hold **FreshBooks** as a follow-on SMB invoicing addition
5. defer **NetSuite** until the cleaner providers are live and well-tested
