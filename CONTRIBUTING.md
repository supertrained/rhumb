# Contributing to Rhumb

We welcome contributions! Rhumb is built to serve agents and the developers who build with them.

## Ways to Contribute

### 🔍 Score Corrections
If you work at or with a service we've scored and the data looks wrong, please:
1. Open an issue with the service slug and the dimension you believe is incorrect
2. Include evidence (API docs, changelog links, error response samples)
3. We'll review and update within 48 hours

### 📝 New Service Evaluations
Want to see a service scored? Open an issue with:
- Service name and primary API docs URL
- Which category it belongs to (payments, auth, ai, etc.)
- Why it's relevant for AI agent workflows

### 🐛 Bug Reports
For bugs in the web UI, API, or MCP server:
1. Open a GitHub issue
2. Include: what you expected, what happened, steps to reproduce
3. For API/MCP issues, include the request and response

### 💻 Code Contributions
1. Fork the repo
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run tests: `cd packages/api && python -m pytest` / `cd packages/web && npm test`
5. Open a PR with a clear description

## Dispute a Score

Every service page on [rhumb.dev](https://rhumb.dev) has a "Dispute this score" option. If you believe a score is inaccurate:

1. Click "Dispute this score" on the service page, or
2. Email [team@supertrained.ai](mailto:team@supertrained.ai) with the service slug and your evidence
3. We review all disputes within 48 hours
4. The AN Score methodology is published and auditable — we'll explain the scoring basis

## AN Score Methodology

The scoring methodology is open and documented in `docs/AN-SCORE-V2-SPEC.md`. We believe transparency builds trust. If you have suggestions for improving the methodology itself, open a discussion.

## Code of Conduct

Be respectful, be constructive, be honest. We're building infrastructure that agents depend on — accuracy and integrity matter more than speed.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
