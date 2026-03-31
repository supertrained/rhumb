import type { RhumbApiClient } from "../api-client.js";
import type { GetRecipeInput, GetRecipeOutput } from "../types.js";

export async function handleGetRecipe(
  input: GetRecipeInput,
  client: RhumbApiClient,
): Promise<GetRecipeOutput | null> {
  try {
    if (!client.getRecipe) {
      return null;
    }
    return await client.getRecipe(input.recipe_id);
  } catch {
    return null;
  }
}
