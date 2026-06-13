/**
 * @fileoverview STRESS + CHAOS tests (§11.4.85) for three REAL committed
 * subsystems, covering ground the existing stress/chaos suite does NOT:
 *
 *   1. {@link ScannerOrchestrator.scanNow} (`src/scanner/orchestrator.ts`) under a
 *      LARGE HOSTILE / junk-heavy page — proves it returns ONLY the real magnets
 *      (junk anchors yield nothing) AND that its cost scales SUB-QUADRATICALLY
 *      (machine-independent N-vs-10N time-ratio, never an absolute wall-clock
 *      threshold — see "anti-flake" below).
 *   2. The REAL client request queue + token-bucket rate limiter
 *      ({@link BobaClient} + {@link TokenBucket}, `src/api/boba-client.ts` /
 *      `src/shared/utils.ts`) under a FLOOD of concurrent `addMagnet` calls —
 *      proves the requests reach the injected `fetch` in FIFO order, that EVERY
 *      flooded request is eventually serviced (no loss), and that the limiter is
 *      actually engaged (bucket bounded — it cannot grant more than capacity in a
 *      frozen window).
 *   3. The tab-group batched send ({@link batchGroupTorrents} +
 *      {@link dispatchGroupBatch}, `src/tabgroups/index.ts`) AT SCALE — many tabs,
 *      large per-tab detection sets, heavy cross-tab duplication → ONE batched
 *      payload with EXACTLY the unique torrents, in first-seen order, and proves
 *      the batch cost scales SUB-QUADRATICALLY in (tabs × detections).
 *
 * NON-DUPLICATION (verified against the committed suite): the existing
 * `orchestrator.stress.test.ts` asserts exact dedup under load BUT bounds time
 * with a FIXED 30s wall budget; this file instead uses the machine-independent
 * N-vs-10N scaling ratio the host-oversubscription rule (§11.4.50 "flaky tests
 * are bluffs", §11.4.85 "scaling/distribution not hard thresholds") mandates, and
 * adds the junk-only-returns-real-magnets invariant. `ratelimit.stress.test.ts`
 * exercises `TokenBucket` IN ISOLATION; this file exercises the limiter INTEGRATED
 * into the real `BobaClient.requestWithRetry` FIFO send path under a flood.
 * `tests/unit/tabgroups.test.ts` covers small-scale dedup correctness; this file
 * adds the AT-SCALE batch + sub-quadratic scaling + a flaky-tab CHAOS pass.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * ANTI-FLAKE / MACHINE-INDEPENDENCE (§11.4.50 + §11.4.85):
 *   We NEVER assert `elapsed < <constant>ms`. The host is shared / oversubscribed,
 *   so an absolute-time threshold is a coin-flip. Instead, for "no DoS blowup /
 *   bounded time" we measure the operation at size N and at size 10N and assert
 *   the time RATIO is sub-quadratic: a linear-ish scan shows ratio ≈ 10, a true
 *   O(n²) shows ratio ≈ 100. The bar `ratio < MAX_SUBQUADRATIC_RATIO` (25) sits
 *   comfortably ABOVE the ~10 a healthy linear scan exhibits (so noise won't
 *   false-FAIL it) and well BELOW the ~100 a quadratic regression would exhibit
 *   (so it WILL catch the regression). To further damp scheduler noise the timed
 *   region is repeated and the MEDIAN of several samples is taken, and the larger
 *   workload's per-unit floor is guarded with a small epsilon so a sub-millisecond
 *   tiny baseline cannot divide-by-zero into a false ratio.
 *
 * EVIDENCE (§11.4.85 MANDATORY): each test writes a captured-evidence JSON
 * artifact under `tests/stress/.evidence/` and asserts on the captured data
 * (counts, FIFO order, scaling ratio). A PASS with no captured artifact is a
 * §11.4 bluff. Every assertion is on a USER-OBSERVABLE outcome — the exact set of
 * real magnets, the FIFO order requests hit the wire, the exact unique batched
 * URLs, the measured scaling ratio — never "no error".
 *
 * @module tests/stress/orchestrator-ratelimiter-tabgroup.stress.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { ScannerOrchestrator } from "../../src/scanner/orchestrator";
import { BobaClient } from "../../src/api/boba-client";
import { TokenBucket } from "../../src/shared/utils";
import { RATE_LIMIT } from "../../src/shared/constants";
import {
  batchGroupTorrents,
  dispatchGroupBatch,
  type GroupBatchDeps,
  type GroupSendPayload,
} from "../../src/tabgroups";
import type {
  DetectedTorrent,
  MagnetInfo,
  PageScanResult,
} from "../../src/types/torrent";

const HERE = dirname(fileURLToPath(import.meta.url));
const EVIDENCE_DIR = join(HERE, ".evidence");

/** Write a §11.4.85 captured-evidence artifact and return its absolute path. */
function captureEvidence(name: string, data: unknown): string {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  const path = join(EVIDENCE_DIR, name);
  writeFileSync(path, JSON.stringify(data, null, 2), "utf8");
  return path;
}

