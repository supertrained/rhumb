import type { APIRoute } from 'astro';

/**
 * IndexNow key verification endpoint.
 * IndexNow crawlers hit GET /indexnow to retrieve the plain-text key.
 *
 * Set INDEXNOW_KEY in your environment. It should be a UUID without dashes
 * (e.g. a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4).
 *
 * Docs: https://www.indexnow.org/documentation
 */
export const GET: APIRoute = async () => {
  const key = import.meta.env.INDEXNOW_KEY;

  if (!key) {
    return new Response("IndexNow key not configured", { status: 404 });
  }

  return new Response(key, {
    status: 200,
    headers: {
      "Content-Type": "text/plain",
      "Cache-Control": "public, max-age=86400",
    },
  });
};
