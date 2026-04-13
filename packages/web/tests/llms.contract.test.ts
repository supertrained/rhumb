import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const ROOT_LLMS = readFileSync(new URL("../../../llms.txt", import.meta.url), "utf8");
const WEB_LLMS = readFileSync(new URL("../public/llms.txt", import.meta.url), "utf8");

describe("llms.txt contract", () => {
  it("matches the canonical root llms surface", () => {
    expect(WEB_LLMS).toBe(ROOT_LLMS);
    expect(WEB_LLMS).toContain("resolve_capability");
    expect(WEB_LLMS).toContain("estimate_capability");
    expect(WEB_LLMS).not.toContain("estimate_cost");
    expect(WEB_LLMS).not.toContain("get_budget_status");
  });
});
