# Discovery expansion — reverse-ETL II

Date: 2026-04-03
Owner: Pedro / Keel runtime review loop

## Why this category

Live production category counts show **`reverse-etl`** at only **3 providers** — the lowest-count category in the entire catalog:
- `census`
- `hightouch`
- `polytomic`

(Plus 4 from the first expansion `0105_reverse_etl_expansion.sql`: `portable`, `hevo-activate`, `omnata`, `grouparoo`.)

Reverse ETL is a core agent workflow enabler. Agents need to push warehouse truth back into CRMs, support tools, and operational SaaS to close the loop between discovery and action. This is also a natural upstream dependency for any agent that:
- reads enriched data from a warehouse
- needs to write those insights back to operational systems (Salesforce, HubSpot, Zendesk, etc.)
- monitors transformation pipelines that feed other tools

The honest Mission 2 call was to deepen **reverse-etl** rather than expand a category already at 5+ providers.

## Added services

### 1. Castled.io
- Slug: `castled-data`
- Score: **8.15**
- Execution: **8.25**
- Access readiness: **7.90**
- Why it made the cut:
  - clean REST API for sync management, models, and destinations
  - strongest Phase 0 candidate in the batch
  - real cloud-native reverse ETL product with clear read-first API surfaces
  - maps directly to `sync.list`, `sync.run`, `sync.status` primitives

### 2. Nexla
- Slug: `nexla`
- Score: **8.00**
- Execution: **8.10**
- Access readiness: **7.75**
- Why it made the cut:
  - developer-focused data operations API for pipeline management and sync state
  - strong cross-platform coverage for agents monitoring transformation runs
  - good second Phase 0 target after Castled for `dataflow.list` and `dataset.get`

### 3. Etleap
- Slug: `etleap`
- Score: **7.85**
- Execution: **7.95**
- Access readiness: **7.65**
- Why it made the cut:
  - enterprise-grade cloud data warehouse reverse ETL with real API coverage
  - solid pipeline status and run management for agent-driven monitoring
  - strong Snowflake/Redshift/BigQuery coverage fills a gap in enterprise catalog depth

### 4. Syncari
- Slug: `syncari`
- Score: **7.80**
- Execution: **7.90**
- Access readiness: **7.55**
- Why it made the cut:
  - bi-directional sync and reverse ETL for multi-system record reconciliation
  - useful for agent workflows that need cross-system data activation awareness
  - dataset and sync inspection are real Phase 0 starting points

### 5. dbt Cloud (Reverse Sync)
- Slug: `dbt-cloud`
- Score: **8.20**
- Execution: **8.30**
- Access readiness: **7.95**
- Why it made the cut:
  - dbt is the transformation layer upstream of virtually every reverse ETL pipeline
  - dbt Cloud exposes clean APIs for job run state and semantic-layer queries
  - agents that can inspect dbt job output become first-class warehouse-aware actors
  - strategically important: dbt Cloud API coverage upgrades every agent that depends on warehouse-transformed outputs

## Phase 0 capability assessment

All five services expose accessible machine-facing APIs suitable for Phase 0 assessment.

### Strongest Phase 0 candidates
1. **dbt Cloud** — best read-first target for `warehouse.job.status` and `warehouse.query` via the semantic layer API
2. **Castled.io** — cleanest sync management API for `sync.list` / `sync.run` / `sync.status`
3. **Nexla** — `dataflow.list` and `dataset.get` primitives with developer API access

### Best initial Phase 0 wedge
Read-first warehouse output inspection:
- `warehouse.job.status` (dbt Cloud job run state)
- `sync.list` / `sync.status` (Castled.io managed syncs)
- `dataflow.status` (Nexla pipeline state)

**Best first provider:** **dbt Cloud**

Why:
- dbt Cloud is the most pervasive transformation layer in modern data stacks
- job run status and semantic-layer queries are genuinely useful to agents without requiring mutation of the transformation graph
- every reverse ETL pipeline starts with dbt; agents that can see dbt output become more capable immediately
- clean REST API with API token auth makes access straightforward

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0156_reverse_etl_expansion_ii.sql`

## Verdict

Reverse ETL was the lowest-count category in the catalog. This batch adds five more real providers and sharpens the next honest Resolve wedge around **read-first warehouse output inspection**, with **dbt Cloud** now the best Phase 0 target for job run state and semantic-layer query primitives, and **Castled.io** as the cleanest sync management Phase 0 candidate.
