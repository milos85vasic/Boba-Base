import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E test configuration for BobaLink extension.
 * Tests the popup, content script, and options page in a real browser.
 */
export default defineConfig({
  /**
   * Test directory containing all E2E spec files.
   */
  testDir: "./tests/e2e",

  /**
   * Run tests sequentially since they share browser state.
   */
  fullyParallel: false,

  /**
   * Fail build on flaky tests in CI.
   */
  forbidOnly: !!process.env.CI,

  /**
   * Retry failed tests once in CI, no retries locally.
   */
  retries: process.env.CI ? 2 : 0,

  /**
   * Number of parallel workers.
   * Use 1 for extension tests to avoid conflicts.
   */
  workers: 1,

  /**
   * Reporter configuration.
   */
  reporter: [
    ["html", { open: "never" }],
    ["list"],
    ...(process.env.CI ? [["github"] as const] : []),
  ],

  /**
   * Shared settings for all projects.
   */
  use: {
    /**
     * Base URL for extension pages.
     * Updated dynamically in test fixtures.
     */
    baseURL: "chrome-extension://test-id/",

    /**
     * Collect trace on retry for debugging.
     */
    trace: "on-first-retry",

    /**
     * Screenshot on failure.
     */
    screenshot: "only-on-failure",

    /**
     * Video recording on retry.
     */
    video: "on-first-retry",

    /**
     * Default viewport size.
     */
    viewport: { width: 1280, height: 720 },

    /**
     * Launch options for Chromium.
     */
    launchOptions: {
      /**
       * Load extension from build directory.
       */
      args: [
        `--disable-extensions-except=${process.env.EXTENSION_PATH || "./dist"}`,
        `--load-extension=${process.env.EXTENSION_PATH || "./dist"}`,
      ],
    },
  },

  /**
   * Project configurations for different browsers.
   */
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        channel: "chromium",
      },
    },
    {
      name: "firefox",
      use: {
        ...devices["Desktop Firefox"],
      },
    },
  ],

  /**
   * Run local dev server before starting tests.
   */
  webServer: {
    command: "npm run build",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },

  /**
   * Global setup and teardown.
   */
  globalSetup: "./tests/e2e/global-setup.ts",
  globalTeardown: "./tests/e2e/global-teardown.ts",

  /**
   * Test timeout in milliseconds.
   */
  timeout: 30000,

  /**
     Expect timeout for assertions.
   */
  expect: {
    timeout: 5000,
  },
});
