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
```

`rhumb score` supports v0.2 dual-score output:
- aggregate recommendation (`score` / `aggregate_recommendation_score`)
- execution score (`execution_score`)
- access readiness score (`access_readiness_score`)
