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
    // Perf/stress tests legitimately run heavy sequential work (multi-thousand-
    // anchor scans, PBKDF2, floods); the default 5 s per-test timeout flakes them
    // under concurrent-suite CPU contention (a §11.4.50 FAIL-bluff — a test killed
    // by the runner for a non-product reason). 30 s is generous enough that no
    // legit test is killed under load, yet still surfaces a genuine hang. The REAL
    // perf budgets are each test's own internal assertion (p99/ratio < threshold),
    // which this does not touch. The two heaviest perf tests also set an explicit
    // larger per-test timeout.
    testTimeout: 30_000,
    include: [
      "tests/unit/**/*.test.ts",
      "tests/perf/**/*.test.ts",
      "tests/stress/**/*.test.ts",
      "tests/chaos/**/*.test.ts",
      "tests/integration/**/*.test.ts",
      "tests/security/**/*.test.ts",
      "tests/a11y/**/*.test.ts",
      "tests/i18n/**/*.test.ts",
      "src/**/*.test.ts",
    ],
    // NOTE: tests/live/** is intentionally NOT in the default suite — it needs a
    // real backend on :7187 and a network probe. Run it explicitly via the
    // `test:live` script (it SKIPs cleanly when the backend is unreachable).
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
