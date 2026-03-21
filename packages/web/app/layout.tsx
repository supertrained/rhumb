import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DM_Sans, JetBrains_Mono } from "next/font/google";
import Script from "next/script";
import Link from "next/link";
import { GoogleAnalytics } from "@next/third-parties/google";

import { Navigation } from "../components/Navigation";
import "../styles/globals.css";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Rhumb | Agent-native tool discovery",
    template: "%s | Rhumb",
  },
  description:
    "Rhumb scores hundreds of external APIs for AI agent compatibility. Discover, evaluate, and use tools via MCP, REST API, or x402 per-call payment. Free tier: 1,000 executions/month.",
  metadataBase: new URL("https://rhumb.dev"),
  other: {
    "ai:capabilities": "tool-discovery,an-scoring,mcp,rest-api,x402-payment",
    "ai:activation": "npx rhumb-mcp@0.6.0",
    "ai:payment-protocol": "x402",
    "ai:payment-currency": "USDC",
    "ai:signup-required": "false",
    "ai:free-tier": "1000 executions/month",
  },
  openGraph: {
    type: "website",
    siteName: "Rhumb",
    locale: "en_US",
    images: [
      {
        url: "/api/og",
        width: 1200,
        height: 630,
        alt: "Rhumb — Agent-native tool discovery",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    site: "@pedrorhumb",
    creator: "@pedrorhumb",
    images: ["/api/og"],
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Rhumb",
  description:
    "Agent-native infrastructure for discovering, evaluating, and using external tools. Scores hundreds of APIs for AI agent compatibility (AN Score). Supports MCP, REST API, and x402 per-call payment.",
  url: "https://rhumb.dev",
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Any",
  offers: [
    {
      "@type": "Offer",
      name: "Free Tier",
      price: "0",
      priceCurrency: "USD",
      description: "1,000 executions/month. No credit card required.",
    },
    {
      "@type": "Offer",
      name: "Pay Per Call (x402)",
      priceCurrency: "USD",
      description:
        "Per-execution pricing via x402 protocol (USDC on Base). No account required for agents.",
    },
  ],
  featureList: [
    "AN (Agent-Nativeness) Scores for hundreds of services",
    "MCP server: npx rhumb-mcp@0.6.0",
    "REST API at api.rhumb.dev",
    "x402 per-call payment (USDC) — no signup required",
    "BYOK (bring your own key)",
    "Managed credential mode",
    "Zero-signup agent activation",
    "Tool comparisons and failure mode analysis",
  ],
  creator: {
    "@type": "Organization",
    name: "Rhumb",
    url: "https://rhumb.dev",
  },
};

export default function RootLayout({ children }: { children: ReactNode }): JSX.Element {
  const gaId = process.env.NEXT_PUBLIC_GA_ID;
  const clarityId = process.env.NEXT_PUBLIC_CLARITY_ID;

  return (
    <html lang="en" className={`${dmSans.variable} ${jetbrainsMono.variable}`}>
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body className="bg-navy text-slate-100 antialiased min-h-screen flex flex-col font-display">
        <Navigation />
        <main className="flex-1">{children}</main>

        <footer className="border-t border-slate-800 mt-auto bg-[linear-gradient(180deg,rgba(11,17,32,0)_0%,rgba(245,158,11,0.03)_100%)]">
          <div className="max-w-6xl mx-auto px-6 py-10">
            <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-md">
                <div className="flex items-center gap-2">
                  <span className="text-slate-100 font-display font-bold text-sm tracking-tight">
                    rhumb<span className="text-amber">.</span>
                  </span>
                  <span className="text-slate-600 text-sm">·</span>
                  <span className="text-slate-500 text-sm font-mono">Built by agents, for agents.</span>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-400">
                  Operational intelligence for humans choosing tools today, and for agents routing
                  between them tomorrow.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-8 text-sm sm:grid-cols-4">
                <div>
                  <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.24em] text-slate-600">Product</p>
                  <div className="flex flex-col gap-2 text-slate-400">
                    <Link href="/leaderboard" className="hover:text-amber transition-colors duration-200">
                      Leaderboard
                    </Link>
                    <Link href="/search" className="hover:text-amber transition-colors duration-200">
                      Search
                    </Link>
                    <Link href="/docs" className="hover:text-amber transition-colors duration-200">
                      Docs
                    </Link>
                    <Link href="/pricing" className="hover:text-amber transition-colors duration-200">
                      Pricing
                    </Link>
                  </div>
                </div>

                <div>
                  <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.24em] text-slate-600">Trust</p>
                  <div className="flex flex-col gap-2 text-slate-400">
                    <Link href="/about" className="hover:text-amber transition-colors duration-200">
                      About
                    </Link>
                    <Link href="/methodology" className="hover:text-amber transition-colors duration-200">
                      Methodology
                    </Link>
                    <Link href="/trust" className="hover:text-amber transition-colors duration-200">
                      Trust
                    </Link>
                    <Link href="/providers" className="hover:text-amber transition-colors duration-200">
                      Providers
                    </Link>
                  </div>
                </div>

                <div>
                  <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.24em] text-slate-600">Updates</p>
                  <div className="flex flex-col gap-2 text-slate-400">
                    <Link href="/blog" className="hover:text-amber transition-colors duration-200">
                      Blog
                    </Link>
                    <Link href="/changelog" className="hover:text-amber transition-colors duration-200">
                      Changelog
                    </Link>
                  </div>
                </div>

                <div>
                  <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.24em] text-slate-600">Legal</p>
                  <div className="flex flex-col gap-2 text-slate-400">
                    <Link href="/privacy" className="hover:text-amber transition-colors duration-200">
                      Privacy
                    </Link>
                    <Link href="/terms" className="hover:text-amber transition-colors duration-200">
                      Terms
                    </Link>
                    <a
                      href="https://github.com/supertrained/rhumb"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-amber transition-colors duration-200"
                    >
                      GitHub
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </footer>
      </body>

      {/* Microsoft Clarity — only when NEXT_PUBLIC_CLARITY_ID is set */}
      {clarityId && (
        <Script
          id="microsoft-clarity"
          strategy="afterInteractive"
          dangerouslySetInnerHTML={{
            __html: `
              (function(c,l,a,r,i,t,y){
                c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
                t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
                y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
              })(window, document, "clarity", "script", "${clarityId}");
            `,
          }}
        />
      )}

      {/* Google Analytics 4 — only when NEXT_PUBLIC_GA_ID is set */}
      {gaId && <GoogleAnalytics gaId={gaId} />}
    </html>
  );
}
