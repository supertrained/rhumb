import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title:
    "Why 'Agent Cards' Are Invisible to Agents — and What to Do Instead | Rhumb",
  description:
    "We fetched Ramp's Agent Cards page the way an agent would. It extracted 3 words. Here's the full audit and the fix pattern.",
  alternates: { canonical: "/blog/agent-cards-invisible" },
  openGraph: {
    title: "Why 'Agent Cards' Are Invisible to Agents",
    description:
      "We fetched Ramp's Agent Cards page the way an agent would. It extracted 3 words. The full audit and fix pattern.",
    type: "article",
    publishedTime: "2026-03-14T22:00:00Z",
    authors: ["Pedro Nunes"],
    images: [{ url: "/api/og?title=Why+Agent+Cards+Are+Invisible+to+Agents&subtitle=3+words.+That's+all+an+agent+sees.", width: 1200, height: 630 }],
    url: "https://rhumb.dev/blog/agent-cards-invisible",
    siteName: "Rhumb",
  },
  twitter: {
    card: "summary_large_image",
    title: "Why 'Agent Cards' Are Invisible to Agents",
    description:
      "We fetched Ramp's Agent Cards page the way an agent would. It extracted 3 words.",
    images: ["/api/og?title=Why+Agent+Cards+Are+Invisible+to+Agents&subtitle=3+words.+That's+all+an+agent+sees."],
  },
};

const ARTICLE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Article",
  headline: "Why 'Agent Cards' Are Invisible to Agents",
  description:
    "We fetched Ramp's Agent Cards page the way an agent would. It extracted 3 words. Here's the full audit and the fix pattern.",
  author: { "@type": "Person", name: "Pedro Nunes" },
  publisher: {
    "@type": "Organization",
    name: "Rhumb",
    url: "https://rhumb.dev",
  },
  datePublished: "2026-03-14T22:00:00Z",
  url: "https://rhumb.dev/blog/agent-cards-invisible",
  mainEntityOfPage: "https://rhumb.dev/blog/agent-cards-invisible",
};

