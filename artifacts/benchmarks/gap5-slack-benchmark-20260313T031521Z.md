# GAP-5 Benchmark — slack POST /api/auth.test

- Generated: 2026-03-13T03:15:21.508556+00:00
- Sample size: 50 (warmup 5)
- Agent ID: `151596ab-5a62-4a95-be85-1869ac0ed82a`
- API base: `http://127.0.0.1:8000`
- Gate pass: ❌ FAIL

## Direct vs Proxy

| Path | Count | Errors | P50 | P95 | P99 | Mean | Min | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Direct | 50 | 0 | 90.4ms | 103.6ms | 360.3ms | 102.5ms | 86.5ms | 595.2ms |
| Proxy | 50 | 0 | 397.6ms | 532.5ms | 664.5ms | 416.6ms | 348.6ms | 722.2ms |

## Proxy Overhead

| Metric | Delta | Threshold |
|---|---:|---:|
| P50 | 307.2ms | 15.0ms |
| P95 | 428.9ms | 30.0ms |
| P99 | 304.3ms | 50.0ms |

_Note: Proxy latencies are client-observed end-to-end timings against the local Rhumb API reference host._
