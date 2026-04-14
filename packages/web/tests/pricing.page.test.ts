import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

(globalThis as typeof globalThis & { React: typeof React }).React = React;

async function renderPricingPage(): Promise<string> {
  const module = await import("../app/pricing/page");
  const page = await module.default();
  return renderToStaticMarkup(page);
}

describe("pricing page", () => {
  it("renders the current estimate handoff truth for agents", async () => {
    const html = await renderPricingPage();

    expect(html).toContain("estimate_capability");
    expect(html).toContain("active execution rail");
    expect(html).toContain("health, and exact cost");
    expect(html).toContain("machine-readable");
    expect(html).toContain("execute_readiness");
    expect(html).toContain("Anonymous direct system-of-record");

    expect(html).not.toContain("Estimate cost before execution");
    expect(html).not.toContain("will cost before you run it");
  });
});
