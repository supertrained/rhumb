/**
 * Dimension scores for all 50 services in the initial dataset.
 *
 * Scores are on a 0.0–10.0 scale across 17 execution dimensions (I1–I7, F1–F7, O1–O3)
 * and 6 access readiness dimensions (A1–A6).
 *
 * Sources: public API documentation reviews, developer community sentiment,
 * status page SLA data, and calibrated heuristics from Rhumb panels 1–4.
 */

export interface ServiceDimensions {
  slug: string;
  dimensions: Record<string, number>;
  access_dimensions: Record<string, number>;
  evidence_count: number;
  freshness: string;
  probe_types: string[];
  production_telemetry: boolean;
  /** Simulated probe latency distribution in milliseconds */
  probe_latency_ms: { p50: number; p95: number; p99: number; samples: number };
  /** Flags for error handling paths */
  auth_required?: boolean;
  docs_unavailable?: boolean;
}

export const SERVICE_DIMENSIONS: ServiceDimensions[] = [
  // ──── Email (5) ────
  {
    slug: "sendgrid",
    dimensions: {
      I1: 8.0, I2: 7.5, I3: 8.0, I4: 7.5, I5: 8.0, I6: 7.0, I7: 7.0,
      F1: 8.0, F2: 7.0, F3: 7.5, F4: 7.5, F5: 7.0, F6: 7.5, F7: 7.0,
      O1: 7.0, O2: 6.5, O3: 6.0,
    },
    access_dimensions: { A1: 4.5, A2: 4.5, A3: 4.5, A4: 6.0, A5: 7.0, A6: 7.0 },
    evidence_count: 54, freshness: "5 hours ago",
    probe_types: ["health", "schema", "load", "webhook"],
    production_telemetry: true,
    probe_latency_ms: { p50: 145, p95: 320, p99: 580, samples: 12 },
  },
  {
    slug: "resend",
    dimensions: {
      I1: 8.5, I2: 9.0, I3: 9.0, I4: 8.5, I5: 8.5, I6: 8.0, I7: 8.0,
      F1: 9.0, F2: 9.0, F3: 9.0, F4: 8.0, F5: 8.5, F6: 9.0, F7: 8.5,
      O1: 9.0, O2: 9.0, O3: 8.0,
    },
    access_dimensions: { A1: 6.5, A2: 6.0, A3: 6.5, A4: 7.5, A5: 7.5, A6: 8.0 },
    evidence_count: 33, freshness: "45 minutes ago",
    probe_types: ["health", "schema", "load", "webhook"],
    production_telemetry: false,
    probe_latency_ms: { p50: 92, p95: 210, p99: 380, samples: 10 },
  },
  {
    slug: "postmark",
    dimensions: {
      I1: 8.0, I2: 8.0, I3: 8.5, I4: 7.0, I5: 7.5, I6: 7.5, I7: 7.5,
      F1: 7.5, F2: 8.0, F3: 8.0, F4: 7.5, F5: 7.5, F6: 8.0, F7: 7.5,
      O1: 8.0, O2: 7.5, O3: 7.0,
    },
    access_dimensions: { A1: 5.0, A2: 4.5, A3: 5.0, A4: 6.0, A5: 7.0, A6: 7.5 },
    evidence_count: 41, freshness: "2 hours ago",
    probe_types: ["health", "schema", "webhook"],
    production_telemetry: false,
    probe_latency_ms: { p50: 110, p95: 260, p99: 420, samples: 9 },
  },
  {
    slug: "mailgun",
    dimensions: {
      I1: 7.5, I2: 7.0, I3: 7.5, I4: 7.0, I5: 7.0, I6: 6.5, I7: 6.5,
      F1: 7.0, F2: 6.5, F3: 7.0, F4: 7.0, F5: 6.5, F6: 7.0, F7: 6.5,
      O1: 6.5, O2: 6.0, O3: 6.0,
    },
    access_dimensions: { A1: 4.0, A2: 4.0, A3: 4.0, A4: 5.5, A5: 6.5, A6: 6.5 },
    evidence_count: 38, freshness: "6 hours ago",
    probe_types: ["health", "schema", "webhook"],
    production_telemetry: false,
    probe_latency_ms: { p50: 165, p95: 380, p99: 650, samples: 8 },
  },
  {
    slug: "amazon-ses",
    dimensions: {
      I1: 9.0, I2: 7.5, I3: 8.0, I4: 8.0, I5: 8.5, I6: 6.0, I7: 8.0,
      F1: 7.0, F2: 6.0, F3: 7.0, F4: 5.5, F5: 7.5, F6: 6.0, F7: 5.5,
      O1: 7.0, O2: 7.0, O3: 6.5,
    },
    access_dimensions: { A1: 3.0, A2: 3.0, A3: 3.5, A4: 4.5, A5: 6.0, A6: 5.5 },
    evidence_count: 48, freshness: "3 hours ago",
    probe_types: ["health", "auth", "schema"],
    production_telemetry: true,
    probe_latency_ms: { p50: 180, p95: 420, p99: 750, samples: 15 },
    auth_required: true,
  },

  // ──── CRM (5) ────
  {
    slug: "hubspot",
    dimensions: {
      I1: 6.5, I2: 6.0, I3: 4.5, I4: 6.0, I5: 5.0, I6: 6.0, I7: 5.5,
      F1: 6.0, F2: 5.0, F3: 6.0, F4: 5.5, F5: 4.0, F6: 6.0, F7: 4.0,
      O1: 4.0, O2: 5.0, O3: 5.5,
    },
    access_dimensions: { A1: 3.0, A2: 3.0, A3: 2.5, A4: 3.0, A5: 5.0, A6: 6.0 },
    evidence_count: 58, freshness: "2 hours ago",
    probe_types: ["health", "auth", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 280, p95: 680, p99: 1200, samples: 14 },
  },
  {
    slug: "salesforce",
    dimensions: {
      I1: 7.0, I2: 5.5, I3: 5.0, I4: 6.5, I5: 5.5, I6: 4.5, I7: 5.0,
      F1: 6.5, F2: 5.5, F3: 5.5, F4: 4.5, F5: 5.0, F6: 5.5, F7: 3.5,
      O1: 5.0, O2: 5.5, O3: 5.0,
    },
    access_dimensions: { A1: 3.5, A2: 3.0, A3: 3.0, A4: 4.0, A5: 5.0, A6: 5.5 },
    evidence_count: 62, freshness: "4 hours ago",
    probe_types: ["health", "auth", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 350, p95: 850, p99: 1500, samples: 16 },
    auth_required: true,
  },
  {
    slug: "pipedrive",
    dimensions: {
      I1: 7.0, I2: 7.0, I3: 7.0, I4: 6.5, I5: 6.5, I6: 6.5, I7: 6.5,
      F1: 7.0, F2: 6.5, F3: 7.0, F4: 7.0, F5: 6.0, F6: 7.0, F7: 6.0,
      O1: 6.5, O2: 6.5, O3: 6.0,
    },
    access_dimensions: { A1: 4.0, A2: 4.0, A3: 4.0, A4: 5.0, A5: 6.0, A6: 6.5 },
    evidence_count: 35, freshness: "8 hours ago",
    probe_types: ["health", "auth", "schema"],
    production_telemetry: false,
    probe_latency_ms: { p50: 195, p95: 450, p99: 780, samples: 10 },
  },
  {
    slug: "copper",
    dimensions: {
      I1: 6.0, I2: 6.0, I3: 6.5, I4: 5.5, I5: 5.5, I6: 5.5, I7: 5.5,
      F1: 5.5, F2: 5.0, F3: 5.5, F4: 6.0, F5: 5.0, F6: 5.5, F7: 5.0,
      O1: 5.5, O2: 5.0, O3: 4.5,
    },
    access_dimensions: { A1: 3.0, A2: 3.0, A3: 3.0, A4: 4.0, A5: 5.0, A6: 5.0 },
    evidence_count: 22, freshness: "12 hours ago",
    probe_types: ["health", "schema"],
    production_telemetry: false,
    probe_latency_ms: { p50: 220, p95: 520, p99: 900, samples: 6 },
  },
  {
    slug: "zoho-crm",
    dimensions: {
      I1: 6.5, I2: 5.5, I3: 5.5, I4: 5.0, I5: 5.0, I6: 5.0, I7: 5.0,
      F1: 5.5, F2: 5.0, F3: 5.5, F4: 5.0, F5: 4.5, F6: 5.0, F7: 4.5,
      O1: 5.0, O2: 4.5, O3: 4.5,
    },
    access_dimensions: { A1: 2.5, A2: 2.5, A3: 2.5, A4: 3.5, A5: 4.5, A6: 5.0 },
    evidence_count: 30, freshness: "10 hours ago",
    probe_types: ["health", "auth", "schema"],
    production_telemetry: false,
    probe_latency_ms: { p50: 240, p95: 580, p99: 1050, samples: 8 },
  },

  // ──── Payments (6) ────
  {
    slug: "stripe",
    dimensions: {
      I1: 9.5, I2: 9.0, I3: 8.5, I4: 9.5, I5: 9.0, I6: 8.0, I7: 9.0,
      F1: 9.0, F2: 9.5, F3: 9.5, F4: 8.5, F5: 10.0, F6: 9.0, F7: 9.0,
      O1: 9.0, O2: 9.0, O3: 8.0,
    },
    access_dimensions: { A1: 6.0, A2: 5.5, A3: 6.0, A4: 7.5, A5: 8.0, A6: 8.0 },
    evidence_count: 72, freshness: "12 minutes ago",
    probe_types: ["health", "auth", "schema", "load", "idempotency"],
    production_telemetry: true,
    probe_latency_ms: { p50: 120, p95: 280, p99: 450, samples: 20 },
  },
  {
    slug: "adyen",
    dimensions: {
      I1: 8.5, I2: 7.5, I3: 7.5, I4: 7.0, I5: 7.5, I6: 7.0, I7: 7.5,
      F1: 7.0, F2: 7.5, F3: 7.5, F4: 6.5, F5: 8.0, F6: 7.0, F7: 6.5,
      O1: 7.5, O2: 7.0, O3: 6.5,
    },
    access_dimensions: { A1: 4.0, A2: 3.5, A3: 4.0, A4: 5.5, A5: 6.5, A6: 6.0 },
    evidence_count: 45, freshness: "3 hours ago",
    probe_types: ["health", "auth", "schema", "load"],
    production_telemetry: true,
    probe_latency_ms: { p50: 155, p95: 340, p99: 580, samples: 12 },
    auth_required: true,
  },
  {
    slug: "braintree",
    dimensions: {
      I1: 7.5, I2: 7.0, I3: 6.5, I4: 6.5, I5: 7.0, I6: 6.0, I7: 6.5,
      F1: 6.5, F2: 6.5, F3: 6.5, F4: 6.0, F5: 7.0, F6: 6.5, F7: 5.5,
      O1: 6.5, O2: 6.0, O3: 5.5,
    },
    access_dimensions: { A1: 3.5, A2: 3.5, A3: 3.5, A4: 5.0, A5: 6.0, A6: 6.0 },
    evidence_count: 40, freshness: "6 hours ago",
    probe_types: ["health", "auth", "schema"],
    production_telemetry: true,
    probe_latency_ms: { p50: 185, p95: 420, p99: 720, samples: 10 },
    auth_required: true,
  },
  {
    slug: "paypal",
    dimensions: {
      I1: 7.5, I2: 6.5, I3: 6.0, I4: 6.0, I5: 6.5, I6: 5.5, I7: 6.0,
      F1: 6.0, F2: 5.5, F3: 5.5, F4: 5.5, F5: 6.5, F6: 5.5, F7: 5.0,
      O1: 5.5, O2: 5.5, O3: 5.0,
    },
    access_dimensions: { A1: 3.0, A2: 3.0, A3: 3.0, A4: 4.0, A5: 5.5, A6: 5.5 },
    evidence_count: 55, freshness: "4 hours ago",
    probe_types: ["health", "auth", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 210, p95: 500, p99: 880, samples: 14 },
    auth_required: true,
  },
  {
    slug: "square",
    dimensions: {
      I1: 8.0, I2: 7.5, I3: 7.5, I4: 7.5, I5: 7.5, I6: 7.0, I7: 7.5,
      F1: 7.5, F2: 7.0, F3: 7.5, F4: 7.0, F5: 7.5, F6: 7.0, F7: 6.5,
      O1: 7.0, O2: 7.0, O3: 6.0,
    },
    access_dimensions: { A1: 4.5, A2: 4.0, A3: 4.5, A4: 6.0, A5: 7.0, A6: 7.0 },
    evidence_count: 42, freshness: "5 hours ago",
    probe_types: ["health", "auth", "schema", "load"],
    production_telemetry: true,
    probe_latency_ms: { p50: 140, p95: 310, p99: 520, samples: 11 },
  },
  {
    slug: "lemon-squeezy",
    dimensions: {
      I1: 7.5, I2: 8.0, I3: 8.0, I4: 7.0, I5: 7.0, I6: 7.5, I7: 7.0,
      F1: 8.0, F2: 7.5, F3: 8.0, F4: 7.5, F5: 7.0, F6: 8.0, F7: 7.5,
      O1: 7.5, O2: 7.5, O3: 6.5,
    },
    access_dimensions: { A1: 5.0, A2: 5.0, A3: 5.0, A4: 6.0, A5: 7.0, A6: 7.5 },
    evidence_count: 25, freshness: "3 hours ago",
    probe_types: ["health", "schema", "webhook"],
    production_telemetry: false,
    probe_latency_ms: { p50: 105, p95: 240, p99: 400, samples: 8 },
  },

  // ──── Auth (5) ────
  {
    slug: "auth0",
    dimensions: {
      I1: 8.5, I2: 7.5, I3: 7.5, I4: 7.5, I5: 8.0, I6: 6.5, I7: 7.5,
      F1: 7.5, F2: 7.0, F3: 7.0, F4: 7.0, F5: 7.5, F6: 7.5, F7: 6.0,
      O1: 7.0, O2: 7.0, O3: 7.0,
    },
    access_dimensions: { A1: 4.5, A2: 4.0, A3: 4.0, A4: 5.5, A5: 6.5, A6: 7.0 },
    evidence_count: 50, freshness: "2 hours ago",
    probe_types: ["health", "auth", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 135, p95: 290, p99: 480, samples: 14 },
  },
  {
    slug: "okta",
    dimensions: {
      I1: 8.0, I2: 7.0, I3: 7.0, I4: 7.0, I5: 7.0, I6: 5.5, I7: 7.0,
      F1: 7.0, F2: 6.5, F3: 6.5, F4: 6.5, F5: 7.0, F6: 6.5, F7: 5.5,
      O1: 6.5, O2: 6.5, O3: 6.5,
    },
    access_dimensions: { A1: 3.5, A2: 3.0, A3: 3.5, A4: 5.0, A5: 6.0, A6: 6.0 },
    evidence_count: 46, freshness: "4 hours ago",
    probe_types: ["health", "auth", "schema"],
    production_telemetry: true,
    probe_latency_ms: { p50: 170, p95: 400, p99: 700, samples: 12 },
    auth_required: true,
  },
  {
    slug: "firebase-auth",
    dimensions: {
      I1: 9.0, I2: 8.0, I3: 8.0, I4: 8.0, I5: 8.0, I6: 7.0, I7: 8.0,
      F1: 7.5, F2: 7.0, F3: 7.5, F4: 6.5, F5: 7.5, F6: 7.0, F7: 6.0,
      O1: 7.5, O2: 7.5, O3: 6.5,
    },
    access_dimensions: { A1: 4.0, A2: 4.0, A3: 4.0, A4: 5.5, A5: 6.5, A6: 6.5 },
    evidence_count: 55, freshness: "1 hour ago",
    probe_types: ["health", "auth", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 95, p95: 220, p99: 380, samples: 16 },
  },
  {
    slug: "clerk",
    dimensions: {
      I1: 8.5, I2: 8.5, I3: 8.5, I4: 8.0, I5: 8.0, I6: 8.0, I7: 8.0,
      F1: 8.5, F2: 8.5, F3: 8.5, F4: 8.0, F5: 8.0, F6: 8.5, F7: 8.0,
      O1: 8.5, O2: 8.5, O3: 7.5,
    },
    access_dimensions: { A1: 6.0, A2: 5.5, A3: 6.0, A4: 7.0, A5: 7.5, A6: 8.0 },
    evidence_count: 30, freshness: "30 minutes ago",
    probe_types: ["health", "auth", "schema", "functional"],
    production_telemetry: false,
    probe_latency_ms: { p50: 80, p95: 180, p99: 300, samples: 10 },
  },
  {
    slug: "cognito",
    dimensions: {
      I1: 8.5, I2: 7.0, I3: 7.0, I4: 7.5, I5: 7.5, I6: 5.0, I7: 7.0,
      F1: 6.0, F2: 5.5, F3: 6.0, F4: 5.5, F5: 6.5, F6: 5.0, F7: 4.5,
      O1: 6.0, O2: 6.0, O3: 5.0,
    },
    access_dimensions: { A1: 3.0, A2: 3.0, A3: 3.0, A4: 4.0, A5: 5.5, A6: 5.0 },
    evidence_count: 44, freshness: "6 hours ago",
    probe_types: ["health", "auth", "schema"],
    production_telemetry: true,
    probe_latency_ms: { p50: 200, p95: 460, p99: 800, samples: 12 },
    auth_required: true,
  },

  // ──── Calendar (5) ────
  {
    slug: "cal-com",
    dimensions: {
      I1: 7.5, I2: 7.5, I3: 8.0, I4: 7.0, I5: 7.0, I6: 7.0, I7: 7.0,
      F1: 8.0, F2: 7.5, F3: 8.0, F4: 7.5, F5: 7.0, F6: 8.0, F7: 7.5,
      O1: 7.5, O2: 7.5, O3: 7.0,
    },
    access_dimensions: { A1: 5.5, A2: 5.5, A3: 5.5, A4: 6.5, A5: 7.5, A6: 8.0 },
    evidence_count: 28, freshness: "1 hour ago",
    probe_types: ["health", "schema", "functional"],
    production_telemetry: false,
    probe_latency_ms: { p50: 115, p95: 260, p99: 430, samples: 8 },
  },
  {
    slug: "calendly",
    dimensions: {
      I1: 7.5, I2: 7.0, I3: 7.5, I4: 6.5, I5: 6.5, I6: 6.5, I7: 6.5,
      F1: 7.0, F2: 6.5, F3: 7.0, F4: 7.0, F5: 6.0, F6: 7.0, F7: 6.0,
      O1: 6.5, O2: 6.5, O3: 6.0,
    },
    access_dimensions: { A1: 4.0, A2: 4.0, A3: 4.0, A4: 5.5, A5: 6.5, A6: 7.0 },
    evidence_count: 32, freshness: "3 hours ago",
    probe_types: ["health", "auth", "schema"],
    production_telemetry: false,
    probe_latency_ms: { p50: 140, p95: 320, p99: 540, samples: 9 },
  },
  {
    slug: "google-calendar",
    dimensions: {
      I1: 9.0, I2: 7.5, I3: 8.0, I4: 7.0, I5: 8.0, I6: 6.5, I7: 8.0,
      F1: 7.5, F2: 7.0, F3: 7.5, F4: 6.0, F5: 7.5, F6: 7.0, F7: 6.0,
      O1: 7.5, O2: 7.0, O3: 7.0,
    },
    access_dimensions: { A1: 4.0, A2: 3.5, A3: 4.0, A4: 5.0, A5: 6.5, A6: 6.5 },
    evidence_count: 60, freshness: "2 hours ago",
    probe_types: ["health", "auth", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 130, p95: 300, p99: 500, samples: 18 },
    auth_required: true,
  },
  {
    slug: "microsoft-outlook",
    dimensions: {
      I1: 8.5, I2: 7.0, I3: 7.0, I4: 7.0, I5: 7.5, I6: 5.5, I7: 7.0,
      F1: 7.0, F2: 6.0, F3: 6.5, F4: 5.5, F5: 7.0, F6: 6.0, F7: 5.0,
      O1: 6.5, O2: 6.5, O3: 6.0,
    },
    access_dimensions: { A1: 3.5, A2: 3.0, A3: 3.5, A4: 4.5, A5: 6.0, A6: 5.5 },
    evidence_count: 52, freshness: "4 hours ago",
    probe_types: ["health", "auth", "schema"],
    production_telemetry: true,
    probe_latency_ms: { p50: 190, p95: 440, p99: 780, samples: 14 },
    auth_required: true,
  },
  {
    slug: "when2meet",
    dimensions: {
      I1: 5.0, I2: 5.5, I3: 6.0, I4: 4.0, I5: 4.5, I6: 5.0, I7: 4.5,
      F1: 3.5, F2: 3.0, F3: 3.5, F4: 5.0, F5: 3.0, F6: 2.5, F7: 3.5,
      O1: 4.0, O2: 3.5, O3: 2.5,
    },
    access_dimensions: { A1: 1.5, A2: 1.5, A3: 1.5, A4: 2.0, A5: 3.5, A6: 3.0 },
    evidence_count: 12, freshness: "2 days ago",
    probe_types: ["health"],
    production_telemetry: false,
    probe_latency_ms: { p50: 350, p95: 800, p99: 1400, samples: 4 },
    docs_unavailable: true,
  },

  // ──── Analytics (5) ────
  {
    slug: "mixpanel",
    dimensions: {
      I1: 8.0, I2: 7.0, I3: 7.5, I4: 7.0, I5: 7.5, I6: 6.5, I7: 7.0,
      F1: 7.5, F2: 7.0, F3: 7.0, F4: 7.0, F5: 6.5, F6: 7.5, F7: 6.5,
      O1: 7.0, O2: 6.5, O3: 5.5,
    },
    access_dimensions: { A1: 4.5, A2: 4.0, A3: 4.5, A4: 5.5, A5: 6.5, A6: 7.0 },
    evidence_count: 38, freshness: "3 hours ago",
    probe_types: ["health", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 160, p95: 370, p99: 620, samples: 10 },
  },
  {
    slug: "segment",
    dimensions: {
      I1: 8.0, I2: 7.5, I3: 8.0, I4: 7.5, I5: 8.0, I6: 7.0, I7: 7.5,
      F1: 7.5, F2: 7.0, F3: 7.5, F4: 7.0, F5: 7.5, F6: 7.5, F7: 6.5,
      O1: 7.5, O2: 7.0, O3: 7.0,
    },
    access_dimensions: { A1: 4.5, A2: 4.5, A3: 4.5, A4: 6.0, A5: 7.0, A6: 7.0 },
    evidence_count: 44, freshness: "2 hours ago",
    probe_types: ["health", "schema", "functional", "webhook"],
    production_telemetry: true,
    probe_latency_ms: { p50: 125, p95: 280, p99: 460, samples: 12 },
  },
  {
    slug: "posthog",
    dimensions: {
      I1: 7.5, I2: 7.5, I3: 8.0, I4: 7.0, I5: 7.0, I6: 7.0, I7: 7.0,
      F1: 8.0, F2: 7.5, F3: 7.5, F4: 7.5, F5: 7.0, F6: 8.0, F7: 7.0,
      O1: 7.5, O2: 7.5, O3: 6.5,
    },
    access_dimensions: { A1: 5.5, A2: 5.5, A3: 5.5, A4: 6.5, A5: 7.5, A6: 8.0 },
    evidence_count: 30, freshness: "1 hour ago",
    probe_types: ["health", "schema", "functional"],
    production_telemetry: false,
    probe_latency_ms: { p50: 110, p95: 250, p99: 420, samples: 9 },
  },
  {
    slug: "amplitude",
    dimensions: {
      I1: 7.5, I2: 7.0, I3: 7.0, I4: 6.5, I5: 7.0, I6: 6.0, I7: 6.5,
      F1: 7.0, F2: 6.5, F3: 6.5, F4: 6.5, F5: 6.0, F6: 7.0, F7: 6.0,
      O1: 6.5, O2: 6.0, O3: 5.5,
    },
    access_dimensions: { A1: 4.0, A2: 3.5, A3: 4.0, A4: 5.0, A5: 6.0, A6: 6.5 },
    evidence_count: 36, freshness: "5 hours ago",
    probe_types: ["health", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 175, p95: 400, p99: 680, samples: 10 },
  },
  {
    slug: "heap",
    dimensions: {
      I1: 7.0, I2: 6.5, I3: 7.0, I4: 6.0, I5: 6.5, I6: 6.0, I7: 6.0,
      F1: 6.0, F2: 5.5, F3: 6.0, F4: 6.0, F5: 5.5, F6: 6.0, F7: 5.5,
      O1: 6.0, O2: 5.5, O3: 5.0,
    },
    access_dimensions: { A1: 3.5, A2: 3.0, A3: 3.5, A4: 4.5, A5: 5.5, A6: 6.0 },
    evidence_count: 24, freshness: "8 hours ago",
    probe_types: ["health", "schema"],
    production_telemetry: false,
    probe_latency_ms: { p50: 200, p95: 470, p99: 800, samples: 7 },
  },

  // ──── Search (4) ────
  {
    slug: "algolia",
    dimensions: {
      I1: 9.0, I2: 9.5, I3: 8.5, I4: 8.0, I5: 8.5, I6: 9.0, I7: 8.5,
      F1: 8.5, F2: 8.5, F3: 8.5, F4: 7.5, F5: 8.0, F6: 8.5, F7: 7.5,
      O1: 8.5, O2: 8.0, O3: 7.0,
    },
    access_dimensions: { A1: 5.5, A2: 5.0, A3: 5.5, A4: 6.5, A5: 7.5, A6: 7.5 },
    evidence_count: 48, freshness: "1 hour ago",
    probe_types: ["health", "schema", "load", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 28, p95: 65, p99: 110, samples: 16 },
  },
  {
    slug: "meilisearch",
    dimensions: {
      I1: 7.5, I2: 9.0, I3: 8.5, I4: 7.0, I5: 7.5, I6: 8.5, I7: 7.5,
      F1: 8.5, F2: 8.0, F3: 8.5, F4: 8.0, F5: 7.5, F6: 9.0, F7: 8.0,
      O1: 8.0, O2: 8.0, O3: 6.0,
    },
    access_dimensions: { A1: 6.5, A2: 6.5, A3: 6.5, A4: 7.5, A5: 8.0, A6: 8.5 },
    evidence_count: 26, freshness: "2 hours ago",
    probe_types: ["health", "schema", "load"],
    production_telemetry: false,
    probe_latency_ms: { p50: 15, p95: 40, p99: 75, samples: 10 },
  },
  {
    slug: "elasticsearch",
    dimensions: {
      I1: 8.0, I2: 7.0, I3: 7.0, I4: 7.0, I5: 7.5, I6: 5.0, I7: 7.0,
      F1: 7.0, F2: 6.5, F3: 7.0, F4: 6.0, F5: 7.0, F6: 6.5, F7: 5.5,
      O1: 7.0, O2: 6.5, O3: 5.5,
    },
    access_dimensions: { A1: 5.0, A2: 5.0, A3: 5.0, A4: 6.0, A5: 7.0, A6: 7.0 },
    evidence_count: 56, freshness: "6 hours ago",
    probe_types: ["health", "schema", "load", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 45, p95: 120, p99: 220, samples: 18 },
  },
  {
    slug: "typesense",
    dimensions: {
      I1: 7.0, I2: 9.0, I3: 8.5, I4: 7.0, I5: 7.5, I6: 8.5, I7: 7.5,
      F1: 8.0, F2: 7.5, F3: 8.0, F4: 8.0, F5: 7.0, F6: 8.5, F7: 7.5,
      O1: 7.5, O2: 7.5, O3: 5.5,
    },
    access_dimensions: { A1: 6.0, A2: 6.0, A3: 6.0, A4: 7.0, A5: 7.5, A6: 8.0 },
    evidence_count: 22, freshness: "4 hours ago",
    probe_types: ["health", "schema", "load"],
    production_telemetry: false,
    probe_latency_ms: { p50: 18, p95: 48, p99: 85, samples: 8 },
  },

  // ──── DevOps (6) ────
  {
    slug: "vercel",
    dimensions: {
      I1: 9.0, I2: 8.5, I3: 8.0, I4: 7.5, I5: 8.0, I6: 8.0, I7: 8.0,
      F1: 8.0, F2: 8.0, F3: 8.0, F4: 7.5, F5: 7.5, F6: 8.0, F7: 7.5,
      O1: 8.0, O2: 8.0, O3: 7.5,
    },
    access_dimensions: { A1: 5.0, A2: 5.0, A3: 5.0, A4: 6.5, A5: 7.5, A6: 7.5 },
    evidence_count: 42, freshness: "1 hour ago",
    probe_types: ["health", "schema", "functional", "load"],
    production_telemetry: true,
    probe_latency_ms: { p50: 95, p95: 220, p99: 370, samples: 12 },
  },
  {
    slug: "netlify",
    dimensions: {
      I1: 8.0, I2: 7.5, I3: 7.5, I4: 7.0, I5: 7.0, I6: 7.0, I7: 7.0,
      F1: 7.0, F2: 7.0, F3: 7.0, F4: 7.0, F5: 6.5, F6: 7.5, F7: 6.5,
      O1: 7.0, O2: 7.0, O3: 6.5,
    },
    access_dimensions: { A1: 4.5, A2: 4.5, A3: 4.5, A4: 5.5, A5: 7.0, A6: 7.0 },
    evidence_count: 38, freshness: "3 hours ago",
    probe_types: ["health", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 120, p95: 280, p99: 460, samples: 10 },
  },
  {
    slug: "aws",
    dimensions: {
      I1: 9.5, I2: 7.5, I3: 7.5, I4: 8.0, I5: 8.5, I6: 5.0, I7: 8.5,
      F1: 7.0, F2: 6.0, F3: 7.0, F4: 5.0, F5: 8.0, F6: 6.0, F7: 4.5,
      O1: 7.5, O2: 7.0, O3: 6.5,
    },
    access_dimensions: { A1: 3.0, A2: 3.0, A3: 3.0, A4: 4.0, A5: 6.0, A6: 5.5 },
    evidence_count: 68, freshness: "30 minutes ago",
    probe_types: ["health", "auth", "schema", "load", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 150, p95: 350, p99: 600, samples: 20 },
    auth_required: true,
  },
  {
    slug: "digital-ocean",
    dimensions: {
      I1: 8.0, I2: 7.5, I3: 8.0, I4: 7.5, I5: 7.5, I6: 7.0, I7: 7.5,
      F1: 7.5, F2: 7.5, F3: 7.5, F4: 7.5, F5: 7.0, F6: 7.5, F7: 7.0,
      O1: 7.5, O2: 7.0, O3: 6.5,
    },
    access_dimensions: { A1: 5.0, A2: 5.0, A3: 5.0, A4: 6.0, A5: 7.0, A6: 7.0 },
    evidence_count: 40, freshness: "2 hours ago",
    probe_types: ["health", "auth", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 130, p95: 300, p99: 500, samples: 12 },
  },
  {
    slug: "render",
    dimensions: {
      I1: 7.5, I2: 7.5, I3: 8.0, I4: 7.0, I5: 7.0, I6: 7.5, I7: 7.0,
      F1: 7.5, F2: 7.5, F3: 7.5, F4: 7.5, F5: 7.0, F6: 8.0, F7: 7.0,
      O1: 7.5, O2: 7.5, O3: 6.5,
    },
    access_dimensions: { A1: 5.0, A2: 5.0, A3: 5.0, A4: 6.5, A5: 7.0, A6: 7.5 },
    evidence_count: 28, freshness: "2 hours ago",
    probe_types: ["health", "schema", "functional"],
    production_telemetry: false,
    probe_latency_ms: { p50: 105, p95: 240, p99: 400, samples: 8 },
  },
  {
    slug: "heroku",
    dimensions: {
      I1: 7.0, I2: 6.5, I3: 6.5, I4: 6.5, I5: 6.5, I6: 4.5, I7: 6.0,
      F1: 6.0, F2: 6.0, F3: 6.0, F4: 6.5, F5: 5.5, F6: 6.0, F7: 5.5,
      O1: 6.0, O2: 5.5, O3: 5.0,
    },
    access_dimensions: { A1: 3.5, A2: 3.5, A3: 3.5, A4: 5.0, A5: 6.0, A6: 6.0 },
    evidence_count: 42, freshness: "8 hours ago",
    probe_types: ["health", "schema", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 180, p95: 420, p99: 720, samples: 12 },
  },

  // ──── Social (3) ────
  {
    slug: "twitter-api",
    dimensions: {
      I1: 7.0, I2: 6.0, I3: 5.5, I4: 5.5, I5: 6.0, I6: 6.0, I7: 5.5,
      F1: 6.0, F2: 5.0, F3: 5.5, F4: 5.0, F5: 5.5, F6: 4.5, F7: 5.0,
      O1: 5.0, O2: 4.5, O3: 5.0,
    },
    access_dimensions: { A1: 2.5, A2: 2.0, A3: 2.0, A4: 3.0, A5: 4.0, A6: 4.5 },
    evidence_count: 50, freshness: "6 hours ago",
    probe_types: ["health", "auth", "schema"],
    production_telemetry: true,
    probe_latency_ms: { p50: 220, p95: 520, p99: 950, samples: 14 },
    auth_required: true,
  },
  {
    slug: "linkedin-api",
    dimensions: {
      I1: 7.0, I2: 6.0, I3: 5.5, I4: 5.0, I5: 5.5, I6: 5.5, I7: 5.5,
      F1: 5.0, F2: 4.5, F3: 5.0, F4: 4.5, F5: 5.0, F6: 4.5, F7: 4.5,
      O1: 5.0, O2: 4.5, O3: 4.0,
    },
    access_dimensions: { A1: 2.0, A2: 2.0, A3: 2.0, A4: 3.0, A5: 4.0, A6: 4.0 },
    evidence_count: 42, freshness: "8 hours ago",
    probe_types: ["health", "auth", "schema"],
    production_telemetry: true,
    probe_latency_ms: { p50: 250, p95: 580, p99: 1000, samples: 10 },
    auth_required: true,
  },
  {
    slug: "bluesky-api",
    dimensions: {
      I1: 6.5, I2: 7.0, I3: 7.5, I4: 6.0, I5: 6.5, I6: 7.0, I7: 6.0,
      F1: 7.0, F2: 6.5, F3: 7.0, F4: 6.5, F5: 6.0, F6: 6.5, F7: 6.5,
      O1: 6.5, O2: 6.5, O3: 5.0,
    },
    access_dimensions: { A1: 5.0, A2: 5.0, A3: 5.0, A4: 6.0, A5: 7.0, A6: 7.5 },
    evidence_count: 18, freshness: "4 hours ago",
    probe_types: ["health", "schema"],
    production_telemetry: false,
    probe_latency_ms: { p50: 160, p95: 380, p99: 640, samples: 6 },
  },

  // ──── AI (6) ────
  {
    slug: "openai",
    dimensions: {
      I1: 8.0, I2: 6.5, I3: 7.0, I4: 7.5, I5: 7.5, I6: 5.0, I7: 6.5,
      F1: 8.0, F2: 7.5, F3: 7.5, F4: 7.5, F5: 7.0, F6: 7.5, F7: 6.0,
      O1: 7.0, O2: 6.5, O3: 5.5,
    },
    access_dimensions: { A1: 5.0, A2: 4.5, A3: 5.0, A4: 6.0, A5: 7.0, A6: 7.0 },
    evidence_count: 65, freshness: "20 minutes ago",
    probe_types: ["health", "auth", "schema", "load", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 450, p95: 1200, p99: 2500, samples: 18 },
  },
  {
    slug: "anthropic",
    dimensions: {
      I1: 8.0, I2: 6.5, I3: 8.0, I4: 7.5, I5: 7.5, I6: 5.5, I7: 7.0,
      F1: 8.5, F2: 8.0, F3: 8.0, F4: 8.0, F5: 7.5, F6: 8.0, F7: 7.0,
      O1: 7.5, O2: 7.5, O3: 5.5,
    },
    access_dimensions: { A1: 5.0, A2: 5.0, A3: 5.0, A4: 6.5, A5: 7.0, A6: 7.5 },
    evidence_count: 45, freshness: "15 minutes ago",
    probe_types: ["health", "auth", "schema", "load", "functional"],
    production_telemetry: true,
    probe_latency_ms: { p50: 500, p95: 1400, p99: 2800, samples: 14 },
  },
  {
    slug: "huggingface",
    dimensions: {
      I1: 7.0, I2: 6.0, I3: 7.0, I4: 6.5, I5: 6.0, I6: 4.5, I7: 5.5,
      F1: 7.0, F2: 6.0, F3: 6.5, F4: 7.0, F5: 5.5, F6: 7.5, F7: 5.5,
      O1: 6.0, O2: 6.0, O3: 4.5,
    },
    access_dimensions: { A1: 5.5, A2: 5.5, A3: 5.5, A4: 6.5, A5: 7.5, A6: 8.0 },
    evidence_count: 35, freshness: "3 hours ago",
    probe_types: ["health", "schema", "functional"],
    production_telemetry: false,
    probe_latency_ms: { p50: 600, p95: 1800, p99: 3500, samples: 10 },
  },
  {
    slug: "replicate",
    dimensions: {
      I1: 7.0, I2: 6.0, I3: 7.5, I4: 6.5, I5: 6.5, I6: 4.0, I7: 5.5,
      F1: 7.5, F2: 7.0, F3: 7.5, F4: 7.5, F5: 6.5, F6: 8.0, F7: 7.0,
      O1: 7.0, O2: 7.0, O3: 6.0,
    },
    access_dimensions: { A1: 5.5, A2: 5.5, A3: 5.5, A4: 6.5, A5: 7.5, A6: 8.0 },
    evidence_count: 28, freshness: "2 hours ago",
    probe_types: ["health", "schema", "functional"],
    production_telemetry: false,
    probe_latency_ms: { p50: 550, p95: 1600, p99: 3200, samples: 8 },
  },
  {
    slug: "cohere",
    dimensions: {
      I1: 7.5, I2: 7.0, I3: 7.5, I4: 7.0, I5: 7.0, I6: 6.0, I7: 6.5,
      F1: 7.5, F2: 7.0, F3: 7.5, F4: 7.0, F5: 6.5, F6: 7.5, F7: 6.5,
      O1: 7.0, O2: 7.0, O3: 5.5,
    },
    access_dimensions: { A1: 5.0, A2: 5.0, A3: 5.0, A4: 6.0, A5: 7.0, A6: 7.5 },
    evidence_count: 30, freshness: "3 hours ago",
    probe_types: ["health", "auth", "schema", "functional"],
    production_telemetry: false,
    probe_latency_ms: { p50: 400, p95: 1100, p99: 2200, samples: 10 },
  },
  {
    slug: "together-ai",
    dimensions: {
      I1: 7.0, I2: 7.0, I3: 7.5, I4: 7.0, I5: 7.0, I6: 5.5, I7: 6.5,
      F1: 7.5, F2: 7.0, F3: 7.5, F4: 7.5, F5: 6.5, F6: 7.5, F7: 7.0,
      O1: 7.0, O2: 7.0, O3: 5.5,
    },
    access_dimensions: { A1: 5.0, A2: 5.0, A3: 5.0, A4: 6.5, A5: 7.5, A6: 7.5 },
    evidence_count: 22, freshness: "2 hours ago",
    probe_types: ["health", "schema", "functional"],
    production_telemetry: false,
    probe_latency_ms: { p50: 380, p95: 950, p99: 1900, samples: 8 },
  },
];
