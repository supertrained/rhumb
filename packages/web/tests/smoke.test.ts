import { describe, expect, it } from "vitest";

import { cn } from "../lib/utils";

describe("cn", () => {
  it("joins truthy tokens", () => {
    expect(cn("a", false, "b", undefined, "c")).toBe("a b c");
  });
});
