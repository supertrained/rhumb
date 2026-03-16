/**
 * budget tool handler
 *
 * Get or set agent budget. Supports:
 * - action="get" (default): check current budget status
 * - action="set": create/update budget
 */

import type { RhumbApiClient } from "../api-client.js";
import type { BudgetInput, BudgetOutput } from "../types.js";

export async function handleBudget(
  input: BudgetInput,
  client: RhumbApiClient
): Promise<BudgetOutput> {
  const action = input.action || "get";

  if (action === "set") {
    if (!input.budget_usd || input.budget_usd <= 0) {
      return {
        agent_id: "",
        budget_usd: null,
        spent_usd: null,
        remaining_usd: null,
        period: null,
        hard_limit: null,
        unlimited: false,
      };
    }
    const result = await client.setBudget(
      input.budget_usd,
      input.period,
      input.hard_limit
    );
    return result as unknown as BudgetOutput;
  }

  // Default: get
  const result = await client.getBudget();
  return result as unknown as BudgetOutput;
}
