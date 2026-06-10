import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

/**
 * Sibling Vitest config for the LIVE integration suite (§11.4.27 / §11.4.52 —
 * "real system, not a mock").
 *
 * The repo-root `vitest.config.ts` deliberately does NOT include
 * `tests/live/**` in its `include` globs, so the always-run `npm test`
 * suite never reaches out to a real backend (live tests SKIP when the
 * backend is down, but we keep them off the default path entirely so a
 * developer's `npm test` is hermetic). This config opts the live suite IN.
 *
 * Run it explicitly from the `extension/` directory:
 *
 *   npx vitest run --config tests/live/vitest.live.config.ts
 *
 * The live test self-guards: if the Boba merge service on :7187 is
 * unreachable it SKIPs with a clear reason rather than failing — so this
 * config is safe to run with or without the backend up.
 *
 * Alternative (no sibling config): add the one line
 *   "tests/live/**\/*.live.test.ts"
 * to the `include` array in the root `vitest.config.ts`.
 */
export default defineConfig({
  resolve: {
    alias: {
      "~": fileURLToPath(new URL("../../src", import.meta.url)),
      "@": fileURLToPath(new URL("../../src", import.meta.url)),
    },
  },
  test: {
    globals: true,
    // node env — this suite talks to a real HTTP service, no DOM needed.
    environment: "node",
    include: ["tests/live/**/*.live.test.ts"],
    // Live calls (real qBittorrent add) can take a few seconds.
    testTimeout: 30_000,
    hookTimeout: 15_000,
  },
});
