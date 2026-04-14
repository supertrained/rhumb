import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getServicesMock } = vi.hoisted(() => ({
  getServicesMock: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  getServices: getServicesMock,
}));

vi.mock("../components/Search", () => ({
  Search: () => null,
}));

async function renderSearchPage(searchParams: Promise<{ q?: string }> = Promise.resolve({})): Promise<string> {
  const module = await import("../app/search/page");
  const page = await module.default({ searchParams });
  return renderToStaticMarkup(page);
}

describe("search page", () => {
  beforeEach(() => {
    getServicesMock.mockReset();
    getServicesMock.mockResolvedValue([]);
  });

  it("renders trust, methodology, and dispute exits in the header", async () => {
    const html = await renderSearchPage();

    expect(html).toContain("Find agent-native tools");
    expect(html).toContain('href="/trust"');
    expect(html).toContain('href="/methodology"');
    expect(html).toContain('href="/providers#dispute-a-score"');
  });
});
