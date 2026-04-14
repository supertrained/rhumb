import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

async function renderProvidersPage(): Promise<string> {
  const module = await import("../app/providers/page");
  return renderToStaticMarkup(module.default());
}

describe("providers page", () => {
  it("routes dispute and contact links through first-party tracking", async () => {
    const html = await renderProvidersPage();

    expect(html).toContain("id=\"dispute-a-score\"");
    expect(html).toContain("href=\"/go?to=https%3A%2F%2Fgithub.com%2Fsupertrained%2Frhumb%2Fissues%2Fnew%3Ftemplate%3Dscore-dispute.md&amp;event=github_dispute_click");
    expect(html).toContain("href=\"/go?to=mailto%3Aproviders%40supertrained.ai%3Fsubject%3DScore%2520Dispute%2520%28Private%29&amp;event=dispute_click");
    expect(html).toContain("href=\"/go?to=mailto%3Aproviders%40supertrained.ai&amp;event=contact_click");
  });

  it("keeps the full dispute contract visible on the live Next providers surface", async () => {
    const html = await renderProvidersPage();

    expect(html).toContain("within 5 business days");
    expect(html).toContain("What to include");
    expect(html).toContain("The specific service, score, or data point you believe is wrong");
    expect(html).toContain("The evidence source we should review, like docs, changelogs, or live behavior");
    expect(html).toContain("Why the current score or explanation is inaccurate or stale");
    expect(html).toContain("Whether your report can be handled publicly or needs a private path first");
    expect(html).toContain("the public dispute log");
    expect(html).toContain("href=\"https://github.com/supertrained/rhumb/issues?q=is%3Aissue+%22Score+dispute%3A%22\"");
  });
});
