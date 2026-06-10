/**
 * @fileoverview WXT content-script entrypoint.
 *
 * Thin wrapper: the real detection/highlight/messaging logic lives in
 * `src/content/index.ts` ({@link initContentScript}). This entrypoint is the
 * SINGLE driver of that logic in a real content-script context — the logic
 * module's former self-init auto-run block was removed precisely because this
 * entrypoint now owns the lifecycle (running both would double-register the
 * `chrome.runtime.onMessage` listener).
 *
 * ## `matches` — least-privilege, single source of truth (§11.4.111)
 * The match list is DERIVED at build time from the curated `SITE_SELECTORS`
 * table in `src/shared/constants.ts` — the one place the supported torrent
 * sites are declared. This keeps the manifest's `content_scripts.matches` in
 * lock-step with the scanner's site DB (no drift), and honours the plan's
 * least-privilege mandate (T1.2: NO `<all_urls>`). Each host becomes
 * `*://*.<host>/*` so `www.` and sub-domains of a known site are covered.
 *
 * @module entrypoints/content
 */
import { defineContentScript } from "wxt/sandbox";

import { initContentScript } from "../content";
import { SITE_SELECTORS } from "../shared/constants";

/**
 * Curated content-script match patterns derived from the single
 * `SITE_SELECTORS` source. `generic` is the fallback selector bucket, not a
 * real host, so it is excluded.
 */
const matches: string[] = Object.keys(SITE_SELECTORS)
  .filter((host) => host !== "generic")
  .map((host) => `*://*.${host}/*`);

export default defineContentScript({
  matches,
  runAt: "document_idle",
  allFrames: false,
  main() {
    void initContentScript().catch((err: unknown) => {
      console.error("[BobaLink] content script init failed", err);
    });
  },
});
