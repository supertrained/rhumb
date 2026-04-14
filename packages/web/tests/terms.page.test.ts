import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

async function renderTermsPage(): Promise<string> {
  const module = await import("../app/terms/page");
  return renderToStaticMarkup(module.default());
}

describe("terms page", () => {
  it("keeps the dispute process aligned with the public dispute template contract", async () => {
    const html = await renderTermsPage();

    expect(html).toContain("GitHub issue template");
    expect(html).toContain(
      'href="https://github.com/supertrained/rhumb/issues/new?template=score-dispute.md"',
    );
    expect(html).toContain('href="mailto:providers@supertrained.ai"');
    expect(html).toContain("responding within 5 business days");
    expect(html).toContain('href="https://github.com/supertrained/rhumb/issues?q=is%3Aissue+%22Score+dispute%3A%22"');
  });

  it("keeps the live Next legal surface aligned with the current terms authority", async () => {
    const html = await renderTermsPage();

    expect(html).toContain("Last updated: March 20, 2026");
    expect(html).toContain("Supertrained Inc.");
    expect(html).toContain("Service tiers and access");
    expect(html).toContain("Execution rails (paid as used):");
    expect(html).toContain("x402 zero-signup (paid):");
    expect(html).toContain("Managed capabilities and proxy services");
    expect(html).toContain("billing@supertrained.ai");
    expect(html).toContain("State of Florida, United States");
    expect(html).toContain("7901 4th St N STE 300");
  });
});
