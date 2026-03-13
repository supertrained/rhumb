-- Migration 0012: Access operational facts landing table for Helm → Keel evidence ingestion
-- Target: Supabase (PostgreSQL 15+)
-- Source: Helm ACCESS-OPERATIONAL-FACT-V1-SUPABASE.sql (fixed: trigger-based dedupe instead of generated column)

begin;

create extension if not exists pgcrypto;

create table if not exists access_operational_facts (
  id uuid primary key default gen_random_uuid(),
  schema_version text not null check (schema_version = 'access_operational_fact_v1'),
  fact_type text not null check (
    fact_type in (
      'proxy_call', 'latency_snapshot', 'circuit_state', 'schema_change',
      'usage_attribution', 'provisioning_outcome', 'provider_support_state',
      'credential_lifecycle', 'provider_friction', 'benchmark_artifact'
    )
  ),
  service_slug text not null,
  provider_slug text not null,
  agent_id text null,
  run_id text null,
  event_type text not null,
  observed_at timestamptz not null,
  environment text not null check (environment in ('production', 'staging', 'local_test')),
  source_type text not null check (source_type in ('runtime_verified', 'tester_generated', 'probe_generated', 'manual_operator')),
  confidence numeric(4,3) not null check (confidence >= 0 and confidence <= 1),
  fresh_until timestamptz not null,
  artifact_ref text null,
  notes text null,
  payload jsonb not null,
  ingress_channel text not null default 'access_proxy',
  ingested_at timestamptz not null default now(),
  raw_packet jsonb null,
  countability_hint text null check (
    countability_hint in (
      'countable_as_evidence_now',
      'evidence_only_not_review_countable',
      'not_countable_config_only'
    )
  ),
  supersedes_fact_id uuid null references access_operational_facts(id) on delete set null,
  invalidated_by_fact_id uuid null references access_operational_facts(id) on delete set null
);

create index if not exists idx_aof_service_observed_at on access_operational_facts (service_slug, observed_at desc);
create index if not exists idx_aof_provider_observed_at on access_operational_facts (provider_slug, observed_at desc);
create index if not exists idx_aof_fact_type_observed_at on access_operational_facts (fact_type, observed_at desc);
create index if not exists idx_aof_event_type_observed_at on access_operational_facts (event_type, observed_at desc);
create index if not exists idx_aof_source_type_observed_at on access_operational_facts (source_type, observed_at desc);
create index if not exists idx_aof_agent_observed_at on access_operational_facts (agent_id, observed_at desc);
create index if not exists idx_aof_run_id on access_operational_facts (run_id) where run_id is not null;
create index if not exists idx_aof_fresh_until on access_operational_facts (fresh_until);
create index if not exists idx_aof_payload_gin on access_operational_facts using gin (payload jsonb_path_ops);

-- Trigger-based dedupe key (generated column approach failed: timestamptz::text is not immutable)
alter table access_operational_facts add column if not exists dedupe_key text;

create or replace function aof_compute_dedupe_key() returns trigger as $$
begin
  NEW.dedupe_key := md5(
    coalesce(NEW.schema_version, '') || '|' ||
    coalesce(NEW.fact_type, '') || '|' ||
    coalesce(NEW.service_slug, '') || '|' ||
    coalesce(NEW.provider_slug, '') || '|' ||
    coalesce(NEW.agent_id, '') || '|' ||
    coalesce(NEW.run_id, '') || '|' ||
    coalesce(NEW.event_type, '') || '|' ||
    coalesce(NEW.environment, '') || '|' ||
    coalesce(NEW.source_type, '') || '|' ||
    coalesce(NEW.observed_at::text, '') || '|' ||
    coalesce(NEW.payload::text, '')
  );
  return NEW;
end;
$$ language plpgsql;

drop trigger if exists trg_aof_dedupe_key on access_operational_facts;
create trigger trg_aof_dedupe_key
  before insert or update on access_operational_facts
  for each row execute function aof_compute_dedupe_key();

create unique index if not exists idx_aof_dedupe_key on access_operational_facts (dedupe_key);

alter table access_operational_facts enable row level security;
create policy "Public read access_operational_facts" on access_operational_facts for select using (true);
create policy "Service role write access_operational_facts" on access_operational_facts for all using (true) with check (true);

comment on table access_operational_facts is 'Raw operational fact packets emitted by Helm/Access for Keel Evidence ingestion. Not review-countable by themselves.';
comment on column access_operational_facts.payload is 'Fact-specific payload validated against access_operational_fact_v1 JSON Schema.';
comment on column access_operational_facts.countability_hint is 'Advisory hint from Helm; Keel remains authoritative on evidence/review counting.';

commit;
