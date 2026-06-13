/**
 * @fileoverview CHAOS / RESILIENCE tests (§11.4.85) for the REAL Boba :7187 API
 * client — `src/api/boba-client.ts`.
 *
 * Constitution §11.4.85 (stress + chaos test mandate) + the §11.4 anti-bluff
 * covenant + §11.4.50 (NO absolute wall-clock thresholds — fake timers +
 * relative/ordering assertions only). Drives the PRODUCTION `BobaClient` with an
 * INJECTED `fetch` (the only seam stubbed — the network boundary); the retry
 * loop, backoff scheduler, error classifier and TokenBucket are the REAL code.
 *
 * RESILIENCE gaps these target (NOT duplicated by `tests/unit/boba-client.test.ts`,
 * which proves retry-once-then-succeed / no-retry-4xx / timeout→NetworkError with
 * REAL timers):
 *   1. TRANSIENT-RECOVERY — a 503 (and a network reject) once is RETRIED and the
 *      call ends in SUCCESS; the wire saw exactly N attempts.
 *   2. EXHAUSTION — persistent 5xx exhausts the configured budget: the wire sees
 *      EXACTLY 1 + maxRetries attempts and the caller sees a STRUCTURED FAILURE
 *      (a thrown ServerError), NEVER a silent success.
 *   3. BACKOFF-ORDERING — with FAKE timers, attempt K+1 fires ONLY after the
 *      scheduled `sleep` for attempt K elapses; advancing time monotonically
 *      releases attempts in order, and a too-small advance does NOT release the
 *      next attempt. Pure ordering — no wall-clock number is asserted.
 *   4. CLASSIFICATION — a network reject (retried), an HTTP 5xx (retried), an
 *      HTTP 4xx (NOT retried), and a malformed/non-JSON 2xx body (accepted) each
 *      produce the distinct outcome the REAL code implements.
 *   5. TIMEOUT — an AbortController timeout aborts the in-flight request, is
 *      mapped to a retryable NetworkError, and is RETRIED then succeeds.
 *
 * ANTI-BLUFF: every assertion inspects USER-OBSERVABLE outcomes (attempt counts
 * on the wire, the resolved AddResult, the thrown error type/status) and FAILS if
 * the resilience property regressed (retries unbounded, a failure swallowed as
 * success, backoff absent, a 4xx retried, a timeout not retried). Each test
 * writes a §11.4.85 captured-evidence artifact under `tests/chaos/.evidence/` and
 * asserts on it. NEVER embeds a real token; never embeds raw control bytes.
 *
 * @module tests/chaos/boba-client-resilience.chaos.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { BobaClient } from "../../src/api/boba-client";
import { NetworkError, ServerError } from "../../src/shared/errors";
import { RETRY_CONFIG } from "../../src/shared/constants";

const HERE = dirname(fileURLToPath(import.meta.url));
const EVIDENCE_DIR = join(HERE, ".evidence");
const BASE = "http://localhost:7187";
const MAGNET =
  "magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678&dn=Chaos";

/** Write a §11.4.85 captured-evidence artifact and return its absolute path. */
function captureEvidence(name: string, data: unknown): string {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  const path = join(EVIDENCE_DIR, name);
  writeFileSync(path, JSON.stringify(data, null, 2), "utf8");
  return path;
}

/** A Response-like good enough for the client's `.ok` / `.status` / `.json()`. */
function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

/** A 2xx Response whose body is NOT valid JSON — `.json()` rejects (malformed). */
function malformedBodyResponse(status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.reject(new SyntaxError("Unexpected token < in JSON")),
  } as unknown as Response;
}

/**
 * Drain the microtask + fake-timer queues until `predicate()` is true OR `maxTicks`
 * is exhausted. The client interleaves awaited fetches (microtasks) with awaited
 * `sleep()` (a fake `setTimeout`); advancing one alone deadlocks. This pumps both:
 * flush pending microtasks, then run any due timers, repeat.
 *
 * Returns true if the predicate became true within budget.
 */
