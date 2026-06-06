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
 * Coverage thresholds are set just BELOW the current measured coverage
 * so the gate is green today but blocks any regression. Measured on
 * 2026-06-06 with `@vitest/coverage-v8`: statements 87.17 %, branches
 * 71.74 %, functions 87.15 %, lines 89.76 % (342 specs). Thresholds sit
 * ~2 points under each measured value to absorb minor refactors while
 * still failing the suite if real coverage drops. Raise these as
 * coverage climbs toward 100 % (see docs/COVERAGE_BASELINE.md).
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
        lines: 87,
        branches: 69,
        functions: 85,
        statements: 85,
      },
    },
  },
});
