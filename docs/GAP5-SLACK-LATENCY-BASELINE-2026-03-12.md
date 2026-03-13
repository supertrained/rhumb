# GAP-5 Slack Latency Baseline — 2026-03-12

Status: **FAIL / Gate 2 remains open**

## Benchmark setup
- Provider: Slack
- Endpoint: `POST /api/auth.test`
- Reference host: local Rhumb API on Mac Studio (`http://127.0.0.1:8000`)
- Sample size: 100 measured calls
- Warmup: 10 calls discarded
- Agent rate limit: 1000 QPM (to avoid contaminating the run with Rhumb's own rate limiter)
- Persistence: proxy snapshot persisted to `proxy_metrics`

## Result

| Path | Errors | P50 | P95 | P99 |
|---|---:|---:|---:|---:|
| Direct Slack | 0 | 91.2ms | 101.0ms | 165.2ms |
| Via Rhumb proxy | 0 | 499.0ms | 622.9ms | 961.0ms |
| **Proxy overhead** | — | **407.8ms** | **522.0ms** | **795.8ms** |

## Gate verdict
Provisional Gate 2 thresholds were:
- P50 overhead ≤ 15ms
- P95 overhead ≤ 30ms
- P99 overhead ≤ 50ms

This run misses all three by a wide margin. Gate 2.E (Latency / reliability) is **not passed**.

## Most important technical finding
The proxy route's internal `[PROXY]` logs show upstream request times clustering around ~90–105ms for successful Slack calls.

But the client-observed proxy latencies are ~499ms P50 / ~961ms P99.

That strongly suggests the dominant overhead is **not** the upstream Slack call itself. The extra latency is appearing **after** the proxy request completes upstream — most likely in Rhumb's own post-request path (durable metering / bookkeeping / response-finalization work).

In other words:
- upstream provider time looks normal
- total proxy path is materially slower
- the overhead appears to be inside Rhumb control-plane completion, not the provider

## Artifacts
- Benchmark script: `scripts/benchmark_proxy_overhead.py`
- Raw JSON artifact: `artifacts/benchmarks/gap5-slack-benchmark-20260313T024434Z.json`
- Raw markdown artifact: `artifacts/benchmarks/gap5-slack-benchmark-20260313T024434Z.md`
- Persisted snapshot: `proxy_metrics.id = 2` for agent `569dc525-1d80-47ad-85a2-f6a7a83f7679`

## Next action
Do **not** claim low-overhead proxy performance yet.

Next debugging slice should isolate which post-upstream steps dominate the delta, starting with:
1. durable metering write cost
2. query logging / middleware cost
3. any unnecessary sync waits before response return

The likely next move is a targeted profiling slice for the proxy hot path, not a threshold debate.
