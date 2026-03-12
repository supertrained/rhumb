import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Changelog",
  description:
    "What's new in Rhumb — changelog of releases, features, and improvements to the AN Score and platform.",
  alternates: { canonical: "/changelog" },
  openGraph: {
    title: "Changelog — Rhumb",
    description: "Track every release and improvement to Rhumb's AN Score platform.",
    type: "website",
    url: "https://rhumb.dev/changelog",
    siteName: "Rhumb",
  },
};

const ENTRIES = [
  {
    version: "v0.3.2",
    date: "March 11, 2026",
    items: [
      "Failure modes live for top 10 services (20 curated entries with severity, agent impact, and workarounds)",
      "Self-score blog: \"We Scored Ourselves First\" — honest 3.5/10 self-assessment published",
      "Score explanation synthesis from rationale data (no more empty explanation fields)",
      "Blog rendering fixed (MDX → TSX conversion for Next.js compatibility)",
      "Service pages: failure mode UI with color-coded severity badges",
      "Expert panel validation: 5/5 GO for launch readiness",
      "About, Methodology, Pricing, Trust, Docs, Changelog, Privacy, Terms, and Provider pages added",
    ],
  },
  {
    version: "v0.3.1",
    date: "March 10, 2026",
    items: [
      "Service integration guides expanded across scored services (guide count under re-verification)",
      "Analytics trifecta: GA4, Google Search Console, and Microsoft Clarity all live",
      "Access Layer deployed to Railway (proxy router, circuit breaker, agent identity, schema detection)",
      "8 Supabase migrations applied (agents, usage events, organizations, schema fingerprints)",
      "Usage analytics middleware instrumented on API routes",
      "AAG Framework blog post: \"The WCAG for AI Agents\"",
    ],
  },
  {
    version: "v0.3.0",
    date: "March 9, 2026",
    items: [
      "Production launch: rhumb.dev live with SSL",
      "UI redesign: dark mode (#0B1120), amber accents, DM Sans + JetBrains Mono",
      "AN Score v0.3: 3-axis scoring (Execution 45%, Access Readiness 40%, Autonomy 15%)",
      "50 services scored across 10 categories on 17 dimensions",
      "MCP server published: npx rhumb-mcp with 4 tools",
      "Dynamic llms.txt for agent discovery",
      "Schema.org structured data, OG/Twitter cards, sitemap, robots.txt",
      "\"Why Stripe Scores 8.1 and PayPal Scores 4.9\" blog post",
    ],
  },
  {
    version: "v0.2.0",
    date: "March 7, 2026",
    items: [
      "Leaderboard pages for all 10 categories",
      "Service detail pages with score breakdown and integration guides",
      "Search functionality across all services",
      "API deployed to Railway with Supabase backend",
      "IndexNow integration for search engine discovery",
    ],
  },
  {
    version: "v0.1.0",
    date: "March 5, 2026",
    items: [
      "Initial scoring engine with 17-dimension AN Score framework",
      "30 services scored",
      "Railway API deployment with FastAPI backend",
      "Supabase database with services and scores tables",
      "Basic web frontend (Next.js 15 + Tailwind 4)",
    ],
  },
  {
    version: "v0.0.1",
    date: "March 2, 2026",
    items: [
      "Project inception",
      "Research synthesis: 4 rounds, 26 panels, 130+ personas",
      "Namespace claimed: rhumb.dev, getrhumb.com, npm \"rhumb\"",
      "Strategy, principles, and build plan authored",
      "GitHub repo initialized (MIT license)",
    ],
  },
];

export default function ChangelogPage() {
  return (
    <div className="bg-navy min-h-screen">
      <div className="max-w-3xl mx-auto px-6 pt-14 pb-24">
        {/* Header */}
        <header className="mb-16">
          <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
            Changelog
          </span>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 leading-tight tracking-tight mt-4 mb-4">
            What&apos;s new
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            Every release, feature, and improvement — from day one.
          </p>
        </header>

        {/* Timeline */}
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-[7px] top-2 bottom-0 w-px bg-slate-800" />

          <div className="space-y-12">
            {ENTRIES.map((entry, i) => (
              <div key={entry.version} className="relative pl-8">
                {/* Dot */}
                <div
                  className={`absolute left-0 top-1.5 w-[15px] h-[15px] rounded-full border-2 ${
                    i === 0
                      ? "bg-amber border-amber"
                      : "bg-navy border-slate-600"
                  }`}
                />

                <div>
                  <div className="flex items-baseline gap-3 mb-3">
                    <span className="font-mono text-sm font-bold text-slate-100">
                      {entry.version}
                    </span>
                    <span className="text-slate-600">·</span>
                    <span className="font-mono text-xs text-slate-500">
                      {entry.date}
                    </span>
                  </div>
                  <ul className="space-y-1.5">
                    {entry.items.map((item, j) => (
                      <li
                        key={j}
                        className="flex items-start gap-2.5 text-sm text-slate-400"
                      >
                        <span className="text-slate-600 mt-1 text-xs">
                          •
                        </span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
