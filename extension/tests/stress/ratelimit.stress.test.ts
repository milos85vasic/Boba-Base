/**
 * @fileoverview STRESS tests (§11.4.85) for the REAL committed {@link TokenBucket}
 * rate limiter (`src/shared/utils.ts`).
 *
 * Constitution §11.4.85 (stress + chaos test mandate) + the §11.4 anti-bluff
 * covenant. These drive the PRODUCTION `TokenBucket` — no mock of the unit under
 * test. The bucket is time-driven (`Date.now()` based refill), so to make the
 * verdict DETERMINISTIC (§11.4.50) we install a controlled clock via
 * `vi.spyOn(Date, "now")` and advance it explicitly. With a frozen clock the
 * refill maths is exact, so "never exceeds capacity per window" and "refills at
 * the configured rate" are asserted as HARD EQUALITIES / BOUNDS, not wall-clock
 * guesses.
 *
 * §11.4.85 STRESS closed-set coverage:
 *   (a) sustained / burst — fire FAR more rapid acquisitions than capacity with
 *                           the clock FROZEN → assert EXACTLY `capacity` succeed
 *                           and the rest are refused (rate never exceeded).
 *   (b) refill over time  — advance the controlled clock and assert tokens are
 *                           replenished at EXACTLY the configured refillRate,
 *                           capped at capacity, never overflowing.
 *   (c) concurrent        — 10 parallel acquirers race for a fixed token budget
 *                           with the clock frozen → assert EXACT accounting
 *                           (total granted == capacity, no over-grant, no
 *                           deadlock).
 *
 * EVIDENCE (§11.4.85 MANDATORY): each test writes a captured-evidence JSON
 * artifact under `tests/stress/.evidence/` containing grant/deny counts +
 * token trajectories and ASSERTS on that captured data. A PASS with no captured
 * artifact is a §11.4 bluff.
 *
 * ANTI-BLUFF: assertions are on USER-OBSERVABLE outcomes — the EXACT number of
 * requests allowed, the token level after refill, total grants under a fixed
 * budget — never "no error". If the limiter over-granted (let more than
 * `capacity` through a frozen window) or under/over-refilled, the EXACT-count
 * assertion FAILS.
 *
 * @module tests/stress/ratelimit.stress.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { TokenBucket } from "../../src/shared/utils";

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
 * A controllable clock that backs `Date.now()` for the duration of a test, so
 * the time-driven refill is fully deterministic (§11.4.50). `now` is the
 * millisecond value returned; `advance(ms)` moves it forward.
 */
interface FakeClock {
  advance(ms: number): void;
  nowMs(): number;
}

let clock: FakeClock;
let dateNowSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  let t = 1_000_000; // arbitrary fixed epoch base (ms)
  clock = {
    advance(ms: number): void {
      t += ms;
    },
    nowMs(): number {
      return t;
    },
  };
  dateNowSpy = vi.spyOn(Date, "now").mockImplementation(() => clock.nowMs());
});

afterEach(() => {
  dateNowSpy.mockRestore();
});

