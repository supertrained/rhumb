# Architecture

## Scoring Service Design

`packages/api/services/scoring.py` is the core AN Score engine.

### Responsibilities

1. **Composite score calculation**
   - 17 dimensions (`I1-I7`, `F1-F7`, `O1-O3`)
   - weighted composite with proportional redistribution for N/A dimensions
   - one-decimal final score

2. **Confidence model**
   - evidence count signal
   - freshness decay signal (minutes → days)
   - probe diversity signal (+ production telemetry bonus)

3. **Tier assignment**
   - `L1`: `< 4.0`
   - `L2`: `4.0 - 5.99`
   - `L3`: `6.0 - 7.99`
   - `L4`: `>= 8.0`

4. **Contextual explanation generation**
   - default deterministic explanation from strongest/weakest dimensions
   - optional Claude Sonnet generation via Anthropic API (`ANTHROPIC_API_KEY`)
   - normalized to single sentence and max char length (`score_explanation_max_chars`)

5. **Persistence + retrieval**
   - repository abstraction (`ScoreRepository`)
   - SQLAlchemy implementation writes to `services` + `an_scores`
   - in-memory fallback for tests/dev resilience

### API Integration

- `POST /v1/score`: computes, persists, returns full score schema
- `GET /v1/services/{slug}/score`: fetch latest score (or bootstrap from hand-scored fixtures)

### CLI Integration

`rhumb score <service>` reads `GET /v1/services/{slug}/score` and renders:
- selected headline mode (`--mode aggregate|execution|access`)
- aggregate recommendation + execution + access readiness lines
- confidence label
- explanation sentence
- category bars
- optional dimension breakdown (`--dimensions`)
- raw payload (`--json`)

`rhumb find <query>` reads `GET /v1/search` and renders:
- ranked service matches with score/tier/confidence
- optional rationale lines (`why`/`reason`/`explanation`)
- raw payload (`--json`)
- result limit control (`--limit`)
