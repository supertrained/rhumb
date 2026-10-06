import { PUBLIC_TRUTH_COUNTS } from "./public-truth-counts";

/**
 * Numbers that must not be shown as the tracked service count.
 * 1000 is the PostgREST max-rows cap (an unpaged `scores` read).
 * 1048 is the paged `scores` / `services` table size, which includes rows
 * the public API does not list. The published catalog is GET /v1/services
 * `data.total` (PUBLIC_TRUTH_COUNTS.services, 999).
 */
const BLOCKED_TRACKED_SERVICE_COUNTS = new Set<number>([1000, 1048]);

export function isPublishableTrackedServiceCount(count: number): boolean {
  return Number.isFinite(count) && count > 0 && !BLOCKED_TRACKED_SERVICE_COUNTS.has(count);
}

/**
 * Headline service count. Prefer a live candidate (the public API total).
 * Reject the PostgREST cap and the scores-table size. Fall back to the
 * committed public catalog, which is also rejected if it is ever one of
 * those two blocked numbers.
 */
export function displayedServiceCount(
  candidate: number,
  publishedFallback: number = PUBLIC_TRUTH_COUNTS.services,
): number {
  if (isPublishableTrackedServiceCount(candidate)) return candidate;
  if (isPublishableTrackedServiceCount(publishedFallback)) return publishedFallback;
  return PUBLIC_TRUTH_COUNTS.services;
}

/**
 * Walk a list with limit/offset until an empty page.
 * One PostgREST response stops at max-rows (Supabase default 1000). Callers
 * that need the whole list (sitemap services, categories, evidence) pass a
 * `fetchPage` that already includes a stable `order=`.
 * A failed first page returns null. A failed later page returns the rows
 * already collected. Stops after `maxPages` (default 50).
 */
export async function collectPagedRows<T>(
  fetchPage: (limit: number, offset: number) => Promise<T[] | null>,
  pageSize = 1000,
  maxPages = 50,
): Promise<T[] | null> {
  const rows: T[] = [];
  for (let page = 0; page < maxPages; page += 1) {
    const batch = await fetchPage(pageSize, page * pageSize);
    if (!batch) return page === 0 ? null : rows;
    if (batch.length === 0) break;
    rows.push(...batch);
  }
  return rows;
}
