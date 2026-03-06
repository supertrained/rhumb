# Using the Rhumb MCP Server with Claude Desktop

This guide walks you through installing and configuring the Rhumb MCP server for use with [Claude Desktop](https://claude.ai/download).

## Prerequisites

- **Node.js** ≥ 18 (LTS recommended)
- **Claude Desktop** installed ([download](https://claude.ai/download))
- **Git** (to clone the repo)

## Installation

```bash
# 1. Clone the Rhumb repository
git clone https://github.com/supertrained/rhumb.git
cd rhumb

# 2. Install dependencies
npm install

# 3. Build the MCP server package
cd packages/mcp
npm run build
```

Verify the build succeeded:

```bash
ls dist/index.js  # should exist after build
```

## Configuration

Claude Desktop discovers MCP servers through its configuration file.

### Locate the config file

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

### Add the Rhumb server

Open `claude_desktop_config.json` and add an entry under `mcpServers`:

```json
{
  "mcpServers": {
    "rhumb": {
      "command": "node",
      "args": ["/absolute/path/to/rhumb/packages/mcp/dist/index.js"],
      "env": {
        "RHUMB_API_BASE_URL": "https://api.rhumb.dev/v1"
      }
    }
  }
}
```

> **Note:** Replace `/absolute/path/to/rhumb` with the actual path to your cloned repository.

#### Using `tsx` for development

During development you can skip the build step and run TypeScript directly:

```json
{
  "mcpServers": {
    "rhumb": {
      "command": "npx",
      "args": ["tsx", "/absolute/path/to/rhumb/packages/mcp/src/index.ts"],
      "env": {
        "RHUMB_API_BASE_URL": "http://localhost:8000/v1"
      }
    }
  }
}
```

### Restart Claude Desktop

After saving the config, restart Claude Desktop. You should see "rhumb" listed in the MCP tools panel (click the 🔌 icon in the input area).

## Example Usage

Once configured, you can invoke Rhumb tools directly from Claude:

### Find tools

> "Find the best email delivery APIs for my agent"

Claude will call `find_tools` with your query and return AN Score–ranked results:

```
Tools found:
1. Resend (slug: resend) — AN Score: 91
   Modern email API with excellent DX
2. Postmark (slug: postmark) — AN Score: 85
   Fast transactional email delivery
3. SendGrid (slug: sendgrid) — AN Score: 82
   Reliable email API with strong SDK support
```

### Get detailed score

> "What's the AN Score breakdown for sendgrid?"

Claude calls `get_score` and returns the full breakdown:

```
SendGrid (sendgrid)
  Aggregate: 82 | Execution: 85 | Access: 79
  Confidence: 0.95 | Tier: ready
  Freshness: 2026-03-01
```

### Find alternatives

> "What are better alternatives to sendgrid?"

Claude calls `get_alternatives` to find higher-scored peers:

```
Alternatives to sendgrid (score: 72):
1. Resend (91) — Higher AN Score alternative
2. Postmark (85) — Higher AN Score alternative
```

### Get failure modes

> "What are the known failure modes for sendgrid?"

Claude calls `get_failure_modes` to extract failure patterns:

```
Failure modes for sendgrid:
1. Rate limit exceeded on burst sends
   Impact: Emails delayed or dropped | Frequency: moderate
   Workaround: Implement exponential backoff with jitter
```

## Debugging

### Check server logs

Claude Desktop logs MCP server output. Find logs at:

| Platform | Path |
|----------|------|
| macOS | `~/Library/Logs/Claude/mcp*.log` |
| Windows | `%APPDATA%\Claude\logs\mcp*.log` |

### Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Server not listed in Claude | Config syntax error | Validate JSON in `claude_desktop_config.json` |
| "Connection refused" errors | API not reachable | Check `RHUMB_API_BASE_URL` and network |
| Tools return empty results | API key / auth issue | Verify API credentials if required |
| Server crashes on start | Missing dependencies | Run `npm install` in `packages/mcp` |
| TypeScript errors with `tsx` | Wrong Node.js version | Use Node.js ≥ 18 |

### Manual testing

You can test the server independently via stdio:

```bash
# Start the server
cd packages/mcp
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | npx tsx src/index.ts
```

This should output a JSON response listing all 4 registered tools.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RHUMB_API_BASE_URL` | `http://localhost:8000/v1` | Rhumb API base URL |

## Transport

The Rhumb MCP server uses **stdio transport** — Claude Desktop communicates with it via stdin/stdout. This is the standard MCP transport for local servers and requires no network port configuration.

For remote/HTTP transport options, see [MCP-INTEGRATION.md](./MCP-INTEGRATION.md#deployment).
