# Together AI — Agent-Native Service Guide

> **AN Score:** 6.32 · **Tier:** L3 · **Category:** AI & Machine Learning

---

## 1. Synopsis
Together AI provides a high-performance inference API for the world's leading open-source models, including Llama 3.1, Mixtral, Qwen, and specialized code-generation models. For agents, Together AI is a critical infrastructure layer that offers a "best of both worlds" approach: the flexibility and cost-efficiency of open-source weights combined with the reliability of a managed, production-grade API. Its primary value proposition for agent operators is the OpenAI-compatible interface, which allows agents to swap inference providers by changing a single base URL. While Together AI does not offer a permanent free tier, it typically provides $5 in starting credits for new accounts—sufficient for millions of tokens of testing across their smaller model variants.

---

## 2. Connection Methods

### REST API
Together AI exposes a RESTful API that is strictly compliant with the OpenAI specification. This is the primary connection method for agents. Most endpoints reside under `https://api.together.xyz/v1`. This compatibility allows agents to use existing OpenAI client libraries by simply reconfiguring the `base_url`.

### SDKs
Official SDKs are maintained for **Python** (`pip install together`) and **TypeScript/JavaScript** (`npm install togetherai`). These libraries provide typed interfaces for model inference, fine-tuning management, and image generation. The Python SDK includes built-in support for asynchronous requests, which is essential for agents managing multiple concurrent thought streams or tool executions.

### Auth Flows
Authentication is handled via a single **Bearer Token** (API Key). Agents should retrieve this from the `TOGETHER_API_KEY` environment variable. The service supports project-level organization, but most agent integrations rely on a global API key. There is no support for OAuth2 or short-lived session tokens, making secure environment management a prerequisite for agent deployment.

### Webhooks
Together AI does not currently offer webhooks for standard inference. For long-running operations like fine-tuning jobs, agents must poll the `GET /v1/fine-tunes/{id}` endpoint to determine job status.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Chat Completions** | `POST /v1/chat/completions` | Primary interface for agent reasoning; supports Llama 3, Mixtral, etc. |
| **Language Models** | `POST /v1/completions` | Base model access for completion tasks without chat templating. |
| **Embeddings** | `POST /v1/embeddings` | Generates vector representations for RAG and semantic memory. |
| **Image Generation** | `POST /v1/images/generations` | Supports Flux.1, SDXL, and other open image models. |
| **Model Discovery** | `GET /v1/models` | Programmatic list of available models and their current status. |
| **Fine-tuning** | `POST /v1/fine-tunes` | Allows agents to trigger custom model training on specific datasets. |

---

## 4. Setup Guide

