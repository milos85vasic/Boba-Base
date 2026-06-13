/**
 * @fileoverview Anti-bluff unit tests for the DYNAMIC-CONTENT
 * (MutationObserver-driven re-scan) path of the REAL ScannerOrchestrator
 * (src/scanner/orchestrator.ts).
 *
 * CLASSIFICATION — UNIT (not integration): drives the REAL production
 * orchestrator (no stub) against a REAL jsdom DOM with REAL DOM mutations and
 * the REAL `MutationObserver`/`debounce` machinery. There is NO network, NO
 * container, NO live service — the only "infrastructure" is the in-process DOM
 * and event emitter. Time is controlled with vitest fake timers (NOT real
 * sleeps), so the suite is deterministic + fast and carries NO absolute
 * wall-clock thresholds (§11.4.50). That makes it a unit test by the project's
 * own taxonomy (its sibling `tests/unit/orchestrator.test.ts` lives here too).
 *
 * WHY THIS FILE EXISTS — THE GENUINE GAP. The single-page MutationObserver path
 * (single-page apps + infinite scroll insert magnet/.torrent links AFTER initial
 * load) is the orchestrator's `setupMutationObserver()` + `debouncedScan`. The
 * existing `tests/unit/orchestrator.test.ts` MutationObserver block has exactly
 * ONE test: "a DOM mutation triggers a debounced re-scan that picks up the NEW
 * magnet" — i.e. only the childList-insertion case, and it asserts only the
 * detected COUNT (not the per-torrent `torrent-detected` event). The four other
 * load-bearing properties of this path were UNTESTED:
 *
 *   (2) ATTRIBUTE MUTATION: an existing anchor whose `href` is CHANGED to a
 *       magnet is detected — proves the observer's `attributeFilter:["href"]`
 *       branch in `setupMutationObserver()` actually re-scans.
 *   (3) RELEVANCE FILTER: an irrelevant mutation (adding a non-anchor `<div>`
 *       with no magnet text) does NOT trigger a re-scan — proves the
 *       `hasRelevantChanges` filter suppresses spurious scans (no wasted
 *       `scan-completed`, detected count unchanged).
 *   (4) DEBOUNCE COALESCING: many rapid relevant insertions inside the debounce
 *       window collapse to ONE re-scan — proves `debounce(..., mutationDebounceMs)`
 *       coalesces, rather than one scan per mutation.
 *   (5) stop() DISCONNECTS: a relevant mutation AFTER `stop()` triggers NO
 *       re-scan — proves `stop()` disconnects the observer AND cancels the
 *       pending debounced scan (no observer leak).
 *
 * Plus a STRONGER variant of (1) that also asserts the `torrent-detected` event
 * fires for the dynamically-added magnet (the user-observable signal the popup
 * actually consumes), which the existing count-only test does not.
 *
 * ANTI-BLUFF (§11.4 / §107). Every assertion is on a USER-OBSERVABLE outcome:
 * the deduped detected set's contents/count, and events captured off the REAL
 * `TypedEventEmitter` the rest of the extension subscribes to. Each test carries
 * a `REGRESSION:` comment naming the production behaviour it pins and the no-op
 * that would make it RED — e.g. removing the `attributeFilter` branch fails (2);
 * removing the `hasRelevantChanges` guard fails (3) (a div would spuriously
 * re-scan); debouncing per-mutation instead of coalescing fails (4); a
 * `stop()` that forgot `disconnect()`/`cancel()` fails (5).
 *
 * jsdom note: `window.location` defaults to http://localhost/, so the site DB
 * resolves the generic selector set (magnet + .torrent). MutationObserver
 * callbacks are microtask-scheduled in jsdom, so after a DOM mutation we flush
 * microtasks (`await Promise.resolve()` ×2) to arm the debounce timer BEFORE
 * advancing fake timers.
 *
 * @module tests/unit/orchestrator-dynamic-content.test
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
import { DEBOUNCE_DELAYS } from "../../src/shared/constants";
import type { DetectedTorrent } from "../../src/types/torrent";

const INFOHASH_A = "0123456789abcdef0123456789abcdef01234567";
const INFOHASH_B = "fedcba9876543210fedcba9876543210fedcba98";
const INFOHASH_C = "1111111111111111111111111111111111111111";

// dn uses %20-encoded spaces (the committed magnet parser decodes via
// decodeURIComponent), matching the sibling orchestrator.test.ts fixtures.
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu%2024.04%20LTS`;
const MAGNET_B = `magnet:?xt=urn:btih:${INFOHASH_B}&dn=Debian%2012`;
const MAGNET_C = `magnet:?xt=urn:btih:${INFOHASH_C}&dn=Fedora%2040`;

/** Mutation debounce window the production code uses (sourced, not hardcoded). */
const DEBOUNCE = DEBOUNCE_DELAYS.MUTATION;

/**
 * Build an orchestrator with mutation observation ENABLED, over a caller-owned
 * emitter so the test can capture the REAL events the extension subscribes to.
 */
