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
