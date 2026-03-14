// Category metadata — shared between page and tests

export type CategoryMeta = {
  name: string;
  description: string;
};

export const CATEGORY_INFO: Record<string, CategoryMeta> = {
  payments: {
    name: "Payments",
    description: "Payment processing, billing, and financial automation services for agents.",
  },
  "agent-payments": {
    name: "Agent Payments",
    description: "Programmable payment infrastructure built specifically for AI agents — virtual cards, spend controls, and audit trails.",
  },
  ai: {
    name: "AI",
    description: "AI model providers, embeddings, and machine learning inference APIs.",
  },
  analytics: {
    name: "Analytics",
    description: "Data analytics, event tracking, and metrics APIs for real-time agent monitoring.",
  },
  auth: {
    name: "Auth",
    description: "Authentication, authorization, and identity services with agent-friendly APIs.",
  },
  calendar: {
    name: "Calendar",
    description: "Scheduling, event management, and calendar integration APIs.",
  },
  crm: {
    name: "CRM",
    description: "Customer relationship management and contact data services.",
  },
  devops: {
    name: "DevOps",
    description: "CI/CD, deployment, infrastructure, and developer tooling APIs.",
  },
  email: {
    name: "Email",
    description: "Email delivery, template management, and transactional email services.",
  },
  search: {
    name: "Search",
    description: "Search engines, vector databases, and retrieval APIs.",
  },
  social: {
    name: "Social",
    description: "Social media platforms and content distribution APIs.",
  },
};

/** Payments first, then all others alphabetically. */
export const ORDERED_SLUGS: string[] = [
  "payments",
  ...Object.keys(CATEGORY_INFO)
    .filter((k) => k !== "payments")
    .sort(),
];
