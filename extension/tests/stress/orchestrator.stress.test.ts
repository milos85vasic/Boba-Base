/**
 * @fileoverview STRESS tests (§11.4.85) for the REAL committed
 * {@link ScannerOrchestrator} (`src/scanner/orchestrator.ts`) and its real scan
 * path (the committed {@link LinkScanner} + {@link TextScanner} over a real jsdom
 * DOM).
 *
 * Constitution §11.4.85 (stress + chaos test mandate) + the §11.4 anti-bluff
 * covenant. These drive the PRODUCTION orchestrator — no mock of the unit under
 * test, no stubbed scanner. A genuine jsdom page is populated with a LARGE
 * number of anchors (magnets + .torrent files + junk + duplicates), the real
 * `scanNow()` runs every registered scanner, aggregates, and DEDUPS by the
 * scanner-supplied STABLE id (`base.ts:computeStableId`, infohash-first). Every
 * assertion is on a USER-OBSERVABLE outcome: the EXACT deduped torrent count
 * (every unique infohash / .torrent URL exactly once), the magnet/torrent-file
 * split, and a sane wall-clock budget — never "no error".
 *
 * §11.4.85 STRESS closed-set coverage:
 *   (a) sustained load — a page with ≥5000 anchors (mix of unique magnets,
 *                        unique .torrent files, junk hrefs, and heavy
 *                        duplicates) → real orchestrator → assert EXACT deduped
 *                        count, completes within a wall-clock budget, no crash,
 *                        bounded memory (heap delta captured + asserted finite).
 *   (b) concurrent     — overlapping scanNow() invocations (the orchestrator's
 *                        `isScanning` guard) — no crash, no deadlock, the
 *                        detected set is never corrupted (count stays exact).
 *   (c) boundary       — empty page (0 detected), single link (1 detected),
 *                        all-duplicate page (1 detected from N identical magnets).
 *
 * EVIDENCE (§11.4.85 MANDATORY): each test writes a captured-evidence JSON
 * artifact under `tests/stress/.evidence/` containing counts + timings and
 * ASSERTS on that captured data (e.g. dedup count EXACT). A PASS with no
 * captured artifact is a §11.4 bluff.
 *
 * DETERMINISM (§11.4.50): the assertions are on EXACT counts and on wall-clock
 * BOUNDS (never equality), so the verdict is reproducible across runs/machines.
 *
 * FAILURE MODES CAUGHT: if cross-scanner / cross-anchor dedup broke (duplicate
 * infohashes counted more than once), the EXACT-count assertion FAILS. If the
 * orchestrator crashed under load, hung (no result), or grew memory without
 * bound, the corresponding assertion FAILS.
 *
 * @module tests/stress/orchestrator.stress.test
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { ScannerOrchestrator } from "../../src/scanner/orchestrator";

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
 * Build a deterministic 40-char hex infohash from a numeric index.
 * (The MAGNET_VALIDATION_REGEX requires exactly 40 hex chars after `btih:`.)
 */
function infohashFor(n: number): string {
  // 8-hex-digit index, repeated to fill 40 chars deterministically.
  const eight = (n >>> 0).toString(16).padStart(8, "0");
  return (eight + eight + eight + eight + eight).slice(0, 40);
}

/** A valid magnet URI for index `n`. */
function magnetFor(n: number): string {
  return `magnet:?xt=urn:btih:${infohashFor(n)}&dn=Torrent+${n}`;
}

/** A valid .torrent file URL for index `n`. */
function torrentFileFor(n: number): string {
  return `https://tracker.example.test/dl/${n}/file-${n}.torrent`;
}

/** Reset the jsdom document body to empty before each test. */
beforeEach(() => {
  document.body.innerHTML = "";
});

afterEach(() => {
  document.body.innerHTML = "";
});

