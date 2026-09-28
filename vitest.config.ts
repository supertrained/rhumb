import { defineConfig } from "vitest/config";

export default defineConfig({
  esbuild: {
    // Contract tests are plain file reads. Do not load packages/astro-web/tsconfig.json,
    // which extends astro and is only resolvable after `npm ci` inside that package.
    tsconfigRaw: "{}",
  },
  test: {
    environment: "node",
    include: [
      "packages/astro-web/tests/public-authority.contract.test.ts",
      "packages/astro-web/tests/astro-authority.contract.test.mjs",
      "packages/astro-web/tests/llms.contract.test.ts",
    ],
  },
});
