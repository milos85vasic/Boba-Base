// Records real-use BobaLink extension scenarios to video (§11.4.143/§11.4.83).
// Loads the BUILT MV3 artifact (.output/chrome-mv3) into a real Chromium
// persistent context with recordVideo enabled, drives genuine user journeys
// (content-script scan → magnet detection + badge; popup UI; options page),
// and writes per-scenario .webm videos. A wrapper ffmpeg-converts them to
// project-prefixed mp4s in /Volumes/T7/Downloads/Recordings.
//
// Run: cd extension && node scripts/record-features.mjs <out-video-dir>
// Exits non-zero (loud) if the extension cannot load — never a silent fake.
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, resolve, join } from "node:path";
import { existsSync, mkdtempSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const EXT = resolve(here, "..", ".output", "chrome-mv3");
const OUT = process.argv[2] || join(tmpdir(), "bobalink-rec");
mkdirSync(OUT, { recursive: true });

if (!existsSync(EXT)) {
  console.error(`FATAL: built extension missing at ${EXT} — run \`wxt build\` first.`);
  process.exit(2);
}

const MAGNET =
  "magnet:?xt=urn:btih:c12fe1c06bba254a9dc9f519b335aa7c1367a88a&dn=Ubuntu-24.04-desktop-amd64";
const FIXTURE =
  `<!doctype html><html><head><title>rutracker fixture</title>` +
  `<style>body{font-family:sans-serif;background:#1e1f22;color:#ddd;padding:24px}` +
  `a{color:#6cf;font-size:18px}h1{color:#e34}</style></head><body>` +
  `<h1>RuTracker — search: ubuntu</h1>` +
  `<p><a id="real-magnet" href="${MAGNET}">Ubuntu 24.04 desktop amd64 (magnet)</a></p>` +
  `<p><a id="plain-link" href="https://example.com/page">Forum rules (not a torrent)</a></p>` +
  `</body></html>`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const userDataDir = mkdtempSync(join(tmpdir(), "bobalink-rec-"));
const context = await chromium.launchPersistentContext(userDataDir, {
  channel: "chromium",
  args: [
    "--headless=new",
    `--disable-extensions-except=${EXT}`,
    `--load-extension=${EXT}`,
  ],
  recordVideo: { dir: OUT, size: { width: 1280, height: 800 } },
});

let [sw] = context.serviceWorkers();
sw ??= await context.waitForEvent("serviceworker", { timeout: 30000 }).catch(() => undefined);
if (!sw) {
  console.error("FATAL: extension service worker never registered — MV3 did not load.");
  await context.close();
  process.exit(3);
}
const extId = /^chrome-extension:\/\/([a-p]{32})\//.exec(sw.url())?.[1];
console.log(`extension_id=${extId}`);

// Scenario 1 — real content-script scan: magnet detected + badged on a matched host.
await context.route("**/*", (route) =>
  route.request().url().includes("rutracker.org")
    ? route.fulfill({ contentType: "text/html", body: FIXTURE })
    : route.abort(),
);
const scan = await context.newPage();
await scan.goto("https://rutracker.org/forum/index.php", { waitUntil: "load" });
await scan.locator("#real-magnet .bobalink-badge").waitFor({ state: "visible", timeout: 15000 });
await sleep(2500); // dwell so the badge is clearly visible in the video
await scan.close();
await context.unroute("**/*");

// Scenario 2 — popup UI (the real BobaLink popup the user opens).
const popup = await context.newPage();
await popup.goto(`chrome-extension://${extId}/popup.html`);
await popup.locator(".header-title").waitFor({ state: "visible", timeout: 10000 });
await sleep(2500);
await popup.close();

// Scenario 3 — options page (7 settings tabs).
const opts = await context.newPage();
await opts.goto(`chrome-extension://${extId}/options.html`);
await opts.locator('[role="tab"]').first().waitFor({ state: "visible", timeout: 10000 });
await sleep(2500);
await opts.close();

await context.close();
console.log(`videos_dir=${OUT}`);
