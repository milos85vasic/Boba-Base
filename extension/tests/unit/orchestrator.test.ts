/**
 * @fileoverview Anti-bluff unit tests for the REAL ScannerOrchestrator
 * (scanner/orchestrator.ts).
 *
 * Imports the production `src/scanner/orchestrator.ts` and drives it against a
 * REAL jsdom DOM. These are USER-OBSERVABLE assertions on the combined,
 * cross-scanner-deduped detected set:
 *
 *   - The orchestrator composes the COMMITTED LinkScanner + TextScanner: a magnet
 *     in an `<a href>` is found by the link scanner; the SAME magnet in bare page
 *     text is found by the text scanner.
 *   - CROSS-SCANNER DEDUP: the same magnet detected by BOTH scanners (link + text)
 *     appears EXACTLY ONCE in `getDetectedTorrents()` — dedup is by the stable
 *     infohash-derived id, so the two scanners' detections collapse into one.
 *   - Detection from both scanners, ignoring non-torrents, stable ids across
 *     re-scans, and a MutationObserver-driven debounced re-scan (fake timers).
 *
 * The dedup + detection assertions FAIL against a no-op stub (or if dedup is
 * removed) — that is the §11.4 anti-bluff RED proof driven in the agent session.
 *
 * Runs under vitest + jsdom (window.location defaults to http://localhost/, so
 * getSiteSelectors() resolves to the generic selector set: magnet + .torrent).
 *
 * @module tests/unit/orchestrator.test
 */

import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
} from "vitest";
import { ScannerOrchestrator } from "../../src/scanner/orchestrator";
import { TypedEventEmitter } from "../../src/shared/events";
import type { DetectedTorrent } from "../../src/types/torrent";

const INFOHASH_SHARED = "0123456789abcdef0123456789abcdef01234567";
const INFOHASH_TEXTONLY = "fedcba9876543210fedcba9876543210fedcba98";

// dn uses %20-encoded spaces (the committed parser decodes via decodeURIComponent).
const MAGNET_SHARED = `magnet:?xt=urn:btih:${INFOHASH_SHARED}&dn=Ubuntu%2024.04%20LTS`;
const MAGNET_TEXTONLY = `magnet:?xt=urn:btih:${INFOHASH_TEXTONLY}&dn=Debian%2012`;
const TORRENT_URL = "https://example.org/files/cool-release.torrent";

/** Build a fresh orchestrator. observeMutations off unless a test wants it. */
function makeOrchestrator(
  observeMutations = false,
  events?: TypedEventEmitter,
): ScannerOrchestrator {
  return new ScannerOrchestrator(events, { observeMutations });
}

/** Find a detected item by its magnet infohash. */
function byInfohash(
  items: readonly DetectedTorrent[],
  infohash: string,
): DetectedTorrent[] {
  return items.filter((it) => it.magnet?.infohash === infohash);
}

