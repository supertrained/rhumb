export type Service = {
  slug: string;
  name: string;
  category: string;
  description?: string;
};

export type ANScore = {
  score: number;
  confidence: number;
  tier: "emerging" | "developing" | "ready" | "native";
  explanation: string;
};

export type LeaderboardItem = {
  serviceSlug: string;
  name: string;
  aggregateRecommendationScore: number | null;
  tier: string | null;
  confidence: number | null;
};

export type LeaderboardViewModel = {
  category: string;
  items: LeaderboardItem[];
};

export type ServiceScoreViewModel = {
  serviceSlug: string;
  aggregateRecommendationScore: number | null;
  executionScore: number | null;
  accessReadinessScore: number | null;
  confidence: number | null;
  tier: string | null;
  explanation: string | null;
};