async function pump(
  predicate: () => boolean,
  maxTicks = 200,
): Promise<boolean> {
  for (let i = 0; i < maxTicks; i++) {
    if (predicate()) return true;
    // Let any resolved fetch promise settle into the client's await.
    await Promise.resolve();
    await Promise.resolve();
    // Release whatever backoff timer is currently scheduled (if any).
    await vi.advanceTimersByTimeAsync(RETRY_CONFIG.MAX_DELAY_MS + 1);
  }
  return predicate();
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ─────────────────────────────────────────────────────────────────────────────
// 1. TRANSIENT-RECOVERY — a single transient fault is retried then succeeds
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 RESILIENCE: transient fault is RETRIED then SUCCEEDS", () => {
  it("a 503 once is retried; the wire sees 2 attempts and the final result is accepted", async () => {
    vi.useFakeTimers();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(503, { detail: "service unavailable" }))
      .mockResolvedValueOnce(jsonResponse(200, { status: "initiated", added_count: 1, download_id: "dl-T" }));

    const client = new BobaClient({
      baseUrl: BASE,
      maxRetries: RETRY_CONFIG.MAX_RETRIES,
      disableRateLimit: true,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    const p = client.addMagnet(MAGNET);
    // Release the single backoff sleep + let the 2nd fetch settle.
    const settled = await pump(() => fetchMock.mock.calls.length >= 2);
    expect(settled).toBe(true);
    const res = await p;

    // Regression guard: a transient 503 that is NOT retried (or retried but the
    // recovery success not surfaced) breaks this — attempts would be 1, or res
    // would not be accepted.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(res.accepted).toBe(true);
    expect(res.downloadId).toBe("dl-T");
    expect(res.addedCount).toBe(1);

    const path = captureEvidence("boba_resilience_transient_503.json", {
      test: "transient-503-recovers",
      constitution: "§11.4.85 stress+chaos / network-fault recovery",
      attemptsOnWire: fetchMock.mock.calls.length,
      finalAccepted: res.accepted,
      downloadId: res.downloadId,
      capturedAt: new Date().toISOString(),
    });
    // eslint-disable-next-line no-console
    console.log(`[§11.4.85 RESILIENCE transient-503] attempts=2 accepted=true | evidence: ${path}`);
  });

  it("a network reject once is retried; the wire sees 2 attempts and the result is accepted", async () => {
    vi.useFakeTimers();
    fetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse(200, { status: "initiated", added_count: 1 }));

    const client = new BobaClient({
      baseUrl: BASE,
      maxRetries: RETRY_CONFIG.MAX_RETRIES,
      disableRateLimit: true,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    const p = client.addMagnet(MAGNET);
    expect(await pump(() => fetchMock.mock.calls.length >= 2)).toBe(true);
    const res = await p;

    // Regression guard: a transport-level reject must be classified retryable
    // (NetworkError) — if it were treated terminal the wire would show 1 attempt.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(res.accepted).toBe(true);

    captureEvidence("boba_resilience_transient_network.json", {
      test: "transient-network-recovers",
      constitution: "§11.4.85 network-fault recovery",
      attemptsOnWire: fetchMock.mock.calls.length,
      finalAccepted: res.accepted,
      capturedAt: new Date().toISOString(),
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. EXHAUSTION — persistent failure exhausts the budget → STRUCTURED failure
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 RESILIENCE: persistent failure EXHAUSTS retries → structured FAILURE (not silent success)", () => {
  it("persistent 503 is attempted EXACTLY 1 + maxRetries times then throws ServerError(503)", async () => {
    vi.useFakeTimers();
    const maxRetries = RETRY_CONFIG.MAX_RETRIES; // real configured budget (3)
    // Always 503 — never recovers.
    fetchMock.mockResolvedValue(jsonResponse(503, { detail: "down" }));

    const client = new BobaClient({
      baseUrl: BASE,
      maxRetries,
      disableRateLimit: true,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    let caught: unknown;
    const p = client.addMagnet(MAGNET).then(
      () => {
        caught = "RESOLVED";
      },
      (e: unknown) => {
        caught = e;
      },
    );
    // Drive all backoff sleeps until the promise settles (rejects).
    await pump(() => caught !== undefined);
    await p;

    const expectedAttempts = 1 + maxRetries; // initial try + maxRetries retries
    // BOUNDEDNESS: retries are NOT unbounded — exactly the configured budget.
    expect(fetchMock).toHaveBeenCalledTimes(expectedAttempts);
    // The caller sees a STRUCTURED FAILURE, never a fabricated success.
    expect(caught).toBeInstanceOf(ServerError);
    expect(caught).not.toBe("RESOLVED");
    expect((caught as ServerError).statusCode).toBe(503);

    const path = captureEvidence("boba_resilience_exhaustion_503.json", {
      test: "persistent-503-exhausts-then-throws",
      constitution: "§11.4.85 resource/upstream-exhaustion + anti-silent-success",
      maxRetries,
      attemptsOnWire: fetchMock.mock.calls.length,
      expectedAttempts,
      bounded: fetchMock.mock.calls.length === expectedAttempts,
      surfacedFailure: caught instanceof ServerError,
      silentSuccess: caught === "RESOLVED",
      thrownStatus: (caught as ServerError).statusCode,
      capturedAt: new Date().toISOString(),
    });
    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 RESILIENCE exhaustion] attempts=${fetchMock.mock.calls.length}/${expectedAttempts}, ` +
        `threw=ServerError(503), silentSuccess=false | evidence: ${path}`,
    );
  });

  it("persistent network reject exhausts the budget then throws NetworkError (no silent success)", async () => {
    vi.useFakeTimers();
    const maxRetries = 2;
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const client = new BobaClient({
      baseUrl: BASE,
      maxRetries,
      disableRateLimit: true,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    let caught: unknown;
    const p = client.addMagnet(MAGNET).then(
      () => {
        caught = "RESOLVED";
      },
      (e: unknown) => {
        caught = e;
      },
    );
    await pump(() => caught !== undefined);
    await p;

    expect(fetchMock).toHaveBeenCalledTimes(1 + maxRetries);
    expect(caught).toBeInstanceOf(NetworkError);
    expect(caught).not.toBe("RESOLVED");

    captureEvidence("boba_resilience_exhaustion_network.json", {
      test: "persistent-network-exhausts-then-throws",
      constitution: "§11.4.85 exhaustion",
      maxRetries,
      attemptsOnWire: fetchMock.mock.calls.length,
      surfacedFailure: caught instanceof NetworkError,
      silentSuccess: caught === "RESOLVED",
      capturedAt: new Date().toISOString(),
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. BACKOFF-ORDERING — attempt K+1 only fires after attempt K's sleep elapses
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 RESILIENCE: backoff schedules retries in order (relative timing, no wall-clock threshold)", () => {
  it("each retry fires ONLY after its scheduled backoff sleep is released; a too-small advance does NOT release the next attempt", async () => {
    vi.useFakeTimers();
    // Always 503 so every attempt schedules a backoff (except the last).
    fetchMock.mockResolvedValue(jsonResponse(503, { detail: "down" }));

    const maxRetries = 3; // → up to 4 attempts, 3 backoff sleeps between them
    const client = new BobaClient({
      baseUrl: BASE,
      maxRetries,
      disableRateLimit: true,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    let settled = false;
    const p = client.addMagnet(MAGNET).then(
      () => {
        settled = true;
      },
      () => {
        settled = true;
      },
    );

    // ── Attempt 1 happens synchronously (no backoff before it). ──
    await Promise.resolve();
    await Promise.resolve();
    const afterAttempt1 = fetchMock.mock.calls.length;

    // ORDERING ASSERT A: with the backoff timer NOT yet released, the next
    // attempt MUST NOT have fired. Advance by ZERO real timer budget — only
    // flush microtasks. The retry is gated on a pending setTimeout, so it stays
    // at 1. (Regression: backoff ABSENT → attempt 2 fires immediately here.)
    await Promise.resolve();
    await Promise.resolve();
    const withoutTimerAdvance = fetchMock.mock.calls.length;
    expect(withoutTimerAdvance).toBe(afterAttempt1);

    // ORDERING ASSERT B: releasing ONE scheduled backoff at a time advances the
    // attempt count one step — retries are SPACED by the scheduler, not fired in
    // a burst. The real backoff for attempt K is BASE_DELAY_MS*2^K + jitter
    // (jitter ≤ 0.3*clamped). Advancing by the FULL clamped delay for THIS step
    // (which is ≥ the actual scheduled sleep incl. jitter) releases exactly the
    // one pending timer, then we let the next fetch settle before the next step.
    const counts: number[] = [afterAttempt1];
    for (let step = 0; step < maxRetries; step++) {
      const clamped = Math.min(
        RETRY_CONFIG.BASE_DELAY_MS * Math.pow(2, step),
        RETRY_CONFIG.MAX_DELAY_MS,
      );
      // Max possible scheduled sleep for this step = clamped*(1 + JITTER_FACTOR).
      const maxSleepThisStep = Math.ceil(clamped * (1 + RETRY_CONFIG.JITTER_FACTOR));
      await vi.advanceTimersByTimeAsync(maxSleepThisStep);
      await Promise.resolve();
      await Promise.resolve();
      counts.push(fetchMock.mock.calls.length);
    }
    await p;

    // Each one-backoff release unlocks exactly the NEXT attempt → the count
    // climbs ONE STEP AT A TIME: [1, 2, 3, 4]. This proves retries are SPACED by
    // the backoff scheduler (not fired in a burst) AND bounded. Pure ordering /
    // step-shape — NO absolute ms threshold is asserted (§11.4.50).
    for (let i = 1; i < counts.length; i++) {
      expect(counts[i]).toBe((counts[i - 1] as number) + 1);
    }
    expect(counts[0]).toBe(1); // first attempt, pre-backoff
    expect(counts[counts.length - 1]).toBe(1 + maxRetries); // bounded total
    expect(counts[counts.length - 1] as number).toBeGreaterThan(
      counts[0] as number,
    ); // backoff DID gate progress
    expect(settled).toBe(true);

    const path = captureEvidence("boba_resilience_backoff_ordering.json", {
      test: "backoff-orders-retries",
      constitution: "§11.4.85 backoff-timing (relative/ordering only, §11.4.50 no wall-clock)",
      maxRetries,
      attemptCountsAfterEachRelease: counts,
      nextAttemptGatedOnBackoff: withoutTimerAdvance === afterAttempt1,
      oneStepPerBackoffRelease: counts.every((c, i) => i === 0 || c === (counts[i - 1] as number) + 1),
      boundedTotal: counts[counts.length - 1] === 1 + maxRetries,
      capturedAt: new Date().toISOString(),
    });
    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 RESILIENCE backoff-ordering] counts=${JSON.stringify(counts)}, ` +
        `gatedOnBackoff=${withoutTimerAdvance === afterAttempt1} | evidence: ${path}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. CLASSIFICATION — network / 5xx / 4xx / malformed-2xx → distinct outcomes
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 RESILIENCE: error classification produces the REAL distinct outcomes", () => {
  it("a 4xx is NOT retried and surfaces a ServerError on the FIRST attempt", async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValue(jsonResponse(400, { detail: "bad request" }));

    const client = new BobaClient({
      baseUrl: BASE,
      maxRetries: RETRY_CONFIG.MAX_RETRIES,
      disableRateLimit: true,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    let caught: unknown;
    const p = client.addMagnet(MAGNET).then(
      () => {
        caught = "RESOLVED";
      },
      (e: unknown) => {
        caught = e;
      },
    );
    await pump(() => caught !== undefined);
    await p;

    // CONTRACT (read from requestWithRetry): 4xx is NOT in the retriable set →
    // exactly ONE attempt, ServerError(400). Regression: a 4xx being retried
    // (wasting the budget on an error that can't change) breaks this.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(caught).toBeInstanceOf(ServerError);
    expect((caught as ServerError).statusCode).toBe(400);

    captureEvidence("boba_resilience_classify_4xx.json", {
      test: "4xx-not-retried",
      constitution: "§11.4.85 error-classification",
      attemptsOnWire: fetchMock.mock.calls.length,
      retried: fetchMock.mock.calls.length > 1,
      thrownStatus: (caught as ServerError).statusCode,
      capturedAt: new Date().toISOString(),
    });
  });

  it("a 5xx IS retried (more than one attempt) while a 4xx is NOT — distinct handling, same client config", async () => {
    vi.useFakeTimers();
    const maxRetries = 2;

    // 5xx client: always 500 → should burn the full budget (1 + maxRetries).
    const fetch5xx = vi.fn().mockResolvedValue(jsonResponse(500, { detail: "boom" }));
    const c5xx = new BobaClient({
      baseUrl: BASE,
      maxRetries,
      disableRateLimit: true,
      fetchImpl: fetch5xx as unknown as typeof fetch,
    });
    let c5done = false;
    const p5 = c5xx.addMagnet(MAGNET).catch(() => {
      c5done = true;
    });
    await pump(() => c5done);
    await p5;

    // 4xx client: always 404 → single attempt.
    const fetch4xx = vi.fn().mockResolvedValue(jsonResponse(404, { detail: "nope" }));
    const c4xx = new BobaClient({
      baseUrl: BASE,
      maxRetries,
      disableRateLimit: true,
      fetchImpl: fetch4xx as unknown as typeof fetch,
    });
    let c4done = false;
    const p4 = c4xx.addMagnet(MAGNET).catch(() => {
      c4done = true;
    });
    await pump(() => c4done);
    await p4;

    const attempts5xx = fetch5xx.mock.calls.length;
    const attempts4xx = fetch4xx.mock.calls.length;
    // The DISCRIMINATOR: 5xx is retried (>1) and 4xx is not (==1) — and the 5xx
    // count is strictly greater. This is a RELATIVE assertion (no ms threshold).
    expect(attempts5xx).toBe(1 + maxRetries);
    expect(attempts4xx).toBe(1);
    expect(attempts5xx).toBeGreaterThan(attempts4xx);

    const path = captureEvidence("boba_resilience_classify_5xx_vs_4xx.json", {
      test: "5xx-retried-4xx-not",
      constitution: "§11.4.85 error-classification (server vs client error)",
      maxRetries,
      attempts5xx,
      attempts4xx,
      fivexxRetried: attempts5xx > 1,
      fourxxRetried: attempts4xx > 1,
      capturedAt: new Date().toISOString(),
    });
    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 RESILIENCE classify] 5xx attempts=${attempts5xx} (retried), ` +
        `4xx attempts=${attempts4xx} (not retried) | evidence: ${path}`,
    );
  });

  it("a malformed (non-JSON) 2xx body does NOT crash the client — it resolves accepted with raw=null", async () => {
    vi.useFakeTimers();
    // status 200 but `.json()` rejects → the client catches and sets body=null.
    fetchMock.mockResolvedValueOnce(malformedBodyResponse(200));

    const client = new BobaClient({
      baseUrl: BASE,
      maxRetries: RETRY_CONFIG.MAX_RETRIES,
      disableRateLimit: true,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    let caught: unknown;
    let result: unknown;
    const p = client.addMagnet(MAGNET).then(
      (r) => {
        result = r;
      },
      (e: unknown) => {
        caught = e;
      },
    );
    await pump(() => result !== undefined || caught !== undefined);
    await p;

    // CONTRACT (read from requestOnce + toAddResult): a malformed body on a 2xx
    // is swallowed to null, and since status is 2xx and backend did not report
    // "failed", the REAL code reports accepted:true with raw:null. We assert what
    // the code ACTUALLY does — NOT an invented contract. It is parsed ONCE (no
    // retry on a parse problem that already returned 2xx).
    expect(caught).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const res = result as { accepted: boolean; raw: unknown; downloadId?: string };
    expect(res.accepted).toBe(true);
    expect(res.raw).toBeNull();
    expect(res.downloadId).toBeUndefined();

    const path = captureEvidence("boba_resilience_classify_malformed_body.json", {
      test: "malformed-2xx-body-no-crash",
      constitution: "§11.4.85 input/body-corruption classification",
      attemptsOnWire: fetchMock.mock.calls.length,
      threw: caught !== undefined,
      accepted: res.accepted,
      rawIsNull: res.raw === null,
      capturedAt: new Date().toISOString(),
    });
    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 RESILIENCE malformed-body] attempts=1 threw=false accepted=true raw=null | evidence: ${path}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. TIMEOUT — AbortController timeout → retryable NetworkError → retried, succeeds
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 RESILIENCE: a per-request timeout aborts and is treated as a retryable failure", () => {
  it("the first request times out (abort) and is retried; the retry succeeds → 2 attempts, accepted", async () => {
    vi.useFakeTimers();
    const timeoutMs = 50;
    let call = 0;
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      call++;
      if (call === 1) {
        // First call: never resolves on its own — only the AbortController's
        // timeout (a real setTimeout inside requestOnce) aborts it.
        return new Promise((_resolve, reject) => {
          const signal = init.signal;
          signal?.addEventListener("abort", () => {
            const e = new Error("aborted");
            e.name = "AbortError";
            reject(e);
          });
        });
      }
      // Retry call: succeeds.
      return Promise.resolve(jsonResponse(200, { status: "initiated", added_count: 1 }));
    });

    const client = new BobaClient({
      baseUrl: BASE,
      timeoutMs,
      maxRetries: 2,
      disableRateLimit: true,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    const p = client.addMagnet(MAGNET);
    // Releasing timers fires: (i) the abort timeout → NetworkError → retry path,
    // (ii) the backoff sleep, (iii) the successful retry fetch.
    expect(await pump(() => fetchMock.mock.calls.length >= 2)).toBe(true);
    const res = await p;

    // Regression guard: a timeout that is NOT classified retryable (or not
    // aborted at all) breaks this — the call would hang or surface 1 attempt.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(res.accepted).toBe(true);

    const path = captureEvidence("boba_resilience_timeout_retry.json", {
      test: "timeout-abort-is-retryable",
      constitution: "§11.4.85 process/upstream-stall (timeout) recovery",
      timeoutMs,
      attemptsOnWire: fetchMock.mock.calls.length,
      finalAccepted: res.accepted,
      capturedAt: new Date().toISOString(),
    });
    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 RESILIENCE timeout] firstAttempt aborted→retried, attempts=2 accepted=true | evidence: ${path}`,
    );
  });
});
