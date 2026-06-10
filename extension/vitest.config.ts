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
    include: [
      "tests/unit/**/*.test.ts",
      "tests/perf/**/*.test.ts",
      "tests/stress/**/*.test.ts",
      "src/**/*.test.ts",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary", "html", "lcov"],
      reportsDirectory: "coverage",
      // All source logic is measured (parsers, scanners, shared, types) per §11.4.27;
      // .d.ts and entrypoint index.ts files are excluded.
      include: ["src/**/*.ts"],
      exclude: ["src/**/*.d.ts", "src/**/index.ts"],
    },
  },
});
