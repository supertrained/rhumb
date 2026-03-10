# OpenAI — Agent-Native Service Guide

> **AN Score:** 7.9 · **Tier:** L3 · **Category:** LLM Provider

---

## 1. Synopsis

OpenAI provides the GPT and o-series family of large language models via API — including GPT-4o, o3, and specialized models for embeddings, image generation (DALL·E), and speech (Whisper, TTS). For agents, OpenAI is a critical inference provider: text generation, code completion, function calling, vision analysis, and embeddings for semantic search. The API is mature, widely adopted, and has the largest ecosystem of tools, libraries, and tutorials. No free API tier; pay-per-token pricing. Playground available at https://platform.openai.com/playground.

---

## 2. Connection Methods

### REST API
- **Base URL:** `https://api.openai.com/v1`
- **Auth:** Bearer token (`Authorization: Bearer sk-...`)
- **Content-Type:** `application/json`
- **Rate Limits:** Tier-based; Tier 1: 500 RPM, 30K TPM for GPT-4o. Increases with usage/spend.
- **Docs:** https://platform.openai.com/docs/api-reference

### SDKs
- **Python:** `pip install openai` — official, comprehensive
- **TypeScript/Node:** `npm install openai` — official
- **Go:** Community SDK (`github.com/sashabaranov/go-openai`)
- **C#, Java, Ruby** — community SDKs available

### MCP
- Community MCP servers for OpenAI exist (check MCP registry)
- OpenAI's function calling natively supports tool-use patterns similar to MCP

### Webhooks
- **Batch API:** Submit batch jobs and poll for completion
- No real-time webhook delivery — use streaming for real-time token output

### Auth Flows
- **API Keys:** Generated in Platform → API Keys
- **Project-scoped keys:** Restrict keys to specific projects
- **Organization-level:** Keys can be scoped to organizations
- **No OAuth** — API key authentication only

---

## 3. Key Primitives

| Primitive | Endpoint | Description |
|-----------|----------|-------------|
| `chat.completions.create` | `POST /v1/chat/completions` | Generate text with conversation history |
| `chat.completions.create` (stream) | Same endpoint, `stream: true` | Streaming token output |
| `embeddings.create` | `POST /v1/embeddings` | Generate vector embeddings for text |
| `images.generate` | `POST /v1/images/generations` | Generate images via DALL·E |
| `audio.transcriptions` | `POST /v1/audio/transcriptions` | Transcribe audio (Whisper) |
| `audio.speech` | `POST /v1/audio/speech` | Text-to-speech |
| `batches.create` | `POST /v1/batches` | Submit batch of requests (50% discount) |

---

## 4. Setup Guide

### For Humans
1. Create account at https://platform.openai.com/signup
2. Add payment method: Settings → Billing → Add payment method
3. Navigate to **API Keys** → Create new secret key
4. Copy the key (starts with `sk-`)
5. Set usage limits: Settings → Limits → set monthly budget
6. Choose default model: `gpt-4o` for balanced quality/speed, `o3` for reasoning-heavy tasks

### For Agents
1. **Credential retrieval:** Pull API key from secure store (env var `OPENAI_API_KEY`)
2. **Connection validation:**
   ```bash
   curl -s https://api.openai.com/v1/models \
     -H "Authorization: Bearer $OPENAI_API_KEY" | jq '.data | length'
   # Should return a number (available models count)
   ```
3. **Error handling:** Check `error.type` — `invalid_api_key`, `rate_limit_exceeded`, `server_error`, `insufficient_quota`, `model_not_found`
4. **Fallback:** On rate limit (429), respect `Retry-After` or back off exponentially. On `insufficient_quota`, check billing. On `server_error` (500), retry up to 3 times. Consider model fallback chain: `gpt-4o` → `gpt-4o-mini` for cost/availability resilience.

---

## 5. Integration Example

