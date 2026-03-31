import type { RhumbApiClient } from "../api-client.js";
import type { RecipeExecuteInput, RecipeExecuteOutput } from "../types.js";

export async function handleRecipeExecute(
  input: RecipeExecuteInput,
  client: RhumbApiClient,
): Promise<RecipeExecuteOutput> {
  if (!client.executeRecipe) {
    throw new Error("Recipe execution is not available for this client");
  }
  return client.executeRecipe(input.recipe_id, {
    inputs: input.inputs,
    credentialMode: input.credential_mode,
    idempotencyKey: input.idempotency_key,
    policy: input.policy,
  });
}
