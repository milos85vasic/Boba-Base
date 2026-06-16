// Records real-use web-dashboard UI features to video (§11.4.143/§11.4.83).
// Drives the LIVE dashboard at $BOBA_URL (default http://localhost:7187 via the
// macOS↔VM tunnel) through non-mutating controls — search, the 5 result tabs,
// theme toggle, the Jackett page + Add-credential dialog — with recordVideo on.
// Avoids state-mutating actions (qBit-add / download) by design.
//
// Run: cd frontend && BOBA_URL=http://localhost:7187 node scripts/record-web-features.mjs <out-dir>
// Each captured step also screenshots to <out-dir>/step-NN-*.png for vision review.
import { chromium } from "playwright";
import { join } from "node:path";
import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";

const URL = process.env.BOBA_URL || "http://localhost:7187";
const OUT = process.argv[2] || join(tmpdir(), "boba-web-rec");
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ channel: "chromium", args: ["--headless=new"] });
const context = await browser.newContext({
  recordVideo: { dir: OUT, size: { width: 1280, height: 900 } },
  viewport: { width: 1280, height: 900 },
});
const page = await context.newPage();
let step = 0;
const shot = async (name) => {
  step += 1;
  await page.screenshot({ path: join(OUT, `step-${String(step).padStart(2, "0")}-${name}.png`) });
  console.log(`captured step ${step}: ${name}`);
};
const clickIf = async (role, name, label) => {
  const loc = page.getByRole(role, { name }).first();
  if (await loc.count().catch(() => 0)) {
    await loc.click().catch(() => {});
    await sleep(1200);
    await shot(label);
    return true;
  }
  console.log(`  (control not present: ${label})`);
  return false;
};

try {
  await page.goto(URL, { waitUntil: "domcontentloaded" });
  await sleep(2000);
  await shot("dashboard-load");

  // Real search so the tabs/grid have context.
  const box = page.getByRole("textbox").first();
  await box.fill("debian");
  await box.press("Enter");
  await sleep(8000);
  await shot("search-results");

  // The 5 result tabs (non-mutating).
  for (const t of ["Trackers", "Active Downloads", "Schedules", "Hooks", "Results"]) {
    await clickIf("button", t, `tab-${t.replace(/\s+/g, "-").toLowerCase()}`);
  }

  // Theme toggle (non-mutating UI).
  await clickIf("button", /light mode|dark mode|Darcula/i, "theme-toggle");

  // Jackett page + Add-credential dialog (open only — never Save).
  await page.goto(`${URL}/jackett`, { waitUntil: "domcontentloaded" });
  await sleep(2500);
  await shot("jackett-page");
  for (const t of ["Configured", "Catalog", "History"]) {
    await clickIf("tab", t, `jackett-tab-${t.toLowerCase()}`) ||
      (await clickIf("button", t, `jackett-tab-${t.toLowerCase()}`));
  }
  await clickIf("button", /Add credential/i, "jackett-add-credential-dialog");
} catch (e) {
  console.error("capture error:", e?.message || e);
} finally {
  await sleep(1500);
  await context.close();
  await browser.close();
  console.log(`videos_dir=${OUT}`);
}
