import type { RhumbApiClient } from "../api-client.js";
import type { ListRecipesInput, ListRecipesOutput } from "../types.js";

export async function handleListRecipes(
  input: ListRecipesInput,
  client: RhumbApiClient,
): Promise<ListRecipesOutput> {
  try {
    if (!client.listRecipes) {
      return { recipes: [], total: 0 };
    }
    const result = await client.listRecipes({
      category: input.category,
      stability: input.stability,
      limit: input.limit ?? 20,
    });
    return {
      recipes: result.items,
      total: result.total,
    };
  } catch {
    return { recipes: [], total: 0 };
  }
}
