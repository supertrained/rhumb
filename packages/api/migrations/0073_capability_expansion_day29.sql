-- Migration 0073: Capability Expansion Day 29
-- Domains: print, iot, database, storage_object
-- New capabilities: 10
-- New mappings: ~36
-- Cumulative target: ~341 capabilities / ~1183 mappings

-- ============================================================
-- DOMAIN: print (Print-on-Demand)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('print.create_order', 'print.create_order', 'print', 'Place a print-on-demand order for a physical product', '{"type":"object","required":["product_id","variant_id","recipient"],"properties":{"product_id":{"type":"string"},"variant_id":{"type":"string"},"quantity":{"type":"integer","default":1},"print_files":{"type":"array","items":{"type":"object","properties":{"placement":{"type":"string"},"url":{"type":"string"}}}},"recipient":{"type":"object","required":["name","address1","city","country_code"],"properties":{"name":{"type":"string"},"email":{"type":"string"},"address1":{"type":"string"},"address2":{"type":"string"},"city":{"type":"string"},"state":{"type":"string"},"zip":{"type":"string"},"country_code":{"type":"string"}}}}}', '{"type":"object","properties":{"order_id":{"type":"string"},"status":{"type":"string"},"estimated_fulfillment_days":{"type":"integer"}}}'),
  ('print.get_status', 'print.get_status', 'print', 'Get the fulfillment and shipping status of a print-on-demand order', '{"type":"object","required":["order_id"],"properties":{"order_id":{"type":"string"}}}', '{"type":"object","properties":{"order_id":{"type":"string"},"status":{"type":"string","enum":["pending","in_production","fulfilled","shipped","cancelled"]},"tracking_number":{"type":"string"},"carrier":{"type":"string"},"shipped_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- print.create_order
  ('print.create_order', 'printful', 'byo', 0.005, 8.1, true),
  ('print.create_order', 'printify', 'byo', 0.004, 7.8, false),
  ('print.create_order', 'gooten', 'byo', 0.005, 7.5, false),
  ('print.create_order', 'gelato', 'byo', 0.005, 7.7, false),
  -- print.get_status
  ('print.get_status', 'printful', 'byo', 0.002, 8.1, true),
  ('print.get_status', 'printify', 'byo', 0.002, 7.8, false),
  ('print.get_status', 'gelato', 'byo', 0.002, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: iot (IoT Device Control & Telemetry)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('iot.get_device_state', 'iot.get_device_state', 'iot', 'Retrieve the current state and telemetry of an IoT device', '{"type":"object","required":["device_id"],"properties":{"device_id":{"type":"string"},"fields":{"type":"array","description":"Specific telemetry fields to retrieve; omit for all"}}}', '{"type":"object","properties":{"device_id":{"type":"string"},"state":{"type":"object","description":"Current device shadow or reported state"},"connected":{"type":"boolean"},"last_seen":{"type":"string"}}}'),
  ('iot.send_command', 'iot.send_command', 'iot', 'Send a command or desired state update to an IoT device', '{"type":"object","required":["device_id","command"],"properties":{"device_id":{"type":"string"},"command":{"type":"string"},"payload":{"type":"object"},"timeout_sec":{"type":"integer","default":30},"qos":{"type":"integer","enum":[0,1,2],"default":1}}}', '{"type":"object","properties":{"message_id":{"type":"string"},"delivered":{"type":"boolean"},"acknowledged":{"type":"boolean"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- iot.get_device_state
  ('iot.get_device_state', 'aws-iot', 'byo', 0.003, 8.2, true),
  ('iot.get_device_state', 'azure-iot-hub', 'byo', 0.003, 8.1, false),
  ('iot.get_device_state', 'google-iot', 'byo', 0.003, 7.8, false),
  ('iot.get_device_state', 'particle', 'byo', 0.002, 7.5, false),
  -- iot.send_command
  ('iot.send_command', 'aws-iot', 'byo', 0.004, 8.2, true),
  ('iot.send_command', 'azure-iot-hub', 'byo', 0.004, 8.1, false),
  ('iot.send_command', 'particle', 'byo', 0.003, 7.5, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: database (Serverless Database Queries)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('database.query', 'database.query', 'database', 'Execute a read-only SQL query against a serverless database', '{"type":"object","required":["connection_id","sql"],"properties":{"connection_id":{"type":"string"},"sql":{"type":"string"},"params":{"type":"array","description":"Positional query parameters"},"limit":{"type":"integer","default":100}}}', '{"type":"object","properties":{"rows":{"type":"array"},"row_count":{"type":"integer"},"columns":{"type":"array"},"latency_ms":{"type":"integer"}}}'),
  ('database.execute', 'database.execute', 'database', 'Execute a write SQL statement (INSERT, UPDATE, DELETE) against a serverless database', '{"type":"object","required":["connection_id","sql"],"properties":{"connection_id":{"type":"string"},"sql":{"type":"string"},"params":{"type":"array"}}}', '{"type":"object","properties":{"rows_affected":{"type":"integer"},"last_insert_id":{"type":"string"},"latency_ms":{"type":"integer"}}}'),
  ('database.get_schema', 'database.get_schema', 'database', 'Retrieve the table and column schema for a database connection', '{"type":"object","required":["connection_id"],"properties":{"connection_id":{"type":"string"},"table":{"type":"string","description":"Specific table; omit for all tables"}}}', '{"type":"object","properties":{"tables":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string"},"columns":{"type":"array"}}}}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- database.query
  ('database.query', 'neon', 'byo', 0.003, 8.2, true),
  ('database.query', 'supabase', 'byo', 0.003, 8.1, false),
  ('database.query', 'planetscale', 'byo', 0.004, 8.0, false),
  ('database.query', 'turso', 'byo', 0.002, 7.8, false),
  -- database.execute
  ('database.execute', 'neon', 'byo', 0.004, 8.2, true),
  ('database.execute', 'supabase', 'byo', 0.004, 8.1, false),
  ('database.execute', 'planetscale', 'byo', 0.005, 8.0, false),
  ('database.execute', 'turso', 'byo', 0.003, 7.8, false),
  -- database.get_schema
  ('database.get_schema', 'neon', 'byo', 0.002, 8.2, true),
  ('database.get_schema', 'supabase', 'byo', 0.002, 8.1, false),
  ('database.get_schema', 'turso', 'byo', 0.002, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: storage_object (Object Storage)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('storage_object.put', 'storage_object.put', 'storage_object', 'Upload or overwrite an object in a storage bucket', '{"type":"object","required":["bucket","key","source_url"],"properties":{"bucket":{"type":"string"},"key":{"type":"string"},"source_url":{"type":"string"},"content_type":{"type":"string"},"metadata":{"type":"object"},"public":{"type":"boolean","default":false}}}', '{"type":"object","properties":{"key":{"type":"string"},"url":{"type":"string"},"etag":{"type":"string"},"bytes":{"type":"integer"}}}'),
  ('storage_object.get', 'storage_object.get', 'storage_object', 'Retrieve an object or generate a pre-signed download URL', '{"type":"object","required":["bucket","key"],"properties":{"bucket":{"type":"string"},"key":{"type":"string"},"signed_url":{"type":"boolean","default":false},"expiry_seconds":{"type":"integer","default":3600}}}', '{"type":"object","properties":{"url":{"type":"string"},"content_type":{"type":"string"},"bytes":{"type":"integer"},"expires_at":{"type":"string"}}}'),
  ('storage_object.delete', 'storage_object.delete', 'storage_object', 'Delete an object or list of objects from a storage bucket', '{"type":"object","required":["bucket","keys"],"properties":{"bucket":{"type":"string"},"keys":{"type":"array","items":{"type":"string"}}}}', '{"type":"object","properties":{"deleted":{"type":"integer"},"errors":{"type":"array"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- storage_object.put
  ('storage_object.put', 'aws-s3', 'byo', 0.002, 8.5, true),
  ('storage_object.put', 'cloudflare-r2', 'byo', 0.001, 8.2, false),
  ('storage_object.put', 'google-gcs', 'byo', 0.002, 8.3, false),
  ('storage_object.put', 'backblaze-b2', 'byo', 0.001, 7.8, false),
  -- storage_object.get
  ('storage_object.get', 'aws-s3', 'byo', 0.001, 8.5, true),
  ('storage_object.get', 'cloudflare-r2', 'byo', 0.001, 8.2, false),
  ('storage_object.get', 'google-gcs', 'byo', 0.001, 8.3, false),
  -- storage_object.delete
  ('storage_object.delete', 'aws-s3', 'byo', 0.001, 8.5, true),
  ('storage_object.delete', 'cloudflare-r2', 'byo', 0.001, 8.2, false),
  ('storage_object.delete', 'google-gcs', 'byo', 0.001, 8.3, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
