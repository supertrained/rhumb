# Vercel production deploy (rhumb.dev)

Root `vercel.json` already builds `packages/astro-web`. GitHub still reported **SUCCESS** with **Canceled by Ignored Build Step** on `47ae176`, so production never rebuilt. Live `https://rhumb.dev/llms.txt` stayed dated **Fri, 05 Jun 2026** with stale `1038 / 415 / 16` and `GET /agent-capabilities.json` 404.

## Repo fix

`vercel.json` now sets `"ignoreCommand": "exit 1"`. Exit `1` means **always build**. Exit `0` is what skips the deploy.

If the project dashboard still has a custom Ignored Build Step, that override can keep skipping even after this lands. Set it to Automatic, or to `exit 1`.

## After merge — force PRODUCTION (Tom)

Dashboard:

1. [Vercel](https://vercel.com) → team **team-supertraineds-projects** → project **rhumb**.
2. **Settings → Git → Ignored Build Step** → Automatic, or command `exit 1`. Save.
3. **Deployments** → ⋯ on the latest Production candidate (this PR’s merge commit, or `47ae176` if you are only catching up Phase A) → **Redeploy**.
4. Uncheck **Use existing Build Cache**. Confirm the target is **Production** (`rhumb.dev`), not Preview.
5. Wait until the deployment is **Ready**, not Canceled.

CLI (from the repo root, linked project):

```bash
npx vercel pull --yes --environment=production
npx vercel build --prod
npx vercel deploy --prebuilt --prod
```

Or, after the ignore step is cleared:

```bash
npx vercel --prod --force
```

Do not treat a GitHub Vercel status of SUCCESS + “Canceled by Ignored Build Step” as a production ship.

## Check

```bash
curl -sSI https://rhumb.dev/llms.txt | rg -i 'date|last-modified'
curl -sS https://rhumb.dev/llms.txt | rg '999|1038|28 callable|16 callable'
curl -sSI https://rhumb.dev/agent-capabilities.json
```

Expect a Date after this deploy, `999` / `28 callable`, and `200` or a redirect to `/.well-known/agent-capabilities.json`.
