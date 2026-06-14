// Playwright config skeleton — see ./README.md for activation steps.
//
// CONST-XII: every test in this directory MUST assert on user-visible
// DOM (page.locator(...).toContainText / toBeVisible / count). A green
// run with assertions only on `page.url()` or response.status() would
// be a bluff — the test must inspect what the operator's eyes see.
import { defineConfig, devices } from '@playwright/test';

const APP_URL = process.env.BOBA_FRONTEND_URL ?? 'http://localhost:4200';
const BACKEND_URL = process.env.BOBA_BACKEND ?? 'http://localhost:7189';

export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.spec\.ts$/,
  fullyParallel: false, // backend state is shared (autoconfig runs, etc.)
  workers: 1,
  retries: 0,
  reporter: [['list']],
  timeout: 30_000,
  outputDir: 'test-results/',
  use: {
    baseURL: APP_URL,
    video: 'on',
    actionTimeout: 15_000,
    // NOTE: do NOT inject extraHTTPHeaders here — they pollute every
    // browser XHR and trigger CORS preflights for headers the backend
    // doesn't whitelist. Specs read backend URL from process.env directly.
    // (Caught by the very first live Playwright run via CONST-XII —
    // X-Boba-Backend triggered CORS preflight rejection.)
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
