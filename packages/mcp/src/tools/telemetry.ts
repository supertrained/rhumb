/**
 * usage_telemetry tool handler
 *
 * Returns a compact execution analytics view for the current agent.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { UsageTelemetryInput, UsageTelemetryOutput } from "../types.js";

function providerStatus(successRate: number): "healthy" | "degraded" | "unhealthy" {
  if (successRate >= 0.95) return "healthy";
  if (successRate >= 0.8) return "degraded";
  return "unhealthy";
}

/**
 * Handle a usage_telemetry request.
 *
 * @param input Validated telemetry query input
 * @param client API client for fetching usage telemetry
 * @returns Formatted usage analytics for agent consumption
 */
export async function handleUsageTelemetry(
  input: UsageTelemetryInput,
  client: RhumbApiClient
): Promise<UsageTelemetryOutput> {
  try {
    const result = await client.getUsageTelemetry({
      days: input.days,
      capability_id: input.capability_id,
      provider: input.provider
    });

    const topCapability = result.by_capability[0]?.capability_id ?? null;
    const topProvider = result.by_provider[0]?.provider ?? null;
    const providerHealth = result.by_provider.map((item) => ({
      provider: item.provider,
      status: providerStatus(item.success_rate),
      success_rate: item.success_rate,
      avg_latency_ms: item.avg_latency_ms,
      calls: item.calls
    }));

    return {
      agent_id: result.agent_id,
      period_days: result.period_days,
      summary: result.summary,
      top_capability: topCapability,
      top_provider: topProvider,
      provider_health: providerHealth,
      by_capability: result.by_capability,
      by_provider: result.by_provider,
      by_time: result.by_time,
      message:
        `Telemetry for ${result.period_days}d: ${result.summary.total_calls} calls, ` +
        `${result.summary.failed_calls} failed, $${result.summary.total_cost_usd.toFixed(2)} total cost.`
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return {
      agent_id: "",
      period_days: input.days ?? 7,
      summary: {
        total_calls: 0,
        successful_calls: 0,
        failed_calls: 0,
        total_cost_usd: 0,
        avg_latency_ms: 0,
        p50_latency_ms: 0,
        p95_latency_ms: 0
      },
      top_capability: null,
      top_provider: null,
      provider_health: [],
      by_capability: [],
      by_provider: [],
      by_time: [],
      message: `Failed to fetch usage telemetry: ${message}`
    };
  }
}
