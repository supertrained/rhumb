import type { APIRoute } from 'astro';

const API_BASE = import.meta.env.PUBLIC_API_BASE_URL ?? "http://localhost:8000/v1";
const ALLOWED_EVENTS = new Set([
  "provider_click",
  "docs_click",
  "dispute_click",
  "github_dispute_click",
  "contact_click",
]);

function extractUtmParams(referer: string | null): Record<string, string | null> {
  if (!referer) {
    return {
      utm_source: null,
      utm_medium: null,
      utm_campaign: null,
      utm_content: null,
    };
  }

  try {
    const url = new URL(referer);
    return {
      utm_source: url.searchParams.get("utm_source"),
      utm_medium: url.searchParams.get("utm_medium"),
      utm_campaign: url.searchParams.get("utm_campaign"),
      utm_content: url.searchParams.get("utm_content"),
    };
  } catch {
    return {
      utm_source: null,
      utm_medium: null,
      utm_campaign: null,
      utm_content: null,
    };
  }
}

function isAllowedDestination(destinationUrl: string): boolean {
  return (
    destinationUrl.startsWith("https://")
    || destinationUrl.startsWith("http://")
    || destinationUrl.startsWith("mailto:")
  );
}

export const GET: APIRoute = async ({ url, request }) => {
  const destinationUrl = url.searchParams.get("to");
  const eventType = url.searchParams.get("event");
  const serviceSlug = url.searchParams.get("service");
  const explicitPagePath = url.searchParams.get("page_path");
  const sourceSurface = url.searchParams.get("source_surface") ?? "unknown";

  if (!destinationUrl || !eventType || !ALLOWED_EVENTS.has(eventType) || !isAllowedDestination(destinationUrl)) {
    return new Response(null, {
      status: 307,
      headers: { Location: "/" },
    });
  }

  const referer = request.headers.get("referer");
  let inferredPagePath: string | null = explicitPagePath;
  if (!inferredPagePath && referer) {
    try {
      inferredPagePath = new URL(referer).pathname;
    } catch {
      inferredPagePath = null;
    }
  }

  const utmParams = extractUtmParams(referer);

  // Fire-and-forget tracking POST
  try {
    fetch(`${API_BASE}/clicks`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Rhumb-Client": "web",
      },
      body: JSON.stringify({
        event_type: eventType,
        destination_url: destinationUrl,
        service_slug: serviceSlug,
        page_path: inferredPagePath,
        source_surface: sourceSurface,
        ...utmParams,
      }),
    }).catch(() => {
      // Tracking must never block the outbound redirect.
    });
  } catch {
    // Tracking must never block the outbound redirect.
  }

  return new Response(null, {
    status: 307,
    headers: {
      Location: destinationUrl,
    },
  });
};
