# GAP-5b Proxy Hot-Path Deflation Result — 2026-03-12

Status: **PARTIAL WIN / Gate 2 still open**

## What changed
Implemented the first hot-path deflation slice:
- split usage metering into build / persist / identity-touch phases
- added queue-backed `ProxyFinalizer`
- moved successful proxy-call durable bookkeeping off the request success path
- added drain-on-shutdown and inline fallback when the queue is unavailable/saturated
- added targeted tests for success-path decoupling, shutdown drain, and saturation fallback

Relevant files:
- `packages/api/routes/proxy.py`
- `packages/api/services/usage_metering.py`
- `packages/api/services/proxy_finalizer.py`
- `packages/api/app.py`
- `packages/api/tests/test_proxy_auth_wiring.py`
- `packages/api/tests/test_proxy_finalizer.py`

## Test result
Targeted suite passed:
```bash
../../.venv/bin/pytest tests/test_proxy_auth_wiring.py tests/test_proxy_finalizer.py tests/test_metering_durability.py -q
```

## Directional benchmark rerun
Ran a post-fix rerun against local API with Supabase enabled:
- command: `./.venv/bin/python scripts/benchmark_proxy_overhead.py --sample-size 50 --warmup 5 --pause-ms 10 --persist-proxy-snapshot`
- artifact: `artifacts/benchmarks/gap5-slack-benchmark-20260313T031521Z.json`

### Result
| Path | P50 | P95 | P99 |
|---|---:|---:|---:|
| Direct Slack | 90.4ms | 103.6ms | 360.3ms |
| Via Rhumb proxy | 397.6ms | 532.5ms | 664.5ms |
| **Proxy overhead** | **307.2ms** | **428.9ms** | **304.3ms** |

## Comparison vs pre-fix clean baseline
Previous clean baseline (100 measured / 10 warmup):
- overhead P50 **407.8ms**
- overhead P95 **522.0ms**
- overhead P99 **795.8ms**

Directional post-fix rerun (50 measured / 5 warmup):
- overhead P50 **307.2ms**
- overhead P95 **428.9ms**
- overhead P99 **304.3ms**

## Interpretation
This slice helped materially. The remaining overhead is still far above the provisional launch-grade thresholds:
- P50 ≤ 15ms
- P95 ≤ 30ms
- P99 ≤ 50ms

So the judgment is:
- **the awaited bookkeeping was a real contributor**
- **removing it from the success path reduced overhead**
- **but there is still a large residual gap**

That residual likely lives in additional request-path work or framework/runtime overhead still sitting between upstream completion and client-observed completion.

## Next move
Do not mark GAP-5 closed.

Next debugging slice should use the new phase instrumentation to isolate what still dominates after queueing success-path finalization, then decide whether the next reduction comes from:
1. additional response-path work still done before return
2. framework/background behavior around response completion
3. pool / auth / middleware overhead not visible in the upstream-only proxy log line
