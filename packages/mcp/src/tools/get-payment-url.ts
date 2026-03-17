/**
 * get_payment_url tool handler
 *
 * Returns a Stripe checkout URL to top up Rhumb credits.
 * Validates amount is between $5 and $5,000.
 */

import type { RhumbApiClient } from "../api-client.js";
import type { GetPaymentUrlInput, GetPaymentUrlOutput } from "../types.js";

export async function handleGetPaymentUrl(
  input: GetPaymentUrlInput,
  client: RhumbApiClient
): Promise<GetPaymentUrlOutput> {
  if (input.amount_usd < 5 || input.amount_usd > 5000) {
    return {
      checkout_url: "",
      amount_usd: input.amount_usd,
      message: `Amount must be between $5 and $5,000. You requested $${input.amount_usd}.`,
    };
  }

  try {
    const session = await client.createCheckout(input.amount_usd);
    return {
      checkout_url: session.checkout_url,
      amount_usd: input.amount_usd,
      message: `Complete payment at: ${session.checkout_url}`,
    };
  } catch (err) {
    return {
      checkout_url: "",
      amount_usd: input.amount_usd,
      message: `Failed to create checkout: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}
