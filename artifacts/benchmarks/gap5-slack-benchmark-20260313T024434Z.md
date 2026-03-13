# GAP-5 Benchmark — slack POST /api/auth.test

- Generated: 2026-03-13T02:44:34.113929+00:00
- Sample size: 100 (warmup 10)
- Agent ID: `569dc525-1d80-47ad-85a2-f6a7a83f7679`
- API base: `http://127.0.0.1:8000`
- Gate pass: ❌ FAIL

## Direct vs Proxy

| Path | Count | Errors | P50 | P95 | P99 | Mean | Min | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Direct | 100 | 0 | 91.2ms | 101.0ms | 165.2ms | 96.1ms | 85.4ms | 459.5ms |
| Proxy | 100 | 0 | 499.0ms | 622.9ms | 961.0ms | 522.1ms | 427.5ms | 971.6ms |

## Proxy Overhead

| Metric | Delta | Threshold |
|---|---:|---:|
| P50 | 407.8ms | 15.0ms |
| P95 | 522.0ms | 30.0ms |
| P99 | 795.8ms | 50.0ms |

_Note: Proxy latencies are client-observed end-to-end timings against the local Rhumb API reference host._
