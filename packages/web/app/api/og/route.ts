import { NextResponse } from "next/server";

/** Placeholder OG endpoint for social cards. */
export async function GET(): Promise<Response> {
  return NextResponse.json({ data: { message: "OG route scaffold" }, error: null });
}
