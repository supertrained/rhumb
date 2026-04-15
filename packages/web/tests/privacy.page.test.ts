import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

async function renderPrivacyPage(): Promise<string> {
  const module = await import("../app/privacy/page");
  return renderToStaticMarkup(module.default());
}

describe("privacy page", () => {
  it("keeps the live Next privacy surface aligned with the current legal authority", async () => {
    const html = await renderPrivacyPage();

    expect(html).toContain("Last updated: March 20, 2026");
    expect(html).toContain("Supertrained Inc.");
    expect(html).toContain("Account data (if you sign up)");
    expect(html).toContain("rhumb_session");
    expect(html).toContain("Execution records:");
    expect(html).toContain("Managed credentials");
    expect(html).toContain("bring-your-own-key (BYOK)");
    expect(html).toContain("Agent Vault");
    expect(html).toContain("encrypted provider credential scoped to your agent");
    expect(html).toContain("injects it only at call time");
    expect(html).toContain("Railway Privacy Policy");
    expect(html).toContain("We will respond within 30 days.");
    expect(html).toContain("Children&#x27;s privacy");
    expect(html).toContain("7901 4th St N STE 300");
  });
});
