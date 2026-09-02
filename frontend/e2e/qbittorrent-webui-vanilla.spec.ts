// Runtime proof that the VANILLA qBittorrent WebUI works through the
// download-proxy on the user-facing port 7186.
//
// WHY THIS EXISTS (§11.4.108 / CONST-XII):
// A themed-WebUI overlay used to rewrite the literal string "qBittorrent"
// to "Боба" inside inline <script> blocks while leaving external .js files
// untouched. That destroyed `window.qBittorrent` — the namespace every
// WebUI script hangs off — and killed the UI's JavaScript entirely.
// HTML-integrity assertions (namespace token present, zero rebrand) could
// NOT see that: the bytes looked fine while the page was dead in a browser.
//
// Therefore the load-bearing assertions here are RUNTIME ones:
//   * the page's JS actually executes (window.qBittorrent is a live object)
//   * ZERO console errors and ZERO uncaught exceptions
//   * a real human login path (type + click), not an API shortcut
//   * the post-login DOM is the real qBittorrent chrome, visible on screen
//
// The negative control (wrong password must NOT log in) is what stops this
// from being a test that would pass against any password.

import { test, expect, type Page, type ConsoleMessage } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const WEBUI = process.env.BOBA_WEBUI_URL ?? 'http://localhost:7186';
const USERNAME = process.env.BOBA_WEBUI_USER ?? 'admin';
const PASSWORD = process.env.BOBA_WEBUI_PASS ?? 'admin';

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

/**
 * Attach console/pageerror/requestfailed listeners BEFORE any navigation, so
 * nothing emitted during the very first script evaluation is missed.
 */
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

function writeEvidence(name: string, d: Diagnostics, extra: Record<string, unknown> = {}): void {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  writeFileSync(
    join(EVIDENCE_DIR, `${name}.json`),
    JSON.stringify(
      {
        capturedAt: new Date().toISOString(),
        target: WEBUI,
        consoleErrorCount: d.consoleErrors.length,
        pageErrorCount: d.pageErrors.length,
        consoleErrors: d.consoleErrors,
        pageErrors: d.pageErrors,
        failedRequests: d.failedRequests,
        allConsoleMessages: d.allConsole,
        ...extra,
      },
      null,
      2,
    ) + '\n',
  );
}

