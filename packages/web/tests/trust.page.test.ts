import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

async function renderTrustPage(): Promise<string> {
  const module = await import("../app/trust/page");
  return renderToStaticMarkup(module.default());
}

describe("trust page", () => {
  it("keeps the public dispute-process guidance visible on the live Next surface", async () => {
    const html = await renderTrustPage();

    expect(html).toContain("href=\"/providers#dispute-a-score\"");
    expect(html).toContain("provider guide");
    expect(html).toContain("5-business-day response target");
    expect(html).toContain("GitHub issue template");
    expect(html).toContain("href=\"https://github.com/supertrained/rhumb/issues/new?template=score-dispute.md\"");
    expect(html).toContain("href=\"mailto:providers@supertrained.ai?subject=Score%20Dispute\"");
    expect(html).toContain("respond within 5 business days");
    expect(html).toContain("href=\"https://github.com/supertrained/rhumb/issues?q=is%3Aissue+%22Score+dispute%3A%22\"");
  });
});
