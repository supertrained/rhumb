import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import {
  collectPagedRows,
  displayedServiceCount,
  isPublishableTrackedServiceCount,
} from "../src/lib/public-catalog.ts";

const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const counts = readFileSync(new URL("../src/lib/public-truth-counts.ts", import.meta.url), "utf8");
const leaderboard = readFileSync(
  new URL("../src/pages/leaderboard/index.astro", import.meta.url),
  "utf8",
);

function countField(name: string): number {
  const match = counts.match(new RegExp(`${name}:\\s*(\\d+)`));
  assert.ok(match, `missing ${name} in public-truth-counts.ts`);
  return Number(match[1]);
}

function sliceExport(source: string, signature: string): string {
  const start = source.indexOf(signature);
  assert.ok(start >= 0, `missing ${signature}`);
  const next = source.indexOf("\nexport ", start + signature.length);
  return source.slice(start, next === -1 ? undefined : next);
}

describe("RH-07bc public catalog count", () => {
  it("keeps the committed public integers and the last-resort headline", () => {
    assert.equal(countField("services"), 999);
    assert.equal(countField("capabilities"), 435);
    assert.equal(countField("callableProviders"), 28);
    assert.equal(countField("categories"), 87);
    assert.equal(displayedServiceCount(0), 999);
  });

  it("shows the API total and never the PostgREST cap or the scores-table size", () => {
    assert.equal(displayedServiceCount(999), 999);
    assert.equal(displayedServiceCount(1000), 999);
    assert.equal(displayedServiceCount(1048), 999);
    assert.equal(displayedServiceCount(0), 999);
    assert.equal(displayedServiceCount(Number.NaN), 999);
    assert.equal(displayedServiceCount(1000, 1048), 999);
    assert.equal(displayedServiceCount(1048, 1000), 999);
    assert.equal(isPublishableTrackedServiceCount(999), true);
    assert.equal(isPublishableTrackedServiceCount(1000), false);
    assert.equal(isPublishableTrackedServiceCount(1048), false);
    assert.equal(displayedServiceCount(1001), 1001);
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
    assert.equal(rows?.length, 1048);
    assert.deepEqual(calls, [
      [1000, 0],
      [1000, 1000],
      [1000, 2000],
    ]);
    assert.equal(displayedServiceCount(rows?.length ?? 0), 999);
  });

  it("returns null on a failed first page and keeps rows when a later page fails", async () => {
    assert.equal(await collectPagedRows(async () => null), null);
    let calls = 0;
    const partial = await collectPagedRows(async () => {
      calls += 1;
      if (calls === 1) return ["a", "b"];
      return null;
    }, 2);
    assert.deepEqual(partial, ["a", "b"]);
  });
});

describe("RH-07bc astro reads", () => {
  it("pages list reads, filters evidence on source_type, and does not headline the scores table", () => {
    assert.match(api, /collectPagedRows/);
    assert.match(api, /supabaseFetchAll/);
    const evidenceFilters = api.match(/evidence_records\?[^`"\n]*/g) ?? [];
    assert.equal(evidenceFilters.length, 2);
    for (const filter of evidenceFilters) {
      assert.equal(filter.includes("evidence_type"), false);
      assert.match(filter, /source_type=in\.\(runtime_verified,tester_generated\)/);
    }
    assert.match(
      api,
      /source_type=in\.\(runtime_verified,tester_generated\)&select=created_at&order=created_at\.desc,id\.desc/,
    );
    assert.match(
      api,
      /source_type=in\.\(runtime_verified,tester_generated\)&select=service_slug&order=service_slug\.asc,id\.asc/,
    );
    assert.match(api, /services\?select=slug,name,category,description&order=name\.asc,slug\.asc/);
    assert.match(api, /services\?select=category,slug&order=slug\.asc/);

    const countFn = sliceExport(api, "export async function getServiceCount");
    assert.match(countFn, /getServiceCountFromAPI/);
    assert.match(countFn, /supabaseFetchAll/);
    assert.match(countFn, /scores\?select=service_slug&order=service_slug\.asc,id\.asc/);
    assert.match(countFn, /isPublishableTrackedServiceCount/);
    assert.match(countFn, /displayedServiceCount/);
    assert.equal(countFn.includes("return new Set"), false);

    assert.match(leaderboard, /displayedServiceCount/);
    assert.match(leaderboard, /PUBLIC_TRUTH\.services/);
    assert.equal(leaderboard.includes("categoryServicesTotal"), false);
    assert.equal(leaderboard.includes("1000"), false);
    assert.equal(leaderboard.includes("1048"), false);
  });
});
