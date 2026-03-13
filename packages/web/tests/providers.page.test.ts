import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

async function renderProvidersPage(): Promise<string> {
  const module = await import("../app/providers/page");
  return renderToStaticMarkup(module.default());
}

describe("providers page", () => {
  it("routes dispute and contact links through first-party tracking", async () => {
    const html = await renderProvidersPage();

    expect(html).toContain("href=\"/go?to=https%3A%2F%2Fgithub.com%2Fsupertrained%2Frhumb%2Fissues%2Fnew%3Ftemplate%3Dscore-dispute.md&amp;event=github_dispute_click");
    expect(html).toContain("href=\"/go?to=mailto%3Aproviders%40supertrained.ai%3Fsubject%3DScore%2520Dispute%2520%28Private%29&amp;event=dispute_click");
    expect(html).toContain("href=\"/go?to=mailto%3Aproviders%40supertrained.ai&amp;event=contact_click");
  });
});
