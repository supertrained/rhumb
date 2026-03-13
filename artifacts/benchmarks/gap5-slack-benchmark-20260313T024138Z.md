# GAP-5 Benchmark — slack POST /api/auth.test

- Generated: 2026-03-13T02:41:38.133090+00:00
- Sample size: 100 (warmup 10)
- Agent ID: `a418a614-b6ba-4fe3-979f-55d501f2794a`
- API base: `http://127.0.0.1:8000`
- Gate pass: ❌ FAIL

## Direct vs Proxy

| Path | Count | Errors | P50 | P95 | P99 | Mean | Min | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Direct | 100 | 0 | 106.9ms | 117.4ms | 119.8ms | 107.6ms | 100.4ms | 121.1ms |
| Proxy | 100 | 99 | 271.6ms | 358.3ms | 405.1ms | 280.5ms | 227.9ms | 590.0ms |

## Proxy Overhead

| Metric | Delta | Threshold |
|---|---:|---:|
| P50 | 164.7ms | 15.0ms |
| P95 | 240.9ms | 30.0ms |
| P99 | 285.3ms | 50.0ms |

_Note: Proxy latencies are client-observed end-to-end timings against the local Rhumb API reference host._
