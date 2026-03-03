SHELL := /bin/bash

.PHONY: dev test lint types build db-migrate

dev:
	@echo "Starting local infra (db + redis)..."
	docker compose up -d db redis
	@echo "Run API: cd packages/api && uvicorn main:app --reload --port 8000"
	@echo "Run Web: cd packages/web && npm run dev"

test:
	cd packages/api && pytest
	cd packages/cli && pytest
	cd packages/web && npm test

lint:
	cd packages/api && black --check . && ruff check .
	cd packages/cli && black --check . && ruff check .
	cd packages/web && npm run lint

types:
	cd packages/api && mypy .
	cd packages/cli && mypy .
	cd packages/web && npm run type-check

build:
	cd packages/web && npm run build

db-migrate:
	psql postgresql://postgres:postgres@localhost:54322/postgres -f supabase/migrations/0001_init.sql
