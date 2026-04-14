import { readFileSync } from "node:fs";
import { join } from "node:path";

import { getCategories, getLeaderboard, getServices } from "../../lib/api";

const CANONICAL_LLMS = readFileSync(
  join(process.cwd(), "public/llms.txt"),
  "utf8",
).trimEnd();

export const revalidate = 3600;

function formatCategoryLabel(slug: string) {
  return slug
    .split("-")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export async function GET() {
  const [services, categories] = await Promise.all([
    getServices(),
    getCategories(),
  ]);

  const categoryData = await Promise.all(
    categories.map(async (category) => {
      const leaderboard = await getLeaderboard(category.slug, { limit: 50 });
      return {
        category,
        items: leaderboard.error ? [] : leaderboard.items,
      };
    }),
  );

  const categoryList = categories
    .map(
      (category) =>
        `- /leaderboard/${category.slug} (${category.serviceCount} services)`
    )
    .join("\n");

  const serviceList = services
    .map(
      (service) =>
        `- /service/${service.slug} — ${service.description ?? service.name} [${service.category}]`
    )
    .join("\n");

  const rankedSnapshot = categoryData
    .map(({ category, items }) => {
      const label = formatCategoryLabel(category.slug);
      const header = `### ${label} (${items.length} ranked in this snapshot)`;

      if (items.length === 0) {
        return `${header}\n- No ranked services were returned for this category in the current snapshot.`;
      }

      const rows = items
        .map(
          (item) =>
            `- **${item.name}** (${item.serviceSlug}): AN Score ${item.aggregateRecommendationScore?.toFixed(1) ?? "N/A"} | Execution ${item.executionScore?.toFixed(1) ?? "N/A"} | Access ${item.accessReadinessScore?.toFixed(1) ?? "N/A"} | Tier ${item.tier ?? "N/A"} → /service/${item.serviceSlug}`,
        )
        .join("\n");

      return `${header}\n${rows}`;
    })
    .join("\n\n");

  const content = `${CANONICAL_LLMS}

## Extended llms-full snapshot
- This route extends the canonical /llms.txt surface with a live category and service snapshot.
- The product, trust, auth, and dispute guidance above remains the authority contract.
- Current fetched snapshot: ${services.length} services across ${categories.length} categories.

## Detailed category index (${categories.length} fetched categories)
${categoryList}

## Detailed scored-service index (${services.length} fetched services)
${serviceList}

## Per-category ranked snapshot
${rankedSnapshot}
`;

  return new Response(content, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
}
