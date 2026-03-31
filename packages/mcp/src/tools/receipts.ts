/**
 * get_receipt tool handler
 *
 * Retrieve an execution receipt by ID. Receipts are the immutable
 * ground truth for every Resolve execution — they contain provider
 * used, cost, latency, chain hash, and routing explanation.
 */

import type { RhumbApiClient } from "../api-client.js";

export interface GetReceiptInput {
  receipt_id: string;
}

export async function handleGetReceipt(
  input: GetReceiptInput,
  client: RhumbApiClient
): Promise<Record<string, unknown>> {
  const base = (client as any).baseUrl || "https://api.rhumb.dev/v1";
  const v2Base = base.replace(/\/v1$/, "/v2");
  const url = `${v2Base}/receipts/${encodeURIComponent(input.receipt_id)}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const apiKey = (client as any).apiKey;
  if (apiKey) {
    headers["X-Rhumb-Key"] = apiKey;
  }

  const resp = await fetch(url, { headers });
  const data = await resp.json();

  if (!resp.ok) {
    return {
      error: true,
      status: resp.status,
      ...(typeof data === "object" && data !== null ? data : { message: String(data) }),
    };
  }

  return typeof data === "object" && data !== null ? data : { result: data };
}
