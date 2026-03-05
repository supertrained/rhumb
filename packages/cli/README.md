# rhumb-cli

Typer-based CLI scaffold for Rhumb.

## Install (editable)

```bash
pip install -e .[dev]
```

## Usage

```bash
rhumb --help
rhumb score stripe
rhumb score stripe --mode execution
rhumb score stripe --mode access --dimensions
rhumb score stripe --json
rhumb find "payment routing"
rhumb find "payment routing" --limit 5 --json
```

`rhumb score` supports v0.2 dual-score output:
- aggregate recommendation (`score` / `aggregate_recommendation_score`)
- execution score (`execution_score`)
- access readiness score (`access_readiness_score`)

`rhumb find` queries `GET /v1/search` and supports:
- human-ranked output (default)
- raw payload output (`--json`)
- result caps (`--limit`)
