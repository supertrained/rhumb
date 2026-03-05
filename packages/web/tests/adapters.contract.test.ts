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
        tier: "L4",
        confidence: 0.95
      }
    ]);
  });

  it("parses score payload contract", () => {
    const payload = {
      service_slug: "stripe",
      aggregate_recommendation_score: 8.9,
      execution_score: 9.1,
      access_readiness_score: 8.4,
      confidence: 0.98,
      tier: "L4",
      explanation: "Reliable payment API"
    };

    const parsed = parseServiceScoreResponse(payload);

    expect(parsed).toEqual({
      serviceSlug: "stripe",
      aggregateRecommendationScore: 8.9,
      executionScore: 9.1,
      accessReadinessScore: 8.4,
      confidence: 0.98,
      tier: "L4",
      explanation: "Reliable payment API"
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