```python
from openai import OpenAI
import os

# Credential setup
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Basic chat completion
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a helpful assistant for developer tooling."},
        {"role": "user", "content": "Compare REST APIs vs GraphQL for agent integration."}
    ],
    max_tokens=500
)
print(response.choices[0].message.content)

# Function calling (tool use)
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": "Look up the current price of AAPL stock"}
    ],
    tools=[
        {
            "type": "function",
            "function": {
                "name": "get_stock_price",
                "description": "Get current stock price by ticker symbol",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Stock ticker symbol"}
                    },
                    "required": ["ticker"]
                }
            }
        }
    ]
)

# Check for tool calls
message = response.choices[0].message
if message.tool_calls:
    for call in message.tool_calls:
        print(f"Function: {call.function.name}({call.function.arguments})")

# Generate embeddings
embedding = client.embeddings.create(
    model="text-embedding-3-small",
    input="Agent-native API design principles"
)
vector = embedding.data[0].embedding
print(f"Embedding dimension: {len(vector)}")  # 1536 for text-embedding-3-small

# Streaming
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Write a haiku about serverless computing."}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Latency (TTFT P50)** | ~300ms | Time to first token (GPT-4o) |
| **Latency (TTFT P95)** | ~1.2s | Varies with prompt length and model load |
| **Throughput** | ~90 tokens/sec | Output tokens (GPT-4o); mini is faster |
| **Uptime** | 99.5%+ | Check https://status.openai.com |
| **Rate Limits** | Tier-based | Tier 1: 500 RPM, 30K TPM (GPT-4o) |
| **Pricing** | GPT-4o: $2.50/$10 per 1M tokens (in/out) | 4o-mini: $0.15/$0.60. Check docs for current pricing. |

---

## 7. Agent-Native Notes

- **Idempotency:** Not applicable — each request generates unique output. Use `seed` parameter for more reproducible outputs (not guaranteed identical). Agents must cache responses when determinism matters.
- **Retry behavior:** Retry on 429 and 500+ with exponential backoff. The Python SDK includes automatic retries (configurable). On `insufficient_quota`, do not retry — escalate for billing resolution.
- **Error codes → agent decisions:** `rate_limit_exceeded` → queue and retry after delay. `model_not_found` → check model name, may need access request. `context_length_exceeded` → truncate input or switch to model with larger context. `server_error` → retry.
- **Schema stability:** The Chat Completions API is stable. OpenAI maintains backward compatibility for core endpoints. Model names change with new releases — pin specific model versions in production (e.g., `gpt-4o-2024-08-06` instead of `gpt-4o`).
- **Cost-per-operation:** Token-based pricing. Agents should estimate tokens before calls (`tiktoken` library for accurate counting). Batch API offers 50% discount for async workloads. Use `gpt-4o-mini` for simple tasks to reduce cost.
- **Structured output:** Use `response_format: { type: "json_schema", json_schema: {...} }` for guaranteed JSON output conforming to a schema. Essential for agents that need to parse responses programmatically.
- **Function calling vs. MCP:** OpenAI's function calling is the most widely adopted tool-use pattern. Agents can define tools as functions and OpenAI returns structured calls. This parallels MCP's tool concept.
- **Vision:** GPT-4o supports image input. Send images as base64 or URLs in the message content. Useful for agents that process screenshots, documents, or visual data.

---

## 8. Rhumb Context: Why OpenAI Scores 7.9 (L3)

OpenAI's **7.9 score** reflects the largest LLM ecosystem with strong agent capabilities offset by access friction and a narrower tool-native story than Anthropic:

1. **Execution Autonomy (8.0)** — Function calling is mature and widely adopted — the most battle-tested tool-use implementation in production agent systems. Structured output (`response_format: json_schema`) guarantees parseable responses, eliminating brittle regex extraction. The `seed` parameter and `temperature: 0` give agents near-deterministic behavior for reproducible workflows. Error types are distinct and actionable: `rate_limit_exceeded` queues, `context_length_exceeded` triggers truncation, `insufficient_quota` escalates.

2. **Access Readiness (7.5)** — No free tier is the primary friction point — agents can't validate end-to-end without adding a payment method first. Once billing is set, setup is fast. Project-scoped API keys reduce blast radius. The Python SDK's built-in retry logic (configurable max retries) means agents don't need custom retry code for most failure modes.

3. **Agent Autonomy (8.0)** — Embeddings (`text-embedding-3-small`) enable semantic search and memory retrieval — critical for agents that need long-term knowledge access. The Batch API (50% discount) makes high-volume inference economically viable. The GPT-4o model family covers vision, audio, and text in one API surface. The ecosystem advantage is real: more community tools, more tutorials, more pre-built integrations than any competitor.

**Bottom line:** OpenAI is the default inference provider for agents that need battle-tested function calling, embeddings, or multi-modal capabilities. The ecosystem size makes third-party integrations and community support significantly easier to find than with any other provider. The no-free-tier constraint means Rhumb scores it below Anthropic, but for production agent systems, it's a tier-1 choice.

**Competitor context:** Anthropic (8.1) scores slightly higher due to MCP-native tool integration, extended thinking for complex reasoning, and a free-tier-equivalent path through the Console. For agents using Claude, Anthropic wins; for agents in the OpenAI ecosystem with function-calling-heavy workflows, OpenAI is equally viable.
