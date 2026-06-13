/**
 * @fileoverview PERFORMANCE / DoS-scaling tests (§11.4.5 + §11.4.85 + §11.4.107)
 * for the REAL committed {@link ScannerOrchestrator} under a junk-flood page —
 * the machine-INDEPENDENT, sub-quadratic *scaling* guard.
 *
 * WHY THIS EXISTS (forensic anchor, 2026-06-13). The security suite's
 * "orchestrator DoS resilience (junk-flood page)" test originally asserted a
 * TIGHT absolute wall-clock budget (`expect(elapsed).toBeLessThan(5000)`). On a
 * shared/oversubscribed host (load-avg 15) the production scan over 50k anchors
 * measured 6608 ms — a NON-product FAIL (the same scan passes <5000 ms in
 * isolation). An absolute wall-clock threshold inside a functional test is a
 * §11.4.1 FAIL-bluff / §11.4.50 flake. The security test now keeps only a
 * GENEROUS hang-ceiling (catches a true hang / quadratic explosion). The
 * RIGOROUS guard against an algorithmic (≈O(n²)) DoS regression lives HERE, as a
 * metamorphic *scaling* relation (§11.4.107(8)): the ratio of scan-time at 10·N
 * vs N anchors. A ratio is DIMENSIONLESS — it cancels the host's absolute speed
 * and load entirely, so it never flakes, yet it still FAILs a real quadratic
 * regression (linear → ratio ≈ 10; quadratic → ratio ≈ 100).
 *
 * Anti-bluff (Constitution §11.4 + §11.4.5 + §11.4.50 + §11.4.107(10)):
 *   - drives the PRODUCTION orchestrator (`src/scanner/orchestrator.ts`) + its
 *     real LinkScanner + TextScanner over a genuine jsdom junk-flood document —
 *     no mock of the unit under test,
 *   - measures at TWO sizes (N and 10·N junk anchors + 2 real magnets), taking
 *     the MIN over several reps at each size (min = the least-noisy estimator;
 *     host stalls only ADD time, so the minimum is closest to intrinsic cost),
 *   - asserts the user-observable CORRECT result EVERY run (EXACTLY the 2 real
 *     magnets — junk excluded — so a fast "0 detected" run is never a false PASS),
 *   - asserts the metamorphic sub-quadratic SCALING ratio AND a generous absolute
 *     hang-bound on the big scan,
 *   - SELF-VALIDATES the scaling oracle with a golden-good (linear) and a
 *     golden-bad (quadratic) synthetic workload (§11.4.107(10) / §1.1 paired
 *     mutation): the SAME threshold that guards the real scan provably ACCEPTS a
 *     linear workload and REJECTS a quadratic one — proving the guard is not a
 *     tautology, AND
 *   - writes a captured-evidence JSON artifact under `tests/perf/.evidence/`. A
 *     PASS with no captured artifact is a §11.4 bluff.
 *
 * ── Threshold calibration (documented per §11.4 anti-bluff / §11.4.6) ──
 *   SUBQUAD_RATIO_MAX = 30 at FACTOR = 10. A linear scan's time scales ≈ FACTOR
 *   (10) plus a small fixed-overhead component, so the real ratio sits well under
 *   ~15. A genuine quadratic (O(n²)) regression scales ≈ FACTOR² (100). 30 is
 *   3× the linear expectation (absorbs the fixed-overhead + measurement noise the
 *   min-estimator does not fully remove) and 0.3× the quadratic expectation —
 *   it ACCEPTS linear, REJECTS quadratic, and is proven to do exactly that by the
 *   golden-good/golden-bad self-validation below. NOT a never-fail bluff
 *   threshold.
 *
 * Runner: Vitest (jsdom env — same as the unit suite). Run explicitly:
 *   cd extension && npx vitest run tests/perf/orchestrator-scaling.perf.test.ts
 *
 * @module tests/perf/orchestrator-scaling.perf
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { ScannerOrchestrator } from "../../src/scanner/orchestrator";
import type { DetectedTorrent } from "../../src/types/torrent";

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
// Calibrated scaling parameters
// ─────────────────────────────────────────────────────────────────────────────

const BASE_N = 1_500; // anchors at the small size (large enough that t(N) is several ms)
const FACTOR = 10; // big size = FACTOR · BASE_N
const BIG_N = BASE_N * FACTOR; // 15,000 anchors
const REPS = 3; // min-of-REPS at each size (least-noisy estimator; min is one-sided)
const SUBQUAD_RATIO_MAX = 30; // linear ≈ FACTOR(10); quadratic ≈ FACTOR²(100); 30 separates them
const BIG_SCAN_HANG_BUDGET_MS = 20_000; // generous absolute hang-ceiling on the 15k-anchor scan
// This is a perf/stress test that intentionally runs many heavy multi-thousand-
// anchor scans; the default 5 s per-test vitest timeout is for unit tests, not a
// product budget. A generous explicit timeout lets the scans complete on a busy
// shared host without flaking (the real DoS guard is the dimensionless ratio
// asserted below, NOT this runner timeout).
const PERF_TEST_TIMEOUT_MS = 120_000;

// Two real magnets buried in the junk flood — the ONLY things that must be detected.
const REAL_A = "0123456789abcdef0123456789abcdef01234567";
const REAL_B = "fedcba9876543210fedcba9876543210fedcba98";

/** Build a junk-flood page: `n` non-torrent anchors + the 2 real magnets. */
function junkFloodHtml(n: number): string {
  const parts: string[] = [];
  for (let i = 0; i < n; i++) {
    parts.push(`<a href="https://junk.example/page${i}.html">j${i}</a>`);
  }
  parts.push(`<a href="magnet:?xt=urn:btih:${REAL_A}&dn=Alpha">A</a>`);
  parts.push(`<a href="magnet:?xt=urn:btih:${REAL_B}&dn=Beta">B</a>`);
  return parts.join("");
}

