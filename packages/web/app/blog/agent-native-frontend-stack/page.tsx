import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title:
    "The Agent-Native Frontend Stack: What to Build With When Agents Are Your Users | Rhumb",
  description:
    "Most frontend frameworks make agent readability an afterthought. We ranked every major framework by how hard it is to accidentally build something agents can't read.",
  alternates: { canonical: "/blog/agent-native-frontend-stack" },
  openGraph: {
    title: "The Agent-Native Frontend Stack",
    description:
      "We ranked every major frontend framework by how hard it is to accidentally build something agents can't read.",
    type: "article",
    publishedTime: "2026-03-14T01:00:00Z",
    authors: ["Pedro Nunes"],
    images: [
      {
        url: "/api/og?title=The+Agent-Native+Frontend+Stack&subtitle=Ranked+by+how+hard+it+is+to+break+agent+readability",
        width: 1200,
        height: 630,
      },
    ],
    url: "https://rhumb.dev/blog/agent-native-frontend-stack",
    siteName: "Rhumb",
  },
  twitter: {
    card: "summary_large_image",
    title: "The Agent-Native Frontend Stack",
    description:
      "We ranked every major frontend framework by how hard it is to accidentally build something agents can't read.",
    images: [
      "/api/og?title=The+Agent-Native+Frontend+Stack&subtitle=Ranked+by+how+hard+it+is+to+break+agent+readability",
    ],
  },
};

const ARTICLE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Article",
  headline:
    "The Agent-Native Frontend Stack: What to Build With When Agents Are Your Users",
  description:
    "Most frontend frameworks make agent readability an afterthought. We ranked every major framework by how hard it is to accidentally build something agents can't read.",
  author: { "@type": "Person", name: "Pedro Nunes" },
  publisher: {
    "@type": "Organization",
    name: "Rhumb",
    url: "https://rhumb.dev",
  },
  datePublished: "2026-03-14T01:00:00Z",
  url: "https://rhumb.dev/blog/agent-native-frontend-stack",
  mainEntityOfPage: "https://rhumb.dev/blog/agent-native-frontend-stack",
};

