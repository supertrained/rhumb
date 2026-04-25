# DC90 Month 1 Measurement Run Scaffold

Date created: 2026-04-25
Owner: Beacon
Review: Keel for Rhumb-mentioned rows; Pedro keeps the source files; Helm only if execution examples are evaluated.

This folder is the Month 1 artifact shape for the DC90 visibility measurement run. It is intentionally blank: no public-improvement claim exists until the 75 rows are collected and reviewed.

## Selected surfaces

Use the same five labels as the Month 0 baseline so Month 1 can compare against the 0/75 starting point:

| Surface | Capture mode |
|---|---|
| `GPT-4` | ChatGPT / GPT-4 answer surface with web retrieval enabled when available. |
| `Claude` | Claude answer surface with web search / citations enabled when available. |
| `Perplexity` | Perplexity answer surface, default web answer mode. |
| `Gemini` | Gemini answer surface with Google-grounded retrieval enabled when available. |
| `Copilot` | Microsoft Copilot answer surface, default web answer mode. |

If a product UI forces a different mode, record the exact mode in `surface_mode` and explain it in `run_notes.md` before scoring.

## Files in this folder

- `scorecard.csv` — all 15 queries × 5 selected surfaces, pre-expanded to 75 rows.
- `scorecard.schema.json` — machine-readable schema for the CSV columns and allowed values.
- `run_notes.md` — run metadata, drift checks, and review status.
- `raw-artifacts/` — raw transcript, screenshot, or export files. Summaries without raw artifacts do not count.

## Raw artifact naming

Store each row's primary artifact at:

```text
raw-artifacts/<query_id>__<surface>__YYYYMMDDTHHMMSSZ.<ext>
```

Examples:

```text
raw-artifacts/Q14__Perplexity__20260515T174200Z.md
raw-artifacts/Q14__Perplexity__20260515T174200Z.png
raw-artifacts/Q14__Perplexity__20260515T174200Z.json
```

Rules:

1. Keep the exact prompt/query text visible in the artifact.
2. Preserve citations/URLs exactly as the surface returned them.
3. If the system gives multiple modes, capture the mode in `surface_mode`.
4. If no result is returned, still save the empty/error artifact and score the row honestly.
5. Do not overwrite artifacts; reruns get a new timestamp and a note.

## Claim boundary

Until Keel reviews the Rhumb-mentioned rows, the only safe public statement is: “Month 1 measurement is in progress.” Do not claim improved recommendation rate, MEO, Resolve retrieval, or citation quality from partial rows.
