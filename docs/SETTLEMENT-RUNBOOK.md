# USDC Settlement Runbook (Phase 1 — Manual)

## Overview

Phase 1 settlement is semi-manual. USDC receipts are batched daily and Pedro
manually initiates the Coinbase conversion. Phase 2 will automate conversion
via the Coinbase API.

## Daily Process (02:00 UTC)

1. Settlement batch auto-created via cron/heartbeat (`POST /v1/admin/settlement/run`)
2. Pedro reviews pending batches: `GET /v1/admin/settlement/pending`
3. Pedro initiates Coinbase conversion manually (on coinbase.com)
4. Pedro marks batch converted: `POST /v1/admin/settlement/{id}/converted`

## API Endpoints

All endpoints require admin auth (`X-Rhumb-Admin-Key` header).

### Create Settlement Batch

```
POST /v1/admin/settlement/run?batch_date=2026-03-17
```

- `batch_date` is optional; defaults to yesterday (UTC)
- Idempotent: returns `{"status": "skipped"}` if batch already exists for that date
- Returns `{"status": "skipped"}` if no unsettled receipts for the date

### List Pending Batches

```
GET /v1/admin/settlement/pending
```

Returns all batches with `status=pending` (not yet converted to USD).

### Mark Batch Converted

```
POST /v1/admin/settlement/{batch_id}/converted
Content-Type: application/json

{
  "total_usd_cents": 15000,
  "coinbase_conversion_id": "cb_conv_abc123"
}
```

- `total_usd_cents` is required (the actual USD amount received after conversion)
- `coinbase_conversion_id` is optional in Phase 1

## Escalation

- If batch total > $1,000 USDC, notify Tom before converting
- If Coinbase conversion fails or is delayed > 24h, flag for manual review

## Troubleshooting

- **Batch not created?** Check that receipts exist for the date with `settled=false`
  and `confirmed_at` within the date range
- **Duplicate batch?** Batch creation is idempotent on `batch_date` — second call
  returns `skipped`
- **Receipts not linked?** Each receipt PATCH is independent; check individual
  receipt `settlement_batch_id` values