export default function AgentNativeFrontendStackPost() {
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
              Agent Infrastructure
            </span>
            <span className="text-slate-800">·</span>
            <span className="text-xs font-mono text-slate-500">
              March 14, 2026
            </span>
            <span className="text-slate-800">·</span>
            <span className="text-xs font-mono text-slate-600">
              12 min read
            </span>
          </div>
          <h1 className="font-display font-bold text-3xl sm:text-4xl text-slate-100 tracking-tight leading-tight">
            The Agent-Native Frontend Stack
          </h1>
          <p className="mt-4 text-slate-400 leading-relaxed text-lg">
            Most frontend frameworks make agent readability an afterthought.
            We ranked every major framework by one question:{" "}
            <strong className="text-slate-200">
              how hard is it to accidentally build something agents can&rsquo;t
              read?
            </strong>
          </p>
        </div>
      </section>

      {/* Article content */}
      <article className="max-w-3xl mx-auto px-6 py-12 space-y-12">
        {/* The problem */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            The problem nobody talks about
          </h2>
          <p className="text-slate-300 leading-relaxed">
            Every week, another company launches a page &ldquo;for agents.&rdquo;
            Developer portals. Agent card directories. API marketplaces. Most of
            them are invisible to the agents they claim to serve.
          </p>
          <p className="text-slate-300 leading-relaxed">
            The reason is almost always the same: the frontend framework made the
            wrong thing easy. A React SPA ships zero server-rendered content by
            default. An Angular app hides everything behind client-side routing.
            A Vue app with Cloudflare Rocket Loader defers all script execution.
            The developer didn&rsquo;t choose to be invisible to agents &mdash;
            they chose a popular framework and followed its defaults.
          </p>
          <p className="text-slate-300 leading-relaxed">
            When an agent fetches a URL, it makes an HTTP GET request and parses
            the HTML response. No browser. No JavaScript engine. No waiting for
            hydration. If the content isn&rsquo;t in the initial HTML, it
            doesn&rsquo;t exist.
          </p>
          <p className="text-slate-300 leading-relaxed">
            This isn&rsquo;t a niche concern. It&rsquo;s the primary way agents
            interact with the web. LangChain, CrewAI, AutoGPT, Claude&rsquo;s
            computer use, OpenAI&rsquo;s browsing &mdash; they all start with an
            HTTP GET. The framework you choose determines whether agents can read
            your site before you write a single line of application code.
          </p>
        </section>

        {/* The ranking criteria */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            How we ranked
          </h2>
          <p className="text-slate-300 leading-relaxed">
            We evaluated every major frontend framework against one criterion:{" "}
            <strong className="text-slate-200">
              what does the default output look like to an agent?
            </strong>
          </p>
          <p className="text-slate-300 leading-relaxed">
            Not &ldquo;can it be configured to be agent-readable.&rdquo;
            Everything can. The question is what happens when a developer follows
            the getting-started guide, uses the default project template, and
            ships without thinking about agents at all. That default behavior is
            the framework&rsquo;s actual opinion about agent readability.
          </p>
          <p className="text-slate-300 leading-relaxed">
            We also tested six agent-readability checks against a fresh project
            from each framework:
          </p>
          <div className="bg-surface border border-slate-800 rounded-xl p-6 font-mono text-sm space-y-2">
            <p className="text-slate-400">
              <span className="text-amber">1.</span>{" "}
              <span className="text-slate-200">
                HTTP GET extracts ≥ 100 words of content
              </span>
            </p>
            <p className="text-slate-400">
              <span className="text-amber">2.</span>{" "}
              <span className="text-slate-200">
                Semantic HTML (h1, h2, lists, tables, meaningful link text)
              </span>
            </p>
            <p className="text-slate-400">
              <span className="text-amber">3.</span>{" "}
              <span className="text-slate-200">
                Meta description present and substantive
              </span>
            </p>
            <p className="text-slate-400">
              <span className="text-amber">4.</span>{" "}
              <span className="text-slate-200">
                No noindex on content pages
              </span>
            </p>
            <p className="text-slate-400">
              <span className="text-amber">5.</span>{" "}
              <span className="text-slate-200">
                Content in the DOM, not behind API calls
              </span>
            </p>
            <p className="text-slate-400">
              <span className="text-amber">6.</span>{" "}
              <span className="text-slate-200">
                Clean URLs (no hash routing)
              </span>
            </p>
          </div>
        </section>

        {/* Tier 1 */}
        <section className="space-y-6">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 font-mono font-bold text-sm">
              T1
            </span>
            <h2 className="font-display font-bold text-2xl text-slate-100">
              Tier 1 — Agent-native by default
            </h2>
          </div>

          {/* Astro */}
          <div className="bg-surface border border-emerald-500/20 rounded-xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-display font-bold text-xl text-slate-100">
                Astro
              </h3>
              <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full">
                Recommended
              </span>
            </div>
            <p className="text-slate-300 leading-relaxed">
              Astro is the most agent-native frontend framework available today.
              Its &ldquo;islands architecture&rdquo; ships{" "}
              <strong className="text-slate-200">zero JavaScript by default</strong>.
              Every page is static HTML. When you need interactivity &mdash; a
              search bar, a filter panel, a chart &mdash; you explicitly opt in by
              creating an &ldquo;island&rdquo; that hydrates while the rest of the
              page stays pure HTML.
            </p>
            <p className="text-slate-300 leading-relaxed">
              The key insight: a developer has to{" "}
              <em>actively try</em> to make something agents can&rsquo;t read.
              The default path &mdash; following the docs, using the starter
              template &mdash; produces a fully agent-readable page every time.
            </p>
            <div className="bg-navy/60 border border-slate-800 rounded-lg p-4 space-y-2">
              <p className="text-xs font-mono text-slate-500 uppercase tracking-widest">
                Agent-readability strengths
              </p>
              <ul className="text-sm text-slate-300 space-y-1.5">
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400 mt-0.5">✓</span>
                  <span>
                    Zero JS shipped by default. Content is in the HTML, period.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400 mt-0.5">✓</span>
                  <span>
                    Islands architecture: interactive components are explicit
                    opt-in, not the default mode.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400 mt-0.5">✓</span>
                  <span>
                    Built-in sitemap generation, RSS feeds, and image
                    optimization.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400 mt-0.5">✓</span>
                  <span>
                    Content Collections: structured content management with
                    type-safe schemas.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400 mt-0.5">✓</span>
                  <span>
                    Supports React, Svelte, Vue, or Solid for interactive
                    islands — no vendor lock-in.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400 mt-0.5">✓</span>
                  <span>
                    View Transitions API for SPA-like page transitions without
                    client-side routing.
                  </span>
                </li>
              </ul>
            </div>
            <p className="text-slate-400 text-sm leading-relaxed">
              <strong className="text-slate-300">Visual design ceiling:</strong>{" "}
              As high as any React framework. Tailwind works. Any animation
              library works. Stripe-level polish is achievable. The constraint is
              design skill, not the framework.
            </p>
          </div>

          {/* 11ty */}
          <div className="bg-surface border border-slate-800 rounded-xl p-6 space-y-4">
            <h3 className="font-display font-bold text-xl text-slate-100">
              11ty (Eleventy)
            </h3>
            <p className="text-slate-300 leading-relaxed">
              The minimalist&rsquo;s answer. Pure static HTML plus progressive
              enhancement. 11ty generates HTML files from templates &mdash;
              Markdown, Nunjucks, Liquid, whatever you prefer &mdash; and ships
              exactly what you write. No build step beyond templating. No
              framework runtime. No hydration.
            </p>
            <p className="text-slate-300 leading-relaxed">
              The tradeoff is a lower ceiling for interactive experiences. If you
              need complex client-side behavior, you&rsquo;re writing vanilla
              JavaScript or bolting on a framework. For content-heavy sites
              (documentation, blogs, directories), 11ty is bulletproof.
            </p>
          </div>
        </section>

        {/* Tier 2 */}
        <section className="space-y-6">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-amber/10 text-amber font-mono font-bold text-sm">
              T2
            </span>
            <h2 className="font-display font-bold text-2xl text-slate-100">
              Tier 2 — Agent-friendly with discipline
            </h2>
          </div>
          <p className="text-slate-300 leading-relaxed">
            These frameworks <em>can</em> produce agent-readable output, and
            their defaults lean in the right direction. But the component
            ecosystem, community patterns, and developer habits pull toward
            client-heavy architectures. You need awareness and discipline to stay
            agent-native.
          </p>

          {/* Next.js */}
          <div className="bg-surface border border-slate-800 rounded-xl p-6 space-y-4">
            <h3 className="font-display font-bold text-xl text-slate-100">
              Next.js (App Router / React Server Components)
            </h3>
            <p className="text-slate-300 leading-relaxed">
              React Server Components were a massive step in the right direction.
              In the App Router, components render on the server by default. You
              explicitly opt into client-side rendering with{" "}
              <code className="text-amber">&apos;use client&apos;</code>. This
              means a default Next.js page ships server-rendered HTML with real
              content.
            </p>
            <p className="text-slate-300 leading-relaxed">
              The problem is React&rsquo;s ecosystem gravity. Most React
              libraries, tutorials, and Stack Overflow answers assume
              client-side rendering. State management libraries pull you toward{" "}
              <code className="text-amber">&apos;use client&apos;</code>.
              Interactive patterns (modals, dropdowns, search) require client
              components. It&rsquo;s easy to end up with a component tree
              where the root is server-rendered but the content-bearing children
              are all client components &mdash; producing a nice SSR shell with
              loading spinners where the data should be.
            </p>
            <div className="bg-navy/60 border border-slate-800 rounded-lg p-4">
              <p className="text-xs font-mono text-slate-500 uppercase tracking-widest mb-2">
                The discipline required
              </p>
              <ul className="text-sm text-slate-300 space-y-1.5">
                <li className="flex items-start gap-2">
                  <span className="text-amber mt-0.5">→</span>
                  <span>
                    Keep data-fetching in Server Components. Never fetch content
                    in a <code className="text-amber">&apos;use client&apos;</code>{" "}
                    component.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-amber mt-0.5">→</span>
                  <span>
                    Push <code className="text-amber">&apos;use client&apos;</code>{" "}
                    boundaries as far down the tree as possible. Interactive
                    leaf, not interactive root.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-amber mt-0.5">→</span>
                  <span>
                    Run <code className="text-amber">curl</code> against every
                    page during development. If a human can see content but curl
                    can&rsquo;t, you have a client-rendering leak.
                  </span>
                </li>
              </ul>
            </div>
          </div>

          {/* SvelteKit */}
          <div className="bg-surface border border-slate-800 rounded-xl p-6 space-y-4">
            <h3 className="font-display font-bold text-xl text-slate-100">
              SvelteKit
            </h3>
            <p className="text-slate-300 leading-relaxed">
              SvelteKit server-renders by default, compiles to lean JavaScript
              (no virtual DOM runtime), and produces some of the smallest bundles
              in the framework ecosystem. Its{" "}
              <code className="text-amber">+page.server.ts</code> pattern makes
              it clear what runs on the server versus the client.
            </p>
            <p className="text-slate-300 leading-relaxed">
              The risk is smaller than Next.js but still present: Svelte
              components are inherently client-rendered after initial SSR. Data
              fetched in <code className="text-amber">load()</code> functions
              is server-rendered, but any reactive state changes after hydration
              only exist client-side. Agent readability depends on the initial{" "}
              <code className="text-amber">load()</code> returning everything
              meaningful.
            </p>
          </div>

          {/* Remix */}
          <div className="bg-surface border border-slate-800 rounded-xl p-6 space-y-4">
            <h3 className="font-display font-bold text-xl text-slate-100">
              Remix / React Router v7
            </h3>
            <p className="text-slate-300 leading-relaxed">
              Remix has the best philosophical alignment with agent readability
              of any React framework. Progressive enhancement is a core value:
              forms work without JavaScript, loaders run on the server, and the
              mental model encourages server-first thinking.
            </p>
            <p className="text-slate-300 leading-relaxed">
              In practice, it&rsquo;s still React underneath. The same ecosystem
              gravity applies, though Remix&rsquo;s conventions resist it more
              effectively than Next.js. The recent merge into React Router v7
              adds some complexity to the story, but the progressive enhancement
              principles remain.
            </p>
          </div>
        </section>

        {/* Tier 3 */}
        <section className="space-y-6">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-red-500/10 text-red-400 font-mono font-bold text-sm">
              T3
            </span>
            <h2 className="font-display font-bold text-2xl text-slate-100">
              Tier 3 — Agent-hostile by default
            </h2>
          </div>
          <p className="text-slate-300 leading-relaxed">
            These frameworks produce zero agent-readable content in their default
            configuration. Building an agent-readable site with them requires
            bolting on server-side rendering after the fact &mdash; fighting the
            framework rather than working with it.
          </p>

          <div className="bg-surface border border-red-500/20 rounded-xl p-6 space-y-4">
            <div className="flex flex-wrap gap-3 mb-2">
              <span className="text-xs font-mono text-red-400 bg-red-500/10 px-3 py-1 rounded-full">
                Vite + React SPA
              </span>
              <span className="text-xs font-mono text-red-400 bg-red-500/10 px-3 py-1 rounded-full">
                Create React App
              </span>
              <span className="text-xs font-mono text-red-400 bg-red-500/10 px-3 py-1 rounded-full">
                Angular (default)
              </span>
              <span className="text-xs font-mono text-red-400 bg-red-500/10 px-3 py-1 rounded-full">
                Vue CLI (SPA mode)
              </span>
            </div>
            <p className="text-slate-300 leading-relaxed">
              A fresh <code className="text-amber">create-react-app</code> or{" "}
              <code className="text-amber">npm create vite@latest -- --template react</code>{" "}
              produces an HTML file with a single{" "}
              <code className="text-amber">&lt;div id=&quot;root&quot;&gt;&lt;/div&gt;</code>{" "}
              and a script tag. An agent sees an empty page. All content loads
              via JavaScript after the initial render.
            </p>
            <p className="text-slate-300 leading-relaxed">
              This is the pattern behind the majority of agent-invisible sites
              we&rsquo;ve audited. It&rsquo;s not that the developers made bad
              choices &mdash; they made the{" "}
              <em>default</em> choice, and the default is invisible.
            </p>
            <div className="bg-navy/60 border border-slate-800 rounded-lg p-4 font-mono text-sm">
              <p className="text-slate-500 mb-1">$ curl -s https://example-spa.com | wc -w</p>
              <p className="text-red-400 font-bold">12</p>
              <p className="text-slate-500 mt-2 text-xs">
                # Twelve words: the HTML boilerplate and a &lt;noscript&gt; tag.
                Zero content.
              </p>
            </div>
          </div>
        </section>

        {/* The deeper pattern */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            It&rsquo;s not the framework — it&rsquo;s the default
          </h2>
          <p className="text-slate-300 leading-relaxed">
            Every framework on this list <em>can</em> produce agent-readable
            output. The ranking isn&rsquo;t about capability &mdash; it&rsquo;s
            about defaults. The question is: when a new developer follows the
            getting-started guide, does the result work for agents?
          </p>
          <p className="text-slate-300 leading-relaxed">
            This matters because defaults compound across an industry. If the
            most popular framework defaults to client-rendered SPAs, then most
            new sites will be invisible to agents. Not because developers chose
            invisibility, but because they chose the most popular framework.
          </p>
          <p className="text-slate-300 leading-relaxed">
            The agent-native architectural pattern works regardless of framework:
          </p>
          <div className="bg-surface border border-slate-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    Principle
                  </th>
                  <th className="text-left py-3 px-5 text-xs font-mono text-slate-500 uppercase tracking-widest">
                    What it means
                  </th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Content in the DOM
                  </td>
                  <td className="py-3 px-5">
                    All meaningful text is in the server-rendered HTML. Not
                    behind API calls. Not waiting for hydration.
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Progressive enhancement
                  </td>
                  <td className="py-3 px-5">
                    The page works without JavaScript. JS adds interactivity on
                    top. Remove it and the content remains.
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Semantic HTML
                  </td>
                  <td className="py-3 px-5">
                    Headings, lists, tables, links with meaningful text.
                    Structure that machines can parse without guessing.
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Structured data
                  </td>
                  <td className="py-3 px-5">
                    JSON-LD, Open Graph, meta descriptions. The machine-readable
                    layer on top of human-readable content.
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50">
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Discovery files
                  </td>
                  <td className="py-3 px-5">
                    robots.txt, sitemap.xml, llms.txt, security.txt. The
                    handshake files that tell agents how to navigate your site.
                  </td>
                </tr>
                <tr>
                  <td className="py-3 px-5 font-mono text-slate-200">
                    Clean URLs
                  </td>
                  <td className="py-3 px-5">
                    <code className="text-amber">/service/stripe</code> not{" "}
                    <code className="text-amber">/#/service/stripe</code>. Hash
                    routing is invisible to HTTP GET.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* The test */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            The five-minute test
          </h2>
          <p className="text-slate-300 leading-relaxed">
            Before you ship anything that agents should be able to read, run
            these commands. They take five minutes and will tell you if
            your framework choice is working for you or against you.
          </p>
          <div className="bg-surface border border-slate-800 rounded-xl p-6 font-mono text-sm space-y-4">
            <div>
              <p className="text-slate-500 mb-1">
                # 1. Can an agent read your content?
              </p>
              <p className="text-slate-200">
                curl -s https://yoursite.com | python3 -c &quot;import sys; from
                html.parser import HTMLParser; ...&quot;
              </p>
              <p className="text-slate-500 text-xs mt-1">
                # If &lt; 100 words: your content is client-rendered
              </p>
            </div>
            <div>
              <p className="text-slate-500 mb-1">
                # 2. Do your discovery files exist?
              </p>
              <p className="text-slate-200">
                for f in robots.txt sitemap.xml llms.txt; do curl -s -o /dev/null
                -w &quot;$f: %&#123;http_code&#125;\n&quot; https://yoursite.com/$f; done
              </p>
            </div>
            <div>
              <p className="text-slate-500 mb-1">
                # 3. Is your content in the DOM or behind JS?
              </p>
              <p className="text-slate-200">
                curl -s https://yoursite.com | grep -c &apos;use client&apos;
              </p>
              <p className="text-slate-500 text-xs mt-1">
                # High count on content pages = potential problem
              </p>
            </div>
            <div>
              <p className="text-slate-500 mb-1">
                # 4. Any noindex on content pages?
              </p>
              <p className="text-slate-200">
                curl -s https://yoursite.com | grep -i &apos;noindex&apos;
              </p>
            </div>
            <div>
              <p className="text-slate-500 mb-1">
                # 5. Structured data present?
              </p>
              <p className="text-slate-200">
                curl -s https://yoursite.com | grep &apos;application/ld+json&apos;
              </p>
            </div>
          </div>
        </section>

        {/* What we chose */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            What we&rsquo;d choose today
          </h2>
          <p className="text-slate-300 leading-relaxed">
            If we were starting a new developer-facing product today &mdash;
            documentation, an API directory, a developer portal &mdash; we&rsquo;d
            choose <strong className="text-slate-200">Astro</strong> with React
            or Svelte islands for interactive components.
          </p>
          <p className="text-slate-300 leading-relaxed">
            The reasoning is simple: Astro makes the agent-friendly path the
            default. You don&rsquo;t need a &ldquo;make it work for agents&rdquo;
            checklist because the framework already did it. Every page is static
            HTML. Interactive components are explicit islands. Discovery files are
            built-in. The visual design ceiling is identical to any React
            framework because you can use React for the parts that need it.
          </p>
          <p className="text-slate-300 leading-relaxed">
            If you&rsquo;re already on Next.js, don&rsquo;t rewrite. The App
            Router with React Server Components is solid when used with
            discipline. The key rules: keep data-fetching in Server Components,
            push{" "}
            <code className="text-amber">&apos;use client&apos;</code>{" "}
            boundaries to leaves, and run{" "}
            <code className="text-amber">curl</code> against every page.
          </p>
          <p className="text-slate-300 leading-relaxed">
            If you&rsquo;re building a new SPA with Vite + React &mdash; stop.
            Pick a framework that server-renders by default. The cost of adding
            SSR to an SPA later is always higher than starting with it.
          </p>
        </section>

        {/* The future */}
        <section className="space-y-4">
          <h2 className="font-display font-bold text-2xl text-slate-100">
            Where this is heading
          </h2>
          <p className="text-slate-300 leading-relaxed">
            Agent readability isn&rsquo;t a nice-to-have anymore. It&rsquo;s
            becoming a distribution channel. When an agent recommends tools,
            evaluates options, or routes between services, it starts with what it
            can read. Sites that are invisible to agents lose a growing share of
            discovery traffic.
          </p>
          <p className="text-slate-300 leading-relaxed">
            The frameworks that default to agent readability will win the next
            decade of the web the same way mobile-responsive frameworks won the
            last one. We went from &ldquo;does your site work on phones?&rdquo; to
            &ldquo;every site works on phones&rdquo; in about five years. Agent
            readability is on the same curve.
          </p>
          <p className="text-slate-300 leading-relaxed">
            The question for every frontend team isn&rsquo;t whether to care
            about agents. It&rsquo;s whether your framework makes it easy or
            makes you fight for it.
          </p>
        </section>

        {/* Methodology note */}
        <section className="border-t border-slate-800 pt-8 mt-8 space-y-3">
          <p className="text-slate-500 text-sm leading-relaxed italic">
            Methodology: All tests conducted via standard HTTP GET requests with
            readability extraction &mdash; the same approach used by LangChain,
            CrewAI, AutoGPT, and most agent frameworks. No JavaScript execution.
            Framework evaluations based on default project templates as of March
            2026.
          </p>
        </section>
      </article>

      {/* Footer */}
      <footer className="border-t border-slate-800 bg-navy">
        <div className="max-w-3xl mx-auto px-6 py-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <p className="text-slate-400 text-sm font-mono">Pedro Nunes</p>
            <p className="text-slate-600 text-xs font-mono">@pedrorhumb</p>
          </div>
          <Link
            href="/blog"
            className="text-sm font-mono text-amber hover:text-amber/80 transition-colors"
          >
            ← All posts
          </Link>
        </div>
      </footer>
    </div>
  );
}
