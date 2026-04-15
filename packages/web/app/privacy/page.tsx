import React from "react";
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
            Last updated: March 20, 2026
          </p>
        </header>

        <div className="space-y-10 text-slate-400 text-sm leading-relaxed">
          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Overview
            </h2>
            <p>
              Rhumb (operated by Supertrained Inc.) is a developer tool that
              scores APIs for AI agent compatibility and provides managed
              capability execution. We are committed to transparency about what
              we collect and why.
            </p>
            <p className="mt-3">
              <strong className="text-slate-200">
                The short version: we collect what we need to operate the
                service, we don&apos;t sell any of it, and we don&apos;t track
                you across sites.
              </strong>
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              What we collect
            </h2>

            <h3 className="font-display font-semibold text-base text-slate-200 mt-6 mb-2">
              Account data (if you sign up)
            </h3>
            <p>
              When you create an account via GitHub or Google OAuth, we receive
              and store:
            </p>
            <ul className="space-y-2 mt-2">
              <li>
                &bull; Your display name and email address (from your OAuth
                provider)
              </li>
              <li>
                &bull; Your OAuth provider identifier (GitHub user ID or Google
                sub)
              </li>
              <li>&bull; An API key we generate for your account</li>
            </ul>
            <p className="mt-3">
              We do <strong className="text-slate-200">not</strong> receive or
              store your OAuth provider password. We use the standard OAuth 2.0
              authorization code flow with CSRF protection.
            </p>

            <h3 className="font-display font-semibold text-base text-slate-200 mt-6 mb-2">
              Session data
            </h3>
            <p>
              When you sign in, we set a{" "}
              <code className="text-amber/80 bg-slate-800 px-1 rounded">
                rhumb_session
              </code>{" "}
              cookie containing a signed JWT token. This cookie is:
            </p>
            <ul className="space-y-2 mt-2">
              <li>&bull; HttpOnly (not accessible to JavaScript)</li>
              <li>&bull; Secure (only transmitted over HTTPS)</li>
              <li>&bull; SameSite=Lax (not sent on cross-site requests)</li>
              <li>&bull; Valid for 7 days</li>
            </ul>

            <h3 className="font-display font-semibold text-base text-slate-200 mt-6 mb-2">
              API and execution data
            </h3>
            <ul className="space-y-2 mt-2">
              <li>
                <strong className="text-slate-200">API query logs:</strong>{" "}
                Search terms, capability execution requests, and timestamps.
                Authenticated requests are associated with your API key.
              </li>
              <li>
                <strong className="text-slate-200">Execution records:</strong>{" "}
                When you use managed capability execution, we log the capability
                called, provider used, latency, cost, and success/failure
                status. We do <strong className="text-slate-200">not</strong>{" "}
                log the contents of your request bodies or upstream responses.
              </li>
              <li>
                <strong className="text-slate-200">Error logs:</strong>{" "}
                Server error logs may contain request metadata (URL, HTTP
                method, status code) for debugging. These are retained for 30
                days.
              </li>
            </ul>

            <h3 className="font-display font-semibold text-base text-slate-200 mt-6 mb-2">
              Payment data
            </h3>
            <ul className="space-y-2 mt-2">
              <li>
                <strong className="text-slate-200">Stripe:</strong>{" "}
                Payment processing is handled by Stripe. We store your Stripe
                customer ID and transaction records (amounts, dates). We do{" "}
                <strong className="text-slate-200">not</strong> store your
                credit card number or payment method details, those are held by
                Stripe.
              </li>
              <li>
                <strong className="text-slate-200">x402/USDC:</strong>{" "}
                For on-chain payments, we record the transaction hash and wallet
                address used for payment verification. Blockchain transactions
                are inherently public.
              </li>
            </ul>

            <h3 className="font-display font-semibold text-base text-slate-200 mt-6 mb-2">
              Web analytics
            </h3>
            <p>
              We use Google Analytics 4 and Microsoft Clarity for anonymized
              usage analytics on{" "}
              <code className="text-amber/80 bg-slate-800 px-1 rounded">
                rhumb.dev
              </code>
              . These tools collect standard web metrics (page views, session
              duration, device type). Both are configured with IP anonymization
              enabled.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              What we do NOT collect
            </h2>
            <ul className="space-y-2 mt-3">
              <li>&bull; We do not store your OAuth provider password</li>
              <li>
                &bull; We do not store credit card numbers (Stripe handles
                payment details)
              </li>
              <li>
                &bull; We do not log upstream API request/response bodies from
                managed executions
              </li>
              <li>&bull; We do not track you across other websites</li>
              <li>
                &bull; We do not build advertising profiles or sell data to
                third parties
              </li>
              <li>
                &bull; We do not use your API queries or execution data to
                train machine learning models
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Managed credentials
            </h2>
            <p>
              When you use Rhumb-managed capability execution, we hold API
              credentials for upstream services on your behalf. These
              credentials:
            </p>
            <ul className="space-y-2 mt-3">
              <li>
                &bull; Are stored in encrypted secret management infrastructure
              </li>
              <li>
                &bull; Are never exposed in API responses, logs, or error
                messages
              </li>
              <li>
                &bull; Are used only to execute the specific capability you
                request
              </li>
              <li>
                &bull; Are shared across users of managed capabilities (they are
                Rhumb&apos;s credentials, not per-user credentials)
              </li>
            </ul>
            <p className="mt-3">
              If you use{" "}
              <strong className="text-slate-200">
                bring-your-own-key (BYOK)
              </strong>{" "}
              mode, your credentials are passed through to the upstream service
              in the same request and are{" "}
              <strong className="text-slate-200">not stored</strong> by Rhumb.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              How we use your data
            </h2>
            <p>Data collected is used to:</p>
            <ul className="space-y-2 mt-3">
              <li>&bull; Authenticate your identity and manage your account</li>
              <li>&bull; Process payments and maintain billing records</li>
              <li>&bull; Execute capability requests on your behalf</li>
              <li>&bull; Enforce budget limits and rate controls</li>
              <li>&bull; Improve search relevance and service coverage</li>
              <li>&bull; Monitor API performance, uptime, and error rates</li>
              <li>
                &bull; Understand aggregate usage patterns (which capabilities
                are most used, which services are most queried)
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Third-party services
            </h2>
            <ul className="space-y-3 mt-3">
              <li>
                <strong className="text-slate-200">GitHub / Google</strong>{" "}
                — OAuth identity providers.{" "}
                <a
                  href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement"
                  className="text-amber hover:underline underline-offset-2"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  GitHub Privacy
                </a>{" "}
                /{" "}
                <a
                  href="https://policies.google.com/privacy"
                  className="text-amber hover:underline underline-offset-2"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Google Privacy
                </a>
              </li>
              <li>
                <strong className="text-slate-200">Stripe</strong> — payment
                processing.{" "}
                <a
                  href="https://stripe.com/privacy"
                  className="text-amber hover:underline underline-offset-2"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Stripe Privacy Policy
                </a>
              </li>
              <li>
                <strong className="text-slate-200">Google Analytics 4</strong>{" "}
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
                <strong className="text-slate-200">Microsoft Clarity</strong>{" "}
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
                <strong className="text-slate-200">Vercel</strong> — frontend
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
                <strong className="text-slate-200">Railway</strong> — API
                hosting.{" "}
                <a
                  href="https://railway.com/legal/privacy"
                  className="text-amber hover:underline underline-offset-2"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Railway Privacy Policy
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
            <p className="mt-3">
              When using managed capabilities, your requests are proxied through
              upstream service APIs (e.g., Stripe, GitHub, Twilio, Slack). Each
              upstream service has its own privacy policy governing data they
              receive through API calls.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Your rights (GDPR / CCPA)
            </h2>
            <p>You have the right to:</p>
            <ul className="space-y-2 mt-3">
              <li>
                &bull; <strong className="text-slate-200">Access</strong> —
                request a copy of all data associated with your account
              </li>
              <li>
                &bull; <strong className="text-slate-200">Correction</strong> —
                request correction of inaccurate data
              </li>
              <li>
                &bull; <strong className="text-slate-200">Deletion</strong> —
                request deletion of your account and associated data
              </li>
              <li>
                &bull; <strong className="text-slate-200">Opt-out of analytics</strong> —
                disable web analytics by using a browser ad blocker or Do Not
                Track setting
              </li>
              <li>
                &bull; <strong className="text-slate-200">Data portability</strong> —
                request your data in a machine-readable format
              </li>
              <li>
                &bull; <strong className="text-slate-200">Non-discrimination</strong> —
                exercising these rights will not affect your service access
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
              . We will respond within 30 days.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Data retention
            </h2>
            <ul className="space-y-2 mt-3">
              <li>
                &bull; Account data: retained while your account is active;
                deleted within 30 days of account deletion request
              </li>
              <li>&bull; API query and execution logs: retained for 90 days</li>
              <li>&bull; Error logs: retained for 30 days</li>
              <li>
                &bull; Billing records: retained for 7 years (tax/legal
                compliance)
              </li>
              <li>
                &bull; Web analytics: per Google Analytics and Microsoft
                Clarity default retention policies
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              Children&apos;s privacy
            </h2>
            <p>
              Rhumb is a developer tool not intended for use by children under
              13. We do not knowingly collect data from children under 13. If
              you believe a child has provided us with personal information,
              please contact us at{" "}
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
              Supertrained Inc.
              <br />
              7901 4th St N STE 300
              <br />
              St Petersburg, FL 33702
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