### For Humans
1. Create an account at [together.ai](https://www.together.ai/).
2. Navigate to the **Settings > API Keys** section.
3. Copy your default API key or create a new one for a specific project.
4. Add a payment method under **Billing** to ensure uninterrupted service once initial credits are exhausted.
5. Explore the **Playground** to test model performance and system prompts.
6. Verify model availability in your specific region via the dashboard.

### For Agents
1. **Provision Credentials:** Inject `TOGETHER_API_KEY` into the agent's environment.
2. **Endpoint Configuration:** Set the base URL to `https://api.together.xyz/v1` if using a generic OpenAI client.
3. **Capability Discovery:** Execute a `GET /v1/models` call to cache the list of supported model strings (e.g., `meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo`).
4. **Health Check:** Perform a minimal token completion (e.g., "ok") to verify connectivity and latency.
5. **Context Window Check:** Programmatically verify the `max_context_length` for the selected model to prevent overflow errors.

---

## 5. Integration Example

```python
import os
from together import Together

# Initialize client
client = Together(api_key=os.environ.get("TOGETHER_API_KEY"))

# Agent reasoning loop
def agent_think(task_description):
    response = client.chat.completions.create(
        model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        messages=[
            {"role": "system", "content": "You are a precise autonomous agent."},
            {"role": "user", "content": task_description}
        ],
        max_tokens=512,
        temperature=0.0, # High determinism for agent logic
        stop=["\nAgent:"],
        stream=False
    )
    
    # Extract reasoning
    thought = response.choices[0].message.content
    return thought

# Example execution
result = agent_think("Analyze the logs and identify the root cause of the 429 error.")
print(f"Agent Thought: {result}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 380ms | Time to first token for standard 7B-70B models. |
| **P95 Latency** | 950ms | Expected during peak load or for very long prompts. |
| **P99 Latency** | 1900ms | Rare spikes; agents should implement a 2s timeout. |
| **Rate Limits** | Variable | Tier-based. Starts at ~3,000 RPM for paid accounts. |
| **Throughput** | High | Specialized "Turbo" models optimized for tokens/sec. |
| **Availability** | 99.9% | Generally stable, though individual models may go offline for updates. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Inference is stateless. Agents should manage their own state/history. Repeated requests with the same `seed` and `temperature: 0` are largely deterministic but not guaranteed across model updates.
*   **Retry Behavior:** Agents should implement exponential backoff specifically for **HTTP 429 (Rate Limit)** and **HTTP 503 (Overloaded)**. The Python SDK handles basic retries, but custom logic is recommended for mission-critical loops.
*   **Error Codes:** 
    *   `401`: Key rotation required.
    *   `429`: Pause execution; back off for 5-10 seconds.
    *   `400`: Context window exceeded; agent must truncate or summarize history.
*   **Schema Stability:** Together AI adheres strictly to the OpenAI JSON schema for chat completions, making it highly stable for agents using `response_format={"type": "json_object"}`.
*   **Cost-per-operation:** Significantly lower than closed-source providers. For example, Llama 3.1 8B is often priced at $0.18 per million tokens, allowing for high-frequency "thinking" steps that would be cost-prohibitive on GPT-4o.
*   **Model Strings:** Unlike OpenAI, Together uses full paths (e.g., `provider/model-name`). Agents must be configured to handle these longer identifiers.
*   **Function Calling:** Support for tool use (function calling) is model-dependent. Agents must verify that the selected model (like Llama 3.1) explicitly supports the `tools` parameter.

---

## 8. Rhumb Context: Why Together AI Scores 6.32 (L3)

Together AI’s **6.32 score** identifies it as a highly capable, "Ready" service that excels in execution speed and cost, though it lacks some of the governance depth found in enterprise-first providers.

1. **Execution Autonomy (7.0)** — The platform provides excellent support for structured outputs and tool use on supported models. The "Turbo" endpoints provide the low-latency response times (P50: 380ms) required for agents to feel responsive in real-time loops. The deterministic `temperature: 0` and `seed` support are robust, allowing agents to produce repeatable results.

2. **Access Readiness (5.8)** — While the sign-up process is fast, the score is tempered by the lack of a permanent free tier and the requirement for manual billing setup for production volumes. However, the OpenAI-compatible API surface means that an agent already "knows" how to talk to Together AI if it can talk to OpenAI, drastically reducing the integration hurdle.

3. **Agent Autonomy (5.67)** — Together AI scores well here due to its breadth of models. An agent can autonomously decide to switch from a high-power 405B model for complex reasoning to a cheap 8B model for simple summarization without changing its underlying API client logic. The main friction point is the manual management of API keys and the lack of advanced team/permission scoping (Governance Readiness: 5).

**Bottom line:** Together AI is the premier choice for agent operators who prioritize open-source flexibility and low latency. It is the best-in-class option for "router" agents that need to dispatch tasks across a variety of model architectures (Llama, Qwen, Mixtral) using a unified interface.

**Competitor context:** **Groq (6.8)** scores higher on pure execution speed but has a much more limited model selection. **OpenAI (7.9)** scores higher due to its superior ecosystem and built-in "Assistant" abstractions, but Together AI wins on cost-per-token and model diversity.
