/**
 * @fileoverview LOCAL vitest config for the SECURITY suite ONLY.
 *
 * The repo-root `vitest.config.ts` `include` globs do not yet list
 * `tests/security/**` (that one-line addition is owned by the config stream).
 * This local config lets the security suite be run + proven green in isolation
 * without editing the shared root config:
 *
 *   npx vitest run -c tests/security/vitest.security.config.ts \
 *     --pool=threads --poolOptions.threads.maxThreads=2
 *
 * It mirrors the root config's resolve aliases + jsdom environment exactly so
 * the tests exercise the same module graph they will under the root config.
 *
 * @module tests/security/vitest.security.config
 */

import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: {
    alias: {
      "~": fileURLToPath(new URL("../../src", import.meta.url)),
      "@": fileURLToPath(new URL("../../src", import.meta.url)),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    root: fileURLToPath(new URL("../..", import.meta.url)),
    include: ["tests/security/**/*.test.ts"],
  },
});