/**
 * One measured scan over an `n`-anchor junk flood: builds the page OUTSIDE the
 * timed region (so we time ONLY the scan), runs a fresh orchestrator's scanNow,
 * and returns BOTH the wall-clock and the detected magnet count.
 */
async function scanOnce(n: number): Promise<{ wallMs: number; magnets: number }> {
  document.body.innerHTML = junkFloodHtml(n);
  const orch = new ScannerOrchestrator(undefined, { observeMutations: false });
  const t0 = performance.now();
  const result = await orch.scanNow();
  const wallMs = performance.now() - t0;
  orch.stop();
  const magnets = result.items.filter(
    (i: DetectedTorrent) => i.type === "magnet",
  ).length;
  document.body.innerHTML = "";
  return { wallMs, magnets };
}

/**
 * MIN scan-time over `reps` runs at size `n`, asserting the EXACT 2-magnet
 * correctness on every run (never a fast "0 detected" false PASS).
 */
async function minScanMs(n: number, reps: number): Promise<number> {
  let best = Infinity;
  for (let i = 0; i < reps; i++) {
    const r = await scanOnce(n);
    expect(r.magnets).toBe(2); // junk excluded, both real magnets found — every run
    best = Math.min(best, r.wallMs);
  }
  return best;
}

// ─────────────────────────────────────────────────────────────────────────────
// Scaling-oracle self-validation (§11.4.107(10) / §1.1) — golden-good + golden-bad
// ─────────────────────────────────────────────────────────────────────────────

// A volatile sink so the synthetic workloads are NOT dead-code-eliminated.
let SINK = 0;

/** MIN wall-time over `reps` of a synchronous workload `fn(n)`. */
function minWorkMs(fn: (n: number) => void, n: number, reps: number): number {
  let best = Infinity;
  for (let i = 0; i < reps; i++) {
    const t0 = performance.now();
    fn(n);
    best = Math.min(best, performance.now() - t0);
  }
  return best;
}

/** Golden-good: a genuinely LINEAR O(n) workload. */
function linearWork(n: number): void {
  let acc = 0;
  for (let i = 0; i < n; i++) acc += (i * 2 + 1) % 7;
  SINK += acc;
}

