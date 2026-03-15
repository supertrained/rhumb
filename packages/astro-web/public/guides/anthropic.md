# Anthropic — Agent-Native Service Guide

> **AN Score:** 8.1 · **Tier:** L4 · **Category:** LLM Provider

---

## 1. Synopsis

Anthropic builds the Claude family of large language models — the backbone for many agent systems. The Messages API provides access to Claude models for text generation, analysis, code writing, and tool use. For agents, Anthropic is often the "brain" — the inference engine that powers reasoning, planning, and decision-making. The API supports streaming, tool use (function calling), vision, and extended thinking. No free tier for API access; pay-per-token pricing. Console available at https://console.anthropic.com.

---

## 2. Connection Methods

### REST API
- **Base URL:** `https://api.anthropic.com`
- **Auth:** API key via `x-api-key` header
- **Content-Type:** `application/json`
- **API Version:** Required header `anthropic-version: 2023-06-01` (check docs for latest)
- **Rate Limits:** Tier-based; new accounts start at 50 req/min, 40K input tokens/min. Increases with usage.
- **Docs:** https://docs.anthropic.com/en/docs

### SDKs
- **Python:** `pip install anthropic` — official, well-maintained
- **TypeScript/Node:** `npm install @anthropic-ai/sdk` — official
- **Go, Rust:** Community SDKs available; check Anthropic docs for recommendations

### MCP
- Anthropic created the MCP standard. Claude supports MCP tool servers natively.
- Claude Desktop and API both support MCP server connections
- **Spec:** https://modelcontextprotocol.io

### Webhooks
- **Message Batches:** Async batch processing with polling for results
- No real-time webhook delivery for individual completions — use streaming instead

### Auth Flows
- **API Keys:** Generated in Console → API Keys
- **Workspace-scoped:** Keys can be scoped to specific workspaces
- **No OAuth** — direct API key authentication only

---

## 3. Key Primitives

| Primitive | Endpoint | Description |
|-----------|----------|-------------|
| `messages.create` | `POST /v1/messages` | Generate a response from Claude (core inference) |
| `messages.create` (stream) | `POST /v1/messages` with `stream: true` | Streaming token-by-token response |
| `messages.count_tokens` | `POST /v1/messages/count_tokens` | Count tokens for a message payload |
| `messages.batches.create` | `POST /v1/messages/batches` | Submit a batch of messages for async processing (50% discount) |
| `messages.batches.results` | `GET /v1/messages/batches/{id}/results` | Retrieve batch results |
| `models.list` | `GET /v1/models` | List available models |

---

## 4. Setup Guide

### For Humans
1. Create account at https://console.anthropic.com
2. Add a payment method (Settings → Billing)
3. Navigate to **API Keys** → Create Key
4. Copy the key (starts with `sk-ant-...`)
5. Set usage limits in Settings → Limits to control spend
6. Choose a default model: `claude-sonnet-4-20250514` for balanced cost/quality, `claude-opus-4-20250514` for maximum capability

### For Agents
1. **Credential retrieval:** Pull API key from secure store (env var `ANTHROPIC_API_KEY`)
2. **Connection validation:**
   ```bash
   curl -s https://api.anthropic.com/v1/messages \
     -H "x-api-key: $ANTHROPIC_API_KEY" \
     -H "anthropic-version: 2023-06-01" \
     -H "content-type: application/json" \
     -d '{"model":"claude-sonnet-4-20250514","max_tokens":50,"messages":[{"role":"user","content":"Say hello"}]}' \
     | jq .content[0].text
   ```
3. **Error handling:** Check `error.type` — `authentication_error`, `rate_limit_error`, `overloaded_error`, `invalid_request_error`
4. **Fallback:** On `overloaded_error` (529), retry with exponential backoff. Consider routing to a smaller model if latency-sensitive. On rate limit, queue requests.

---

## 5. Integration Example

