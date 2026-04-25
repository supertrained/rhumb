# DC90 Month 1 Measurement Setup

Date: 2026-04-25
Owner: Beacon
Review gates: Keel reviews all Rhumb-mentioned rows before public claims; Pedro maintains the scaffold.

This setup turns the DC90 measurement protocol into an executable Month 1 run shape. It does **not** claim any visibility improvement.

## Selected Month 1 surfaces

To preserve comparability with the Month 0 baseline, Month 1 uses the same five retrieval/answer labels:

1. `GPT-4`
2. `Claude`
3. `Perplexity`
4. `Gemini`
5. `Copilot`

The runner must record the exact UI/model/retrieval mode in `surface_mode` for every row because the product labels can map to different backends over time.

## Query and artifact shape

- Query set: Q1–Q15 from `docs/DC90-RESOLVE-CONTENT-MEASUREMENT-PACK-2026-04-25.md`.
- Scorecard: `docs/dc90-measurement/month1-2026-04/scorecard.csv` contains all 75 query × surface rows.
- Raw artifacts: `docs/dc90-measurement/month1-2026-04/raw-artifacts/`.
- Artifact naming: `<query_id>__<surface>__YYYYMMDDTHHMMSSZ.<ext>`.
- Run notes and drift checks: `docs/dc90-measurement/month1-2026-04/run_notes.md`.

## Scoring readiness

The CSV pre-expands the scoring columns needed for the Month 1 rollup:

- Rhumb mention and Resolve mention
- Citation URL and citation type
- Entity accuracy, claim accuracy, and actionability on 0–3 scales
- Competitors named and Composio pressure
- Keel review state
- Notes with exact quotes / artifact pointers

## Acceptance boundary

Beacon can call Month 1 complete only when all 75 rows have artifacts, Keel has reviewed every Rhumb-mentioned row, and any public improvement claim is explicitly tied to the fresh artifacts. Partial results stay internal diagnostics.
