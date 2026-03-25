# Examples

Runnable examples showing how agents and developers use Rhumb.

## Quick start

```bash
pip install httpx  # only dependency for Python examples
```

## Examples

| File | What it shows | Auth needed? |
|------|--------------|-------------|
| [discover-and-evaluate.py](discover-and-evaluate.py) | Search → Score → Failure modes | No |
| [resolve-and-execute.py](resolve-and-execute.py) | Resolve → Estimate → Execute | Yes (for execution) |
| [budget-aware-routing.py](budget-aware-routing.py) | Budget + cost-optimal routing | Yes |
| [mcp-quickstart.md](mcp-quickstart.md) | MCP setup for Claude, Cursor, etc. | Optional |

## Run discovery (no API key needed)

```bash
python examples/discover-and-evaluate.py
```

## Run execution (API key required)

```bash
export RHUMB_API_KEY=your_key_here
python examples/resolve-and-execute.py
```

Get an API key at [rhumb.dev/auth/login](https://rhumb.dev/auth/login).
