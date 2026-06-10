import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

/**
 * Vitest configuration for BobaLink unit tests.
 *
 * Runner = Vitest + @vitest/coverage-v8 (matches Boba frontend/ — NOT Jest).
 * jsdom environment so DOM-dependent helpers (escapeHtml) and Web Crypto
 * (via Node's global crypto) work. Coverage collects the shared/types logic
 * libs (UI/entrypoints are later phases). Path aliases mirror tsconfig.
 */
export default defineConfig({
  resolve: {
    alias: {
      "~": fileURLToPath(new URL("./src", import.meta.url)),
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    include: ["tests/unit/**/*.test.ts", "src/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary", "html", "lcov"],
      reportsDirectory: "coverage",
      include: ["src/shared/**/*.ts", "src/types/**/*.ts"],
      exclude: ["src/**/*.d.ts", "src/**/index.ts"],
    },
  },
});
