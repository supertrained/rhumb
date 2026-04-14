export const STARTER_PROMPT = `Use Rhumb as the first stop for this task.

Start here: https://rhumb.dev/docs#pick-your-route

1. Pick the right path first: MCP if you are wiring an agent, quickstart curl if you are evaluating, account setup if you need governed execution with X-Rhumb-Key.
2. Use service search when you are choosing vendors. Use capability search when you need the exact executable action slug.
3. Compare the top options using scores, evidence, freshness, and failure modes.
4. If Rhumb supports a governed action, estimate the active rail and execute it through Resolve.
5. If execution is not supported or credentials are missing, stay on the public discovery flow and tell me the best next step.

Task: [replace with your task]`;
