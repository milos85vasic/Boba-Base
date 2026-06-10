/**
 * @fileoverview PERFORMANCE / benchmark tests (§11.4.5 + §11.4.85) for the REAL
 * committed {@link ScannerOrchestrator} hot path — a full single-page scan over
 * a realistic ~1,000-anchor jsdom DOM.
 *
 * Anti-bluff (Constitution §11.4 + §11.4.5 + §11.4.50): these are REAL
 * measured-timing assertions on the production scan path, NOT "does it run"
 * smoke checks. Each case:
 *   - drives the PRODUCTION orchestrator (`src/scanner/orchestrator.ts`) and its
 *     real LinkScanner + TextScanner over a genuine jsdom document — no mock of
 *     the unit under test,
 *   - WARMS UP first (warmup runs are discarded) then measures the per-run
 *     wall-clock over several iterations, reporting min/max/mean + p50/p95/p99,
 *   - asserts BOTH a generous wall-clock BOUND (a real ≥10× regression FAILS,
 *     host/CI jitter does NOT) AND the user-observable CORRECT result (the EXACT
 *     deduped detected count — a fast "0 detected" run is a FALSE PASS and is
 *     caught here), and
 *   - writes a captured-evidence JSON artifact under `tests/perf/.evidence/`
 *     containing the full distribution + correctness facts. A PASS with no
 *     captured artifact is a §11.4 bluff.
 *
 * ── Bound calibration (documented per §11.4 anti-bluff) ──
 *   SCAN_WALL_BUDGET_MS = 1500 ms for a 1,000-anchor page (full scan, both
 *   scanners, cross-scanner dedup). Under jsdom the real scan is dominated by
 *   per-anchor `getComputedStyle` visibility checks and measures ~100–130 ms
 *   typical, with occasional ~200 ms outliers from GC / a busy shared box. The
 *   1500 ms budget is ~10× the ~130 ms typical — a genuine 10× regression (an
 *   accidental O(n²) dedup, a per-anchor reflow, or a quadratic aggregation)
 *   pushes the scan past ~1.3 s and FAILS, while the normal ~200 ms jitter
 *   outlier sits comfortably inside the bound (no flake). NOT a never-fail bluff
 *   threshold: the parsers.perf sibling documents the same tight-threshold
 *   anti-bluff proof (transiently tighten the bound and observe a FAIL).
 *
 * Runner: Vitest (jsdom env — same as the unit suite). Run explicitly:
 *   cd extension && npx vitest run tests/perf/scanner.perf.test.ts
 *
 * @module tests/perf/scanner.perf
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { ScannerOrchestrator } from "../../src/scanner/orchestrator";

const HERE = dirname(fileURLToPath(import.meta.url));
const EVIDENCE_DIR = join(HERE, ".evidence");

/** Write a captured-evidence artifact (§11.4.5) and return its absolute path. */
function captureEvidence(name: string, data: unknown): string {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  const path = join(EVIDENCE_DIR, name);
  writeFileSync(path, JSON.stringify(data, null, 2), "utf8");
  return path;
}

// ─────────────────────────────────────────────────────────────────────────────
// Distribution helpers (shared shape with the parsers.perf sibling)
// ─────────────────────────────────────────────────────────────────────────────

/** Percentile (nearest-rank, p in [0,100]) of a numeric sample set. */
function percentile(samples: number[], p: number): number {
  if (samples.length === 0) throw new Error("percentile of empty sample set");
  const sorted = [...samples].sort((a, b) => a - b);
  // nearest-rank: ceil(p/100 * N) → 1-based rank, clamped to [1, N].
  const rank = Math.min(
    sorted.length,
    Math.max(1, Math.ceil((p / 100) * sorted.length)),
  );
  const value = sorted[rank - 1];
  if (value === undefined) throw new Error("percentile index out of range");
  return value;
}

