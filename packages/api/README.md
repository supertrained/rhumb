# rhumb-api

FastAPI backend scaffold for Rhumb.

## Run

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn main:app --reload --port 8000
```

## Test

```bash
pytest
```
