import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const source = readFileSync(new URL("../src/pages/index.astro", import.meta.url), "utf8");
const logoPng = readFileSync(new URL("../public/logo.png", import.meta.url));

const DESCRIPTION =
  "Rhumb is the tool discovery and governed access layer for AI agents: use Index to compare capabilities and evidence, then use Resolve for supported execution routes.";

function pageDescription(): string {
  const match = source.match(/const description =\n  "([^"]*)";/);
  assert.ok(match, "homepage description constant missing");
  return match[1];
}

function extractObjectLiteral(constName: string): string {
  const marker = `const ${constName} = `;
  const start = source.indexOf(marker);
  assert.ok(start >= 0, `missing ${constName}`);
  const brace = source.indexOf("{", start + marker.length);
  assert.ok(brace >= 0, `missing object for ${constName}`);
  let depth = 0;
  for (let i = brace; i < source.length; i++) {
    const ch = source[i];
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return source.slice(brace, i + 1);
    }
  }
  throw new Error(`unterminated ${constName}`);
}

function evalLiteral(literal: string, description: string): Record<string, unknown> {
  return new Function("description", `"use strict"; return (${literal});`)(description) as Record<
    string,
    unknown
  >;
}

function pngSize(buf: Buffer): { width: number; height: number } {
  assert.equal(buf.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

describe("RH-10 homepage brand JSON-LD", () => {
  const description = pageDescription();
  const website = evalLiteral(extractObjectLiteral("WEBSITE_JSON_LD"), description);
  const organization = evalLiteral(extractObjectLiteral("HOME_JSON_LD"), description);
  const logo = organization.logo as Record<string, unknown>;

  it("emits WebSite first, then Organization, then the existing agent route", () => {
    assert.match(
      source,
      /jsonLdBlocks=\{\[WEBSITE_JSON_LD, HOME_JSON_LD, AGENT_ROUTE_JSON_LD\]\}/,
    );
    assert.equal(website["@context"], "https://schema.org");
    assert.equal(website["@type"], "WebSite");
    assert.equal(organization["@context"], "https://schema.org");
    assert.equal(organization["@type"], "Organization");
  });

  it("names the site Rhumb and joins WebSite to Organization", () => {
    assert.equal(website["@id"], "https://rhumb.dev/#website");
    assert.equal(website.name, "Rhumb");
    assert.deepEqual(website.alternateName, ["rhumb.dev", "Rhumb Labs"]);
    assert.equal(website.url, "https://rhumb.dev/");
    assert.equal(website.inLanguage, "en");
    assert.deepEqual(website.publisher, { "@id": "https://rhumb.dev/#organization" });

    assert.equal(organization["@id"], "https://rhumb.dev/#organization");
    assert.equal(organization.name, "Rhumb");
    assert.deepEqual(organization.alternateName, ["Rhumb Labs", "rhumb.dev"]);
    assert.equal(organization.url, "https://rhumb.dev/");
    assert.equal(description, DESCRIPTION);
    assert.equal(organization.description, description);
  });

  it("points Organization.logo at the 512 logo.png and keeps sameAs to GitHub only", () => {
    const size = pngSize(logoPng);
    assert.equal(size.width, 512);
    assert.equal(size.height, 512);
    assert.equal(logo["@type"], "ImageObject");
    assert.equal(logo.url, "https://rhumb.dev/logo.png");
    assert.equal(logo.width, size.width);
    assert.equal(logo.height, size.height);
    assert.equal(source.includes("favicon.ico"), false);
    assert.equal(source.includes("npmjs.com"), false);
    assert.equal(source.includes("x.com"), false);
    assert.deepEqual(organization.sameAs, ["https://github.com/supertrained/rhumb"]);
  });

  it("leaves the homepage title, meta, and visible sections alone", () => {
    assert.match(source, /title="Rhumb \| From task to trusted tool call"/);
    assert.match(source, /ogTitle="Rhumb \| From task to trusted tool call"/);
    assert.match(source, /canonical="https:\/\/rhumb\.dev\/"/);
    const body = source.split("---").at(-1) ?? "";
    for (const section of [
      "<Hero />",
      "<StatsStrip />",
      "<DualEntry />",
      "<JourneySection />",
      "<ProductModel />",
      "<EvidenceSection />",
      "<QuickstartSection />",
      "<FinalCTA />",
    ]) {
      assert.equal(body.includes(section), true, section);
    }
  });

  it("serializes both brand blocks as JSON-LD scripts would", () => {
    const blocks = [website, organization].map((block) => JSON.parse(JSON.stringify(block)));
    assert.equal(blocks[0]["@type"], "WebSite");
    assert.equal(blocks[1]["@type"], "Organization");
    assert.equal(blocks[1].logo.url, "https://rhumb.dev/logo.png");
  });
});