/** Golden-bad: a genuinely QUADRATIC O(n²) workload. */
function quadraticWork(n: number): void {
  let acc = 0;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) acc += (i ^ j) & 1;
  }
  SINK += acc;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("perf: scaling-oracle self-validation (golden-good linear / golden-bad quadratic)", () => {
  it("the SUBQUAD_RATIO_MAX threshold ACCEPTS a linear workload and REJECTS a quadratic one", () => {
    // The scaling threshold is meaningless unless it provably distinguishes
    // linear from quadratic growth. Prove it on synthetic workloads of KNOWN
    // complexity, at the SAME FACTOR the real scan uses — so the guard below is
    // demonstrably not a tautology (§11.4.107(10) analyzer self-validation; the
    // golden-bad is the §1.1 paired mutation made permanent).

    // Sizes chosen so both workloads measure in a stable, non-trivial range.
    const LIN_BASE = 200_000; // O(n): cheap per element
    const QUAD_BASE = 1_500; // O(n²): 1,500² = 2.25M ops at base

    // Warmup (discarded — primes the JIT).
    linearWork(LIN_BASE);
    quadraticWork(QUAD_BASE);

    const linBase = minWorkMs(linearWork, LIN_BASE, 5);
    const linBig = minWorkMs(linearWork, LIN_BASE * FACTOR, 5);
    const linRatio = linBig / linBase;

    const quadBase = minWorkMs(quadraticWork, QUAD_BASE, 3);
    const quadBig = minWorkMs(quadraticWork, QUAD_BASE * FACTOR, 3);
    const quadRatio = quadBig / quadBase;

    const evidence = {
      test: "scaling-oracle-self-validation",
      constitution: "§11.4.107(10) analyzer self-validation; §1.1 paired mutation",
      factor: FACTOR,
      threshold: SUBQUAD_RATIO_MAX,
      linear: { base: LIN_BASE, baseMs: linBase, bigMs: linBig, ratio: linRatio },
      quadratic: {
        base: QUAD_BASE,
        baseMs: quadBase,
        bigMs: quadBig,
        ratio: quadRatio,
      },
      sink: SINK, // keep the optimizer honest
    };
    const path = captureEvidence("scaling_oracle_self_validation.json", evidence);

    // eslint-disable-next-line no-console
    console.log(
      `[perf] scaling-oracle self-validation @factor=${FACTOR} threshold=${SUBQUAD_RATIO_MAX}: ` +
        `linearRatio=${linRatio.toFixed(2)} (accept) quadraticRatio=${quadRatio.toFixed(2)} (reject) ` +
        `| evidence: ${path}`,
    );

    // GOLDEN-GOOD: a linear workload's ratio (≈FACTOR) is ACCEPTED.
    expect(linRatio).toBeLessThan(SUBQUAD_RATIO_MAX);
    // GOLDEN-BAD: a quadratic workload's ratio (≈FACTOR²) is REJECTED — proving
    // the same threshold below would catch a real O(n²) scan regression.
    expect(quadRatio).toBeGreaterThan(SUBQUAD_RATIO_MAX);
  }, PERF_TEST_TIMEOUT_MS);
});

describe("perf: ScannerOrchestrator junk-flood DoS scaling (machine-independent)", () => {
  it("scales SUB-QUADRATICALLY from N to 10·N junk anchors AND returns EXACTLY the 2 real magnets", async () => {
    // Warmup (discarded) at the small size to prime caches/JIT.
    await minScanMs(BASE_N, 1);

    const tBase = await minScanMs(BASE_N, REPS); // min over REPS @ N
    const tBig = await minScanMs(BIG_N, REPS); // min over REPS @ 10·N
    const ratio = tBig / tBase;

    const evidence = {
      test: "orchestrator-junkflood-scaling",
      constitution: "§11.4.85 scaling + §11.4.107(8) metamorphic + §11.4.5 captured",
      baseAnchors: BASE_N,
      bigAnchors: BIG_N,
      factor: FACTOR,
      reps: REPS,
      baseScanMs: tBase,
      bigScanMs: tBig,
      ratio,
      subQuadThreshold: SUBQUAD_RATIO_MAX,
      isSubQuadratic: ratio < SUBQUAD_RATIO_MAX,
      hangBudgetMs: BIG_SCAN_HANG_BUDGET_MS,
      withinHangBudget: tBig <= BIG_SCAN_HANG_BUDGET_MS,
      magnetsDetectedEveryRun: 2,
    };
    const path = captureEvidence("orchestrator_junkflood_scaling.json", evidence);

    // eslint-disable-next-line no-console
    console.log(
      `[perf] orchestrator junk-flood scaling N=${BASE_N}→${BIG_N} (×${FACTOR}): ` +
        `tBase=${tBase.toFixed(2)}ms tBig=${tBig.toFixed(2)}ms ratio=${ratio.toFixed(2)} ` +
        `(sub-quad threshold ${SUBQUAD_RATIO_MAX}) | evidence: ${path}`,
    );

    // METAMORPHIC sub-quadratic scaling — machine-INDEPENDENT (a ratio cancels
    // absolute host speed/load). A real O(n²) DoS regression → ratio ≈ 100 FAILS;
    // host jitter never moves the ratio past 30.
    expect(ratio).toBeLessThan(SUBQUAD_RATIO_MAX);
    // Generous absolute hang-ceiling — catches a true hang / infinite loop the
    // ratio alone could not (e.g. both sizes equally hung).
    expect(tBig).toBeLessThanOrEqual(BIG_SCAN_HANG_BUDGET_MS);
  }, PERF_TEST_TIMEOUT_MS);
});
