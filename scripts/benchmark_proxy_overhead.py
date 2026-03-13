#!/usr/bin/env python3
"""Benchmark Rhumb proxy overhead against a real provider endpoint.

Reference harness for GAP-5 (Gate 2 — Proxy Maturity).

Default target:
- Direct: Slack `POST /api/auth.test`
- Proxy:  Rhumb `/v1/proxy/` -> Slack `POST /api/auth.test`

The script:
1. creates a fresh agent via the local admin API,
2. grants that agent access to Slack,
3. performs warmup calls,
4. benchmarks direct and proxied calls sequentially,
5. computes P50/P95/P99 and proxy-overhead deltas,
6. optionally persists a proxy-side snapshot to Supabase,
7. writes JSON + markdown artifacts,
8. fails non-zero if SLA thresholds are exceeded.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
API_PKG = ROOT / "packages" / "api"
if str(API_PKG) not in sys.path:
    sys.path.insert(0, str(API_PKG))

from db.client import get_supabase_client  # noqa: E402
from services.proxy_latency import LatencyTracker  # noqa: E402


@dataclass
class BenchStats:
    count: int
    success_count: int
    error_count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float


@dataclass
class BenchResult:
    generated_at: str
    provider: str
    endpoint: str
    sample_size: int
    warmup: int
    direct: BenchStats
    proxy: BenchStats
    overhead_ms: dict[str, float]
    thresholds_ms: dict[str, float]
    gate_pass: bool
    api_base_url: str
    agent_id: str
    artifact_note: str


def percentile(values: list[float], pct: int) -> float:
    return float(np.percentile(np.array(values), pct))


def summarize(latencies_ms: list[float], successes: list[bool]) -> BenchStats:
    if not latencies_ms:
        return BenchStats(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return BenchStats(
        count=len(latencies_ms),
        success_count=sum(1 for ok in successes if ok),
        error_count=sum(1 for ok in successes if not ok),
        p50_ms=percentile(latencies_ms, 50),
        p95_ms=percentile(latencies_ms, 95),
        p99_ms=percentile(latencies_ms, 99),
        mean_ms=float(np.mean(np.array(latencies_ms))),
        min_ms=min(latencies_ms),
        max_ms=max(latencies_ms),
    )


def get_env_or_sop(env_name: str, item_name: str, field: str = "credential") -> str:
    value = os.getenv(env_name)
    if value:
        return value
    result = subprocess.run(
        [
            "sop",
            "item",
            "get",
            item_name,
            "--vault",
            "OpenClaw Agents",
            "--fields",
            field,
            "--reveal",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    value = result.stdout.strip()
    if not value:
        raise RuntimeError(f"No value returned for {item_name}:{field}")
    return value


def api_request(
    client: httpx.Client,
    method: str,
    url: str,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return client.request(method=method, url=url, json=json_body, headers=headers)


def create_agent_and_key(api_base_url: str) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    with httpx.Client(timeout=30.0) as client:
        resp = api_request(
            client,
            "POST",
            f"{api_base_url}/v1/admin/agents",
            {
                "name": f"gap5-benchmark-{suffix}",
                "organization_id": "org_gap5_benchmark",
                "rate_limit_qpm": 1000,
                "tags": ["gap5", "benchmark", "slack"],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        agent_id = data["agent_id"]
        api_key = data["api_key"]

        grant = api_request(
            client,
            "POST",
            f"{api_base_url}/v1/admin/agents/{agent_id}/grant-access",
            {"service": "slack"},
        )
        grant.raise_for_status()
        return agent_id, api_key


def benchmark_direct(
    sample_size: int,
    warmup: int,
    slack_token: str,
    pause_ms: float,
) -> tuple[list[float], list[bool]]:
    latencies: list[float] = []
    successes: list[bool] = []
    headers = {"Authorization": f"Bearer {slack_token}"}
    with httpx.Client(timeout=30.0) as client:
        total = warmup + sample_size
        for i in range(total):
            start = time.perf_counter()
            resp = client.post("https://slack.com/api/auth.test", headers=headers)
            elapsed_ms = (time.perf_counter() - start) * 1000
            ok = resp.status_code == 200 and resp.json().get("ok") is True
            if i >= warmup:
                latencies.append(elapsed_ms)
                successes.append(ok)
            if pause_ms > 0:
                time.sleep(pause_ms / 1000.0)
    return latencies, successes


def benchmark_proxy(
    api_base_url: str,
    sample_size: int,
    warmup: int,
    api_key: str,
    pause_ms: float,
    tracker: LatencyTracker,
    agent_id: str,
) -> tuple[list[float], list[bool], dict[str, Any] | None]:
    latencies: list[float] = []
    successes: list[bool] = []
    last_body: dict[str, Any] | None = None
    headers = {"X-Rhumb-Key": api_key}
    body = {"service": "slack", "method": "POST", "path": "/api/auth.test"}
    with httpx.Client(timeout=45.0) as client:
        total = warmup + sample_size
        for i in range(total):
            start = time.perf_counter()
            resp = client.post(f"{api_base_url}/v1/proxy/", json=body, headers=headers)
            elapsed_ms = (time.perf_counter() - start) * 1000
            parsed: dict[str, Any] | None = None
            try:
                parsed = resp.json()
            except Exception:
                parsed = None
            ok = (
                resp.status_code == 200
                and isinstance(parsed, dict)
                and parsed.get("status_code") == 200
                and (
                    (parsed.get("body") or {}).get("ok") is True
                    or (parsed.get("body") or {}).get("team") is not None
                )
            )
            if i >= warmup:
                latencies.append(elapsed_ms)
                successes.append(ok)
                tracker.record(
                    service="slack",
                    agent_id=agent_id,
                    latency_ms=elapsed_ms,
                    perf_start=start,
                    perf_end=time.perf_counter(),
                    status_code=resp.status_code,
                    success=ok,
                )
                last_body = parsed
            if pause_ms > 0:
                time.sleep(pause_ms / 1000.0)
    return latencies, successes, last_body


def to_markdown(result: BenchResult) -> str:
    d = result.direct
    p = result.proxy
    oh = result.overhead_ms
    lines = [
        f"# GAP-5 Benchmark — {result.provider} {result.endpoint}",
        "",
        f"- Generated: {result.generated_at}",
        f"- Sample size: {result.sample_size} (warmup {result.warmup})",
        f"- Agent ID: `{result.agent_id}`",
        f"- API base: `{result.api_base_url}`",
        f"- Gate pass: {'✅ PASS' if result.gate_pass else '❌ FAIL'}",
        "",
        "## Direct vs Proxy",
        "",
        "| Path | Count | Errors | P50 | P95 | P99 | Mean | Min | Max |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| Direct | {d.count} | {d.error_count} | {d.p50_ms:.1f}ms | {d.p95_ms:.1f}ms | {d.p99_ms:.1f}ms | {d.mean_ms:.1f}ms | {d.min_ms:.1f}ms | {d.max_ms:.1f}ms |",
        f"| Proxy | {p.count} | {p.error_count} | {p.p50_ms:.1f}ms | {p.p95_ms:.1f}ms | {p.p99_ms:.1f}ms | {p.mean_ms:.1f}ms | {p.min_ms:.1f}ms | {p.max_ms:.1f}ms |",
        "",
        "## Proxy Overhead",
        "",
        "| Metric | Delta | Threshold |",
        "|---|---:|---:|",
        f"| P50 | {oh['p50_ms']:.1f}ms | {result.thresholds_ms['p50_ms']:.1f}ms |",
        f"| P95 | {oh['p95_ms']:.1f}ms | {result.thresholds_ms['p95_ms']:.1f}ms |",
        f"| P99 | {oh['p99_ms']:.1f}ms | {result.thresholds_ms['p99_ms']:.1f}ms |",
        "",
        f"_Note: {result.artifact_note}_",
        "",
    ]
    return "\n".join(lines)


async def persist_snapshot_if_enabled(
    enabled: bool,
    tracker: LatencyTracker,
    agent_id: str,
) -> None:
    if not enabled:
        return
    supabase = await get_supabase_client()
    await tracker.persist_to_supabase(supabase, service="slack", agent_id=agent_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Rhumb proxy overhead")
    parser.add_argument("--api-base-url", default=os.getenv("RHUMB_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--sample-size", type=int, default=int(os.getenv("BENCH_N", "100")))
    parser.add_argument("--warmup", type=int, default=int(os.getenv("BENCH_WARMUP", "10")))
    parser.add_argument("--pause-ms", type=float, default=float(os.getenv("BENCH_PAUSE_MS", "50")))
    parser.add_argument("--p50-threshold-ms", type=float, default=float(os.getenv("PROXY_OVERHEAD_P50_MS", "15")))
    parser.add_argument("--p95-threshold-ms", type=float, default=float(os.getenv("PROXY_OVERHEAD_P95_MS", "30")))
    parser.add_argument("--p99-threshold-ms", type=float, default=float(os.getenv("PROXY_OVERHEAD_P99_MS", "50")))
    parser.add_argument("--out-dir", default=os.getenv("BENCH_OUT_DIR", str(ROOT / "artifacts" / "benchmarks")))
    parser.add_argument("--persist-proxy-snapshot", action="store_true")
    args = parser.parse_args()

    slack_token = get_env_or_sop("SLACK_BOT_TOKEN", "slack_app_token")
    agent_id, api_key = create_agent_and_key(args.api_base_url)

    direct_latencies, direct_successes = benchmark_direct(
        sample_size=args.sample_size,
        warmup=args.warmup,
        slack_token=slack_token,
        pause_ms=args.pause_ms,
    )

    tracker = LatencyTracker()
    proxy_latencies, proxy_successes, _ = benchmark_proxy(
        api_base_url=args.api_base_url,
        sample_size=args.sample_size,
        warmup=args.warmup,
        api_key=api_key,
        pause_ms=args.pause_ms,
        tracker=tracker,
        agent_id=agent_id,
    )

    direct = summarize(direct_latencies, direct_successes)
    proxy = summarize(proxy_latencies, proxy_successes)
    overhead = {
        "p50_ms": proxy.p50_ms - direct.p50_ms,
        "p95_ms": proxy.p95_ms - direct.p95_ms,
        "p99_ms": proxy.p99_ms - direct.p99_ms,
    }
    thresholds = {
        "p50_ms": args.p50_threshold_ms,
        "p95_ms": args.p95_threshold_ms,
        "p99_ms": args.p99_threshold_ms,
    }
    gate_pass = (
        overhead["p50_ms"] <= thresholds["p50_ms"]
        and overhead["p95_ms"] <= thresholds["p95_ms"]
        and overhead["p99_ms"] <= thresholds["p99_ms"]
        and direct.error_count == 0
        and proxy.error_count == 0
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = BenchResult(
        generated_at=datetime.now(UTC).isoformat(),
        provider="slack",
        endpoint="POST /api/auth.test",
        sample_size=args.sample_size,
        warmup=args.warmup,
        direct=direct,
        proxy=proxy,
        overhead_ms=overhead,
        thresholds_ms=thresholds,
        gate_pass=gate_pass,
        api_base_url=args.api_base_url,
        agent_id=agent_id,
        artifact_note="Proxy latencies are client-observed end-to-end timings against the local Rhumb API reference host.",
    )

    json_path = out_dir / f"gap5-slack-benchmark-{timestamp}.json"
    md_path = out_dir / f"gap5-slack-benchmark-{timestamp}.md"
    json_path.write_text(json.dumps(asdict(result), indent=2) + "\n")
    md_path.write_text(to_markdown(result))

    if args.persist_proxy_snapshot:
        import asyncio
        asyncio.run(persist_snapshot_if_enabled(True, tracker, agent_id))

    print(json.dumps(asdict(result), indent=2))
    print(f"\nArtifacts:\n- {json_path}\n- {md_path}")

    return 0 if gate_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
