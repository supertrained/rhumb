# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Rhumb, please report it responsibly.

**Email:** [security@supertrained.ai](mailto:security@supertrained.ai)

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix

We aim to acknowledge reports within 48 hours and provide a resolution timeline within 5 business days.

**Do not** open a public GitHub issue for security vulnerabilities.

## Security Architecture

### Credential handling
- Provider credentials are loaded at runtime from encrypted storage (1Password)
- Credentials are never stored in source control
- TTL-based credential refresh (60-minute cycle)
- Per-provider auth injection with scoped access patterns

### Agent Vault mode
- Agent-owned credentials encrypted at rest
- Rhumb injects at call time, never stores in plaintext
- Credentials scoped to the agent that owns them

### API authentication
- API keys required for all write/execute operations
- Read/discovery endpoints are public (no PII exposed)
- Rate limiting per IP and per API key
- x402 payment verification for anonymous execution

### Infrastructure
- API hosted on Railway with TLS
- Database on Supabase with row-level security
- Circuit breakers prevent cascade failures
- Managed credential daily execution caps

### Payment security
- x402 USDC payment verification with replay prevention
- Transaction hash deduplication (24-hour TTL)
- Stripe checkout for prepaid credit purchases

## Scope

This policy applies to:
- The Rhumb API (`api.rhumb.dev`)
- The Rhumb website (`rhumb.dev`)
- The MCP server (`rhumb-mcp` npm package)
- This GitHub repository

## Acknowledgments

We appreciate responsible disclosure and will credit reporters (with permission) for confirmed vulnerabilities.
