import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const ROOT_MANIFEST = JSON.parse(
  readFileSync(new URL("../../../agent-capabilities.json", import.meta.url), "utf8")
) as Record<string, unknown>;

describe("agent capabilities route", () => {
  it("serves the canonical public agent-capabilities contract", async () => {
    const mod = await import("../app/.well-known/agent-capabilities.json/route");
    const res = await mod.GET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("application/json; charset=utf-8");
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe("*");
    expect(body).toEqual(ROOT_MANIFEST);
  });
});
