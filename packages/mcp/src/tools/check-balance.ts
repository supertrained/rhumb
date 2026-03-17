/**
 * check_balance tool handler
 *
 * Returns the current credit balance for the organization.
 * Includes a low-balance warning when under $1.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { CheckBalanceInput, CheckBalanceOutput } from "../types.js";

export async function handleCheckBalance(
  _input: CheckBalanceInput,
  client: RhumbApiClient
): Promise<CheckBalanceOutput> {
  try {
    const balance = await client.getBalance();
    return {
      balance_usd: balance.balance_usd,
      balance_usd_cents: balance.balance_usd_cents,
      auto_reload_enabled: balance.auto_reload_enabled,
      message: balance.balance_usd_cents < 100
        ? `⚠️ Low balance: $${balance.balance_usd}. Top up at https://rhumb.dev/pricing`
        : `Balance: $${balance.balance_usd}`,
    };
  } catch (err) {
    return {
      balance_usd: 0,
      balance_usd_cents: 0,
      auto_reload_enabled: false,
      message: `Failed to check balance: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}
