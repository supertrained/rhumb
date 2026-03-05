# AN v0.2 Calibration & Rank-Delta Verification

This artifact locks the 20-service calibration set used for Slice 5 validation.


## Validation commands
```bash
.venv/bin/pytest packages/api/tests/test_scoring_engine.py -q
.venv/bin/pytest packages/api/tests -q
```

## Calibration table (Execution + Access -> Aggregate)

| Service | Execution | Access | Aggregate (raw) | Aggregate (rounded) | Exec Rank | v0.2 Rank | Shift |
|---|---:|---:|---:|---:|---:|---:|---:|
| stripe | 8.9 | 6.59 | 8.21 | 8.2 | 1 | 1 | +0 |
| resend | 8.6 | 6.83 | 8.07 | 8.1 | 2 | 2 | +0 |
| supabase | 8.1 | 7.55 | 7.93 | 7.9 | 6 | 3 | +3 |
| linear | 8.4 | 6.74 | 7.90 | 7.9 | 3 | 4 | -1 |
| cloudflare-workers | 8.3 | 6.74 | 7.83 | 7.8 | 4 | 5 | -1 |
| anthropic | 8.1 | 7.02 | 7.78 | 7.8 | 5 | 6 | -1 |
| openai | 7.9 | 7.33 | 7.73 | 7.7 | 10 | 7 | +3 |
| cal-com | 8.0 | 7.05 | 7.71 | 7.7 | 9 | 8 | +1 |
| github | 8.0 | 6.32 | 7.50 | 7.5 | 8 | 9 | -1 |
| vercel | 7.8 | 6.74 | 7.48 | 7.5 | 11 | 10 | +1 |
| postmark | 8.1 | 5.71 | 7.38 | 7.4 | 7 | 11 | -4 |
| hunter | 7.5 | 6.38 | 7.16 | 7.2 | 13 | 12 | +1 |
| twilio | 7.6 | 5.61 | 7.00 | 7.0 | 12 | 13 | -1 |
| sendgrid | 7.4 | 5.31 | 6.77 | 6.8 | 14 | 14 | +0 |
| slack | 7.2 | 5.10 | 6.57 | 6.6 | 15 | 15 | +0 |
| airtable | 6.9 | 5.79 | 6.57 | 6.6 | 16 | 16 | +0 |
| notion | 6.7 | 5.48 | 6.33 | 6.3 | 17 | 17 | +0 |
| peopledatalabs | 6.6 | 4.79 | 6.06 | 6.1 | 18 | 18 | +0 |
| apollo | 6.3 | 4.41 | 5.73 | 5.7 | 19 | 19 | +0 |
| hubspot | 5.4 | 3.49 | 4.83 | 4.8 | 20 | 20 | +0 |

## High-signal checks
- Largest positive movers: `supabase` (+3), `openai` (+3)
- Largest negative mover: `postmark` (-4)
- Access guardrail risk case: `hubspot` access=3.49 (<4.0)
- Probe confidence wiring verified in tests for both probe freshness and probe latency telemetry inputs.