// ─────────────────────────────────────────────────────────────────────────────
// (a) STRESS — sustained load: large page, EXACT deduped count, wall budget
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: ScannerOrchestrator sustained load (large page, exact dedup, wall budget)", () => {
  it("scans a 6000-anchor page (magnets + .torrents + junk + duplicates) — EXACT deduped count, bounded time + memory", async () => {
    // Composition of the page (chosen so the EXPECTED deduped count is exact):
    //   UNIQUE_MAGNETS distinct magnet infohashes, each repeated DUP_FACTOR times
    //   UNIQUE_FILES   distinct .torrent file URLs (no repeats)
    //   JUNK           non-torrent anchors (mailto/#/plain pages) — must be ignored
    const UNIQUE_MAGNETS = 1500;
    const DUP_FACTOR = 3; // each magnet appears 3× → dedup must collapse to 1
    const UNIQUE_FILES = 800;
    const JUNK = 700;

    const totalAnchors = UNIQUE_MAGNETS * DUP_FACTOR + UNIQUE_FILES + JUNK;

    // Build the DOM in one innerHTML write (fast; avoids per-node reflow cost).
    const parts: string[] = [];
    for (let i = 0; i < UNIQUE_MAGNETS; i++) {
      const m = magnetFor(i);
      for (let d = 0; d < DUP_FACTOR; d++) {
        parts.push(`<a href="${m}">magnet ${i} copy ${d}</a>`);
      }
    }
    for (let i = 0; i < UNIQUE_FILES; i++) {
      parts.push(`<a href="${torrentFileFor(i)}">file ${i}</a>`);
    }
    for (let i = 0; i < JUNK; i++) {
      // Junk hrefs: not magnet:, not .torrent — must NOT be detected.
      parts.push(`<a href="https://example.test/page/${i}">junk ${i}</a>`);
      parts.push(`<a href="#anchor-${i}">frag ${i}</a>`);
    }
    document.body.innerHTML = parts.join("");

    // EXPECTED deduped detected count:
    //   each unique magnet infohash → 1 (the DUP_FACTOR copies collapse)
    //   each unique .torrent URL    → 1
    //   junk                        → 0
    const expectedDetected = UNIQUE_MAGNETS + UNIQUE_FILES;

    // Disable the mutation observer — this test is about a single big scan, and
    // observeMutations would attach a live observer we don't need.
    const orch = new ScannerOrchestrator(undefined, {
      observeMutations: false,
      // includeHidden defaults are fine; jsdom getComputedStyle treats fresh
      // anchors as visible, so the hidden filter does not drop our links.
    });

    const heapBefore =
      typeof process !== "undefined" ? process.memoryUsage().heapUsed : 0;
    const t0 = performance.now();
    const result = await orch.scanNow();
    const wallMs = performance.now() - t0;
    const heapAfter =
      typeof process !== "undefined" ? process.memoryUsage().heapUsed : 0;
    const heapDeltaBytes = heapAfter - heapBefore;

    // USER-OBSERVABLE: the deduped detected set is EXACTLY the unique torrents.
    const detected = orch.getDetectedTorrents();
    const magnets = detected.filter((d) => d.type === "magnet");
    const files = detected.filter((d) => d.type === "torrent-file");

    expect(orch.getDetectedCount()).toBe(expectedDetected);
    expect(detected.length).toBe(expectedDetected);
    expect(magnets.length).toBe(UNIQUE_MAGNETS);
    expect(files.length).toBe(UNIQUE_FILES);

    // The PageScanResult snapshot agrees with the deduped set.
    expect(result.magnetCount).toBe(UNIQUE_MAGNETS);
    expect(result.torrentFileCount).toBe(UNIQUE_FILES);
    expect(result.items.length).toBe(expectedDetected);

    // Dedup is structural: every detected id is distinct (no duplicate survived).
    const ids = new Set(detected.map((d) => d.id));
    expect(ids.size).toBe(expectedDetected);

    // Junk was ignored: no detected item carries a non-torrent identity.
    const badType = detected.some(
      (d) => d.type !== "magnet" && d.type !== "torrent-file",
    );
    expect(badType).toBe(false);

    // Sane wall-clock budget (BOUND, not equality — §11.4.50 determinism). A
    // 6000-anchor scan that took >30s would indicate pathological blow-up.
    const WALL_BUDGET_MS = 30_000;
    expect(wallMs).toBeLessThan(WALL_BUDGET_MS);

    // Bounded memory: the heap delta must be a finite number (not NaN/∞) and
    // not absurd (< 512 MiB for a 6000-anchor scan). This catches an unbounded
    // accumulation regression.
    const MEMORY_BUDGET_BYTES = 512 * 1024 * 1024;
    expect(Number.isFinite(heapDeltaBytes)).toBe(true);
    expect(heapDeltaBytes).toBeLessThan(MEMORY_BUDGET_BYTES);

    const evidence = {
      test: "sustained-load-6000-anchors",
      constitution: "§11.4.85 stress sustained",
      page: {
        totalAnchors,
        uniqueMagnets: UNIQUE_MAGNETS,
        dupFactor: DUP_FACTOR,
        magnetAnchors: UNIQUE_MAGNETS * DUP_FACTOR,
        uniqueFiles: UNIQUE_FILES,
        junkAnchors: JUNK * 2,
      },
      expectedDetected,
      actualDetected: detected.length,
      magnetCount: magnets.length,
      torrentFileCount: files.length,
      distinctIds: ids.size,
      dedupCorrect: detected.length === expectedDetected && ids.size === expectedDetected,
      junkIgnored: !badType,
      wallMs,
      wallBudgetMs: WALL_BUDGET_MS,
      withinWallBudget: wallMs < WALL_BUDGET_MS,
      heapDeltaBytes,
      memoryBudgetBytes: MEMORY_BUDGET_BYTES,
      withinMemoryBudget: heapDeltaBytes < MEMORY_BUDGET_BYTES,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("orchestrator_sustained_load.json", evidence);

    // Assert on the CAPTURED artifact's claims (the artifact IS the proof).
    expect(evidence.dedupCorrect).toBe(true);
    expect(evidence.junkIgnored).toBe(true);
    expect(evidence.withinWallBudget).toBe(true);
    expect(evidence.withinMemoryBudget).toBe(true);
    expect(evidence.actualDetected).toBe(expectedDetected);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS sustained] ${totalAnchors} anchors → ${detected.length} deduped ` +
        `(${magnets.length} magnets + ${files.length} files), expected ${expectedDetected}, ` +
        `wall=${wallMs.toFixed(1)}ms, heapΔ=${(heapDeltaBytes / 1024 / 1024).toFixed(1)}MiB | evidence: ${path}`,
    );
  });

  it("dedups a magnet that appears BOTH as an <a href> AND as bare page text — counted ONCE across scanners", async () => {
    // Cross-scanner dedup: the LinkScanner sees the magnet in the <a href>; the
    // TextScanner sees the SAME magnet infohash in a separate text node. Because
    // both derive the same STABLE id, the orchestrator must collapse them to 1.
    const N = 400;
    const parts: string[] = [];
    for (let i = 0; i < N; i++) {
      const m = magnetFor(i);
      // (1) as an anchor href (LinkScanner)
      parts.push(`<a href="${m}">link ${i}</a>`);
      // (2) the SAME magnet as bare text in a <p> (TextScanner). The text node
      //     must be ≥20 chars (TextScanner skips very short nodes) — the magnet
      //     URI is well over 20 chars, so it is accepted.
      parts.push(`<p>Paste: ${m} — enjoy your torrent number ${i}</p>`);
    }
    document.body.innerHTML = parts.join("");

    const orch = new ScannerOrchestrator(undefined, { observeMutations: false });
    await orch.scanNow();

    const detected = orch.getDetectedTorrents();
    const ids = new Set(detected.map((d) => d.id));

    // EXACTLY N distinct magnets — NOT 2N. If cross-scanner dedup broke, this
    // would be 2N and the assertion FAILS.
    expect(detected.length).toBe(N);
    expect(ids.size).toBe(N);
    expect(detected.every((d) => d.type === "magnet")).toBe(true);

    const evidence = {
      test: "cross-scanner-dedup",
      constitution: "§11.4.85 stress sustained",
      uniqueMagnets: N,
      anchorOccurrences: N,
      textOccurrences: N,
      totalOccurrences: 2 * N,
      detected: detected.length,
      distinctIds: ids.size,
      dedupedToUnique: detected.length === N && ids.size === N,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("orchestrator_cross_scanner_dedup.json", evidence);

    expect(evidence.dedupedToUnique).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS sustained] ${2 * N} occurrences (link+text) of ${N} unique magnets → ` +
        `${detected.length} deduped | evidence: ${path}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (b) STRESS — concurrent contention: overlapping scanNow(), no corruption
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: ScannerOrchestrator concurrent scans (no deadlock, set never corrupted)", () => {
  it("fires 10 overlapping scanNow() calls — all resolve, no deadlock, deduped count stays EXACT", async () => {
    const UNIQUE = 1000;
    const parts: string[] = [];
    for (let i = 0; i < UNIQUE; i++) {
      parts.push(`<a href="${magnetFor(i)}">m ${i}</a>`);
    }
    document.body.innerHTML = parts.join("");

    const orch = new ScannerOrchestrator(undefined, { observeMutations: false });

    // Fire 10 scans concurrently. The orchestrator's `isScanning` guard means
    // overlapping scans either run or short-circuit, but the detected set must
    // NEVER be corrupted (no infohash counted twice, none lost).
    const CONCURRENCY = 10;
    const t0 = performance.now();
    const results = await Promise.all(
      Array.from({ length: CONCURRENCY }, () => orch.scanNow()),
    );
    const wallMs = performance.now() - t0;

    // No deadlock: Promise.all resolved (the test would hang/time out otherwise).
    expect(results.length).toBe(CONCURRENCY);

    // The detected set converges to EXACTLY the unique magnets — concurrent
    // scans did not double-insert or lose any.
    const detected = orch.getDetectedTorrents();
    const ids = new Set(detected.map((d) => d.id));
    expect(orch.getDetectedCount()).toBe(UNIQUE);
    expect(detected.length).toBe(UNIQUE);
    expect(ids.size).toBe(UNIQUE);

    // The orchestrator returned to a quiescent (not-scanning) state.
    expect(orch.isCurrentlyScanning()).toBe(false);

    const evidence = {
      test: "concurrent-scans-10",
      constitution: "§11.4.85 stress concurrent",
      concurrency: CONCURRENCY,
      uniqueMagnets: UNIQUE,
      resolvedScans: results.length,
      finalDetected: detected.length,
      distinctIds: ids.size,
      setExact: detected.length === UNIQUE && ids.size === UNIQUE,
      deadlock: false, // Promise.all resolved
      quiescentAfter: !orch.isCurrentlyScanning(),
      wallMs,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("orchestrator_concurrent.json", evidence);

    expect(evidence.setExact).toBe(true);
    expect(evidence.quiescentAfter).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS concurrent] ${CONCURRENCY} overlapping scans of ${UNIQUE} unique magnets → ` +
        `final=${detected.length}, distinct=${ids.size}, deadlock=false, ` +
        `wall=${wallMs.toFixed(1)}ms | evidence: ${path}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (c) STRESS — boundary: empty page / single link / all-duplicate page
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: ScannerOrchestrator boundaries (empty / single / all-duplicate)", () => {
  it("handles empty page (0), single link (1), and an all-duplicate page (1 from N copies)", async () => {
    const perCase: Record<string, unknown> = {};

    // --- empty page: nothing detected, no crash ---
    {
      document.body.innerHTML = "";
      const orch = new ScannerOrchestrator(undefined, { observeMutations: false });
      const res = await orch.scanNow();
      expect(orch.getDetectedCount()).toBe(0);
      expect(orch.getDetectedTorrents().length).toBe(0);
      expect(res.magnetCount).toBe(0);
      expect(res.torrentFileCount).toBe(0);
      perCase["empty-page"] = { detected: orch.getDetectedCount() };
    }

    // --- single link: exactly one detected ---
    {
      document.body.innerHTML = `<a href="${magnetFor(7)}">only one</a>`;
      const orch = new ScannerOrchestrator(undefined, { observeMutations: false });
      await orch.scanNow();
      const detected = orch.getDetectedTorrents();
      expect(detected.length).toBe(1);
      expect(detected[0]?.type).toBe("magnet");
      perCase["single-link"] = { detected: detected.length };
    }

    // --- all-duplicate page: N identical magnets collapse to 1 ---
    {
      const N = 500;
      const m = magnetFor(99);
      const html = Array.from(
        { length: N },
        (_unused, i) => `<a href="${m}">dup ${i}</a>`,
      ).join("");
      document.body.innerHTML = html;
      const orch = new ScannerOrchestrator(undefined, { observeMutations: false });
      await orch.scanNow();
      const detected = orch.getDetectedTorrents();
      // All N identical → exactly 1 deduped. If dedup broke this would be N.
      expect(detected.length).toBe(1);
      perCase["all-duplicate"] = {
        copies: N,
        detected: detected.length,
        dedupedToOne: detected.length === 1,
      };
    }

    const evidence = {
      test: "boundaries",
      constitution: "§11.4.85 stress boundary",
      perCase,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("orchestrator_boundaries.json", evidence);

    // Assert on captured boundary facts.
    expect((perCase["empty-page"] as { detected: number }).detected).toBe(0);
    expect((perCase["single-link"] as { detected: number }).detected).toBe(1);
    expect((perCase["all-duplicate"] as { dedupedToOne: boolean }).dedupedToOne).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS boundary] empty/single/all-dup: ${JSON.stringify(perCase)} | evidence: ${path}`,
    );
  });
});
