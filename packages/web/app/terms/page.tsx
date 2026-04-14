import React from "react";
import type { Metadata } from "next";

import { PUBLIC_TRUTH } from "../../lib/public-truth";

export const metadata: Metadata = {
  title: "Terms of Service",
  description:
    "Rhumb's terms of service. Scores are opinions, API is provided as-is, data licensed CC BY 4.0.",
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
            Last updated: March 11, 2026
          </p>
        </header>

        <div className="space-y-10 text-slate-400 text-sm leading-relaxed">
          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              1. Acceptance
            </h2>
            <p>
              By accessing Rhumb (&ldquo;the Service&rdquo;), operated by
              Supertrained LLC, you agree to these Terms of Service. If you
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
                opinions based on documentation analysis
              </strong>
              . They are not warranties, guarantees, or certifications of
              any kind. Scores reflect our assessment of how well a
              service&apos;s published documentation suggests it will work
              for autonomous AI agents.
            </p>
            <p className="mt-3">
              Scores may change as documentation is updated, methodologies
              are refined, or disputes are resolved. We make reasonable
              efforts to be accurate but do not guarantee the correctness
              of any individual score.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              3. API usage
            </h2>
            <p>
              The Rhumb API is currently provided{" "}
              <strong className="text-slate-200">
                free of charge with no authentication required
              </strong>
              . This may change in the future — we will provide reasonable
              notice before requiring authentication or introducing usage
              limits.
            </p>
            <p className="mt-3">The API is provided as-is, with:</p>
            <ul className="space-y-2 mt-3">
              <li>
                • No guaranteed uptime or service level agreement (SLA)
              </li>
              <li>
                • No guaranteed response time or rate limit protections
              </li>
              <li>
                • No commitment to backward compatibility of response
                schemas (we aim for stability but are at v0.3)
              </li>
            </ul>
            <p className="mt-3">
              We reserve the right to block or rate-limit abusive usage,
              including but not limited to: automated scraping at scale,
              denial-of-service attempts, or usage that degrades the
              service for other users.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              4. Data licensing
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
                  Creative Commons Attribution 4.0 International (CC BY
                  4.0)
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
                © 2026 Supertrained LLC. All rights reserved unless
                otherwise noted.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              5. Dispute process
            </h2>
            <p>
              If you believe a score is inaccurate, you may file a dispute
              via:
            </p>
            <ul className="space-y-2 mt-3">
              <li>
                •{" "}
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
                •{" "}
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
              We commit to reviewing every dispute and responding within 5
              business days. Outcomes of public disputes are published on
              GitHub. We reserve final editorial discretion on all scores.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              6. Limitation of liability
            </h2>
            <p>
              The Service is provided &ldquo;as is&rdquo; without warranty
              of any kind, express or implied. Supertrained LLC shall not
              be liable for any damages arising from the use of AN Scores,
              failure mode data, or any other information provided through
              the Service.
            </p>
            <p className="mt-3">
              This includes but is not limited to: decisions made based on
              AN Scores, tool selection influenced by leaderboard rankings,
              or business impact from published failure mode data.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              7. Changes to terms
            </h2>
            <p>
              We may update these terms. Material changes will be announced
              in our{" "}
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
              8. Governing law
            </h2>
            <p>
              These Terms are governed by and construed in accordance with
              the laws of the State of California, United States.
            </p>
          </section>

          <section>
            <h2 className="font-display font-bold text-xl text-slate-100 mb-3">
              9. Contact
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
