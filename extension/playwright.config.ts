import { defineConfig } from "@playwright/test";

/**
 * Playwright E2E config for BobaLink (Phase 8).
 *
 * Drives a real Chromium instance with the BUILT MV3 extension
 * (`.output/chrome-mv3`) loaded, then asserts user-observable facts about
 * the actual artifact (service worker registers, popup + options pages
 * render their real UI). MV3 extension loading requires a full (non
 * `headless_shell`) Chromium with a persistent context, so there is a
 * single chromium project and no global headless flag — the spec itself
 * launches the persistent context with the extension args.
 */
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  projects: [{ name: "chromium" }],
});
