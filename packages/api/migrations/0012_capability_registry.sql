-- Migration: 0012_capability_registry
-- Description: Capability registry — maps agent capabilities to services
-- Date: 2026-03-16
-- Depends: existing services + scores tables

-- Capability definitions
CREATE TABLE IF NOT EXISTS capabilities (
    id TEXT PRIMARY KEY,                    -- e.g. "email.send"
    domain TEXT NOT NULL,                   -- e.g. "email"
    action TEXT NOT NULL,                   -- e.g. "send"
    description TEXT NOT NULL,
    input_hint TEXT,                        -- what the agent should provide
    outcome TEXT,                           -- what success looks like
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(domain, action)
);

-- Capability-to-service mappings
CREATE TABLE IF NOT EXISTS capability_services (
    capability_id TEXT NOT NULL REFERENCES capabilities(id) ON DELETE CASCADE,
    service_slug TEXT NOT NULL,             -- references services(slug)
    credential_modes TEXT[] NOT NULL DEFAULT '{byo}',
    auth_method TEXT,                       -- api_key, oauth2, basic, etc.
    endpoint_pattern TEXT,                  -- primary endpoint for this capability
    cost_per_call NUMERIC,                 -- estimated cost in USD (NULL = free tier)
    cost_currency TEXT DEFAULT 'USD',
    free_tier_calls INTEGER,               -- monthly free tier if any
    notes TEXT,
    is_primary BOOLEAN DEFAULT true,       -- primary capability for this service?
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (capability_id, service_slug)
);

-- Capability bundles (compound capabilities)
CREATE TABLE IF NOT EXISTS capability_bundles (
    id TEXT PRIMARY KEY,                   -- e.g. "prospect.enrich_and_verify"
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    example TEXT,
    value_proposition TEXT,                -- why the bundle > individual capabilities
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Bundle-to-capability mappings
CREATE TABLE IF NOT EXISTS bundle_capabilities (
    bundle_id TEXT NOT NULL REFERENCES capability_bundles(id) ON DELETE CASCADE,
    capability_id TEXT NOT NULL REFERENCES capabilities(id) ON DELETE CASCADE,
    sequence_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bundle_id, capability_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_capabilities_domain ON capabilities(domain);
CREATE INDEX IF NOT EXISTS idx_capability_services_slug ON capability_services(service_slug);
CREATE INDEX IF NOT EXISTS idx_capability_services_mode ON capability_services USING gin(credential_modes);
CREATE INDEX IF NOT EXISTS idx_bundle_capabilities_cap ON bundle_capabilities(capability_id);

-- RLS
ALTER TABLE capabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE capability_services ENABLE ROW LEVEL SECURITY;
ALTER TABLE capability_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE bundle_capabilities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "capabilities_read" ON capabilities FOR SELECT USING (true);
CREATE POLICY "capability_services_read" ON capability_services FOR SELECT USING (true);
CREATE POLICY "capability_bundles_read" ON capability_bundles FOR SELECT USING (true);
CREATE POLICY "bundle_capabilities_read" ON bundle_capabilities FOR SELECT USING (true);