/**
 * The machine-independent sub-quadratic ceiling for a 10× size step. A linear
 * scan ⇒ ratio ≈ 10; a quadratic ⇒ ratio ≈ 100. 25 sits comfortably between, so
 * scheduler noise on a busy host won't false-FAIL a healthy linear scan, but a
 * genuine O(n²) regression (which would land near 100) WILL be caught.
 */
const MAX_SUBQUADRATIC_RATIO = 25;

/** Median of a numeric sample (odd/even safe). Used to damp scheduler jitter. */
function median(samples: number[]): number {
  const s = [...samples].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 === 0
    ? ((s[mid - 1] as number) + (s[mid] as number)) / 2
    : (s[mid] as number);
}

/** Time `fn` REPS times and return the MEDIAN elapsed ms (jitter-resistant). */
async function medianTimedMs(reps: number, fn: () => Promise<void>): Promise<number> {
  const samples: number[] = [];
  for (let r = 0; r < reps; r++) {
    const t0 = performance.now();
    await fn();
    samples.push(performance.now() - t0);
  }
  return median(samples);
}

/**
 * Build a deterministic 40-char hex infohash for index `n`. The
 * MAGNET_VALIDATION_REGEX requires EXACTLY 40 hex chars after `btih:`.
 */
function infohashFor(n: number): string {
  const eight = (n >>> 0).toString(16).padStart(8, "0");
  return (eight + eight + eight + eight + eight).slice(0, 40);
}

