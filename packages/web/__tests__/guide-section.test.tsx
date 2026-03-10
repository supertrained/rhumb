// @vitest-environment jsdom

import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuideSection } from "../components/guide-section";

const SAMPLE_GUIDE = `## Synopsis
A short guide with [docs](https://example.com) and \`inline code\`.

## Setup Guide
\`\`\`bash
npm install demo-service
\`\`\`

| Step | Value |
| --- | --- |
| One | Done |
`;

describe("GuideSection", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(global.navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  afterEach(() => {
    cleanup();
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders without error when given valid markdown", () => {
    render(React.createElement(GuideSection, { guideContent: SAMPLE_GUIDE }));

    expect(screen.getByRole("button", { name: /view integration guide/i })).toBeTruthy();
  });

  it("starts collapsed with guide content hidden", () => {
    render(React.createElement(GuideSection, { guideContent: SAMPLE_GUIDE }));

    expect(screen.queryByText("Synopsis")).toBeNull();
    expect(screen.queryByText(/A short guide/)).toBeNull();
  });

  it("toggle button shows and hides guide content", () => {
    render(React.createElement(GuideSection, { guideContent: SAMPLE_GUIDE }));

    fireEvent.click(screen.getByRole("button", { name: /view integration guide/i }));
    expect(screen.getByRole("button", { name: /hide integration guide/i })).toBeTruthy();
    expect(screen.getByText("Synopsis")).toBeTruthy();
    expect(screen.getByText(/A short guide with/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /hide integration guide/i }));
    expect(screen.getByRole("button", { name: /view integration guide/i })).toBeTruthy();
    expect(screen.queryByText("Synopsis")).toBeNull();
  });

  it("renders a copy button for code blocks", () => {
    render(React.createElement(GuideSection, { guideContent: SAMPLE_GUIDE }));

    fireEvent.click(screen.getByRole("button", { name: /view integration guide/i }));

    expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
    expect(screen.getByText("npm install demo-service")).toBeTruthy();
  });

  it("handles missing guide content gracefully", () => {
    const { container, rerender } = render(
      React.createElement(GuideSection, { guideContent: null })
    );

    expect(container.innerHTML).toBe("");

    rerender(React.createElement(GuideSection, { guideContent: "   " }));
    expect(container.innerHTML).toBe("");
  });
});