// ─────────────────────────────────────────────────────────────────────────────
// (a) STRESS — burst: fire >> capacity with the clock frozen, never over-grant
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: TokenBucket burst (rate never exceeded within a frozen window)", () => {
  it("fires 100000 rapid consumes with the clock FROZEN — EXACTLY `capacity` succeed, rest refused", () => {
    const CAPACITY = 50;
    const REFILL_PER_SEC = 10;
    const ATTEMPTS = 100_000;

    const bucket = new TokenBucket(CAPACITY, REFILL_PER_SEC);

    // Clock is frozen (we never advance it), so NO refill can occur — the bucket
    // may grant at most `capacity` tokens across the whole burst.
    let granted = 0;
    let refused = 0;
    for (let i = 0; i < ATTEMPTS; i++) {
      if (bucket.consume()) granted++;
      else refused++;
    }

    // USER-OBSERVABLE: exactly `capacity` requests allowed, the rest refused.
    // The rate is NEVER exceeded — over-granting even one would FAIL here.
    expect(granted).toBe(CAPACITY);
    expect(refused).toBe(ATTEMPTS - CAPACITY);
    expect(granted + refused).toBe(ATTEMPTS);
    // Bucket is now empty; the very next consume (clock still frozen) is refused.
    expect(bucket.consume()).toBe(false);
    expect(bucket.getAvailableTokens()).toBeLessThan(1);

    const evidence = {
      test: "burst-frozen-window",
      constitution: "§11.4.85 stress burst",
      capacity: CAPACITY,
      refillPerSec: REFILL_PER_SEC,
      attempts: ATTEMPTS,
      granted,
      refused,
      rateNeverExceeded: granted === CAPACITY,
      everyAttemptAccounted: granted + refused === ATTEMPTS,
      emptyAfterBurst: bucket.getAvailableTokens() < 1,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("ratelimit_burst.json", evidence);

    expect(evidence.rateNeverExceeded).toBe(true);
    expect(evidence.everyAttemptAccounted).toBe(true);
    expect(evidence.emptyAfterBurst).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS burst] ${ATTEMPTS} consumes, capacity=${CAPACITY}: ` +
        `granted=${granted}, refused=${refused}, over-grant=${granted - CAPACITY} | evidence: ${path}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (b) STRESS — refill over time: exact replenishment at the configured rate
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: TokenBucket refill (exact rate, capacity-capped, never deadlocks)", () => {
  it("refills at EXACTLY the configured rate across many advance/drain windows, capped at capacity", () => {
    const CAPACITY = 20;
    const REFILL_PER_SEC = 5; // 5 tokens/sec → 1 token per 200ms
    const bucket = new TokenBucket(CAPACITY, REFILL_PER_SEC);

    // Drain the full initial capacity.
    let drained = 0;
    while (bucket.consume()) drained++;
    expect(drained).toBe(CAPACITY);

    const trajectory: { afterMs: number; available: number; consumedThisWindow: number }[] = [];
    let elapsedMs = 0;

    // Run 30 windows of 1 second each. Each window should add EXACTLY
    // REFILL_PER_SEC tokens (until capacity), which we then drain and count.
    const WINDOWS = 30;
    for (let w = 0; w < WINDOWS; w++) {
      clock.advance(1000); // +1 second
      elapsedMs += 1000;

      // After a 1s advance on an empty bucket, available should be EXACTLY
      // REFILL_PER_SEC (capped at capacity). getAvailableTokens() triggers a
      // refill and returns the level.
      const available = bucket.getAvailableTokens();
      expect(available).toBeCloseTo(Math.min(CAPACITY, REFILL_PER_SEC), 6);

      // Drain whatever refilled and count it — must equal REFILL_PER_SEC.
      let consumedThisWindow = 0;
      while (bucket.consume()) consumedThisWindow++;
      expect(consumedThisWindow).toBe(REFILL_PER_SEC);

      trajectory.push({ afterMs: elapsedMs, available, consumedThisWindow });
    }

    // Capacity cap: drain to empty, advance a LONG time, assert it never exceeds
    // capacity (no overflow accumulation).
    clock.advance(1_000_000); // 1000 seconds → would be 5000 tokens uncapped
    const cappedAvailable = bucket.getAvailableTokens();
    expect(cappedAvailable).toBeCloseTo(CAPACITY, 6);
    expect(cappedAvailable).toBeLessThanOrEqual(CAPACITY);

    // Sub-window precision: from empty, advance exactly 200ms (1 token at 5/sec).
    let drainAgain = 0;
    while (bucket.consume()) drainAgain++;
    expect(drainAgain).toBe(CAPACITY);
    clock.advance(200);
    expect(bucket.getAvailableTokens()).toBeCloseTo(1, 6);

    const allWindowsExact = trajectory.every(
      (t) => t.consumedThisWindow === REFILL_PER_SEC,
    );

    const evidence = {
      test: "refill-exact-rate",
      constitution: "§11.4.85 stress refill",
      capacity: CAPACITY,
      refillPerSec: REFILL_PER_SEC,
      initialDrain: drained,
      windows: WINDOWS,
      perWindowExpected: REFILL_PER_SEC,
      allWindowsExact,
      cappedAvailableAfterLongIdle: cappedAvailable,
      capRespected: cappedAvailable <= CAPACITY + 1e-9,
      oneTokenPer200ms: true,
      trajectorySample: trajectory.slice(0, 3),
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("ratelimit_refill.json", evidence);

    expect(evidence.allWindowsExact).toBe(true);
    expect(evidence.capRespected).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS refill] ${WINDOWS} windows @ ${REFILL_PER_SEC}/s: allExact=${allWindowsExact}, ` +
        `cap-after-long-idle=${cappedAvailable} (cap=${CAPACITY}) | evidence: ${path}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (c) STRESS — concurrent: 10 parallel acquirers, exact accounting, no deadlock
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: TokenBucket concurrent acquirers (exact accounting, no over-grant, no deadlock)", () => {
  it("runs 10 parallel acquirers against a fixed budget — total grants == capacity, no over-grant", async () => {
    const CAPACITY = 100;
    const REFILL_PER_SEC = 0; // no refill → the budget is EXACTLY `capacity`
    const ACQUIRERS = 10;
    const PER_ACQUIRER_ATTEMPTS = 1000; // 10 * 1000 = 10000 attempts for 100 tokens

    const bucket = new TokenBucket(CAPACITY, REFILL_PER_SEC);

    // Each acquirer is an async task that repeatedly tries to consume. They are
    // scheduled concurrently via Promise.all; JS is single-threaded so each
    // consume() is atomic, but the interleaving of awaits is the contention
    // surface. The INVARIANT: total tokens granted across ALL acquirers must be
    // EXACTLY `capacity` — never more (over-grant) and, with no refill, never
    // fewer (every token claimable is claimed).
    const grantsPerAcquirer = new Array<number>(ACQUIRERS).fill(0);

    const acquirer = async (idx: number): Promise<void> => {
      for (let i = 0; i < PER_ACQUIRER_ATTEMPTS; i++) {
        // Yield to interleave with the other acquirers (real contention).
        await Promise.resolve();
        if (bucket.consume()) {
          grantsPerAcquirer[idx] = (grantsPerAcquirer[idx] ?? 0) + 1;
        }
      }
    };

    const t0 = performance.now();
    await Promise.all(
      Array.from({ length: ACQUIRERS }, (_unused, idx) => acquirer(idx)),
    );
    const wallMs = performance.now() - t0;

    const totalGranted = grantsPerAcquirer.reduce((s, v) => s + v, 0);

    // EXACT accounting: total grants == capacity. Over-grant (>capacity) means
    // the limiter leaked; under-grant (<capacity, with refill 0) means it lost
    // tokens. Either FAILS here.
    expect(totalGranted).toBe(CAPACITY);
    // No deadlock: Promise.all resolved (would hang/time out otherwise).
    // Bucket is exhausted — clock frozen + refill 0 → no further grants.
    expect(bucket.consume()).toBe(false);
    expect(bucket.getAvailableTokens()).toBeLessThan(1);

    const evidence = {
      test: "concurrent-acquirers-10",
      constitution: "§11.4.85 stress concurrent",
      capacity: CAPACITY,
      refillPerSec: REFILL_PER_SEC,
      acquirers: ACQUIRERS,
      perAcquirerAttempts: PER_ACQUIRER_ATTEMPTS,
      totalAttempts: ACQUIRERS * PER_ACQUIRER_ATTEMPTS,
      grantsPerAcquirer,
      totalGranted,
      exactAccounting: totalGranted === CAPACITY,
      overGrant: totalGranted - CAPACITY,
      deadlock: false, // Promise.all resolved
      exhaustedAfter: bucket.getAvailableTokens() < 1,
      wallMs,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("ratelimit_concurrent.json", evidence);

    expect(evidence.exactAccounting).toBe(true);
    expect(evidence.overGrant).toBe(0);
    expect(evidence.exhaustedAfter).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS concurrent] ${ACQUIRERS} acquirers × ${PER_ACQUIRER_ATTEMPTS} attempts for ` +
        `${CAPACITY} tokens: totalGranted=${totalGranted}, over-grant=${totalGranted - CAPACITY}, ` +
        `wall=${wallMs.toFixed(1)}ms | evidence: ${path}`,
    );
  });
});
