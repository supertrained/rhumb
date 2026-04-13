import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

(globalThis as typeof globalThis & { React: typeof React }).React = React;

async function renderDocsPage(): Promise<string> {
  const module = await import("../app/docs/page");
  const page = await module.default();
  return renderToStaticMarkup(page);
}

describe("docs page", () => {
  it("renders the current MCP tool surface and resolve handoff guidance", async () => {
    const html = await renderDocsPage();

    expect(html).toContain("resolve_capability");
    expect(html).toContain("credential-mode filtering");
    expect(html).toContain("machine-readable recovery handoffs");
    expect(html).toContain("search suggestions when the capability ID is wrong");
    expect(html).toContain("estimate_capability");
    expect(html).toContain("check_credentials");
    expect(html).toContain("rhumb_list_recipes");
    expect(html).toContain("get_receipt");

    expect(html).not.toContain("estimate_cost");
    expect(html).not.toContain("get_credentials");
    expect(html).not.toContain("search_services");
    expect(html).not.toContain("get_ceremonies");
  });
});
