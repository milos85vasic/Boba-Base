// Dedicated Playwright config for the LIVE-STACK runtime browser proofs
// (qbittorrent-webui-vanilla.spec.ts + angular-dashboard-console.spec.ts).
//
// Kept separate from playwright.config.ts because:
//   * that config's baseURL is the Angular dev server on :4200, while these
//     specs drive the live stack on :7186 / :7187 by absolute URL;
//   * these specs must run against a SYSTEM Chromium. Playwright's bundled
//     browser download refuses this host outright:
//       "ERROR: Playwright does not support chromium on ubuntu26.04-x64"
//     so `executablePath` points at the host's own Chromium instead.
//
// Host safety (§12.6 / §12.12): headless, ONE worker, no retries, no video.
// Invoke under `nice -n 19`.

import { defineConfig, devices } from '@playwright/test';
import { existsSync } from 'node:fs';

/** First system Chromium-family browser present on this host. */
function resolveBrowser(): string {
  const explicit = process.env.BOBA_CHROMIUM_PATH;
  if (explicit) {
    if (!existsSync(explicit)) {
      throw new Error(
        `BOBA_CHROMIUM_PATH="${explicit}" does not exist. ` +
          `Point it at a Chromium/Chrome binary, or unset it to auto-detect.`,
      );
    }
    return explicit;
  }

  const candidates = [
    '/snap/bin/chromium',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/opt/google/chrome/chrome',
  ];
  const found = candidates.find((p) => existsSync(p));
  if (!found) {
    throw new Error(
      'No system Chromium found. Playwright cannot download its own on this ' +
        'host (ubuntu26.04-x64 is unsupported by the bundled build). Install ' +
        'one — e.g. `sudo snap install chromium` — or set BOBA_CHROMIUM_PATH. ' +
        `Looked in: ${candidates.join(', ')}`,
    );
  }
  return found;
}

export default defineConfig({
  testDir: './e2e',
  testMatch: [
    '**/qbittorrent-webui-vanilla.spec.ts',
    '**/angular-dashboard-console.spec.ts',
    '**/runtime-guards-mutation.spec.ts',
  ],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  timeout: 60_000,
  outputDir: 'test-results-runtime/',
  use: {
    ...devices['Desktop Chrome'],
    headless: true,
    actionTimeout: 15_000,
    video: 'off',
    trace: 'off',
    launchOptions: {
      executablePath: resolveBrowser(),
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    },
  },
});
