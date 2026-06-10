/**
 * @fileoverview STRESS tests (§11.4.85) for the REAL committed OfflineQueue and
 * its injected send pipeline (`src/api/queue.ts`).
 *
 * Constitution §11.4.85 (stress + chaos test mandate) + the §11.4 anti-bluff
 * covenant. These exercise the PRODUCTION `OfflineQueue` class — no mock of the
 * unit under test. The queue persists into the REAL `src/shared/storage`
 * helpers, which here are backed by an in-memory `chrome.storage.local` fake
 * installed onto `globalThis` (the same pattern the unit suite uses), so every
 * persistence assertion is a genuine read-back of what the queue wrote.
 *
 * §11.4.85 STRESS closed-set coverage:
 *   (a) sustained load    — enqueue ≥1000 items, assert ALL persisted, assert
 *                           FIFO dequeue order preserved, capture per-op timing.
 *   (b) concurrent        — ≥10 concurrent enqueue/flush operations, assert no
 *                           lost items, no deadlock, final queue count correct.
 *   (c) boundary          — empty-queue flush, single item, at-max (eviction).
 *
 * EVIDENCE (§11.4.85 MANDATORY): each test writes a captured-evidence JSON
 * artifact under `tests/stress/.evidence/` containing per-iteration latencies
 * and/or counts, and asserts on that captured data (e.g. all 1000 accounted,
 * FIFO order intact). A PASS with no captured artifact is a §11.4 bluff.
 *
 * ANTI-BLUFF: assertions are on USER-OBSERVABLE outcomes — persisted item
 * counts, dequeue ORDER, final queue size — never "no error". Each test fails
 * if the resilience property were broken (a queue that dropped items, lost FIFO
 * order, or deadlocked under contention FAILS).
 *
 * @module tests/stress/queue.stress.test
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { OfflineQueue, type OfflineQueueItem, type QueueSender } from "../../src/api/queue";
import { STORAGE_KEYS } from "../../src/shared/constants";

const HERE = dirname(fileURLToPath(import.meta.url));
const EVIDENCE_DIR = join(HERE, ".evidence");

/** Write a §11.4.85 captured-evidence artifact and return its absolute path. */
function captureEvidence(name: string, data: unknown): string {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  const path = join(EVIDENCE_DIR, name);
  writeFileSync(path, JSON.stringify(data, null, 2), "utf8");
  return path;
}

/** Latency distribution summary (§11.4.85 stress metrics). */
interface LatencyStats {
  count: number;
  min: number;
  max: number;
  mean: number;
  p50: number;
  p95: number;
  p99: number;
}

