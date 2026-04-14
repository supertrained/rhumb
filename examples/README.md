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
| [resolve-and-execute.py](resolve-and-execute.py) | Resolve → machine-readable recovery handoff → Estimate → Execute | No for resolve, yes for estimate/execute |
| [budget-aware-routing.py](budget-aware-routing.py) | Budget + cost-optimal routing | Yes |
| [dogfood-telemetry-loop.py](dogfood-telemetry-loop.py) | Repeatable Resolve → telemetry verification loop | Yes |
| [mcp-quickstart.md](mcp-quickstart.md) | MCP setup for Claude, Cursor, etc. | Optional |

## Run discovery (no API key needed)

```bash
python examples/discover-and-evaluate.py
```

## Run resolve walkthrough (no API key needed)

```bash
python examples/resolve-and-execute.py
```

The script will still show the ranked providers plus any machine-readable recovery handoff Rhumb already chose. Set `RHUMB_API_KEY` only when you want to continue into estimate and execute.

## Run full execution (API key required)

```bash
export RHUMB_API_KEY=your_key_here
python examples/resolve-and-execute.py
```

## Run the dogfood loop (API key required)

```bash
export RHUMB_API_KEY=your_key_here
python examples/dogfood-telemetry-loop.py
```

Get an API key at [rhumb.dev/auth/login](https://rhumb.dev/auth/login).