test.describe('vanilla qBittorrent WebUI through the download-proxy (:7186)', () => {
  // ---------------------------------------------------------------------
  // NEGATIVE CONTROL — runs first. If this ever passes with a good password,
  // or the positive test passes with a bad one, every other assertion below
  // is worthless. §11.4.201: a guard never observed refusing is unvalidated.
  // ---------------------------------------------------------------------
  test('negative control: a wrong password does NOT log in', async ({ page }) => {
    const d = attachDiagnostics(page);

    await page.goto(WEBUI, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#loginform')).toBeVisible();

    await page.locator('#username').fill(USERNAME);
    await page.locator('#password').fill('definitely-not-the-password-9f3a1c');
    await page.locator('#loginButton').click();

    // The WebUI writes the rejection into #error_msg and stays on the form.
    const errorMsg = page.locator('#error_msg');
    await expect(errorMsg).toContainText('Invalid Username or Password', {
      timeout: 10_000,
    });

    const errorText = (await errorMsg.textContent()) ?? '';

    // A rate-limit ban would ALSO leave us on the login form — that would be
    // a pass for the wrong reason (§11.4.201 false-negative). Detect it and
    // fail loudly rather than silently crediting the guard.
    expect(
      errorText.toLowerCase(),
      `Login was refused by an IP BAN, not by credential rejection. ` +
        `This test cannot prove password checking while banned. ` +
        `Server said: ${errorText}`,
    ).not.toContain('banned');

    // Still on the login form, and the main WebUI never rendered.
    await expect(page.locator('#loginform')).toBeVisible();
    await expect(page.locator('#desktop')).toHaveCount(0);

    // The authenticated JS bundle must NOT have run.
    const hasNamespace = await page.evaluate(
      () => typeof (globalThis as Record<string, unknown>).qBittorrent !== 'undefined',
    );
    expect(
      hasNamespace,
      'window.qBittorrent must not exist on the unauthenticated login page',
    ).toBe(false);

    writeEvidence('negative-control-wrong-password', d, {
      verdict: 'login refused',
      errorMessage: errorText,
    });
  });

  // ---------------------------------------------------------------------
  // POSITIVE — the real end-user path.
  // ---------------------------------------------------------------------
  test('real UI login executes the WebUI JS with zero console errors', async ({ page }) => {
    const d = attachDiagnostics(page);

    await page.goto(WEBUI, { waitUntil: 'domcontentloaded' });

    // (c) Log in through the actual DOM — type into the real fields, click
    //     the real button. No api/v2/auth/login shortcut.
    await expect(page.locator('#loginform')).toBeVisible();
    await page.locator('#username').fill(USERNAME);
    await page.locator('#password').fill(PASSWORD);
    await page.locator('#loginButton').click();

    // (d) The post-login DOM is the genuine qBittorrent UI.
    await expect(page.locator('#desktop')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('#desktopNavbar')).toBeVisible();
    await expect(page.locator('#mochaToolbar')).toBeVisible();
    await expect(page.locator('#desktopFooter')).toBeVisible();
    await expect(page.locator('#transfersTabLink')).toBeVisible();

    // Real menu text the operator's eyes would see, not just element presence.
    await expect(page.locator('#desktopNavbar')).toContainText('File');
    await expect(page.locator('#desktopNavbar')).toContainText('Edit');

    // (e) THE assertion the removed overlay used to break: the WebUI's own
    //     JS namespace must exist as a live object built by external scripts.
    //
    //     MEASURED 2026-09-01 — a `typeof qBittorrent === 'object'` wait is
    //     NOT sufficient: it resolves the instant monkeypatch.js (the first
    //     deferred script) creates the object, while client.js /
    //     dynamicTable.js / misc.js have not run yet. Sampled at that moment
    //     the namespace held only 5 early keys and a `keys.length > 0` check
    //     passed — it would have passed with client.js completely broken.
    //     So: wait for full `load` (all deferred scripts executed), then
    //     assert the specific members the UI cannot function without.
    await page.waitForLoadState('load');
    await page.waitForFunction(
      () => {
        const q = (globalThis as Record<string, unknown>).qBittorrent as
          | Record<string, unknown>
          | undefined;
        return !!q && typeof q === 'object' && typeof q.Client === 'object';
      },
      undefined,
      { timeout: 20_000 },
    );

    const namespace = await page.evaluate(() => {
      const q = (globalThis as Record<string, unknown>).qBittorrent as
        | Record<string, unknown>
        | undefined;
      return {
        type: typeof q,
        isObject: q !== null && typeof q === 'object',
        keys: q ? Object.keys(q).sort() : [],
        // Proof the namespace holds real callables, not empty placeholders.
        clientMemberTypes: q?.Client
          ? Object.fromEntries(
              Object.entries(q.Client as Record<string, unknown>).map(([k, v]) => [
                k,
                typeof v,
              ]),
            )
          : {},
      };
    });

    expect(namespace.type, 'window.qBittorrent must be a JS object').toBe('object');
    expect(namespace.isObject).toBe(true);

    // Every member below is registered by a DIFFERENT external script. If the
    // string "qBittorrent" were corrupted in any of them (the historical
    // overlay defect) the corresponding key would be missing here.
    //   Client, Filters, Search, TransferList, Rss <- client.js
    //   DynamicTable, TorrentContent <- dynamicTable.js
    //   Misc <- misc.js          ContextMenu <- contextmenu.js
    //   Filesystem <- filesystem.js   FileTree <- file-tree.js
    //   ProgressBar <- progressbar.js Cache <- cache.js
    //   Statistics <- statistics.js   Dialog <- mocha-init.js
    //
    // MEASURED 2026-09-01 — `Log` is deliberately NOT required: no eagerly
    // loaded script ASSIGNS window.qBittorrent.Log (they only reference it);
    // it is registered lazily when the Log tab opens. Requiring it made this
    // guard refuse a perfectly healthy page — a §11.4.201(1) false positive
    // in the guard itself. This list is the measured healthy set.
    const REQUIRED_MEMBERS = [
      'Cache',
      'Client',
      'ClientData',
      'ColorScheme',
      'ContextMenu',
      'Dialog',
      'DynamicTable',
      'FileTree',
      'Filesystem',
      'Filters',
      'LocalPreferences',
      'Misc',
      'ProgressBar',
      'Search',
      'Statistics',
      'TorrentContent',
      'TransferList',
    ];
    const missing = REQUIRED_MEMBERS.filter((m) => !namespace.keys.includes(m));
    expect(
      missing,
      `window.qBittorrent is missing members registered by external scripts — ` +
        `those scripts did not run or could not see the namespace. ` +
        `Missing: ${JSON.stringify(missing)}. Present: ${JSON.stringify(namespace.keys)}`,
    ).toEqual([]);

    // The namespace must hold real functions, not hollow objects.
    const clientFnCount = Object.values(namespace.clientMemberTypes).filter(
      (t) => t === 'function',
    ).length;
    expect(
      clientFnCount,
      `window.qBittorrent.Client exposes no functions — present but dead. ` +
        `Members: ${JSON.stringify(namespace.clientMemberTypes)}`,
    ).toBeGreaterThan(0);

    // The live client must actually be talking to the API — proof the JS is
    // not merely parsed but running its sync loop.
    await expect(page.locator('#connectionStatus')).toBeVisible();
    await expect(page.locator('#connectionStatus')).not.toHaveClass(/disconnected/, {
      timeout: 20_000,
    });

    // ---------------------------------------------------------------------
    // CONTROL NEEDLE (§11.4.201(6)(7)(b)) — a zero from a BLIND listener and
    // a zero from a CLEAN page are the same quiet zero. The login page proved
    // the listener works, but this page arrived via login.js's
    // `location.replace()` navigation. Prove the listener still sees THROUGH
    // that navigation before trusting its silence below.
    // ---------------------------------------------------------------------
    const NEEDLE = 'BOBA_CONTROL_NEEDLE_c7f21a';
    await page.evaluate((n) => console.error(n), NEEDLE);
    await expect
      .poll(() => d.consoleErrors.filter((e) => e.includes(NEEDLE)).length, {
        timeout: 5_000,
        message:
          'Control needle NOT observed — the console listener is blind on the ' +
          'post-login page, so any "zero console errors" result below would be ' +
          'a false null, not evidence.',
      })
      .toBe(1);

    // The needle is instrument self-proof, not a product defect — exclude it.
    const realConsoleErrors = d.consoleErrors.filter((e) => !e.includes(NEEDLE));

    mkdirSync(EVIDENCE_DIR, { recursive: true });
    const shot = join(EVIDENCE_DIR, 'qbittorrent-webui-logged-in.png');
    await page.screenshot({ path: shot, fullPage: true });

    writeEvidence('positive-login-console', d, {
      verdict: 'logged in',
      qBittorrentNamespace: namespace,
      controlNeedleObserved: true,
      realConsoleErrors,
      screenshot: shot,
    });

    // (f) LOAD-BEARING: zero console errors, zero uncaught exceptions —
    //     now trustworthy, because the control needle proved the listener
    //     was actually seeing on this page.
    expect(
      d.pageErrors,
      `Uncaught page exceptions during WebUI load/login:\n${d.pageErrors.join('\n---\n')}`,
    ).toEqual([]);
    expect(
      realConsoleErrors,
      `Console errors during WebUI load/login:\n${realConsoleErrors.join('\n')}`,
    ).toEqual([]);
  });
});