```python
import anthropic
import os

# Credential setup
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Basic message
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Summarize the key benefits of agent-native APIs in 3 bullet points."}
    ]
)
print(response.content[0].text)

# Tool use (function calling)
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    tools=[
        {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"]
            }
        }
    ],
    messages=[
        {"role": "user", "content": "What's the weather in San Francisco?"}
    ]
)

# Check if Claude wants to use a tool
for block in response.content:
    if block.type == "tool_use":
        print(f"Tool call: {block.name}({block.input})")
    elif block.type == "text":
        print(f"Text: {block.text}")

# Streaming
with client.messages.stream(
    model="claude-sonnet-4-20250514",
    max_tokens=512,
    messages=[{"role": "user", "content": "Write a haiku about APIs."}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Latency (TTFT P50)** | ~500ms | Time to first token (Sonnet) |
| **Latency (TTFT P95)** | ~1.5s | Varies by model and prompt length |
| **Throughput** | ~80 tokens/sec | Output tokens (Sonnet); Haiku faster, Opus slower |
| **Uptime** | 99.5%+ | Check https://status.anthropic.com |
| **Rate Limits** | Tier-based | Tier 1: 50 req/min, 40K input tokens/min |
| **Pricing** | Sonnet: $3/$15 per 1M tokens (in/out) | Opus: $15/$75. Haiku: $0.80/$4. Check docs for current. |

---

## 7. Agent-Native Notes

- **Idempotency:** Not applicable — each request generates a new response. Agents must cache responses if deterministic behavior is needed (use `temperature: 0` for more consistency).
- **Retry behavior:** Retry on 429 (rate limit) and 529 (overloaded) with exponential backoff. The Python SDK has built-in retry logic. Never retry on 400 (bad request) — fix the input.
- **Error codes → agent decisions:** `overloaded_error` → back off or route to different model. `rate_limit_error` → queue. `authentication_error` → key invalid, escalate. `invalid_request_error` → check token limits, model name.
- **Schema stability:** The Messages API is stable. Anthropic versions the API and maintains backward compatibility. MTBBC is strong for the core messages endpoint. Model names change with new releases.
- **Cost-per-operation:** Highly variable — depends on token count. Agents should estimate token usage before calls. Use `count_tokens` endpoint for precise budgeting. Batch API offers 50% discount for non-time-sensitive work.
- **Tool use:** Claude supports structured tool use (function calling). Define tools with JSON Schema. Claude will return `tool_use` blocks when it wants to invoke a tool. This is the foundation for agent-tool interaction.
- **Extended thinking:** For complex reasoning, enable `thinking` parameter. Increases latency and cost but dramatically improves accuracy for multi-step problems.
- **Context window:** Up to 200K tokens input. Agents should manage context carefully — trim conversation history, summarize long threads, and use the `system` message for stable instructions.

---

## 8. Rhumb Context: Why Anthropic Scores 8.1 (L4)

Anthropic's **8.1 score** reflects its position as the inference engine purpose-built for agent architectures:

1. **Execution Autonomy (8.0)** — Tool use (function calling) is a first-class primitive, not a bolt-on. Claude returns structured `tool_use` blocks that agents parse deterministically. Extended thinking mode unlocks multi-step reasoning for complex agent tasks. Error types are distinct and actionable — `overloaded_error` triggers backoff, `rate_limit_error` triggers queuing, `authentication_error` escalates.

2. **Access Readiness (7.8)** — No free tier introduces friction for new agent setups (requires billing before first call). That said, Console setup is fast, API keys are instant, and the Python/TypeScript SDKs include built-in retry logic. The Batch API (50% discount) is a significant advantage for cost-conscious agents running high-volume inference.

3. **Agent Autonomy (8.5)** — Anthropic created MCP. Claude supports MCP tool servers natively — both in Claude Desktop and the API. This is the deepest tool ecosystem integration of any LLM provider. The 200K context window enables agents to pass full codebases, long documents, and conversation histories without truncation. Streaming makes real-time agent pipelines feasible.

**Bottom line:** For agent systems where Claude is the reasoning core, Anthropic's API is the natural choice. MCP-native support means agent tool ecosystems built on Anthropic's standard integrate with minimal friction. Prioritize for complex reasoning tasks; use the Batch API to manage inference costs at scale.

**Competitor context:** OpenAI (7.9) scores slightly lower — comparable capabilities but less MCP-native integration and no equivalent to extended thinking for deep reasoning chains. For agents already embedded in the Claude ecosystem, the MCP advantage compounds over time.
