-- AUD-18 Wave 1b: AWS S3 read capabilities seed
-- Mirror of packages/api/migrations/0161_object_storage_read_capabilities_seed.sql
-- Date: 2026-04-08

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
(
    'object.list',
    'object',
    'list',
    'List objects in an allowlisted AWS S3 bucket or prefix',
    'storage_ref, bucket, prefix (optional), continuation_token (optional), max_keys',
    'Object metadata list: key, size, etag, last_modified, storage_class, truncation cursor'
),
(
    'object.head',
    'object',
    'head',
    'Fetch metadata for an allowlisted object in AWS S3',
    'storage_ref, bucket, key',
    'Object metadata: size, content_type, etag, last_modified, metadata_keys'
),
(
    'object.get',
    'object',
    'get',
    'Fetch a bounded object body from AWS S3',
    'storage_ref, bucket, key, range_start (optional), range_end (optional), max_bytes, decode_as',
    'Bounded object body as text or base64 plus bytes_returned and truncation state'
)
ON CONFLICT (id) DO UPDATE SET
    domain = EXCLUDED.domain,
    action = EXCLUDED.action,
    description = EXCLUDED.description,
    input_hint = EXCLUDED.input_hint,
    outcome = EXCLUDED.outcome;
