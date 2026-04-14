export interface ActivationPath {
  kicker: string;
  title: string;
  badge: string;
  href: string;
  summary: string;
  detail: string;
  tone: string;
}

export const PRIMARY_ACTIVATION_PATHS: ActivationPath[] = [
  {
    kicker: "Evaluator path",
    title: "Evaluating with curl",
    badge: "Free reads",
    href: "/quickstart#rest-path",
    summary:
      "Start with the free read endpoints. See real responses, learn the product model, and judge the trust layer before signup.",
    detail:
      "Best when you are sizing up Rhumb, sharing a first link, or validating the discovery story with minimal setup.",
    tone: "border-slate-700 bg-slate-900/70 text-slate-300",
  },
  {
    kicker: "Builder path",
    title: "Building an agent",
    badge: "MCP first",
    href: "/quickstart#mcp-path",
    summary:
      "Install the MCP server or use the starter prompt. Reach for capability IDs when the agent needs executable actions, not just vendor names.",
    detail:
      "Best when Claude, Codex, Cursor, or another runtime already speaks tools and should keep Rhumb inside the loop.",
    tone: "border-amber/20 bg-amber/10 text-amber",
  },
  {
    kicker: "Operator path",
    title: "Need an account and reusable key",
    badge: "Default rail",
    href: "/auth/login",
    summary:
      "Sign up for identity, add credits, then execute with X-Rhumb-Key. Signup creates the account. Funding unlocks governed execution.",
    detail:
      "Best when you want managed routing, dashboard controls, spend visibility, and repeat traffic on one stable key.",
    tone: "border-emerald-500/20 bg-emerald-500/10 text-emerald-300",
  },
];
