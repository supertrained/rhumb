/**
 * get_ledger tool handler
 *
 * Returns recent billing ledger entries with optional filtering.
 * Clamps limit to 1–100 range.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { GetLedgerInput, GetLedgerOutput } from "../types.js";

export async function handleGetLedger(
  input: GetLedgerInput,
  client: RhumbApiClient
): Promise<GetLedgerOutput> {
  const limit = Math.min(Math.max(input.limit ?? 20, 1), 100);

  try {
    const ledger = await client.getLedger(limit, input.event_type);
    return ledger;
  } catch (err) {
    return {
      entries: [],
      total_count: 0,
    };
  }
}
