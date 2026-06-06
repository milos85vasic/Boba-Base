import { defineConfig } from 'vitest/config';
import angular from '@analogjs/vite-plugin-angular';

/**
 * Vitest configuration picked up by Angular's `@angular/build:unit-test` builder.
 *
 * The @analogjs/vite-plugin-angular plugin enables JIT compilation of
 * components that use `templateUrl` / `styleUrls` (external template and
 * style files) inside Vitest, which the stock Angular CLI test builder
 * does not resolve on its own outside of webpack/Karma.
 *
 * Coverage thresholds start at 40 % across the board so the Phase 5 spec
 * expansion locks in a baseline without blocking CI. Later phases raise
 * these per-module toward 100 % (see docs/COVERAGE_BASELINE.md).
 */
export default defineConfig({
  plugins: [angular()],
  test: {
    globals: true,
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
    setupFiles: ['src/test-setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      reportsDirectory: './coverage',
      include: ['src/app/**/*.ts'],
      exclude: [
        'src/app/**/*.spec.ts',
        'src/app/**/*.d.ts',
        'src/app/**/*.module.ts',
        'src/app/**/*.config.ts',
        'src/app/**/*.routes.ts',
        'src/app/**/index.ts',
      ],
      thresholds: {
        lines: 40,
        branches: 40,
        functions: 40,
        statements: 40,
      },
    },
  },
});
