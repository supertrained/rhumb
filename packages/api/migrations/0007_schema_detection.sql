-- Round 13 (WU 2.4): Schema change detection

CREATE TABLE IF NOT EXISTS schema_fingerprints (
    id BIGSERIAL PRIMARY KEY,
    service_id BIGINT NOT NULL,
    endpoint TEXT NOT NULL,
    fingerprint_hash TEXT NOT NULL,
    schema_tree JSONB,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(service_id, endpoint)
);

CREATE TABLE IF NOT EXISTS schema_events (
    id BIGSERIAL PRIMARY KEY,
    service_id BIGINT NOT NULL,
    endpoint TEXT NOT NULL,
    fingerprint_hash TEXT NOT NULL,
    change_type TEXT,
    severity TEXT,
    captured_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_schema_events_service FOREIGN KEY (service_id) REFERENCES services(id)
);

CREATE INDEX IF NOT EXISTS idx_schema_events_service_endpoint
    ON schema_events(service_id, endpoint);
CREATE INDEX IF NOT EXISTS idx_schema_events_captured_at
    ON schema_events(captured_at DESC);

CREATE TABLE IF NOT EXISTS schema_alerts (
    id BIGSERIAL PRIMARY KEY,
    service_id BIGINT NOT NULL,
    endpoint TEXT NOT NULL,
    change_detail JSONB,
    severity TEXT,
    alert_sent_at TIMESTAMP WITH TIME ZONE,
    webhook_url TEXT,
    webhook_status INT,
    retry_count INT NOT NULL DEFAULT 0,
    retry_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_schema_alerts_service FOREIGN KEY (service_id) REFERENCES services(id)
);

CREATE INDEX IF NOT EXISTS idx_schema_alerts_service_pending
    ON schema_alerts(service_id)
    WHERE webhook_status IS NULL;
CREATE INDEX IF NOT EXISTS idx_schema_alerts_created_at
    ON schema_alerts(created_at DESC);
