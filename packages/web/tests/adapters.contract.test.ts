import { describe, expect, it } from "vitest";

import {
  parseLaunchDashboardResponse,
  parseLeaderboardResponse,
  parseServiceScoreResponse,
  parseServicesResponse
} from "../lib/adapters";

describe("web adapters", () => {
  it("parses leaderboard payload contract", () => {
    const payload = {
      data: {
        category: "payments",
        items: [
          {
            service_slug: "stripe",
            name: "Stripe",
            aggregate_recommendation_score: 8.9,
            execution_score: 9.1,
            access_readiness_score: 8.4,
            probe_freshness: "12 minutes ago",
            calculated_at: "2026-03-05T22:00:00Z",
            tier: "L4",
            confidence: 0.95
          }
        ]
      },
      error: null
    };

    const parsed = parseLeaderboardResponse(payload);

    expect(parsed.category).toBe("payments");
    expect(parsed.items).toEqual([
      {
        serviceSlug: "stripe",
        name: "Stripe",
        aggregateRecommendationScore: 8.9,
        executionScore: 9.1,
        accessReadinessScore: 8.4,
        freshness: "12 minutes ago",
        calculatedAt: "2026-03-05T22:00:00Z",
        tier: "L4",
        confidence: 0.95,
        p1Score: null,
        g1Score: null,
        w1Score: null
      }
    ]);
    expect(parsed.error).toBeNull();
  });

  it("returns a typed error for invalid leaderboard payload", () => {
    const parsed = parseLeaderboardResponse(null);

    expect(parsed).toEqual({
      category: "unknown",
      items: [],
      error: "Invalid leaderboard payload"
    });
  });

  it("parses score payload contract", () => {
    const payload = {
      service_slug: "stripe",
      aggregate_recommendation_score: 8.9,
      execution_score: 9.1,
      access_readiness_score: 8.4,
      confidence: 0.98,
      tier: "L4",
      tier_label: "Agent Native",
      explanation: "Reliable payment API",
      calculated_at: "2026-03-05T23:00:00Z",
      dimension_snapshot: {
        probe_freshness: "12 minutes ago",
        active_failures: [
          {
            id: "AF-oauth-redirect",
            summary: "Token refresh requires browser redirect in some flows"
          }
        ],
        alternatives: [
          {
            service: "square",
            score: 7.4
          }
        ]
      }
    };

    const parsed = parseServiceScoreResponse(payload);

    expect(parsed).toEqual({
      serviceSlug: "stripe",
      aggregateRecommendationScore: 8.9,
      executionScore: 9.1,
      accessReadinessScore: 8.4,
      confidence: 0.98,
      tier: "L4",
      tierLabel: "Agent Native",
      explanation: "Reliable payment API",
      calculatedAt: "2026-03-05T23:00:00Z",
      evidenceFreshness: "12 minutes ago",
      activeFailures: [
        {
          id: "AF-oauth-redirect",
          summary: "Token refresh requires browser redirect in some flows"
        }
      ],
      alternatives: [
        {
          serviceSlug: "square",
          score: 7.4
        }
      ],
      p1Score: null,
      g1Score: null,
      w1Score: null,
      p1Rationale: null,
      g1Rationale: null,
      w1Rationale: null,
      autonomyTier: null,
      baseUrl: null,
      docsUrl: null,
      openapiUrl: null,
      mcpServerUrl: null
    });
  });

  it("parses launch dashboard payload contract", () => {
    const payload = {
      data: {
        window: "7d",
        start_at: "2026-03-06T00:00:00Z",
        generated_at: "2026-03-13T00:00:00Z",
        coverage: {
          public_service_count: 53
        },
        queries: {
          total: 12,
          machine_total: 7,
          by_source: [{ key: "mcp", count: 5 }],
          top_query_types: [{ key: "score_lookup", count: 6 }],
          top_services: [{ key: "stripe", count: 4 }],
          top_searches: [{ key: "payments", count: 2 }],
          unique_clients: 3,
          repeat_clients: 1,
          repeat_client_rate: 0.3333,
          latest_activity_at: "2026-03-13T00:00:00Z"
        },
        clicks: {
          total: 4,
          provider_clicks: 3,
          top_provider_domains: [{ key: "stripe.com", count: 2 }],
          top_source_surfaces: [{ key: "service_page", count: 3 }],
          provider_ctr: [{ service_slug: "stripe", clicks: 2, views: 4, ctr: 0.5 }],
          dispute_clicks: { email: 1, github: 0, contact: 1 },
          latest_activity_at: "2026-03-13T00:00:00Z"
        }
      },
      error: null
    };

    expect(parseLaunchDashboardResponse(payload)).toEqual({
      window: "7d",
      startAt: "2026-03-06T00:00:00Z",
      generatedAt: "2026-03-13T00:00:00Z",
      coverage: {
        publicServiceCount: 53
      },
      queries: {
        total: 12,
        machineTotal: 7,
        bySource: [{ key: "mcp", count: 5 }],
        topQueryTypes: [{ key: "score_lookup", count: 6 }],
        topServices: [{ key: "stripe", count: 4 }],
        topSearches: [{ key: "payments", count: 2 }],
        uniqueClients: 3,
        repeatClients: 1,
        repeatClientRate: 0.3333,
        latestActivityAt: "2026-03-13T00:00:00Z"
      },
      clicks: {
        total: 4,
        providerClicks: 3,
        topProviderDomains: [{ key: "stripe.com", count: 2 }],
        topSourceSurfaces: [{ key: "service_page", count: 3 }],
        providerCtr: [{ service_slug: "stripe", clicks: 2, views: 4, ctr: 0.5 }],
        disputeClicks: { email: 1, github: 0, contact: 1 },
        latestActivityAt: "2026-03-13T00:00:00Z"
      }
    });
  });

  it("parses service list payload contract", () => {
    const payload = {
      data: {
        items: [
          {
            slug: "stripe",
            name: "Stripe",
            category: "payments",
            description: "Payments API"
          }
        ]
      },
      error: null
    };

    expect(parseServicesResponse(payload)).toEqual([
      {
        slug: "stripe",
        name: "Stripe",
        category: "payments",
        description: "Payments API"
      }
    ]);
  });
});
