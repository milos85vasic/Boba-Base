#!/usr/bin/env node
/**
 * nnmclub-cookie-harvest.mjs
 *
 * Purpose:
 *   Obtain a real NNMClub session cookie set FULLY AUTOMATICALLY by driving a
 *   genuine headless Chromium through the login flow. nnmclub.to/forum/login.php
 *   is gated behind a Cloudflare Turnstile JS CAPTCHA (see
 *   docs/qa/nnmclub-login-diagnosis-20260616.md). A plain HTTP password POST
 *   sends no cf-turnstile-response token and gets HTTP 200 with NO Set-Cookie.
 *   A real browser renders + (in managed/non-interactive mode) often
 *   auto-resolves Turnstile WITHOUT a click, after which the server issues the
 *   phpbb2mysql_4_sid session cookie.
 *
 * Behaviour:
 *   - Launches headless Chromium (Playwright, reused from extension/node_modules).
 *   - Navigates to login.php, fills NNMCLUB_USERNAME / NNMCLUB_PASSWORD (env),
 *     submits, and WAITS for the post-login phpbb2mysql_4_sid cookie to appear.
 *   - On success: prints the cookie string (phpbb2mysql_4_sid + phpbb2mysql_4_data
 *     + cf_clearance when present) in NNMCLUB_COOKIES form to stdout, exit 0.
 *   - On Turnstile block / timeout / bad creds: prints an HONEST diagnostic to
 *     stderr and exits non-zero. NEVER fakes a cookie.
 *
 * Inputs (env):
 *   NNMCLUB_USERNAME, NNMCLUB_PASSWORD   (required; values never printed)
 *   NNMCLUB_BASE_URL                     (optional; default https://nnmclub.to)
 *   NNMCLUB_HARVEST_HEADFUL=1            (optional; run headed for debugging /
 *                                         interactive Turnstile fallback)
 *   NNMCLUB_HARVEST_TIMEOUT_MS           (optional; default 60000)
 *   PLAYWRIGHT_MODULE                    (optional; path to a playwright install)
 *
 * Outputs:
 *   stdout (success only): `name=value; name=value`  — feed to NNMCLUB_COOKIES
 *   stderr: human-readable progress + honest failure reason
 *
 * Side-effects: none (no files written, no creds logged).
 * Dependencies: Playwright + a Chromium browser (already installed for this repo).
 * Cross-references: scripts/nnmclub-cookie-refresh.sh (wiring),
 *   download-proxy/src/merge_service/search.py (_search_nnmclub consumes cookies),
 *   docs/qa/nnmclub-login-diagnosis-20260616.md (root-cause FACT).
 */

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");

// Reuse the Playwright + Chromium already vendored in this repo. Prefer the
// extension copy, then frontend, then a globally resolvable one.
function loadChromium() {
  const candidates = [];
  if (process.env.PLAYWRIGHT_MODULE) candidates.push(process.env.PLAYWRIGHT_MODULE);
  candidates.push(
    path.join(repoRoot, "extension", "node_modules", "playwright"),
    path.join(repoRoot, "frontend", "node_modules", "playwright"),
    "playwright",
  );
  const require = createRequire(import.meta.url);
  for (const c of candidates) {
    try {
      const pw = require(c);
      if (pw && pw.chromium) return pw.chromium;
    } catch {
      /* try next */
    }
  }
  throw new Error(
    "Playwright not found. Expected extension/node_modules/playwright " +
      "(run `cd extension && npm install`) or set PLAYWRIGHT_MODULE.",
  );
}

const LOGGER = (msg) => process.stderr.write(`[nnmclub-harvest] ${msg}\n`);

