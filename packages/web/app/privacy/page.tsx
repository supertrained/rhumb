import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "Rhumb's privacy policy. What we collect, what we don't, and how we handle your data.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <div className="bg-navy min-h-screen">
      <div className="max-w-3xl mx-auto px-6 pt-14 pb-24">
        <header className="mb-12">
          <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
            Legal
          </span>
          <h1 className="font-display font-bold text-3xl text-slate-100 leading-tight tracking-tight mt-4 mb-4">
            Privacy Policy
          </h1>
          <p className="text-sm text-slate-500 font-mono">
            Last updated: March 11, 2026
          </p>
        </header>

        <div className="space-y-10 text-slate-400 text-sm leading-relaxed">
          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Overview
            </h2>
            <p>
              Rhumb (operated by Supertrained LLC) is a developer tool that
              scores APIs for AI agent compatibility. We are committed to
              transparency about what we collect and why.
            </p>
            <p className="mt-3">
              <strong className="text-slate-200">
                The short version: we collect minimal data, we don&apos;t
                sell any of it, and we don&apos;t track you across sites.
              </strong>
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              What we collect
            </h2>
            <ul className="space-y-3 mt-3">
              <li>
                <strong className="text-slate-200">
                  API query logs:
                </strong>{" "}
                When you use our API or MCP server, we log search terms and
                timestamps to improve relevance. These logs do not contain
                personally identifiable information (PII).
              </li>
              <li>
                <strong className="text-slate-200">
                  Web analytics:
                </strong>{" "}
                We use Google Analytics 4 and Microsoft Clarity for
                anonymized usage analytics. These tools collect standard
                web metrics (page views, session duration, device type).
                Both are configured with IP anonymization enabled.
              </li>
              <li>
                <strong className="text-slate-200">
                  Error logs:
                </strong>{" "}
                Server error logs may contain request metadata (URL, HTTP
                method, status code) for debugging. These are retained for
                30 days and contain no PII.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              What we do NOT collect
            </h2>
            <ul className="space-y-2 mt-3">
              <li>
                • We do not collect personal information (names, emails,
                addresses)
              </li>
              <li>
                • We do not collect payment information or authentication
                tokens
              </li>
              <li>• We do not use cookies for tracking or advertising</li>
              <li>• We do not track you across other websites</li>
              <li>
                • We do not build user profiles or sell data to third
                parties
              </li>
              <li>
                • We do not use your API queries to train machine learning
                models
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              How we use your data
            </h2>
            <p>Data collected is used solely to:</p>
            <ul className="space-y-2 mt-3">
              <li>• Improve search relevance and service coverage</li>
              <li>• Monitor API performance and uptime</li>
              <li>
                • Understand aggregate usage patterns (which categories are
                most searched, which services are most viewed)
              </li>
              <li>• Debug errors and improve reliability</li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Third-party services
            </h2>
            <ul className="space-y-3 mt-3">
              <li>
                <strong className="text-slate-200">
                  Google Analytics 4
                </strong>{" "}
                — anonymized web analytics.{" "}
                <a
                  href="https://policies.google.com/privacy"
                  className="text-amber hover:underline underline-offset-2"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Google Privacy Policy
                </a>
              </li>
              <li>
                <strong className="text-slate-200">
                  Microsoft Clarity
                </strong>{" "}
                — session recordings and heatmaps (anonymized).{" "}
                <a
                  href="https://privacy.microsoft.com/en-us/privacystatement"
                  className="text-amber hover:underline underline-offset-2"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Microsoft Privacy Statement
                </a>
              </li>
              <li>
                <strong className="text-slate-200">Vercel</strong> —
                hosting.{" "}
                <a
                  href="https://vercel.com/legal/privacy-policy"
                  className="text-amber hover:underline underline-offset-2"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Vercel Privacy Policy
                </a>
              </li>
              <li>
                <strong className="text-slate-200">Supabase</strong> —
                database hosting.{" "}
                <a
                  href="https://supabase.com/privacy"
                  className="text-amber hover:underline underline-offset-2"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Supabase Privacy Policy
                </a>
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Your rights (GDPR / CCPA)
            </h2>
            <p>
              Since we collect minimal, anonymized data, most rights
              (access, deletion, portability) apply to very limited data.
              However, you have the right to:
            </p>
            <ul className="space-y-2 mt-3">
              <li>
                • <strong className="text-slate-200">Access</strong> —
                request a copy of any data associated with your usage
              </li>
              <li>
                • <strong className="text-slate-200">Deletion</strong> —
                request deletion of any stored data
              </li>
              <li>
                • <strong className="text-slate-200">Opt-out</strong> —
                disable analytics by using a browser ad blocker or
                do-not-track setting
              </li>
              <li>
                •{" "}
                <strong className="text-slate-200">Data portability</strong>{" "}
                — request your data in a machine-readable format
              </li>
            </ul>
            <p className="mt-3">
              For any privacy-related requests, contact{" "}
              <a
                href="mailto:privacy@supertrained.ai"
                className="text-amber hover:underline underline-offset-2"
              >
                privacy@supertrained.ai
              </a>
              .
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Data retention
            </h2>
            <ul className="space-y-2 mt-3">
              <li>• API query logs: retained for 90 days</li>
              <li>• Error logs: retained for 30 days</li>
              <li>
                • Web analytics: per Google Analytics and Microsoft Clarity
                default retention policies
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Changes to this policy
            </h2>
            <p>
              We will update this page when our data practices change. For
              significant changes, we&apos;ll note the update in our{" "}
              <a
                href="/changelog"
                className="text-amber hover:underline underline-offset-2"
              >
                changelog
              </a>
              .
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Contact
            </h2>
            <p>
              For privacy-related questions or requests:
              <br />
              <a
                href="mailto:privacy@supertrained.ai"
                className="text-amber hover:underline underline-offset-2"
              >
                privacy@supertrained.ai
              </a>
            </p>
            <p className="mt-3">
              Supertrained LLC
              <br />
              Los Angeles, CA
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
