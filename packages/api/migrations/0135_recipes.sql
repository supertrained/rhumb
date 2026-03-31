-- WU-42.1: Recipe execution engine — recipe definitions and executions
--
-- Layer 3 core tables for compiled recipe storage and execution tracking.

-- Recipe definitions (compiled, immutable once published)
CREATE TABLE IF NOT EXISTS recipes (
    recipe_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    version         TEXT NOT NULL DEFAULT '1.0.0',
    category        TEXT NOT NULL DEFAULT '',
    stability       TEXT NOT NULL DEFAULT 'beta',
    tier            TEXT NOT NULL DEFAULT 'premium',
    definition      JSONB NOT NULL,  -- Full compiled recipe definition
    inputs_schema   JSONB,
    outputs_schema  JSONB,
    step_count      INTEGER NOT NULL DEFAULT 0,
    max_total_cost_usd REAL NOT NULL DEFAULT 10.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published       BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_recipes_category ON recipes (category);
CREATE INDEX IF NOT EXISTS idx_recipes_stability ON recipes (stability, published);

-- Recipe executions (one per run)
CREATE TABLE IF NOT EXISTS recipe_executions (
    execution_id    TEXT PRIMARY KEY,
    recipe_id       TEXT NOT NULL REFERENCES recipes(recipe_id),
    status          TEXT NOT NULL DEFAULT 'validating',
    inputs          JSONB,
    total_cost_usd  REAL NOT NULL DEFAULT 0.0,
    total_duration_ms INTEGER NOT NULL DEFAULT 0,
    step_count      INTEGER NOT NULL DEFAULT 0,
    steps_completed INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    org_id          TEXT,
    agent_id        TEXT,
    credential_mode TEXT NOT NULL DEFAULT 'rhumb_managed'
);

CREATE INDEX IF NOT EXISTS idx_recipe_executions_recipe ON recipe_executions (recipe_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_recipe_executions_status ON recipe_executions (status);
CREATE INDEX IF NOT EXISTS idx_recipe_executions_org ON recipe_executions (org_id, started_at DESC);

-- Recipe step executions (one per step per run)
CREATE TABLE IF NOT EXISTS recipe_step_executions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id    TEXT NOT NULL REFERENCES recipe_executions(execution_id),
    step_id         TEXT NOT NULL,
    capability_id   TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    cost_usd        REAL NOT NULL DEFAULT 0.0,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    receipt_id      TEXT,
    provider_used   TEXT,
    retries_used    INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    outputs         JSONB,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_recipe_step_executions_exec ON recipe_step_executions (execution_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_recipe_step_executions_unique ON recipe_step_executions (execution_id, step_id);

COMMENT ON TABLE recipes IS 'Compiled recipe definitions for Layer 3 deterministic composition. Immutable once published.';
COMMENT ON TABLE recipe_executions IS 'Recipe execution tracking — one row per recipe run.';
COMMENT ON TABLE recipe_step_executions IS 'Per-step execution tracking within a recipe run.';
