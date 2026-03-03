import type { Service } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/v1";

/** Fetch all services. */
export async function getServices(): Promise<Service[]> {
  const response = await fetch(`${API_BASE}/services`, { cache: "no-store" });
  if (!response.ok) {
    return [];
  }
  const payload = (await response.json()) as { data?: { items?: Service[] } };
  return payload.data?.items ?? [];
}