async function main() {
  const username = process.env.NNMCLUB_USERNAME;
  const password = process.env.NNMCLUB_PASSWORD;
  if (!username || !password) {
    LOGGER("FATAL: NNMCLUB_USERNAME / NNMCLUB_PASSWORD not set in environment.");
    process.exit(3);
  }

  const baseUrl = (process.env.NNMCLUB_BASE_URL || "https://nnmclub.to").replace(/\/+$/, "");
  const loginUrl = `${baseUrl}/forum/login.php`;
  const timeoutMs = Number.parseInt(process.env.NNMCLUB_HARVEST_TIMEOUT_MS || "60000", 10);
  const headful = process.env.NNMCLUB_HARVEST_HEADFUL === "1";

  const chromium = loadChromium();

  LOGGER(`launching ${headful ? "headed" : "headless"} Chromium`);
  const browser = await chromium.launch({
    headless: !headful,
    args: ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
  });

  let exitCode = 1;
  try {
    const context = await browser.newContext({
      // A genuine desktop UA + viewport — Turnstile's managed mode is more
      // likely to auto-pass a browser that looks real.
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      viewport: { width: 1280, height: 900 },
      locale: "ru-RU",
    });
    const page = await context.newPage();

    LOGGER(`navigating to login form`);
    await page.goto(loginUrl, { waitUntil: "domcontentloaded", timeout: timeoutMs });

    // Fill credentials. nnmclub phpBB login uses name="username"/"password".
    await page.fill('input[name="username"]', username, { timeout: 15000 });
    await page.fill('input[name="password"]', password, { timeout: 15000 });
    LOGGER("credentials filled (values not logged)");

    // Give Turnstile a moment to render + auto-resolve in managed mode. We do
    // NOT click the widget — a real browser frequently passes silently.
    await page.waitForTimeout(4000);

    // Submit the login form. The submit control is name="login" (value "вход").
    LOGGER("submitting login form");
    await Promise.race([
      page.click('input[name="login"]', { timeout: 10000 }).catch(() => {}),
      page.click('button[type="submit"]', { timeout: 10000 }).catch(() => {}),
      page.press('input[name="password"]', "Enter").catch(() => {}),
    ]);

    // Poll for the session cookie to appear. Success = phpbb2mysql_4_sid set.
    const deadline = Date.now() + timeoutMs;
    let sid = null;
    while (Date.now() < deadline) {
      const cookies = await context.cookies();
      sid = cookies.find((c) => c.name === "phpbb2mysql_4_sid");
      if (sid && sid.value && sid.value.length > 0) break;
      await page.waitForTimeout(1500);
    }

    const cookies = await context.cookies();
    const sidCookie = cookies.find((c) => c.name === "phpbb2mysql_4_sid");
    if (!sidCookie || !sidCookie.value) {
      // Detect whether Turnstile is still blocking us (interactive challenge).
      const bodyText = await page.evaluate(() => document.body?.innerText || "").catch(() => "");
      const turnstilePresent = await page
        .evaluate(() => !!document.querySelector(".cf-turnstile, [data-sitekey], iframe[src*='challenges.cloudflare.com']"))
        .catch(() => false);
      LOGGER("FAILURE: no phpbb2mysql_4_sid session cookie after login attempt.");
      if (turnstilePresent) {
        LOGGER(
          "Cloudflare Turnstile is still present and did NOT auto-resolve — " +
            "this is an INTERACTIVE challenge (bot-detected). Unattended " +
            "headless automation is blocked. Options: (1) re-run headful with " +
            "NNMCLUB_HARVEST_HEADFUL=1 and solve it once, (2) use a persistent " +
            "browser profile, (3) export NNMCLUB_COOKIES manually from a " +
            "logged-in browser, (4) a Turnstile-solver service.",
        );
      } else if (/неверный|invalid|пароль|password|incorrect/i.test(bodyText)) {
        LOGGER("The page suggests the credentials were rejected — verify NNMCLUB_USERNAME/PASSWORD.");
      } else {
        LOGGER("No Turnstile widget detected but login did not produce a session — site flow may have changed.");
      }
      exitCode = 2;
    } else {
      // SUCCESS — assemble NNMCLUB_COOKIES (sid + data + cf_clearance if present).
      const wanted = ["phpbb2mysql_4_sid", "phpbb2mysql_4_data", "cf_clearance"];
      const parts = [];
      for (const name of wanted) {
        const c = cookies.find((x) => x.name === name);
        if (c && c.value) parts.push(`${c.name}=${c.value}`);
      }
      LOGGER(`SUCCESS: obtained session (${parts.map((p) => p.split("=")[0]).join(", ")})`);
      // The ONLY thing on stdout is the cookie string — easy to capture.
      process.stdout.write(parts.join("; ") + "\n");
      exitCode = 0;
    }

    await context.close();
  } catch (err) {
    LOGGER(`FATAL: ${err && err.message ? err.message : String(err)}`);
    exitCode = 1;
  } finally {
    await browser.close();
  }
  process.exit(exitCode);
}

main().catch((err) => {
  LOGGER(`FATAL (unhandled): ${err && err.message ? err.message : String(err)}`);
  process.exit(1);
});
