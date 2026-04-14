import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

async function renderMethodologyPage(): Promise<string> {
  const module = await import("../app/methodology/page");
  return renderToStaticMarkup(module.default());
}

describe("methodology page", () => {
  it("keeps the public dispute process visible on the live Next surface", async () => {
    const html = await renderMethodologyPage();

    expect(html).toContain("Open a GitHub issue →");
    expect(html).toContain("href=\"https://github.com/supertrained/rhumb/issues/new?template=score-dispute.md\"");
    expect(html).toContain("Email privately →");
    expect(html).toContain("href=\"mailto:providers@supertrained.ai?subject=Score%20Dispute\"");
    expect(html).toContain("Read the dispute process →");
    expect(html).toContain("href=\"/providers#dispute-a-score\"");
    expect(html).toContain("within 5 business days");
  });
});
