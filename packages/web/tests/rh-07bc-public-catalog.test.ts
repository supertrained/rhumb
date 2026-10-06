import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  collectPagedRows,
  displayedServiceCount,
  isPublishableTrackedServiceCount,
} from "../../astro-web/src/lib/public-catalog";
import { PUBLIC_TRUTH_COUNTS } from "../../astro-web/src/lib/public-truth-counts";

const api = readFileSync(new URL("../../astro-web/src/lib/api.ts", import.meta.url), "utf8");
const leaderboard = readFileSync(
  new URL("../../astro-web/src/pages/leaderboard/index.astro", import.meta.url),
  "utf8",
);

function sliceExport(source: string, signature: string): string {
  const start = source.indexOf(signature);
  expect(start).toBeGreaterThan(-1);
  const next = source.indexOf("\nexport ", start + signature.length);
  return source.slice(start, next === -1 ? undefined : next);
}

describe("RH-07bc public catalog count", () => {
  it("keeps the committed public integers", () => {
    expect(PUBLIC_TRUTH_COUNTS.services).toBe(999);
    expect(PUBLIC_TRUTH_COUNTS.capabilities).toBe(435);
    expect(PUBLIC_TRUTH_COUNTS.callableProviders).toBe(28);
    expect(PUBLIC_TRUTH_COUNTS.categories).toBe(87);
  });

  it("shows the API total and never the PostgREST cap or the scores-table size", () => {
    expect(displayedServiceCount(999)).toBe(999);
    expect(displayedServiceCount(1000)).toBe(999);
    expect(displayedServiceCount(1048)).toBe(999);
    expect(displayedServiceCount(0)).toBe(999);
    expect(displayedServiceCount(Number.NaN)).toBe(999);
    expect(displayedServiceCount(1000, 1048)).toBe(999);
    expect(displayedServiceCount(1048, 1000)).toBe(999);
    expect(isPublishableTrackedServiceCount(999)).toBe(true);
    expect(isPublishableTrackedServiceCount(1000)).toBe(false);
    expect(isPublishableTrackedServiceCount(1048)).toBe(false);
    // A later live total that is neither blocked number still wins.
    expect(displayedServiceCount(1001)).toBe(1001);
  });

  it("pages past a 1000-row PostgREST page", async () => {
    const pages = [
      Array.from({ length: 1000 }, (_, index) => index),
      Array.from({ length: 48 }, (_, index) => 1000 + index),
      [],
    ];
    const calls: Array<[number, number]> = [];
    const rows = await collectPagedRows(async (limit, offset) => {
      calls.push([limit, offset]);
      return pages.shift() ?? [];
    });
    expect(rows).toHaveLength(1048);
    expect(calls).toEqual([
      [1000, 0],
      [1000, 1000],
      [1000, 2000],
    ]);
    expect(displayedServiceCount(rows?.length ?? 0)).toBe(999);
  });

  it("returns null on a failed first page and keeps rows when a later page fails", async () => {
    expect(await collectPagedRows(async () => null)).toBeNull();
    let calls = 0;
    const partial = await collectPagedRows(async () => {
      calls += 1;
      if (calls === 1) return ["a", "b"];
      return null;
    }, 2);
    expect(partial).toEqual(["a", "b"]);
  });
});

describe("RH-07bc astro reads", () => {
  it("pages list reads, filters evidence on source_type, and does not headline the scores table", () => {
    expect(api).toContain("collectPagedRows");
    expect(api).toContain("supabaseFetchAll");
    const evidenceFilters = api.match(/evidence_records\?[^`"\n]*/g) ?? [];
    expect(evidenceFilters.length).toBe(2);
    for (const filter of evidenceFilters) {
      expect(filter).not.toContain("evidence_type");
      expect(filter).toContain("source_type=in.(runtime_verified,tester_generated)");
    }
    expect(api).toContain(
      "source_type=in.(runtime_verified,tester_generated)&select=created_at&order=created_at.desc,id.desc",
    );
    expect(api).toContain(
      "source_type=in.(runtime_verified,tester_generated)&select=service_slug&order=service_slug.asc,id.asc",
    );
    expect(api).toContain("services?select=slug,name,category,description&order=name.asc,slug.asc");
    expect(api).toContain("services?select=category,slug&order=slug.asc");

    const countFn = sliceExport(api, "export async function getServiceCount");
    expect(countFn).toContain("getServiceCountFromAPI");
    expect(countFn).toContain("supabaseFetchAll");
    expect(countFn).toContain("scores?select=service_slug&order=service_slug.asc,id.asc");
    expect(countFn).toContain("isPublishableTrackedServiceCount");
    expect(countFn).toContain("displayedServiceCount");
    expect(countFn).not.toContain("return new Set");

    expect(leaderboard).toContain("displayedServiceCount");
    expect(leaderboard).toContain("PUBLIC_TRUTH.services");
    expect(leaderboard).not.toContain("categoryServicesTotal");
    expect(leaderboard).not.toContain("1000");
    expect(leaderboard).not.toContain("1048");
  });
});
