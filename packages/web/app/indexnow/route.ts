import { NextResponse } from "next/server";

/**
 * IndexNow key verification endpoint.
 * IndexNow crawlers hit GET /indexnow to retrieve the plain-text key.
 *
 * Set INDEXNOW_KEY in your environment. It should be a UUID without dashes
 * (e.g. a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4).
 *
 * Docs: https://www.indexnow.org/documentation
 */
export async function GET(): Promise<NextResponse> {
  const key = process.env.INDEXNOW_KEY;

  if (!key) {
    return new NextResponse("IndexNow key not configured", { status: 404 });
  }

  return new NextResponse(key, {
    status: 200,
    headers: {
      "Content-Type": "text/plain",
      "Cache-Control": "public, max-age=86400",
    },
  });
}
