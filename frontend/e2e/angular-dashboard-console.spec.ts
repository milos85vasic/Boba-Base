// Runtime proof that the Angular dashboard served on :7187 actually
// BOOTSTRAPS in a browser — that <app-root> hydrates into real rendered
// content rather than staying the empty shell the server sends.
//
// The served HTML is literally `<body><app-root></app-root>...`. An HTTP-200
// on that document proves nothing about the app: a broken bundle, a failed
// module preload, or a runtime exception in main.ts all still serve 200 and
// leave the operator staring at a blank page. Only a real browser that
// executes main-*.js can tell the difference (§11.4.108 layer 3/4).

import { test, expect, type Page, type ConsoleMessage } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const DASHBOARD = process.env.BOBA_DASHBOARD_URL ?? 'http://localhost:7187';

const EVIDENCE_DIR =
  process.env.BOBA_EVIDENCE_DIR ??
  join(
    process.cwd(),
    '..',
    'docs/qa/2026-09-01-qbittorrent-login-repair/runs/browser',
  );

interface Diagnostics {
  consoleErrors: string[];
  pageErrors: string[];
  failedRequests: string[];
  allConsole: string[];
}

function attachDiagnostics(page: Page): Diagnostics {
  const d: Diagnostics = {
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    allConsole: [],
  };

  page.on('console', (msg: ConsoleMessage) => {
    const loc = msg.location();
    const where = loc.url ? ` @ ${loc.url}:${loc.lineNumber}:${loc.columnNumber}` : '';
    const line = `[${msg.type()}] ${msg.text()}${where}`;
    d.allConsole.push(line);
    if (msg.type() === 'error') d.consoleErrors.push(line);
  });

  page.on('pageerror', (err) => {
    d.pageErrors.push(`${err.name}: ${err.message}\n${err.stack ?? '<no stack>'}`);
  });

  page.on('requestfailed', (req) => {
    d.failedRequests.push(
      `${req.method()} ${req.url()} -> ${req.failure()?.errorText ?? 'unknown'}`,
    );
  });

  return d;
}

test('Angular dashboard (:7187) hydrates <app-root> with zero console errors', async ({
  page,
}) => {
  const d = attachDiagnostics(page);

  await page.goto(DASHBOARD, { waitUntil: 'domcontentloaded' });

  const appRoot = page.locator('app-root');
  await expect(appRoot).toHaveCount(1);

  // HYDRATION: the shell must gain real child elements. An unhydrated
  // <app-root></app-root> has zero children and empty text — exactly what a
  // "served a stub" regression looks like, and exactly what an HTTP-only
  // check cannot distinguish from a working app.
  await page.waitForFunction(
    () => {
      const el = document.querySelector('app-root');
      return !!el && el.children.length > 0;
    },
    undefined,
    { timeout: 20_000 },
  );

  const hydration = await page.evaluate(() => {
    const el = document.querySelector('app-root');
    return {
      childElementCount: el?.children.length ?? 0,
      renderedTextLength: (el?.textContent ?? '').trim().length,
      innerHTMLLength: (el?.innerHTML ?? '').length,
      firstChildTags: Array.from(el?.children ?? [])
        .slice(0, 8)
        .map((c) => c.tagName.toLowerCase()),
    };
  });

  expect(
    hydration.childElementCount,
    'app-root rendered no child elements — Angular did not bootstrap',
  ).toBeGreaterThan(0);
  expect(
    hydration.renderedTextLength,
    'app-root rendered no visible text — the app is an empty shell',
  ).toBeGreaterThan(0);

  // Something in the hydrated tree must actually be on screen for a user.
  await expect(appRoot).toBeVisible();

  // CONTROL NEEDLE (§11.4.201(6)(7)(b)) — a clean page and a blind listener
  // both report zero. Prove the listener is actually seeing before trusting
  // its silence in the assertions below.
  const NEEDLE = 'BOBA_CONTROL_NEEDLE_a41e9d';
  await page.evaluate((n) => console.error(n), NEEDLE);
  await expect
    .poll(() => d.consoleErrors.filter((e) => e.includes(NEEDLE)).length, {
      timeout: 5_000,
      message:
        'Control needle NOT observed — the console listener is blind, so a ' +
        '"zero console errors" result would be a false null, not evidence.',
    })
    .toBe(1);

  const realConsoleErrors = d.consoleErrors.filter((e) => !e.includes(NEEDLE));

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  const shot = join(EVIDENCE_DIR, 'angular-dashboard-hydrated.png');
  await page.screenshot({ path: shot, fullPage: true });

  writeFileSync(
    join(EVIDENCE_DIR, 'angular-dashboard-console.json'),
    JSON.stringify(
      {
        capturedAt: new Date().toISOString(),
        target: DASHBOARD,
        hydration,
        consoleErrorCount: d.consoleErrors.length,
        pageErrorCount: d.pageErrors.length,
        consoleErrors: d.consoleErrors,
        controlNeedleObserved: true,
        realConsoleErrors,
        pageErrors: d.pageErrors,
        failedRequests: d.failedRequests,
        allConsoleMessages: d.allConsole,
        screenshot: shot,
      },
      null,
      2,
    ) + '\n',
  );

  expect(
    d.pageErrors,
    `Uncaught page exceptions on the Angular dashboard:\n${d.pageErrors.join('\n---\n')}`,
  ).toEqual([]);
  expect(
    realConsoleErrors,
    `Console errors on the Angular dashboard:\n${realConsoleErrors.join('\n')}`,
  ).toEqual([]);
});