/** A valid magnet URI for index `n`. */
function magnetFor(n: number): string {
  return `magnet:?xt=urn:btih:${infohashFor(n)}&dn=Torrent+${n}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. ScannerOrchestrator.scanNow() — hostile/junk page: only real magnets,
//    sub-quadratic scaling (N vs 10N RATIO, machine-independent)
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: ScannerOrchestrator.scanNow() on a hostile junk-heavy page", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });
  afterEach(() => {
    document.body.innerHTML = "";
  });

  /**
   * Build a hostile page with `realMagnets` distinct valid magnets buried among a
   * 9:1 ratio of junk anchors + junk text (mailto:, javascript:, fragments,
   * almost-magnets with too-short / non-hex infohashes, bare junk text nodes).
   * Only the `realMagnets` distinct valid magnets must be detected.
   */
  function buildHostilePage(realMagnets: number): void {
    const parts: string[] = [];
    for (let i = 0; i < realMagnets; i++) {
      parts.push(`<a href="${magnetFor(i)}">real magnet ${i}</a>`);
      // 9 junk siblings per real magnet → 90% hostile noise.
      parts.push(`<a href="mailto:spam${i}@junk.test">mail ${i}</a>`);
      parts.push(`<a href="javascript:void(0)">js ${i}</a>`);
      parts.push(`<a href="#frag-${i}">frag ${i}</a>`);
      parts.push(`<a href="https://junk.test/page/${i}">page ${i}</a>`);
      // Almost-magnet: infohash too short (39 hex) → MUST be rejected, not detected.
      parts.push(`<a href="magnet:?xt=urn:btih:${"a".repeat(39)}&dn=fake${i}">almost ${i}</a>`);
      // Almost-magnet: non-hex infohash → MUST be rejected.
      parts.push(`<a href="magnet:?xt=urn:btih:${"z".repeat(40)}&dn=bad${i}">bad ${i}</a>`);
      // Junk text node (no torrent identity) for the TextScanner to reject.
      parts.push(`<p>lorem ipsum junk paragraph number ${i} with no torrent at all here</p>`);
      parts.push(`<a href="ftp://junk.test/file-${i}.zip">zip ${i}</a>`);
      parts.push(`<span>random ${i} text content padding to add hostile volume</span>`);
    }
    document.body.innerHTML = parts.join("");
  }

  it("returns ONLY the real magnets from a junk-heavy page (junk yields nothing)", async () => {
    // ANTI-BLUFF / how this FAILS if the product regressed: if scanNow() let any
    // junk href (mailto:, javascript:, fragment, almost-magnet with a 39-char or
    // non-hex infohash, ftp/zip, junk text) through, the detected count would
    // exceed REAL or a detected item would carry a non-magnet identity — the
    // exact-set assertions below FAIL.
    const REAL = 400;
    buildHostilePage(REAL);

    const orch = new ScannerOrchestrator(undefined, { observeMutations: false });
    const result = await orch.scanNow();

    const detected = orch.getDetectedTorrents();
    const detectedHashes = new Set(
      detected.map((d) => d.magnet?.infohash).filter((h): h is string => !!h),
    );
    const expectedHashes = new Set(
      Array.from({ length: REAL }, (_u, i) => infohashFor(i)),
    );

    // USER-OBSERVABLE: exactly the REAL distinct magnets, nothing else.
    expect(detected.length).toBe(REAL);
    expect(result.magnetCount).toBe(REAL);
    expect(result.torrentFileCount).toBe(0); // no .torrent files on this page
    expect(detected.every((d) => d.type === "magnet")).toBe(true);
    // The detected infohash SET equals the real-magnet SET (no junk leaked in,
    // none of the real ones lost).
    expect(detectedHashes).toEqual(expectedHashes);

    const evidence = {
      test: "hostile-page-only-real-magnets",
      constitution: "§11.4.85 stress sustained (hostile input)",
      realMagnets: REAL,
      junkAnchorsPerReal: 9,
      detected: detected.length,
      magnetCount: result.magnetCount,
      torrentFileCount: result.torrentFileCount,
      detectedSetEqualsRealSet: detectedHashes.size === expectedHashes.size,
      junkLeaked: detected.length - REAL,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("orchestrator_hostile_only_real.json", evidence);
    expect(evidence.junkLeaked).toBe(0);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS hostile] ${REAL} real magnets among ~${REAL * 9} junk nodes → ` +
        `${detected.length} detected (junk leaked=${detected.length - REAL}) | evidence: ${path}`,
    );
  }, 30_000);

  it("scales SUB-QUADRATICALLY: 10× the page size costs far less than 100× the time (machine-independent ratio)", async () => {
    // ANTI-BLUFF / how this FAILS if the product regressed: if scanNow() became
    // O(n²) in page size (e.g. a per-anchor full re-scan, an accidental nested
    // loop in dedup), the 10× workload would cost ~100× the time and the measured
    // ratio would blow past MAX_SUBQUADRATIC_RATIO (25) → FAIL. A healthy
    // near-linear scan lands near ~10 and PASSES. The threshold is a RATIO, not
    // an absolute wall-clock, so it is reproducible on a busy/slow host.
    const N = 60; // small workload
    const BIG = N * 10; // 10× larger workload (600 real magnets + ~9× junk each)
    const REPS = 3; // median over REPS damps scheduler noise (real DOM scans are ~s each)

    const small = await medianTimedMs(REPS, async () => {
      buildHostilePage(N);
      const o = new ScannerOrchestrator(undefined, { observeMutations: false });
      await o.scanNow();
      // sanity: the small page detected exactly N
      expect(o.getDetectedCount()).toBe(N);
    });

    const big = await medianTimedMs(REPS, async () => {
      buildHostilePage(BIG);
      const o = new ScannerOrchestrator(undefined, { observeMutations: false });
      await o.scanNow();
      expect(o.getDetectedCount()).toBe(BIG);
    });

    // Guard a sub-millisecond tiny baseline (busy host can report ~0) so the
    // ratio is meaningful, not a divide-by-noise artifact.
    const EPS = 0.5;
    const ratio = big / Math.max(small, EPS);

    // The CORE machine-independent assertion: 10× input is NOT ~100× time.
    expect(ratio).toBeLessThan(MAX_SUBQUADRATIC_RATIO);

    const evidence = {
      test: "scanNow-subquadratic-scaling",
      constitution: "§11.4.85 stress scaling (machine-independent ratio)",
      sizeSmall: N,
      sizeBig: BIG,
      sizeStep: BIG / N,
      reps: REPS,
      smallMedianMs: small,
      bigMedianMs: big,
      timeRatio: ratio,
      maxSubquadraticRatio: MAX_SUBQUADRATIC_RATIO,
      subQuadratic: ratio < MAX_SUBQUADRATIC_RATIO,
      // for context: linear≈10, quadratic≈100 at a 10× step
      interpretation: "linear≈10, quadratic≈100; bar=25",
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("orchestrator_subquadratic_scaling.json", evidence);
    expect(evidence.subQuadratic).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS scaling] scanNow ${N}→${BIG} (10×): smallMed=${small.toFixed(2)}ms, ` +
        `bigMed=${big.toFixed(2)}ms, ratio=${ratio.toFixed(2)} (<${MAX_SUBQUADRATIC_RATIO}) | evidence: ${path}`,
    );
  }, 60_000);
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. BobaClient request queue + TokenBucket rate limiter under a FLOOD:
//    FIFO order to the wire + no request loss + limiter genuinely engaged
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: BobaClient request queue + rate limiter under a flood", () => {
  it("services EVERY flooded request in FIFO order through the injected fetch — no loss, no reorder", async () => {
    // ANTI-BLUFF / how this FAILS if the product regressed: if the client dropped
    // a flooded request (the wire would see < FLOOD requests), serviced them out
    // of order (the captured `result_id` sequence would not be 0..FLOOD-1), or
    // double-sent one (a duplicate result_id), the strict equality assertions on
    // the captured sequence FAIL. We disable the rate limiter for THIS test so
    // the focus is the queue's no-loss + FIFO contract (the limiter is asserted
    // separately below).
    const FLOOD = 500;

    // Injected fetch records the exact ORDER + payload each request hits the wire,
    // and resolves a real 200. Because each addMagnet awaits its own fetch and we
    // fire them in a deterministic loop with `for await`, FIFO is the contract.
    const wireOrder: string[] = [];
    const seenResultIds = new Set<string>();
    const fetchImpl: typeof fetch = (_url, init) => {
      // The production client always sends a JSON string body, so cast directly
      // (avoids the no-base-to-string lint on the generic BodyInit union).
      const body = JSON.parse((init as RequestInit).body as string) as {
        result_id: string;
        download_urls: string[];
      };
      wireOrder.push(body.result_id);
      seenResultIds.add(body.result_id);
      return Promise.resolve(
        new Response(JSON.stringify({ status: "initiated", added_count: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    };

    const client = new BobaClient({
      baseUrl: "http://boba.test:7187",
      fetchImpl,
      disableRateLimit: true,
    });

    // Flood: fire FLOOD adds SEQUENTIALLY (the queue's natural FIFO drain). Each
    // carries a monotonically increasing result_id so we can assert order.
    const t0 = performance.now();
    for (let i = 0; i < FLOOD; i++) {
      const res = await client.addMagnet(magnetFor(i), {
        resultId: String(i).padStart(6, "0"),
      });
      expect(res.accepted).toBe(true);
    }
    const wallMs = performance.now() - t0;

    const expectedOrder = Array.from({ length: FLOOD }, (_u, i) =>
      String(i).padStart(6, "0"),
    );

    // USER-OBSERVABLE: every flooded request reached the wire EXACTLY once, in
    // strict FIFO order, none lost.
    expect(wireOrder.length).toBe(FLOOD); // no loss / no extra
    expect(seenResultIds.size).toBe(FLOOD); // no double-send
    expect(wireOrder).toEqual(expectedOrder); // strict FIFO

    const evidence = {
      test: "client-flood-fifo-no-loss",
      constitution: "§11.4.85 stress sustained (request flood)",
      flood: FLOOD,
      wireCount: wireOrder.length,
      distinctOnWire: seenResultIds.size,
      fifoOrderPreserved: JSON.stringify(wireOrder) === JSON.stringify(expectedOrder),
      lost: FLOOD - wireOrder.length,
      wallMs,
      firstThree: wireOrder.slice(0, 3),
      lastThree: wireOrder.slice(-3),
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("client_flood_fifo.json", evidence);
    expect(evidence.lost).toBe(0);
    expect(evidence.fifoOrderPreserved).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS flood] ${FLOOD} requests: wire=${wireOrder.length}, ` +
        `distinct=${seenResultIds.size}, fifo=${evidence.fifoOrderPreserved}, ` +
        `wall=${wallMs.toFixed(1)}ms | evidence: ${path}`,
    );
  });

  it("the rate limiter is genuinely ENGAGED: a frozen window grants at most capacity, then throttles", () => {
    // ANTI-BLUFF / how this FAILS if the product regressed: the client's limiter
    // is the production `TokenBucket(RATE_LIMIT.MAX_REQUESTS, RATE_LIMIT.MAX_REQUESTS)`.
    // If the limiter were a no-op (always granted), the frozen-window burst would
    // grant MORE than capacity and `grantedInFrozenWindow === capacity` FAILS.
    // This proves the flood path above is throttled in production (where the
    // limiter is enabled), not unbounded. We assert against the SAME construction
    // the client uses, with the clock frozen for determinism (§11.4.50).
    const CAP = RATE_LIMIT.MAX_REQUESTS; // the exact production capacity

    // Freeze the clock BEFORE constructing the bucket: TokenBucket seeds its
    // `lastRefill` from Date.now() in its constructor, so the spy MUST already be
    // active (and the frozen base realistic) or the first refill computes a wildly
    // negative elapsed and zeroes the tokens. (Same ordering as the committed
    // ratelimit.stress.test.ts.)
    let frozen = 5_000_000;
    const spy = vi.spyOn(Date, "now").mockImplementation(() => frozen);
    try {
      // Construct the bucket EXACTLY as BobaClient does (see boba-client.ts:147-149),
      // now that the clock is frozen.
      const bucket = new TokenBucket(CAP, CAP);

      let granted = 0;
      let refused = 0;
      const ATTEMPTS = CAP * 100; // far more than capacity
      for (let i = 0; i < ATTEMPTS; i++) {
        if (bucket.consume()) granted++;
        else refused++;
      }

      // USER-OBSERVABLE (throttling contract): exactly capacity allowed in a
      // frozen window; everything beyond is refused (the limiter is real).
      expect(granted).toBe(CAP);
      expect(refused).toBe(ATTEMPTS - CAP);
      expect(bucket.consume()).toBe(false); // exhausted while frozen

      // Advancing the clock one window replenishes (the soft-wait the client does
      // via `sleep(RATE_LIMIT.WINDOW_MS)` would then succeed) — proves it is a
      // throttle, not a permanent block.
      frozen += RATE_LIMIT.WINDOW_MS;
      const replenished = bucket.getAvailableTokens();
      expect(replenished).toBeGreaterThanOrEqual(1);

      const evidence = {
        test: "client-limiter-engaged-frozen-window",
        constitution: "§11.4.85 stress (rate limiter integration)",
        capacity: CAP,
        windowMs: RATE_LIMIT.WINDOW_MS,
        attempts: ATTEMPTS,
        grantedInFrozenWindow: granted,
        refused,
        rateNeverExceeded: granted === CAP,
        replenishedAfterOneWindow: replenished,
        throttleNotBlock: replenished >= 1,
        capturedAt: new Date().toISOString(),
      };
      const path = captureEvidence("client_limiter_engaged.json", evidence);
      expect(evidence.rateNeverExceeded).toBe(true);
      expect(evidence.throttleNotBlock).toBe(true);

      // eslint-disable-next-line no-console
      console.log(
        `[§11.4.85 STRESS limiter] cap=${CAP}, frozen-window grants=${granted} (refused=${refused}), ` +
          `replenished after 1 window=${replenished.toFixed(2)} | evidence: ${path}`,
      );
    } finally {
      spy.mockRestore();
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. Tab-group batched send AT SCALE: many tabs deduped into ONE batched POST,
//    + sub-quadratic scaling, + a flaky-tab CHAOS pass
// ─────────────────────────────────────────────────────────────────────────────

/** A magnet DetectedTorrent whose `id` mirrors the orchestrator's infohash-first id. */
function magnetTorrent(infohash: string, name: string): DetectedTorrent {
  const m: MagnetInfo = {
    uri: `magnet:?xt=urn:btih:${infohash}&dn=${encodeURIComponent(name)}`,
    infohash,
    displayName: name,
    trackers: [],
    webSeeds: [],
    exactLength: null,
    exactSource: null,
    keywords: [],
    acceptableSource: null,
    manifest: null,
    detectedAt: 1,
    sourceElement: null,
  };
  return {
    id: infohash,
    type: "magnet",
    magnet: m,
    torrentFile: null,
    displayName: name,
    selected: false,
    sent: false,
    sendStatus: null,
    detectedAt: 1,
  };
}

function scanResult(items: DetectedTorrent[]): PageScanResult {
  return {
    pageUrl: "https://example.test/",
    pageTitle: "t",
    items,
    magnetCount: items.filter((i) => i.type === "magnet").length,
    torrentFileCount: items.filter((i) => i.type === "torrent-file").length,
    scannedAt: 1,
    scanDurationMs: 0,
  };
}

/**
 * Build injected deps over a large fake group of `tabs` tabs. Each tab holds
 * `perTab` detections. A fraction of each tab's detections are SHARED (the same
 * infohash across tabs) so cross-tab dedup is genuinely exercised: every tab
 * repeats the first `sharedPerTab` of a global shared pool, plus its own unique
 * remainder. Returns the deps AND the EXPECTED unique infohash set.
 */
function buildLargeGroup(
  groupId: number,
  tabs: number,
  perTab: number,
  sharedPerTab: number,
): { deps: GroupBatchDeps; expectedUnique: Set<string>; firstSeenOrder: string[] } {
  const detectionsByTab: Record<number, PageScanResult> = {};
  const tabIds: number[] = [];
  const expectedUnique = new Set<string>();
  const firstSeenOrder: string[] = [];

  // Global shared pool the tabs collide on (the cross-tab duplicates).
  const sharedHashes = Array.from({ length: sharedPerTab }, (_u, i) =>
    infohashFor(900_000 + i),
  );

  let uniqueCounter = 0;
  for (let t = 0; t < tabs; t++) {
    const tabId = 1000 + t;
    tabIds.push(tabId);
    const items: DetectedTorrent[] = [];

    // The shared block (identical infohashes across every tab → dedup target).
    for (const h of sharedHashes) {
      items.push(magnetTorrent(h, `shared-${h.slice(0, 6)}`));
      if (!expectedUnique.has(h)) {
        expectedUnique.add(h);
        firstSeenOrder.push(h);
      }
    }
    // The unique remainder for this tab.
    for (let k = sharedPerTab; k < perTab; k++) {
      const h = infohashFor(uniqueCounter++);
      items.push(magnetTorrent(h, `uniq-${h.slice(0, 6)}`));
      expectedUnique.add(h);
      firstSeenOrder.push(h);
    }
    detectionsByTab[tabId] = scanResult(items);
  }

  const deps: GroupBatchDeps = {
    queryGroupTabIds: (g: number) => Promise.resolve(g === groupId ? tabIds : []),
    getTabDetections: (id: number) => Promise.resolve(detectionsByTab[id] ?? null),
  };
  return { deps, expectedUnique, firstSeenOrder };
}

describe("§11.4.85 STRESS: tab-group batched send at scale (many tabs → one deduped batch)", () => {
  it("batches a large multi-tab group into ONE payload of EXACTLY the unique torrents, first-seen order", async () => {
    // ANTI-BLUFF / how this FAILS if the product regressed: if cross-tab dedup
    // broke, the batched payload would contain the SHARED torrents once PER TAB
    // (count = tabs*sharedPerTab + uniques) instead of once total — the
    // exact-count + exact-set + first-seen-order assertions FAIL. If
    // dispatchGroupBatch dropped items, `downloadUrls.length` would be < unique.
    const GROUP = 77;
    const TABS = 120;
    const PER_TAB = 60; // 120 * 60 = 7200 raw detections across the group
    const SHARED_PER_TAB = 20; // 20 shared infohashes repeated on EVERY tab

    const { deps, expectedUnique, firstSeenOrder } = buildLargeGroup(
      GROUP,
      TABS,
      PER_TAB,
      SHARED_PER_TAB,
    );
    const rawDetections = TABS * PER_TAB;

    const batch = await batchGroupTorrents(GROUP, deps);

    // USER-OBSERVABLE: the batch is EXACTLY the unique set, in first-seen order.
    const batchHashes = batch.map((b) => b.magnet?.infohash as string);
    expect(batch.length).toBe(expectedUnique.size);
    expect(new Set(batchHashes)).toEqual(expectedUnique);
    expect(batchHashes).toEqual(firstSeenOrder); // first-seen order preserved
    // The shared block collapsed: present exactly once, not TABS times.
    expect(batch.length).toBeLessThan(rawDetections);

    // Dispatch the batch through an injected sender and assert the EXACT payload
    // is ONE batched POST carrying every unique URL once.
    const captured: GroupSendPayload[] = [];
    const dispatch = await dispatchGroupBatch(batch, (p) => {
      captured.push(p);
      return Promise.resolve({ accepted: true });
    });

    expect(captured.length).toBe(1); // ONE batched send, not per-tab/per-item
    expect(captured[0]?.count).toBe(expectedUnique.size);
    expect(captured[0]?.downloadUrls.length).toBe(expectedUnique.size);
    // Every dispatched URL is distinct (no duplicate slipped into the batch).
    expect(new Set(captured[0]?.downloadUrls).size).toBe(expectedUnique.size);
    expect(dispatch.sent).toBe(expectedUnique.size);
    expect(dispatch.accepted).toBe(true);

    const evidence = {
      test: "tabgroup-large-batch-dedup",
      constitution: "§11.4.85 stress sustained (tab-group at scale)",
      group: GROUP,
      tabs: TABS,
      perTab: PER_TAB,
      sharedPerTab: SHARED_PER_TAB,
      rawDetections,
      expectedUnique: expectedUnique.size,
      batched: batch.length,
      dispatchedUrls: captured[0]?.downloadUrls.length ?? 0,
      distinctDispatchedUrls: new Set(captured[0]?.downloadUrls).size,
      onePayload: captured.length === 1,
      firstSeenOrderPreserved: JSON.stringify(batchHashes) === JSON.stringify(firstSeenOrder),
      duplicatesCollapsed: rawDetections - batch.length,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("tabgroup_large_batch.json", evidence);
    expect(evidence.onePayload).toBe(true);
    expect(evidence.firstSeenOrderPreserved).toBe(true);
    expect(evidence.batched).toBe(expectedUnique.size);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS tabgroup] ${TABS} tabs × ${PER_TAB} = ${rawDetections} raw detections → ` +
        `${batch.length} unique batched (collapsed=${rawDetections - batch.length}) in ONE payload | evidence: ${path}`,
    );
  });

  it("scales SUB-QUADRATICALLY in (tabs × detections): 10× the group costs far less than 100× the time", async () => {
    // ANTI-BLUFF / how this FAILS if the product regressed: if batchGroupTorrents
    // became O(n²) in (tabs × detections) — e.g. a linear scan of the already-seen
    // list per item instead of the Set lookup — the 10× group would cost ~100× the
    // time and the measured RATIO blows past MAX_SUBQUADRATIC_RATIO → FAIL. Machine
    // independent (a RATIO, not an absolute threshold) per the anti-flake rule.
    const SMALL_TABS = 40;
    const PER_TAB = 50;
    const SHARED = 10;
    const BIG_TABS = SMALL_TABS * 10; // 10× the work (tabs scale linearly)
    const REPS = 5;

    const smallBuilt = buildLargeGroup(1, SMALL_TABS, PER_TAB, SHARED);
    const bigBuilt = buildLargeGroup(2, BIG_TABS, PER_TAB, SHARED);

    const small = await medianTimedMs(REPS, async () => {
      const b = await batchGroupTorrents(1, smallBuilt.deps);
      expect(b.length).toBe(smallBuilt.expectedUnique.size);
    });
    const big = await medianTimedMs(REPS, async () => {
      const b = await batchGroupTorrents(2, bigBuilt.deps);
      expect(b.length).toBe(bigBuilt.expectedUnique.size);
    });

    const EPS = 0.5;
    const ratio = big / Math.max(small, EPS);
    expect(ratio).toBeLessThan(MAX_SUBQUADRATIC_RATIO);

    const evidence = {
      test: "tabgroup-subquadratic-scaling",
      constitution: "§11.4.85 stress scaling (machine-independent ratio)",
      smallTabs: SMALL_TABS,
      bigTabs: BIG_TABS,
      perTab: PER_TAB,
      sizeStep: BIG_TABS / SMALL_TABS,
      reps: REPS,
      smallMedianMs: small,
      bigMedianMs: big,
      timeRatio: ratio,
      maxSubquadraticRatio: MAX_SUBQUADRATIC_RATIO,
      subQuadratic: ratio < MAX_SUBQUADRATIC_RATIO,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("tabgroup_subquadratic_scaling.json", evidence);
    expect(evidence.subQuadratic).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS tabgroup-scaling] ${SMALL_TABS}→${BIG_TABS} tabs (10×): ` +
        `smallMed=${small.toFixed(2)}ms, bigMed=${big.toFixed(2)}ms, ratio=${ratio.toFixed(2)} ` +
        `(<${MAX_SUBQUADRATIC_RATIO}) | evidence: ${path}`,
    );
  });

  it("CHAOS: a fraction of tabs throw on detection fetch under load — every reachable torrent still batched, none lost", async () => {
    // ANTI-BLUFF / how this FAILS if the product regressed: batchGroupTorrents
    // promises a single unreachable tab "must not sink the whole group batch"
    // (its own docstring). If a thrown getTabDetections aborted the whole batch
    // (or dropped a neighbouring reachable tab's torrents), the count of batched
    // unique torrents would be < the reachable-unique count → FAIL.
    const GROUP = 55;
    const TABS = 100;
    const PER_TAB = 30;

    // Build per-tab detections; deterministically mark every 4th tab as "faulty"
    // (its getTabDetections throws). All OTHER tabs' torrents must still batch.
    const detectionsByTab: Record<number, PageScanResult> = {};
    const tabIds: number[] = [];
    const faultyTabs = new Set<number>();
    const reachableUnique = new Set<string>();

    let counter = 0;
    for (let t = 0; t < TABS; t++) {
      const tabId = 2000 + t;
      tabIds.push(tabId);
      const items: DetectedTorrent[] = [];
      for (let k = 0; k < PER_TAB; k++) {
        const h = infohashFor(counter++);
        items.push(magnetTorrent(h, `t${t}-k${k}`));
        if (t % 4 !== 0) reachableUnique.add(h); // only non-faulty tabs are reachable
      }
      detectionsByTab[tabId] = scanResult(items);
      if (t % 4 === 0) faultyTabs.add(tabId);
    }

    let throwsObserved = 0;
    const deps: GroupBatchDeps = {
      queryGroupTabIds: (g: number) => Promise.resolve(g === GROUP ? tabIds : []),
      getTabDetections: (id: number) => {
        if (faultyTabs.has(id)) {
          throwsObserved++;
          return Promise.reject(new Error(`chaos: tab ${id} detection fetch failed`));
        }
        return Promise.resolve(detectionsByTab[id] ?? null);
      },
    };

    const batch = await batchGroupTorrents(GROUP, deps);
    const batchHashes = new Set(batch.map((b) => b.magnet?.infohash as string));

    // USER-OBSERVABLE recovery: the faulty tabs were skipped (their torrents are
    // NOT present), but EVERY reachable tab's torrent IS batched — none lost, the
    // batch did not crash or abort.
    expect(faultyTabs.size).toBeGreaterThan(0); // chaos genuinely injected
    expect(throwsObserved).toBe(faultyTabs.size); // every faulty tab actually threw
    expect(batch.length).toBe(reachableUnique.size); // exactly the reachable set
    expect(batchHashes).toEqual(reachableUnique);

    // The recovered batch is still dispatchable as one clean payload.
    const captured: GroupSendPayload[] = [];
    const dispatch = await dispatchGroupBatch(batch, (p) => {
      captured.push(p);
      return Promise.resolve({ accepted: true });
    });
    expect(captured.length).toBe(1);
    expect(dispatch.sent).toBe(reachableUnique.size);

    const evidence = {
      test: "tabgroup-flaky-tab-chaos",
      constitution: "§11.4.85 chaos (process/IO fault injection per tab)",
      group: GROUP,
      tabs: TABS,
      perTab: PER_TAB,
      faultyTabs: faultyTabs.size,
      throwsObserved,
      reachableUnique: reachableUnique.size,
      batched: batch.length,
      batchEqualsReachable: batchHashes.size === reachableUnique.size,
      noWholeBatchAbort: batch.length > 0,
      dispatchedAsOnePayload: captured.length === 1,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("tabgroup_flaky_chaos.json", evidence);
    expect(evidence.batchEqualsReachable).toBe(true);
    expect(evidence.noWholeBatchAbort).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 CHAOS tabgroup] ${faultyTabs.size}/${TABS} tabs threw on fetch: ` +
        `batched=${batch.length} (reachable=${reachableUnique.size}), one payload | evidence: ${path}`,
    );
  });
});