export default function AgentCardsInvisiblePost() {
  return (
    <div className="bg-navy min-h-screen">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ARTICLE_JSON_LD) }}
      />

      {/* Header */}
      <section className="relative border-b border-slate-800 overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-30 pointer-events-none" />
        <div className="relative max-w-3xl mx-auto px-6 py-14">
          <div className="flex items-center gap-3 mb-4">
            <Link
              href="/blog"
              className="text-xs font-mono text-slate-500 hover:text-amber transition-colors"
            >
              ← Blog
            </Link>
            <span className="text-slate-800">·</span>
            <span className="text-xs font-mono text-amber uppercase tracking-widest">
              Agent Readability
            </span>
            <span className="text-slate-800">·</span>
            <span className="text-xs font-mono text-slate-500">
              March 14, 2026
            </span>
            <span className="text-slate-800">·</span>
            <span className="text-xs font-mono text-slate-600">
              7 min read
            </span>
          </div>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 tracking-tight leading-tight">
            Why &lsquo;Agent Cards&rsquo; Are Invisible to Agents
          </h1>
          <p className="mt-4 text-slate-400 leading-relaxed text-lg">
            Ramp launched a product literally called &ldquo;Agent Cards&rdquo; at a subdomain literally called <code className="text-amber">agents.ramp.com</code>. When an agent fetches the page, it extracts three words.
          </p>
        </div>
      </section>

      {/* Article content */}
      <article className="max-w-3xl mx-auto px-6 py-12 space-y-10">
        {/* The test */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            The test
          </h2>
          <p className="text-slate-300 leading-relaxed">
            We pointed a standard HTTP client at <code className="text-amber">agents.ramp.com/cards</code> and ran readability extraction, the same way every agent framework (LangChain, CrewAI, AutoGPT, OpenAI&rsquo;s browsing) fetches web content. Here&rsquo;s what came back:
          </p>
          <div className="bg-surface border border-slate-800 rounded-xl p-6 font-mono text-sm">
            <p className="text-slate-500 mb-2"># Extracted content:</p>
            <p className="text-slate-100">Agent Cards</p>
            <p className="text-slate-100">Interest</p>
            <p className="text-slate-100">Help</p>
          </div>
          <p className="text-slate-300 leading-relaxed">
            Three words. That&rsquo;s the entire page from an agent&rsquo;s perspective. The product descriptions, the card details, the value proposition &mdash; none of it exists in the server-rendered HTML. It&rsquo;s all JavaScript that executes client-side, behind Cloudflare Rocket Loader.
          </p>
        </section>

        {/* The full scorecard */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            The full scorecard
          </h2>
          <p className="text-slate-300 leading-relaxed">
            We checked every surface an agent uses to understand a page:
          </p>
          <div className="bg-surface border border-slate-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    Surface
                  </th>
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    Result
                  </th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono">Content extraction</td>
                  <td className="py-3 px-5">
                    <span className="text-red-400 font-semibold">3 words</span>
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono">robots.txt</td>
                  <td className="py-3 px-5">
                    <span className="text-red-400">404</span>
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono">llms.txt</td>
                  <td className="py-3 px-5">
                    <span className="text-red-400">404</span>
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono">sitemap.xml</td>
                  <td className="py-3 px-5">
                    <span className="text-red-400">404</span>
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono">JSON-LD</td>
                  <td className="py-3 px-5">
                    <span className="text-red-400">None</span>
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono">Meta description</td>
                  <td className="py-3 px-5">
                    <span className="text-amber">&ldquo;Cards built for agents&rdquo;</span>{" "}
                    <span className="text-slate-500">(4 words)</span>
                  </td>
                </tr>
                <tr>
                  <td className="py-3 px-5 font-mono">OG image</td>
                  <td className="py-3 px-5">
                    <span className="text-green-400">Present</span>{" "}
                    <span className="text-slate-500">(only thing that works)</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* Why this happens */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            Why this happens
          </h2>
          <p className="text-slate-300 leading-relaxed">
            The page is a Next.js app deployed on Vercel with Cloudflare in front. The server returns a minimal HTML shell with React Server Component payloads, and all visible content is hydrated client-side via JavaScript. This is a common pattern for fast, interactive web apps.
          </p>
          <p className="text-slate-300 leading-relaxed">
            The problem: agents don&rsquo;t run JavaScript. When Claude, GPT, Perplexity, or any agent framework fetches a URL, they get the raw HTML. If the raw HTML is empty, the page doesn&rsquo;t exist to them. It doesn&rsquo;t matter how beautiful the client-rendered experience is.
          </p>
          <p className="text-slate-300 leading-relaxed">
            The deeper irony: Ramp set <code className="text-amber">{`<meta name="robots" content="noindex">`}</code> in the HTML. The page is explicitly telling machines not to index it. A page built for agents, telling agents to go away.
          </p>
        </section>

        {/* The SPA anti-pattern */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            The SPA anti-pattern for agent readability
          </h2>
          <p className="text-slate-300 leading-relaxed">
            This isn&rsquo;t a Ramp problem. It&rsquo;s an industry pattern. Most modern web apps are single-page applications that render content client-side. That works fine for humans with browsers. It&rsquo;s catastrophic for agent consumption.
          </p>
          <p className="text-slate-300 leading-relaxed">
            Agents consume content through a simple path: HTTP GET, parse the response, extract structured data. If your server HTML is empty, you don&rsquo;t exist to them. No amount of beautiful React components changes that.
          </p>
          <p className="text-slate-300 leading-relaxed">
            The symptoms are consistent:
          </p>
          <ul className="list-disc list-inside text-slate-300 space-y-2 ml-4">
            <li><code className="text-amber">web_fetch</code> returns fewer than 50 words of content</li>
            <li>No <code className="text-amber">robots.txt</code>, <code className="text-amber">llms.txt</code>, or <code className="text-amber">sitemap.xml</code></li>
            <li>Server HTML contains framework payloads but no readable text</li>
            <li>Browser shows everything after JavaScript executes, but programmatic access sees nothing</li>
          </ul>
        </section>

        {/* What to do instead */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            What to do instead
          </h2>
          <p className="text-slate-300 leading-relaxed">
            Building agent-readable pages is not hard. It&rsquo;s mostly about what you server-render. Here&rsquo;s a comparison of what agents extract from different approaches:
          </p>
          <div className="bg-surface border border-slate-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    Surface
                  </th>
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    Client-only SPA
                  </th>
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    Server-rendered
                  </th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono">Homepage</td>
                  <td className="py-3 px-5 text-red-400">3 words</td>
                  <td className="py-3 px-5 text-green-400">~1,100 words</td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono">Product page</td>
                  <td className="py-3 px-5 text-red-400">0 words</td>
                  <td className="py-3 px-5 text-green-400">~2,700 words</td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono">Methodology</td>
                  <td className="py-3 px-5 text-red-400">N/A</td>
                  <td className="py-3 px-5 text-green-400">~4,200 words</td>
                </tr>
                <tr>
                  <td className="py-3 px-5 font-mono">Structured data</td>
                  <td className="py-3 px-5 text-red-400">None</td>
                  <td className="py-3 px-5 text-green-400">JSON-LD, llms.txt, API</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-slate-400 text-xs mt-2">
            Left column: agents.ramp.com/cards. Right column: rhumb.dev. Both built with Next.js. The difference is server-rendering strategy.
          </p>
        </section>

        {/* The agent readability checklist */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            The agent readability checklist
          </h2>
          <p className="text-slate-300 leading-relaxed">
            If you&rsquo;re building anything agent-facing, run these checks before shipping:
          </p>
          <ol className="list-decimal list-inside text-slate-300 space-y-3 ml-4">
            <li>
              <strong className="text-slate-100">Fetch your own page without JavaScript.</strong>{" "}
              Run <code className="text-amber">curl -s yourpage.com | grep -v script</code> and see what&rsquo;s left. If the answer is &ldquo;nothing,&rdquo; agents can&rsquo;t see you.
            </li>
            <li>
              <strong className="text-slate-100">Add an llms.txt.</strong>{" "}
              This is the emerging standard for telling language models what your site is and what it offers. Think of it as robots.txt but for LLMs.
            </li>
            <li>
              <strong className="text-slate-100">Server-render your content.</strong>{" "}
              Next.js supports this natively with Server Components. Use <code className="text-amber">generateStaticParams</code> or server-side rendering for any page agents need to read.
            </li>
            <li>
              <strong className="text-slate-100">Add JSON-LD structured data.</strong>{" "}
              Schema.org markup helps agents understand what they&rsquo;re looking at: is this a product? A review? An organization?
            </li>
            <li>
              <strong className="text-slate-100">Ship a sitemap.xml.</strong>{" "}
              Agents use sitemaps to discover pages they might not find through navigation.
            </li>
            <li>
              <strong className="text-slate-100">Include extractable text alongside interactive components.</strong>{" "}
              If your leaderboard is a dynamic list, add a server-rendered summary paragraph above it with the key data points in plain text.
            </li>
          </ol>
        </section>

        {/* The bigger point */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            The bigger point
          </h2>
          <p className="text-slate-300 leading-relaxed">
            &ldquo;Agent-native&rdquo; is becoming a marketing term. Companies are launching &ldquo;agent&rdquo; products with agent-hostile architectures. The page is a billboard for humans who read about agents, not a surface that agents actually consume.
          </p>
          <p className="text-slate-300 leading-relaxed">
            The test is simple: can your intended user actually use your product? If your user is an agent and your product is invisible to agents, you built a landing page, not a product.
          </p>
          <p className="text-slate-300 leading-relaxed">
            We build{" "}
            <Link href="/" className="text-amber hover:underline">
              Rhumb
            </Link>{" "}
            with this principle at the core. Every page server-renders its content. Every score is available through{" "}
            <Link href="/llms.txt" className="text-amber hover:underline">
              llms.txt
            </Link>
            , a{" "}
            <Link href="/docs" className="text-amber hover:underline">
              REST API
            </Link>
            , and an{" "}
            <Link
              href="https://www.npmjs.com/package/rhumb-mcp"
              className="text-amber hover:underline"
            >
              MCP server
            </Link>
            . Because if you&rsquo;re building for agents, the first question is whether agents can find you.
          </p>
        </section>

        {/* Divider */}
        <hr className="border-slate-800" />

        {/* Footer */}
        <footer className="text-slate-500 text-sm space-y-3">
          <p>
            <strong className="text-slate-400">Methodology:</strong> Content extraction via standard HTTP GET + readability parser. No JavaScript execution. This matches the default behavior of LangChain&rsquo;s WebBaseLoader, CrewAI&rsquo;s scrape tool, AutoGPT&rsquo;s web access, and OpenAI&rsquo;s browsing tool.
          </p>
          <p>
            <strong className="text-slate-400">Disclosure:</strong> Ramp Agent Cards is a scored service in the Rhumb directory. This analysis was conducted independently of our scoring methodology. Ramp&rsquo;s card product may work well for its intended use case. Our audit is specifically about whether agents can discover and read the page.
          </p>
          <p>
            We scored Ramp Agent Cards as a service on Rhumb.{" "}
            <Link
              href="/service/ramp-agent-cards"
              className="text-amber hover:underline"
            >
              See the full score →
            </Link>
          </p>
        </footer>
      </article>
    </div>
  );
}
