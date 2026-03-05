# rhumb-web

Next.js 15 App Router app for Rhumb Discover surfaces.

## Local run

```bash
npm ci
npm run dev
```

Optional checks:

```bash
npm run test
npm run type-check
```

## Route map

- `/` — homepage hero + search entry + leaderboard preview
- `/leaderboard/[category]` — category leaderboard with aggregate/execution/access badges
- `/service/[slug]` — service profile, contextual explanation, failures, alternatives
- `/search` — service search entrypoint
- `/llms.txt` — machine-discovery baseline export
