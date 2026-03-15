/**
 * Helpers for first-party outbound click tracking.
 */

export type TrackedClickEvent =
  | "provider_click"
  | "docs_click"
  | "dispute_click"
  | "github_dispute_click"
  | "contact_click";

type BuildTrackedOutboundHrefArgs = {
  destinationUrl: string;
  eventType: TrackedClickEvent;
  serviceSlug?: string;
  pagePath?: string;
  sourceSurface: string;
};

/**
 * Build a first-party redirect URL that logs an outbound click before forwarding.
 */
export function buildTrackedOutboundHref({
  destinationUrl,
  eventType,
  serviceSlug,
  pagePath,
  sourceSurface,
}: BuildTrackedOutboundHrefArgs): string {
  const params = new URLSearchParams({
    to: destinationUrl,
    event: eventType,
    source_surface: sourceSurface,
  });

  if (serviceSlug) {
    params.set("service", serviceSlug);
  }
  if (pagePath) {
    params.set("page_path", pagePath);
  }

  return `/go?${params.toString()}`;
}
