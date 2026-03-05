import { describe, expect, it } from "vitest";

import {
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
        confidence: 0.95
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
      ]
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
