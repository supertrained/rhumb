import MANIFEST from "../../../../../agent-capabilities.json";

export const dynamic = "force-static";

export async function GET() {
  return new Response(JSON.stringify(MANIFEST, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
      "Access-Control-Allow-Origin": "*",
    },
  });
}