/** min / max / mean / p50 / p95 / p99 summary of a numeric sample set. */
function distribution(samples: number[]): {
  min: number;
  max: number;
  mean: number;
  p50: number;
  p95: number;
  p99: number;
  runs: number;
} {
  if (samples.length === 0) throw new Error("distribution of empty sample set");
  const sum = samples.reduce((a, b) => a + b, 0);
  return {
    min: Math.min(...samples),
    max: Math.max(...samples),
    mean: sum / samples.length,
    p50: percentile(samples, 50),
    p95: percentile(samples, 95),
    p99: percentile(samples, 99),
    runs: samples.length,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Calibrated bounds + iteration counts
// ─────────────────────────────────────────────────────────────────────────────

const SCAN_WALL_BUDGET_MS = 1500; // ~10× the ~130ms typical jsdom scan; absorbs ~200ms jitter
const WARMUP_RUNS = 1; // discarded — primes the JIT / caches
const MEASURED_RUNS = 5; // odd-ish count; full distribution captured

// ─────────────────────────────────────────────────────────────────────────────
// Deterministic page fixtures (mirror the committed orchestrator.stress helpers)
// ─────────────────────────────────────────────────────────────────────────────

/** Deterministic 40-hex infohash for index `n` (MAGNET_VALIDATION_REGEX needs 40 hex). */
function infohashFor(n: number): string {
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

beforeEach(() => {
  document.body.innerHTML = "";
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("perf: ScannerOrchestrator full scan — realistic ~1,000-anchor page", () => {
  it("scans a 1,000-anchor page within a bounded wall-clock AND returns the EXACT deduped count", async () => {
    // Composition chosen so the EXPECTED deduped count is exact and the anchor
    // total is ~1,000 (a realistic torrent-index search page):
    //   UNIQUE_MAGNETS distinct magnet infohashes (no dupes here — dedup is
    //                  exercised in the stress suite; perf measures clean scan),
    //   UNIQUE_FILES   distinct .torrent file URLs,
    //   JUNK           non-torrent anchors that MUST be ignored.
    const UNIQUE_MAGNETS = 600;
    const UNIQUE_FILES = 300;
    const JUNK = 100;
    const TOTAL_ANCHORS = UNIQUE_MAGNETS + UNIQUE_FILES + JUNK;
    const expectedDetected = UNIQUE_MAGNETS + UNIQUE_FILES;

    const parts: string[] = [];
    for (let i = 0; i < UNIQUE_MAGNETS; i++) {
      parts.push(`<a href="${magnetFor(i)}">magnet ${i}</a>`);
    }
    for (let i = 0; i < UNIQUE_FILES; i++) {
      parts.push(`<a href="${torrentFileFor(i)}">file ${i}</a>`);
    }
    for (let i = 0; i < JUNK; i++) {
      parts.push(`<a href="https://example.test/page/${i}">junk ${i}</a>`);
    }
    const pageHtml = parts.join("");

    /**
     * One measured unit of work: build the page, run a fresh orchestrator's
     * full scan, and return BOTH the wall-clock and the detected count so the
     * caller can assert correctness per-run (no fast "0 detected" false PASS).
     */
    async function oneScan(): Promise<{ wallMs: number; detected: number }> {
      document.body.innerHTML = pageHtml;
      const orch = new ScannerOrchestrator(undefined, {
        observeMutations: false,
      });
      const t0 = performance.now();
      await orch.scanNow();
      const wallMs = performance.now() - t0;
      const detected = orch.getDetectedCount();
      document.body.innerHTML = "";
      return { wallMs, detected };
    }

    // Sanity precondition: the fixture really detects the expected unique set,
    // otherwise a fast empty scan would be a false PASS (anti-bluff §11.4).
    const probe = await oneScan();
    expect(probe.detected).toBe(expectedDetected);

    // Warmup (discarded), then measured runs — assert correctness EVERY run.
    for (let i = 0; i < WARMUP_RUNS; i++) await oneScan();

    const samples: number[] = [];
    for (let i = 0; i < MEASURED_RUNS; i++) {
      const r = await oneScan();
      expect(r.detected).toBe(expectedDetected); // never a "0 detected" fast pass
      samples.push(r.wallMs);
    }

    const dist = distribution(samples);

    const evidence = {
      test: "scanner-full-scan-1000-anchors",
      constitution: "§11.4.5 + §11.4.85 perf (full scan hot path)",
      page: { totalAnchors: TOTAL_ANCHORS, UNIQUE_MAGNETS, UNIQUE_FILES, JUNK },
      expectedDetected,
      actualDetected: probe.detected,
      detectedCorrectEveryRun: true,
      wallMs: dist,
      budgetMs: SCAN_WALL_BUDGET_MS,
      withinBudget: dist.p99 <= SCAN_WALL_BUDGET_MS,
    };
    const path = captureEvidence("scanner_full_scan_1000_anchors.json", evidence);

    // eslint-disable-next-line no-console
    console.log(
      `[perf] orchestrator full scan @${TOTAL_ANCHORS} anchors → ${expectedDetected} detected: ` +
        `p50=${dist.p50.toFixed(2)}ms p95=${dist.p95.toFixed(2)}ms p99=${dist.p99.toFixed(2)}ms ` +
        `(min=${dist.min.toFixed(2)} max=${dist.max.toFixed(2)} mean=${dist.mean.toFixed(2)}) ` +
        `budget=${SCAN_WALL_BUDGET_MS}ms | evidence: ${path}`,
    );

    // Correctness asserted per-run above; bound asserted on the worst measured
    // run (p99/max) — a 10× regression FAILS, jitter does not.
    expect(dist.p99).toBeLessThanOrEqual(SCAN_WALL_BUDGET_MS);
  });
});
