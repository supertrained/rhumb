-- Persist the currently supported Resolve v2 account-level policy subset.

create table if not exists resolve_account_policies (
  org_id text primary key references orgs(id) on delete cascade,
  pin text,
  provider_preference jsonb not null default '[]'::jsonb,
  provider_deny jsonb not null default '[]'::jsonb,
  allow_only jsonb not null default '[]'::jsonb,
  max_cost_usd numeric(12,6),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_resolve_account_policies_updated_at
  on resolve_account_policies(updated_at desc);
