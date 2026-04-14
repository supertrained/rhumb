import React from "react";
import type { Metadata } from "next";

import { PUBLIC_TRUTH } from "../../lib/public-truth";

export const metadata: Metadata = {
  title: "Terms of Service",
  description:
    "Rhumb's terms of service. Scores, API usage, proxy services, payments, and data licensing.",
  alternates: { canonical: "/terms" },
};

export default function TermsPage() {
  return (
    <div className="bg-navy min-h-screen">
      <div className="max-w-3xl mx-auto px-6 pt-14 pb-24">
        <header className="mb-12">
          <span className="text-xs font-mono font-semibold text-amber uppercase tracking-widest">
            Legal
          </span>
          <h1 className="font-display font-bold text-3xl text-slate-100 leading-tight tracking-tight mt-4 mb-4">
            Terms of Service
          </h1>
          <p className="text-sm text-slate-500 font-mono">
            Last updated: March 20, 2026
          </p>
        </header>

        <div className="space-y-10 text-slate-400 text-sm leading-relaxed">
          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              1. Acceptance
            </h2>
            <p>
              By accessing Rhumb (&ldquo;the Service&rdquo;), operated by
              Supertrained Inc., you agree to these Terms of Service. If you
              disagree, please do not use the Service.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              2. Nature of scores
            </h2>
            <p>
              AN Scores are{" "}
              <strong className="text-slate-200">
                opinions based on documentation analysis and, where available,
                runtime testing
              </strong>
              . They are not warranties, guarantees, or certifications of any
              kind. Scores reflect our assessment of how well a service&apos;s
              published documentation and observed behavior suggest it will work
              for autonomous AI agents.
            </p>
            <p className="mt-3">
              Scores may change as documentation is updated, runtime evidence is
              collected, methodologies are refined, or disputes are resolved. We
              make reasonable efforts to be accurate but do not guarantee the
              correctness of any individual score.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              3. Service tiers and access
            </h2>
            <p>Rhumb offers multiple tiers of access:</p>
            <ul className="space-y-3 mt-3">
              <li>
                <strong className="text-slate-200">
                  Browse (free, no auth):
                </strong>{" "}
                Score data, service profiles, failure modes, leaderboards, and
                search are available without authentication.
              </li>
              <li>
                <strong className="text-slate-200">
                  Execution rails (paid as used):
                </strong>{" "}
                Authenticated execution may use governed API key,
                wallet-prefund, or BYOK depending on the rail you choose.
                Discovery remains free, and current pricing and markup terms are
                published at{" "}
                <a
                  href="/pricing"
                  className="text-amber hover:underline underline-offset-2"
                >
                  /pricing
                </a>
                .
              </li>
              <li>
                <strong className="text-slate-200">
                  x402 zero-signup (paid):
                </strong>{" "}
                Agents with x402 capability may use execution endpoints without
                an account by including a valid USDC payment proof with each
                request.
              </li>
            </ul>
            <p className="mt-3">
              We reserve the right to modify access rails, pricing, and billing
              terms with reasonable notice.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              4. Managed capabilities and proxy services
            </h2>
            <p>
              Rhumb offers managed capability execution, where we proxy API
              calls to third-party services on your behalf using credentials we
              manage. When using managed capabilities:
            </p>
            <ul className="space-y-2 mt-3">
              <li>
                &bull; You are responsible for compliance with the upstream
                service&apos;s terms of service
              </li>
              <li>
                &bull; Rhumb acts as a technical intermediary, not as the
                provider of the upstream service
              </li>
              <li>
                &bull; For Rhumb-managed execution rails, we apply the current
                markup disclosed at{" "}
                <a
                  href="/pricing"
                  className="text-amber hover:underline underline-offset-2"
                >
                  /pricing
                </a>
                ; BYOK routes do not add markup to the credential itself
              </li>
              <li>
                &bull; We are not liable for upstream service outages, errors,
                or changes to their APIs
              </li>
              <li>
                &bull; We reserve the right to suspend managed capability access
                for any account engaged in abusive usage
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              5. Acceptable use
            </h2>
            <p>You agree not to use the Service to:</p>
            <ul className="space-y-2 mt-3">
              <li>
                &bull; Send unsolicited messages (spam) via managed capabilities
              </li>
              <li>
                &bull; Engage in phishing, fraud, or other deceptive practices
              </li>
              <li>
                &bull; Attempt to access other users&apos; data, keys, or sessions
              </li>
              <li>
                &bull; Circumvent payment, rate limiting, or authentication
                mechanisms
              </li>
              <li>
                &bull; Use managed credentials for purposes unrelated to your
                legitimate application
              </li>
              <li>
                &bull; Systematically overload the API to degrade service for
                others
              </li>
            </ul>
            <p className="mt-3">
              Violation of these terms may result in immediate suspension of
              access without refund.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              6. Payments and refunds
            </h2>
            <p>
              <strong className="text-slate-200">Stripe prepaid balance:</strong>{" "}
              Funds added via Stripe are prepaid credits. Credits are
              non-refundable once consumed by capability executions. Unused
              credits may be refunded within 30 days of purchase by contacting{" "}
              <a
                href="mailto:billing@supertrained.ai"
                className="text-amber hover:underline underline-offset-2"
              >
                billing@supertrained.ai
              </a>
              .
            </p>
            <p className="mt-3">
              <strong className="text-slate-200">x402/USDC payments:</strong>{" "}
              USDC payments are on-chain and final. Refunds for x402 payments
              are processed at our discretion and returned to the originating
              wallet address.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              7. API and service disclaimer
            </h2>
            <p>The API and all services are provided as-is, with:</p>
            <ul className="space-y-2 mt-3">
              <li>
                &bull; No guaranteed uptime or service level agreement (SLA)
              </li>
              <li>
                &bull; No guaranteed response time or rate limit protections
              </li>
              <li>
                &bull; No commitment to backward compatibility of response
                schemas (we aim for stability but reserve the right to evolve
                the API)
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              8. Data licensing
            </h2>
            <ul className="space-y-3 mt-3">
              <li>
                <strong className="text-slate-200">
                  Score data (AN Scores, failure modes, leaderboards):
                </strong>{" "}
                Licensed under{" "}
                <a
                  href="https://creativecommons.org/licenses/by/4.0/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-amber hover:underline underline-offset-2"
                >
                  Creative Commons Attribution 4.0 International (CC BY 4.0)
                </a>
                . You may use, share, and adapt the data for any purpose,
                including commercial use, provided you give attribution.
              </li>
              <li>
                <strong className="text-slate-200">Source code:</strong>{" "}
                Licensed under the{" "}
                <a
                  href="https://opensource.org/licenses/MIT"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-amber hover:underline underline-offset-2"
                >
                  MIT License
                </a>
                .
              </li>
              <li>
                <strong className="text-slate-200">
                  Service guides and blog content:
                </strong>{" "}
                &copy; 2026 Supertrained Inc. All rights reserved unless
                otherwise noted.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              9. Dispute process
            </h2>
            <p>
              If you believe a score is inaccurate, you may file a dispute via:
            </p>
            <ul className="space-y-2 mt-3">
              <li>
                &bull;{" "}
                <a
                  href={PUBLIC_TRUTH.publicDisputeTemplateUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-amber hover:underline underline-offset-2"
                >
                  GitHub issue template
                </a>{" "}
                (public)
              </li>
              <li>
                &bull;{" "}
                <a
                  href={`mailto:${PUBLIC_TRUTH.privateDisputesEmail}`}
                  className="text-amber hover:underline underline-offset-2"
                >
                  {PUBLIC_TRUTH.privateDisputesEmail}
                </a>{" "}
                (private)
              </li>
            </ul>
            <p className="mt-3">
              We commit to reviewing every dispute and responding within{" "}
              {PUBLIC_TRUTH.disputeResponseSlaBusinessDays} business days.
              Outcomes of public disputes are published on{" "}
              <a
                href={PUBLIC_TRUTH.publicDisputesUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-amber hover:underline underline-offset-2"
              >
                GitHub
              </a>
              . We reserve final editorial discretion on all scores.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              10. Limitation of liability
            </h2>
            <p>
              The Service is provided &ldquo;as is&rdquo; without warranty of
              any kind, express or implied. Supertrained Inc. shall not be
              liable for any damages arising from the use of AN Scores, failure
              mode data, managed capability executions, proxy services, or any
              other information or functionality provided through the Service.
            </p>
            <p className="mt-3">
              This includes but is not limited to: decisions made based on AN
              Scores, tool selection influenced by leaderboard rankings,
              business impact from published failure mode data, costs incurred
              through managed capability execution, or upstream service failures
              during proxied calls.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              11. Changes to terms
            </h2>
            <p>
              We may update these terms. Material changes will be announced in
              our{" "}
              <a
                href="/changelog"
                className="text-amber hover:underline underline-offset-2"
              >
                changelog
              </a>{" "}
              and noted by updating the &ldquo;Last updated&rdquo; date.
              Continued use of the Service after changes constitutes
              acceptance.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              12. Governing law
            </h2>
            <p>
              These Terms are governed by and construed in accordance with the
              laws of the State of Florida, United States.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              13. Contact
            </h2>
            <p>
              For questions about these terms:
              <br />
              <a
                href="mailto:legal@supertrained.ai"
                className="text-amber hover:underline underline-offset-2"
              >
                legal@supertrained.ai
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