/** min/max/mean/p50/p95/p99 over a latency sample (§11.4.85 stress metrics). */
function latencyStats(samples: number[]): LatencyStats {
  if (samples.length === 0) return { count: 0, min: 0, max: 0, mean: 0, p50: 0, p95: 0, p99: 0 };
  const sorted = [...samples].sort((a, b) => a - b);
  const at = (q: number): number => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))] as number;
  const sum = sorted.reduce((s, v) => s + v, 0);
  return {
    count: sorted.length,
    min: sorted[0] as number,
    max: sorted[sorted.length - 1] as number,
    mean: sum / sorted.length,
    p50: at(0.5),
    p95: at(0.95),
    p99: at(0.99),
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// In-memory chrome.storage.local fake (the queue persists through the REAL
// src/shared/storage helpers, which call globalThis.chrome.storage.local).
// ─────────────────────────────────────────────────────────────────────────────

interface FakeStorage {
  store: Map<string, unknown>;
}

function installChromeStorage(): FakeStorage {
  const store = new Map<string, unknown>();
  const local = {
    get(keys?: string | string[] | null): Promise<Record<string, unknown>> {
      const out: Record<string, unknown> = {};
      if (keys === null || keys === undefined) {
        for (const [k, v] of store) out[k] = v;
        return Promise.resolve(out);
      }
      const list = Array.isArray(keys) ? keys : [keys];
      for (const k of list) if (store.has(k)) out[k] = store.get(k);
      return Promise.resolve(out);
    },
    set(items: Record<string, unknown>): Promise<void> {
      for (const [k, v] of Object.entries(items)) {
        // chrome.storage.local serialises to JSON — replicate that fidelity so
        // we never accidentally persist a live object reference.
        store.set(k, JSON.parse(JSON.stringify(v)));
      }
      return Promise.resolve();
    },
    remove(keys: string | string[]): Promise<void> {
      const list = Array.isArray(keys) ? keys : [keys];
      for (const k of list) store.delete(k);
      return Promise.resolve();
    },
  };
  (globalThis as unknown as { chrome: unknown }).chrome = {
    storage: { local, onChanged: { addListener() {}, removeListener() {} } },
  };
  return { store };
}

/** Read the persisted queue array straight out of the backing store. */
function readPersisted(fake: FakeStorage): OfflineQueueItem[] {
  return (fake.store.get(STORAGE_KEYS.QUEUE) as OfflineQueueItem[] | undefined) ?? [];
}

let fake: FakeStorage;

beforeEach(() => {
  fake = installChromeStorage();
});

afterEach(() => {
  delete (globalThis as unknown as { chrome?: unknown }).chrome;
});

// ─────────────────────────────────────────────────────────────────────────────
// (a) STRESS — sustained load: ≥1000 enqueues, persisted + FIFO preserved
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: OfflineQueue sustained load (≥1000 items, FIFO preserved)", () => {
  it("enqueues 1000 items — ALL persisted, dequeue order is FIFO, timing captured", async () => {
    const N = 1000;
    // maxSize ≥ N so nothing is evicted — this test is about NO-LOSS + ORDER.
    const queue = new OfflineQueue(N + 10);
    await queue.init();

    const enqueueLatencies: number[] = [];
    const expectedOrder: string[] = []; // infohash sequence in insertion order

    for (let i = 0; i < N; i++) {
      const infohash = `infohash-${String(i).padStart(6, "0")}`;
      const t0 = performance.now();
      const item = await queue.enqueue(
        infohash,
        `magnet:?xt=urn:btih:${infohash}`,
        null,
        `Torrent ${i}`,
        "srv-stress",
        "normal",
      );
      enqueueLatencies.push(performance.now() - t0);
      expectedOrder.push(item.torrent.infohash);
    }

    // USER-OBSERVABLE: every one of the 1000 lives in the queue AND on disk.
    expect(queue.getSize()).toBe(N);
    const persisted = readPersisted(fake);
    expect(persisted.length).toBe(N);

    // FIFO: in-memory order, persisted order, and insertion order all agree.
    const memOrder = queue.getItems().map((i) => i.torrent.infohash);
    const diskOrder = persisted.map((i) => i.torrent.infohash);
    expect(memOrder).toEqual(expectedOrder);
    expect(diskOrder).toEqual(expectedOrder);

    // Dead-letter dequeue from the FRONT (operator removing the head) keeps the
    // remaining order intact — proves FIFO is structural, not incidental.
    const headId = queue.getItems()[0]?.id as string;
    const removed = await queue.dequeue(headId);
    expect(removed).toBe(true);
    expect(queue.getSize()).toBe(N - 1);
    expect(queue.getItems().map((i) => i.torrent.infohash)).toEqual(expectedOrder.slice(1));

    const stats = latencyStats(enqueueLatencies);
    const evidence = {
      test: "sustained-load-1000",
      constitution: "§11.4.85 stress sustained",
      enqueued: N,
      persistedCount: persisted.length,
      allAccountedFor: persisted.length === N,
      fifoOrderPreserved: JSON.stringify(diskOrder) === JSON.stringify(expectedOrder),
      enqueueLatencyMs: stats,
      sampleFirst3: expectedOrder.slice(0, 3),
      sampleLast3: expectedOrder.slice(-3),
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("queue_sustained_load.json", evidence);

    // Assert on the CAPTURED artifact's claims (no bluff: the artifact is the proof).
    expect(evidence.allAccountedFor).toBe(true);
    expect(evidence.fifoOrderPreserved).toBe(true);
    expect(evidence.enqueueLatencyMs.count).toBe(N);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS sustained] ${N} enqueues: ${persisted.length} persisted, ` +
        `FIFO=${evidence.fifoOrderPreserved}, p95=${stats.p95.toFixed(3)}ms | evidence: ${path}`,
    );
  });

  it("flushes ≥1000 queued sends through the injected sender — every item sent, queue drains to 0", async () => {
    const N = 1000;
    const queue = new OfflineQueue(N + 10);
    await queue.init();

    const sentOrder: string[] = [];
    const sender: QueueSender = (item) => {
      sentOrder.push(item.torrent.infohash);
      return Promise.resolve(true); // all succeed → all removed
    };

    const expectedOrder: string[] = [];
    for (let i = 0; i < N; i++) {
      const infohash = `flush-${String(i).padStart(6, "0")}`;
      await queue.enqueue(infohash, `magnet:?xt=urn:btih:${infohash}`, null, `T${i}`, "srv", "normal");
      expectedOrder.push(infohash);
    }

    const t0 = performance.now();
    const result = await queue.processQueue(sender);
    const flushMs = performance.now() - t0;

    // USER-OBSERVABLE: all sent, none remaining, persisted store emptied.
    expect(result.processed).toBe(N);
    expect(result.succeeded).toBe(N);
    expect(result.failed).toBe(0);
    expect(result.remaining).toBe(0);
    expect(queue.getSize()).toBe(0);
    expect(readPersisted(fake).length).toBe(0);
    // sender saw every item exactly once, in FIFO order (same-priority → FIFO).
    expect(sentOrder).toEqual(expectedOrder);

    const evidence = {
      test: "sustained-flush-1000",
      constitution: "§11.4.85 stress sustained",
      enqueued: N,
      sent: sentOrder.length,
      remainingAfterFlush: result.remaining,
      persistedAfterFlush: readPersisted(fake).length,
      flushOrderIsFifo: JSON.stringify(sentOrder) === JSON.stringify(expectedOrder),
      flushWallMs: flushMs,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("queue_sustained_flush.json", evidence);

    expect(evidence.sent).toBe(N);
    expect(evidence.remainingAfterFlush).toBe(0);
    expect(evidence.flushOrderIsFifo).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS sustained] flushed ${N}: sent=${sentOrder.length}, ` +
        `remaining=${result.remaining}, fifo=${evidence.flushOrderIsFifo}, ` +
        `wall=${flushMs.toFixed(1)}ms | evidence: ${path}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (b) STRESS — concurrent contention: ≥10 concurrent enqueue/flush, no loss
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: OfflineQueue concurrent contention (≥10 parallel ops, no loss, no deadlock)", () => {
  it("runs 50 concurrent enqueues — no item lost, final count exact, no deadlock", async () => {
    const CONCURRENCY = 50;
    const queue = new OfflineQueue(CONCURRENCY + 10);
    await queue.init();

    // Fire CONCURRENCY enqueues in parallel via Promise.all (interleaved awaits
    // on the shared storage promise — the contention surface).
    const t0 = performance.now();
    const items = await Promise.all(
      Array.from({ length: CONCURRENCY }, (_, i) =>
        queue.enqueue(
          `conc-${String(i).padStart(4, "0")}`,
          `magnet:?xt=urn:btih:conc-${i}`,
          null,
          `Concurrent ${i}`,
          "srv",
          "normal",
        ),
      ),
    );
    const wallMs = performance.now() - t0;

    // No deadlock: Promise.all resolved (the test would hang/time out otherwise).
    // No loss: exactly CONCURRENCY distinct items present in memory AND on disk.
    expect(items.length).toBe(CONCURRENCY);
    expect(queue.getSize()).toBe(CONCURRENCY);

    const memIds = new Set(queue.getItems().map((i) => i.id));
    expect(memIds.size).toBe(CONCURRENCY); // all IDs unique → none clobbered

    const persisted = readPersisted(fake);
    const persistedHashes = new Set(persisted.map((p) => p.torrent.infohash));
    const expectedHashes = new Set(items.map((i) => i.torrent.infohash));
    expect(persisted.length).toBe(CONCURRENCY);
    expect(persistedHashes).toEqual(expectedHashes);

    const evidence = {
      test: "concurrent-enqueue-50",
      constitution: "§11.4.85 stress concurrent",
      concurrency: CONCURRENCY,
      resolvedItems: items.length,
      finalQueueSize: queue.getSize(),
      uniqueIds: memIds.size,
      persistedCount: persisted.length,
      noItemLost: persistedHashes.size === CONCURRENCY,
      deadlock: false, // Promise.all resolved
      wallMs,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("queue_concurrent_enqueue.json", evidence);

    expect(evidence.noItemLost).toBe(true);
    expect(evidence.finalQueueSize).toBe(CONCURRENCY);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS concurrent] ${CONCURRENCY} parallel enqueues: ` +
        `final=${queue.getSize()}, unique=${memIds.size}, lost=${CONCURRENCY - persistedHashes.size}, ` +
        `wall=${wallMs.toFixed(1)}ms | evidence: ${path}`,
    );
  });

  it("interleaves 12 concurrent enqueues with 12 concurrent flushes — no lost item, no double-send, no deadlock", async () => {
    const PAIRS = 12;
    const queue = new OfflineQueue(1000);
    await queue.init();

    // Pre-seed some items so flushes have work; then fire enqueues and flushes
    // concurrently. The queue's internal `processing` guard means overlapping
    // flushes must NOT double-send or lose an item.
    const sentCounts = new Map<string, number>();
    const sender: QueueSender = (item) => {
      sentCounts.set(item.torrent.infohash, (sentCounts.get(item.torrent.infohash) ?? 0) + 1);
      return Promise.resolve(true);
    };

    const enqueueOf = (tag: string): Promise<OfflineQueueItem> =>
      queue.enqueue(tag, `magnet:?xt=urn:btih:${tag}`, null, tag, "srv", "normal");

    // Seed
    const seeded: string[] = [];
    for (let i = 0; i < PAIRS; i++) {
      const tag = `seed-${i}`;
      await enqueueOf(tag);
      seeded.push(tag);
    }

    // Concurrent burst: PAIRS new enqueues + PAIRS flush attempts, all parallel.
    const newTags = Array.from({ length: PAIRS }, (_, i) => `burst-${i}`);
    const ops: Promise<unknown>[] = [
      ...newTags.map((t) => enqueueOf(t)),
      ...Array.from({ length: PAIRS }, () => queue.processQueue(sender)),
    ];
    await Promise.all(ops);

    // Drain any stragglers that were enqueued after the last concurrent flush
    // had already snapshot its pending set (a real, expected race — the queue
    // must STILL eventually send them, never drop them).
    let guard = 0;
    while (queue.getSize() > 0 && guard < 20) {
      await queue.processQueue(sender);
      guard++;
    }

    // USER-OBSERVABLE: queue fully drained, no item sent more than once.
    expect(queue.getSize()).toBe(0);
    expect(readPersisted(fake).length).toBe(0);

    const doubleSent = [...sentCounts.entries()].filter(([, c]) => c > 1);
    expect(doubleSent).toEqual([]); // no double-send

    // Every seeded + burst tag was sent exactly once → no item lost.
    const allTags = [...seeded, ...newTags];
    for (const tag of allTags) {
      expect(sentCounts.get(tag)).toBe(1);
    }

    const evidence = {
      test: "concurrent-enqueue-flush-interleave",
      constitution: "§11.4.85 stress concurrent",
      seeded: seeded.length,
      burst: newTags.length,
      totalExpected: allTags.length,
      distinctSent: sentCounts.size,
      doubleSentCount: doubleSent.length,
      finalQueueSize: queue.getSize(),
      drainPasses: guard,
      deadlock: false,
      noItemLost: sentCounts.size === allTags.length && allTags.every((t) => sentCounts.get(t) === 1),
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("queue_concurrent_interleave.json", evidence);

    expect(evidence.noItemLost).toBe(true);
    expect(evidence.doubleSentCount).toBe(0);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS concurrent] interleave seed=${seeded.length}+burst=${newTags.length}: ` +
        `distinctSent=${sentCounts.size}, doubleSent=${doubleSent.length}, ` +
        `final=${queue.getSize()} | evidence: ${path}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (c) STRESS — boundary: empty flush, single item, at-max eviction
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: OfflineQueue boundaries (empty / single / max-eviction)", () => {
  it("handles empty-queue flush, single-item lifecycle, and max-size FIFO eviction", async () => {
    const perCase: Record<string, unknown> = {};

    // --- empty-queue flush: a no-op processing pass, never throws ---
    {
      const q = new OfflineQueue(10);
      await q.init();
      const calls: string[] = [];
      const sender: QueueSender = (i) => {
        calls.push(i.id);
        return Promise.resolve(true);
      };
      const res = await q.processQueue(sender);
      expect(res.processed).toBe(0);
      expect(res.succeeded).toBe(0);
      expect(res.remaining).toBe(0);
      expect(calls).toEqual([]); // sender never invoked on an empty queue
      perCase["empty-flush"] = { processed: res.processed, senderCalls: calls.length };
    }

    // --- single item: enqueue → flush success → drains to 0 ---
    {
      const q = new OfflineQueue(10);
      await q.init();
      await q.enqueue("only-1", "magnet:?xt=urn:btih:only", null, "Only", "srv", "high");
      expect(q.getSize()).toBe(1);
      expect(readPersisted(fake).length).toBe(1);
      const res = await q.processQueue((_i) => Promise.resolve(true));
      expect(res.succeeded).toBe(1);
      expect(q.getSize()).toBe(0);
      expect(readPersisted(fake).length).toBe(0);
      perCase["single-item"] = { sentSucceeded: res.succeeded, finalSize: q.getSize() };
    }

    // --- max-size eviction: enqueue maxSize+overflow, OLDEST FIFO-evicted ---
    {
      const MAX = 5;
      const OVERFLOW = 3;
      const q = new OfflineQueue(MAX);
      await q.init();
      const inserted: string[] = [];
      for (let i = 0; i < MAX + OVERFLOW; i++) {
        const tag = `evict-${i}`;
        await q.enqueue(tag, `magnet:?xt=urn:btih:${tag}`, null, tag, "srv", "normal");
        inserted.push(tag);
      }
      // Never exceeds MAX.
      expect(q.getSize()).toBe(MAX);
      expect(readPersisted(fake).length).toBe(MAX);
      // The OLDEST `OVERFLOW` items were evicted (FIFO eviction from the front);
      // the surviving set is exactly the last MAX inserted, in order.
      const survivors = q.getItems().map((i) => i.torrent.infohash);
      const expectedSurvivors = inserted.slice(OVERFLOW); // dropped first OVERFLOW
      expect(survivors).toEqual(expectedSurvivors);
      perCase["max-eviction"] = {
        max: MAX,
        inserted: inserted.length,
        finalSize: q.getSize(),
        evictedOldest: inserted.slice(0, OVERFLOW),
        survivors,
        fifoEviction: JSON.stringify(survivors) === JSON.stringify(expectedSurvivors),
      };
    }

    const evidence = {
      test: "boundaries",
      constitution: "§11.4.85 stress boundary",
      perCase,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("queue_boundaries.json", evidence);

    // Assert the captured boundary facts.
    expect((perCase["empty-flush"] as { senderCalls: number }).senderCalls).toBe(0);
    expect((perCase["single-item"] as { finalSize: number }).finalSize).toBe(0);
    expect((perCase["max-eviction"] as { fifoEviction: boolean }).fifoEviction).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS boundary] empty/single/max: ${JSON.stringify(perCase)} | evidence: ${path}`,
    );
  });
});
