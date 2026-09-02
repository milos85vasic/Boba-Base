// PAIRED §1.1 MUTATION / golden-bad fixtures (§11.4.107(10), §11.4.115(F)).
//
// A guard never observed FAILING on a genuinely broken artifact is
// unvalidated instrumentation and proves nothing when it passes. These tests
// deliberately BREAK the page in the browser and assert the sibling specs'
// load-bearing conditions would be VIOLATED — i.e. they prove those specs
// can actually fail.
//
// The corruption reproduced here is the real historical defect: a themed
// overlay rewrote the literal string "qBittorrent" to "Боба" in script
// content, destroying the `window.qBittorrent` namespace every WebUI script
// hangs off — while the HTML bytes still looked perfectly fine.
//
// These run against the live stack but mutate ONLY the in-browser response
// (page.route), never the server, the container, or any file on disk.

import { test, expect } from '@playwright/test';

const WEBUI = process.env.BOBA_WEBUI_URL ?? 'http://localhost:7186';
const DASHBOARD = process.env.BOBA_DASHBOARD_URL ?? 'http://localhost:7187';
const USERNAME = process.env.BOBA_WEBUI_USER ?? 'admin';
const PASSWORD = process.env.BOBA_WEBUI_PASS ?? 'admin';

test('MUTATION: rebranding "qBittorrent" inside client.js breaks the namespace guard', async ({
  page,
}) => {
  // Reproduce the overlay: rewrite the namespace token in an EXTERNAL script,
  // exactly the way the removed themed overlay rewrote it in inline ones.
  await page.route('**/scripts/client.js*', async (route) => {
    const response = await route.fetch();
    const body = await response.text();
    await route.fulfill({
      response,
      body: body.replaceAll('qBittorrent', 'Боба'),
    });
  });

  await page.goto(WEBUI, { waitUntil: 'domcontentloaded' });
  await page.locator('#username').fill(USERNAME);
  await page.locator('#password').fill(PASSWORD);
  await page.locator('#loginButton').click();

  await expect(page.locator('#desktop')).toBeVisible({ timeout: 20_000 });
  await page.waitForLoadState('load');

  // The DOM still renders — which is precisely why an HTML-integrity check
  // could never catch this. The damage is only visible at runtime.
  const keys = await page.evaluate(() => {
    const q = (globalThis as Record<string, unknown>).qBittorrent as
      | Record<string, unknown>
      | undefined;
    return q ? Object.keys(q).sort() : [];
  });

  // The members client.js OWNS (assigns via `window.qBittorrent.X ??=`) MUST
  // now be absent — proving the sibling spec's REQUIRED_MEMBERS assertion
  // would fail on a corrupted build.
  //
  // MEASURED 2026-09-01 — `Statistics` is deliberately excluded: it is
  // assigned by statistics.js, NOT client.js, so it legitimately survives
  // this mutation. Listing it made this fixture claim the guard was toothless
  // when the guard was fine — the mutation must target only what client.js
  // genuinely owns.
  const clientOwned = ['Client', 'Filters', 'Search', 'TransferList'];
  const stillPresent = clientOwned.filter((m) => keys.includes(m));
  expect(
    stillPresent,
    `Mutation had no effect — the namespace guard is NOT load-bearing. ` +
      `Expected client.js members to vanish, but these survived: ${JSON.stringify(stillPresent)}. ` +
      `Namespace: ${JSON.stringify(keys)}`,
  ).toEqual([]);
});

test('MUTATION: blocking main bundle leaves the Angular <app-root> shell empty', async ({
  page,
}) => {
  // Abort the Angular entry bundle: the exact "served a stub / bundle broken"
  // regression the hydration assertion exists to catch.
  await page.route('**/main-*.js', (route) => route.abort());

  await page.goto(DASHBOARD, { waitUntil: 'domcontentloaded' });

  // Give it the same budget the real spec allows before concluding.
  await page.waitForTimeout(3_000);

  const hydration = await page.evaluate(() => {
    const el = document.querySelector('app-root');
    return {
      exists: !!el,
      childElementCount: el?.children.length ?? 0,
      renderedTextLength: (el?.textContent ?? '').trim().length,
    };
  });

  expect(hydration.exists, 'app-root element should still be in the served HTML').toBe(
    true,
  );
  // HTTP still returned 200 and <app-root> is still there — yet nothing
  // rendered. This is the state an HTTP-only check cannot distinguish from
  // a working app, and the state the hydration assertion must reject.
  expect(
    hydration.childElementCount,
    'Mutation had no effect — the hydration guard is NOT load-bearing. ' +
      'app-root still rendered children with the main bundle blocked.',
  ).toBe(0);
  expect(hydration.renderedTextLength).toBe(0);
});
