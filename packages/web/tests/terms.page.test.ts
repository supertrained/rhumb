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
    expect(html).toContain("Outcomes of public disputes are published on GitHub");
  });
});