describe("ScannerOrchestrator — cross-scanner orchestration (anti-bluff, real jsdom)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("CROSS-SCANNER DEDUP: same magnet as <a href> AND as bare text → ONE result", async () => {
    // The SAME magnet appears twice in the page:
    //   (1) as an anchor href  → the committed LinkScanner detects it
    //   (2) as bare paragraph text → the committed TextScanner detects it
    // The orchestrator MUST merge these into a SINGLE detected torrent.
    document.body.innerHTML = `
      <a id="link" href="${MAGNET_SHARED}">Ubuntu via link</a>
      <p id="text">Here is the same release as plain text: ${MAGNET_SHARED} — enjoy!</p>
    `;

    const orchestrator = makeOrchestrator();
    const result = await orchestrator.scanNow();

    const detected = orchestrator.getDetectedTorrents();
    const sharedMatches = byInfohash(detected, INFOHASH_SHARED);

    // EXACTLY ONE entry for the shared magnet, despite two scanners finding it.
    expect(sharedMatches.length).toBe(1);
    expect(orchestrator.getDetectedCount()).toBe(1);
    expect(result.magnetCount).toBe(1);
    expect(result.items.length).toBe(1);
    // The single surviving entry carries the correct identity.
    expect(sharedMatches[0]?.magnet?.infohash).toBe(INFOHASH_SHARED);
    expect(sharedMatches[0]?.displayName).toBe("Ubuntu 24.04 LTS");
  });

  it("detects magnets from BOTH scanners (link-only + text-only), merged", async () => {
    // One magnet ONLY in an anchor (link scanner's job),
    // a DIFFERENT magnet ONLY in bare text (text scanner's job).
    document.body.innerHTML = `
      <a href="${MAGNET_SHARED}">Ubuntu (anchor only)</a>
      <p>A different release pasted as text: ${MAGNET_TEXTONLY} thanks</p>
    `;

    const orchestrator = makeOrchestrator();
    await orchestrator.scanNow();

    const detected = orchestrator.getDetectedTorrents();
    expect(orchestrator.getDetectedCount()).toBe(2);
    // The link-only magnet was found by the LinkScanner.
    expect(byInfohash(detected, INFOHASH_SHARED).length).toBe(1);
    // The text-only magnet was found by the TextScanner.
    expect(byInfohash(detected, INFOHASH_TEXTONLY).length).toBe(1);
  });

  it("also surfaces .torrent file links alongside magnets", async () => {
    document.body.innerHTML = `
      <a href="${MAGNET_SHARED}">Magnet</a>
      <a href="${TORRENT_URL}">Get the .torrent</a>
    `;

    const orchestrator = makeOrchestrator();
    const result = await orchestrator.scanNow();

    expect(result.magnetCount).toBe(1);
    expect(result.torrentFileCount).toBe(1);
    const file = orchestrator
      .getDetectedTorrents()
      .find((it) => it.type === "torrent-file");
    expect(file?.torrentFile?.url).toBe(TORRENT_URL);
  });

  it("IGNORES non-torrent content (normal links, prose with no magnet)", async () => {
    document.body.innerHTML = `
      <a href="https://example.org/page.html">A normal page link here</a>
      <a href="mailto:someone@example.com">Email me right now please</a>
      <p>Just some ordinary prose without any torrent of any kind at all.</p>
      <a href="#top">Jump to the very top of this page now</a>
    `;

    const orchestrator = makeOrchestrator();
    const result = await orchestrator.scanNow();

    expect(orchestrator.getDetectedCount()).toBe(0);
    expect(result.items.length).toBe(0);
    expect(result.magnetCount).toBe(0);
    expect(result.torrentFileCount).toBe(0);
  });

  it("produces STABLE ids: re-scanning the SAME page does not duplicate entries", async () => {
    document.body.innerHTML = `
      <a href="${MAGNET_SHARED}">Ubuntu via link</a>
      <p>Same magnet again as text: ${MAGNET_SHARED} cheers</p>
    `;

    const orchestrator = makeOrchestrator();

    const first = await orchestrator.scanNow();
    const idsAfterFirst = orchestrator
      .getDetectedTorrents()
      .map((it) => it.id)
      .sort();

    // A second scan of the unchanged DOM must NOT add anything.
    await orchestrator.scanNow();
    const idsAfterSecond = orchestrator
      .getDetectedTorrents()
      .map((it) => it.id)
      .sort();

    expect(first.magnetCount).toBe(1);
    expect(orchestrator.getDetectedCount()).toBe(1);
    expect(idsAfterSecond).toEqual(idsAfterFirst);
  });
});

describe("ScannerOrchestrator — MutationObserver-driven re-scan (fake timers)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("a DOM mutation triggers a debounced re-scan that picks up the NEW magnet", async () => {
    // Start with an empty page and an observing orchestrator.
    const orchestrator = makeOrchestrator(true);
    orchestrator.start();

    // Drain the initial scan (no torrents yet).
    await vi.runOnlyPendingTimersAsync();
    expect(orchestrator.getDetectedCount()).toBe(0);

    // Inject a magnet anchor AFTER start — the MutationObserver should notice.
    const anchor = document.createElement("a");
    anchor.setAttribute("href", MAGNET_SHARED);
    anchor.textContent = "Newly added magnet";
    document.body.appendChild(anchor);

    // MutationObserver callbacks are microtask-scheduled in jsdom; flush them so
    // the debounced re-scan timer is actually armed.
    await Promise.resolve();
    await Promise.resolve();

    // Before the debounce window elapses, nothing has been re-scanned yet.
    expect(orchestrator.getDetectedCount()).toBe(0);

    // Advance past the 500ms debounce window and let the async scan settle.
    await vi.advanceTimersByTimeAsync(600);

    // The re-scan picked up the newly-added magnet.
    expect(orchestrator.getDetectedCount()).toBe(1);
    expect(
      byInfohash(orchestrator.getDetectedTorrents(), INFOHASH_SHARED).length,
    ).toBe(1);

    orchestrator.stop();
  });
});
