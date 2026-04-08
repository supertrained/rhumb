-- AUD-18 Wave 1: Database read capabilities seed
-- Adds db.query.read, db.schema.describe, db.row.get to the capability registry.
-- These capabilities execute directly against PostgreSQL via connection_ref,
-- not through the proxy layer.
-- Date: 2026-04-07

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
(
    'db.query.read',
    'database',
    'query_read',
    'Execute a read-only SQL query against a PostgreSQL database',
    'connection_ref, query (SELECT only), params (optional), max_rows, timeout_ms',
    'Query results: column metadata + rows, bounded by row limit and timeout'
),
(
    'db.schema.describe',
    'database',
    'schema_describe',
    'Describe the schema of a PostgreSQL database (tables, columns, relationships)',
    'connection_ref, schemas (default: public), tables (optional), include_relationships',
    'Schema metadata: table names, column types, nullable flags, foreign keys'
),
(
    'db.row.get',
    'database',
    'row_get',
    'Get specific rows from a PostgreSQL table by filters',
    'connection_ref, table, schema (default: public), filters, columns, limit, order_by',
    'Matching rows with selected columns, bounded by row limit'
)
ON CONFLICT (id) DO UPDATE SET
    domain = EXCLUDED.domain,
    action = EXCLUDED.action,
    description = EXCLUDED.description,
    input_hint = EXCLUDED.input_hint,
    outcome = EXCLUDED.outcome;

-- DB capabilities use direct PostgreSQL connections, not the capability_services
-- proxy mapping.  The provider is "postgresql" (the agent's own database).
-- No capability_services rows needed — the execute path resolves connection_ref
-- to a DSN via environment variables.