function makeObservingOrchestrator(events: TypedEventEmitter): ScannerOrchestrator {
  return new ScannerOrchestrator(events, { observeMutations: true });
}

/** Find detected items by magnet infohash (user-observable detected-set query). */
function byInfohash(
  items: readonly DetectedTorrent[],
  infohash: string,
): DetectedTorrent[] {
  return items.filter((it) => it.magnet?.infohash === infohash);
}

/**
 * Flush the microtasks jsdom uses to deliver MutationObserver callbacks, so the
 * debounced re-scan timer is armed BEFORE we advance fake timers. Two ticks is
 * enough for the observer callback + the debounce scheduling.
 */
async function flushObserverMicrotasks(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

describe("ScannerOrchestrator — dynamic-content MutationObserver path (real jsdom, fake timers)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("(1) inserting a magnet anchor AFTER start fires torrent-detected + adds it to the detected set", async () => {
    // REGRESSION: pins the childList-insertion branch of setupMutationObserver()
    // AND that mergeResults() emits a per-torrent `torrent-detected` for the
    // dynamically-added magnet (the signal the popup/badge consume). A no-op
    // orchestrator (never wires the observer, or never re-scans) leaves the set
    // at 0 and never emits the event → RED. Stronger than the existing
    // count-only test, which never asserts the event fires.
    const events = new TypedEventEmitter();
    const detected: Array<{ id: string; url: string }> = [];
    events.on("torrent-detected", (p) => detected.push({ id: p.id, url: p.url }));

    const orchestrator = makeObservingOrchestrator(events);
    orchestrator.start();

    // Drain the initial (empty-page) scan.
    await vi.runOnlyPendingTimersAsync();
    expect(orchestrator.getDetectedCount()).toBe(0);
    expect(detected).toHaveLength(0);

    // Dynamic insertion (SPA / infinite-scroll appends a magnet link).
    const anchor = document.createElement("a");
    anchor.setAttribute("href", MAGNET_A);
    anchor.textContent = "Ubuntu 24.04 LTS";
    document.body.appendChild(anchor);

    await flushObserverMicrotasks();
    // Before the debounce window elapses, nothing has re-scanned yet.
    expect(orchestrator.getDetectedCount()).toBe(0);

    await vi.advanceTimersByTimeAsync(DEBOUNCE + 100);

    // User-observable: the magnet is now in the deduped detected set...
    expect(orchestrator.getDetectedCount()).toBe(1);
    expect(byInfohash(orchestrator.getDetectedTorrents(), INFOHASH_A)).toHaveLength(1);
    // ...and the per-torrent event fired exactly once for it.
    expect(detected).toHaveLength(1);
    expect(detected[0]?.url).toBe(MAGNET_A);

    orchestrator.stop();
  });

  it("(2) changing an existing anchor's href TO a magnet (attribute mutation) is detected", async () => {
    // REGRESSION: pins the `attributeFilter:["href"]` + the
    // `mutation.type === "attributes"` branch in setupMutationObserver(). The
    // observer is registered with attributeFilter:["href"]; if that branch (or
    // the filter) were dropped, a plain non-magnet anchor whose href is LATER
    // rewritten to a magnet would never be re-scanned → detected count stays 0
    // → RED. Drives the real "href flips to magnet" SPA pattern.
    const events = new TypedEventEmitter();
    const detected: string[] = [];
    events.on("torrent-detected", (p) => detected.push(p.url));

    // A non-torrent anchor present at start (initial scan must ignore it).
    const anchor = document.createElement("a");
    anchor.setAttribute("href", "https://example.org/not-a-torrent");
    anchor.textContent = "Pending link";
    document.body.appendChild(anchor);

    const orchestrator = makeObservingOrchestrator(events);
    orchestrator.start();
    await vi.runOnlyPendingTimersAsync();
    expect(orchestrator.getDetectedCount()).toBe(0);

    // Mutate the href to a magnet (attribute mutation, not a child insertion).
    anchor.setAttribute("href", MAGNET_B);

    await flushObserverMicrotasks();
    expect(orchestrator.getDetectedCount()).toBe(0); // still inside debounce

    await vi.advanceTimersByTimeAsync(DEBOUNCE + 100);

    // User-observable: the now-magnet anchor was picked up via the href-attr path.
    expect(orchestrator.getDetectedCount()).toBe(1);
    expect(byInfohash(orchestrator.getDetectedTorrents(), INFOHASH_B)).toHaveLength(1);
    expect(detected).toContain(MAGNET_B);

    orchestrator.stop();
  });

  it("(3) an irrelevant mutation (non-anchor <div>, no magnet text) triggers NO re-scan", async () => {
    // REGRESSION: pins the `hasRelevantChanges` relevance filter. If that guard
    // were removed (debouncedScan() called on EVERY mutation), adding an inert
    // <div> would fire a spurious re-scan → a `scan-completed` event would be
    // emitted → RED. We assert ZERO additional scan-completed events after the
    // initial scan AND an unchanged detected count.
    const events = new TypedEventEmitter();
    let scanCompletedCount = 0;
    events.on("scan-completed", () => {
      scanCompletedCount += 1;
    });

    const orchestrator = makeObservingOrchestrator(events);
    orchestrator.start();
    await vi.runOnlyPendingTimersAsync();

    // The initial scan completes once; capture that baseline.
    const baselineScans = scanCompletedCount;
    expect(baselineScans).toBeGreaterThanOrEqual(1);
    expect(orchestrator.getDetectedCount()).toBe(0);

    // Add irrelevant content: a <div> with prose, no anchor, no "magnet:" text.
    const div = document.createElement("div");
    div.textContent = "Just some article prose, nothing torrent-related here.";
    document.body.appendChild(div);

    await flushObserverMicrotasks();
    await vi.advanceTimersByTimeAsync(DEBOUNCE + 100);

    // User-observable: no NEW scan ran (count of scan-completed unchanged) and
    // the detected set is still empty — the relevance filter suppressed it.
    expect(scanCompletedCount).toBe(baselineScans);
    expect(orchestrator.getDetectedCount()).toBe(0);

    orchestrator.stop();
  });

  it("(4) many rapid relevant insertions within the debounce window coalesce into ONE re-scan", async () => {
    // REGRESSION: pins the debounce coalescing of debouncedScan. The observer
    // calls debouncedScan() for EACH relevant mutation; debounce must collapse
    // a burst inside the window into a single scan. If debounce were removed
    // (scan-per-mutation), we'd see one extra scan-completed per insertion → the
    // count would jump by ~3 instead of 1 → RED. We assert EXACTLY one extra
    // scan-completed beyond the initial, and all three magnets present.
    const events = new TypedEventEmitter();
    let scanCompletedCount = 0;
    events.on("scan-completed", () => {
      scanCompletedCount += 1;
    });

    const orchestrator = makeObservingOrchestrator(events);
    orchestrator.start();
    await vi.runOnlyPendingTimersAsync();
    const baselineScans = scanCompletedCount;
    expect(baselineScans).toBeGreaterThanOrEqual(1);

    // Three relevant insertions, each well inside the debounce window. We use a
    // FRACTION of the window between them (NOT an absolute wall-clock sleep) so
    // the burst stays within one debounce period deterministically.
    const step = Math.floor(DEBOUNCE / 4);
    for (const m of [MAGNET_A, MAGNET_B, MAGNET_C]) {
      const a = document.createElement("a");
      a.setAttribute("href", m);
      a.textContent = m;
      document.body.appendChild(a);
      await flushObserverMicrotasks();
      // Advance less than the full window → the debounce timer keeps resetting.
      await vi.advanceTimersByTimeAsync(step);
    }

    // Still mid-debounce after the last insertion: no coalesced scan yet.
    expect(scanCompletedCount).toBe(baselineScans);

    // Now let the (single) coalesced scan fire.
    await vi.advanceTimersByTimeAsync(DEBOUNCE + 100);

    // User-observable: exactly ONE re-scan ran for the whole burst...
    expect(scanCompletedCount).toBe(baselineScans + 1);
    // ...and all three dynamically-added magnets are in the detected set.
    expect(orchestrator.getDetectedCount()).toBe(3);
    expect(byInfohash(orchestrator.getDetectedTorrents(), INFOHASH_A)).toHaveLength(1);
    expect(byInfohash(orchestrator.getDetectedTorrents(), INFOHASH_B)).toHaveLength(1);
    expect(byInfohash(orchestrator.getDetectedTorrents(), INFOHASH_C)).toHaveLength(1);

    orchestrator.stop();
  });

  it("(5) stop() disconnects the observer: a relevant mutation AFTER stop triggers NO re-scan", async () => {
    // REGRESSION: pins stop() -> mutationObserver.disconnect() + debouncedScan
    // .cancel(). If stop() forgot to disconnect (observer leak) OR forgot to
    // cancel a pending debounce, a magnet inserted AFTER stop() would still be
    // re-scanned → detected count would become 1 / scan-completed would tick →
    // RED. We assert the post-stop insertion is IGNORED.
    const events = new TypedEventEmitter();
    let scanCompletedCount = 0;
    events.on("scan-completed", () => {
      scanCompletedCount += 1;
    });

    const orchestrator = makeObservingOrchestrator(events);
    orchestrator.start();
    await vi.runOnlyPendingTimersAsync();
    const baselineScans = scanCompletedCount;
    expect(orchestrator.getDetectedCount()).toBe(0);

    // Stop the orchestrator — observer must disconnect, pending scans cancel.
    orchestrator.stop();

    // Insert a real magnet AFTER stop(). A live observer would re-scan it.
    const anchor = document.createElement("a");
    anchor.setAttribute("href", MAGNET_A);
    anchor.textContent = "Added after stop";
    document.body.appendChild(anchor);

    await flushObserverMicrotasks();
    await vi.advanceTimersByTimeAsync(DEBOUNCE + 100);

    // User-observable: nothing happened — no new scan, set still empty.
    expect(scanCompletedCount).toBe(baselineScans);
    expect(orchestrator.getDetectedCount()).toBe(0);
  });
});
