import { describe, it, expect } from "vitest";
import YAML from "yaml";
import fs from "fs";
import path from "path";

const datasetPath = path.join(__dirname, "../public/data/initial-dataset.yaml");
const datasetContent = fs.readFileSync(datasetPath, "utf-8");
const dataset = YAML.parse(datasetContent);

describe("Initial Dataset Schema Validation", () => {
  it("should have valid metadata section", () => {
    expect(dataset.metadata).toBeDefined();
    expect(dataset.metadata.curated_at).toBeDefined();
    expect(dataset.metadata.total_services).toBe(50);
    expect(dataset.metadata.categories).toBe(10);
  });

  it("should have 50 services defined", () => {
    expect(dataset.services).toBeDefined();
    expect(Array.isArray(dataset.services)).toBe(true);
    expect(dataset.services.length).toBe(50);
  });

  it("should have all required service fields", () => {
    const requiredFields = ["slug", "name", "category", "description", "official_docs"];

    dataset.services.forEach((service: any, idx: number) => {
      requiredFields.forEach((field) => {
        expect(service[field]).toBeDefined(
          `Service ${idx} (${service.slug}) missing field: ${field}`
        );
        expect(typeof service[field]).toBe("string");
      });
    });
  });

  it("should have valid slug format (alphanumeric + dashes, 3-50 chars)", () => {
    const slugRegex = /^[a-z0-9-]{3,50}$/;

    dataset.services.forEach((service: any) => {
      expect(service.slug).toMatch(
        slugRegex,
        `Invalid slug format: ${service.slug}`
      );
    });
  });

  it("should have unique slugs", () => {
    const slugs = dataset.services.map((s: any) => s.slug);
    const uniqueSlugs = new Set(slugs);

    expect(uniqueSlugs.size).toBe(slugs.length);

    // Report duplicates if found
    const duplicates = slugs.filter((slug, idx) => slugs.indexOf(slug) !== idx);
    expect(duplicates.length).toBe(0, `Duplicate slugs: ${duplicates.join(", ")}`);
  });

  it("should have valid category assignments (exactly one per service)", () => {
    const validCategories = new Set([
      "email",
      "crm",
      "payments",
      "auth",
      "calendar",
      "analytics",
      "search",
      "devops",
      "social",
      "ai",
    ]);

    dataset.services.forEach((service: any) => {
      expect(validCategories.has(service.category)).toBe(
        true,
        `Invalid category '${service.category}' for ${service.slug}`
      );
    });
  });

  it("should have consistent category distribution", () => {
    const categoryCount = {};

    dataset.services.forEach((service: any) => {
      if (!categoryCount[service.category]) {
        categoryCount[service.category] = 0;
      }
      categoryCount[service.category]++;
    });

    // Verify distribution matches metadata (excluding "total" field)
    const expectedDistribution = { ...dataset.distribution };
    delete expectedDistribution.total;
    expect(categoryCount).toEqual(expectedDistribution);
  });

  it("should have descriptions under 120 characters", () => {
    dataset.services.forEach((service: any) => {
      expect(service.description.length).toBeLessThanOrEqual(120);
      expect(service.description.length).toBeGreaterThan(10);
    });
  });

  it("should have valid documentation URLs", () => {
    const urlRegex = /^https?:\/\/.+/;

    dataset.services.forEach((service: any) => {
      expect(service.official_docs).toMatch(
        urlRegex,
        `Invalid URL for ${service.slug}: ${service.official_docs}`
      );
    });
  });

  it("should have 10 categories with descriptions", () => {
    expect(dataset.categories).toBeDefined();
    expect(Object.keys(dataset.categories).length).toBe(10);
  });

  it("should have correct distribution totals", () => {
    let total = 0;
    Object.entries(dataset.distribution).forEach(([key, count]: any) => {
      if (typeof count === "number" && key !== "total") {
        total += count;
      }
    });

    expect(total).toBe(50);
  });

  it("should have valid metadata timestamp", () => {
    const timestamp = new Date(dataset.metadata.curated_at);
    expect(timestamp.getTime()).toBeGreaterThan(0);
    expect(timestamp.getTime()).toBeLessThanOrEqual(Date.now() + 300000); // within 5 minutes (tolerance for test execution)
    expect(timestamp.getTime()).toBeGreaterThanOrEqual(Date.now() - 3600000); // not older than 1 hour
  });

  it("should have consistent category membership", () => {
    const categoryCounts = {};

    dataset.services.forEach((service: any) => {
      if (!categoryCounts[service.category]) {
        categoryCounts[service.category] = [];
      }
      categoryCounts[service.category].push(service.slug);
    });

    // Verify each service is in exactly one category
    const allSlugs = dataset.services.map((s: any) => s.slug);
    const memberships = Object.values(categoryCounts).flat();

    expect(memberships.length).toBe(allSlugs.length);
    expect(new Set(memberships).size).toBe(allSlugs.length);
  });
});
