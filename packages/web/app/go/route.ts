import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/v1";
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

export async function GET(request: NextRequest): Promise<NextResponse> {
  const destinationUrl = request.nextUrl.searchParams.get("to");
  const eventType = request.nextUrl.searchParams.get("event");
  const serviceSlug = request.nextUrl.searchParams.get("service");
  const explicitPagePath = request.nextUrl.searchParams.get("page_path");
  const sourceSurface = request.nextUrl.searchParams.get("source_surface") ?? "unknown";

  if (!destinationUrl || !eventType || !ALLOWED_EVENTS.has(eventType) || !isAllowedDestination(destinationUrl)) {
    return NextResponse.redirect(new URL("/", request.url), { status: 307 });
  }

  const referer = request.headers.get("referer");
  let inferredPagePath = explicitPagePath;
  if (!inferredPagePath && referer) {
    try {
      inferredPagePath = new URL(referer).pathname;
    } catch {
      inferredPagePath = null;
    }
  }

  const utmParams = extractUtmParams(referer);

  try {
    await fetch(`${API_BASE}/clicks`, {
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
      cache: "no-store",
    });
  } catch {
    // Tracking must never block the outbound redirect.
  }

  return new NextResponse(null, {
    status: 307,
    headers: {
      Location: destinationUrl,
    },
  });
}
