/**
 * @fileoverview Anti-bluff unit tests for the REAL offline-queue module.
 *
 * Imports the production `src/api/queue.ts` and drives it against the in-memory
 * chrome.storage fake (tests/unit/chrome-fake.ts) installed on globalThis — the
 * SAME real-storage round-trip the storage suite uses, so persistence assertions
 * inspect actual bytes written under STORAGE_KEYS.QUEUE rather than a mock that
 * always agrees (§11.4 / §11.4.69).
 *
 * The actual network SEND is INJECTED as a callback (the queue never imports the
 * boba-client — a sibling builds that), so these tests drive the queue's real
 * enqueue / persist / FIFO-evict / priority-order / retry / dead-letter / clear
 * mechanics with a controllable fake sender and assert user-observable outcomes:
 *   - enqueue → item persisted to chrome.storage.local (read storage back, see it)
 *   - process → injected send callback invoked in FIFO + priority order
 *   - FIFO eviction at max size (enqueue maxSize+1 → oldest dropped)
 *   - retry increments attempts + transitions to dead-letter after N failures
 *   - clear empties the queue (and storage)
 *   - persistence survives re-instantiation (new queue.init() reads persisted items)
 *
 * Each assertion targets a behaviour a no-op stub of the feature would fail.
 *
 * @module tests/unit/api-queue.test
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { createChromeStorageFake } from "./chrome-fake";

let fake: ReturnType<typeof createChromeStorageFake>;

beforeEach(() => {
  fake = createChromeStorageFake();
  (globalThis as unknown as { chrome: unknown }).chrome = fake.chrome;
  vi.resetModules();
});

async function loadQueue() {
  return import("../../src/api/queue");
}

/** Read the raw persisted queue array straight out of the fake backing store. */
function persistedQueue(): unknown[] {
  const raw = fake.store.get("bobalink_queue");
  return Array.isArray(raw) ? raw : [];
}

/** Minimal enqueue helper that fills the required reference-shaped args. */
type EnqueueArgs = Parameters<
  Awaited<ReturnType<typeof loadQueue>>["OfflineQueue"]["prototype"]["enqueue"]
>;

/**
 * Identity pin over the reference `enqueue` signature: a reference-API drift
 * surfaces as a type error at the call site. Returns the tuple unchanged so
 * runtime behaviour is identical to an inline call.
 */
function enqArgs(...args: EnqueueArgs): EnqueueArgs {
  return args;
}

/**
 * Assert a value is present, returning it narrowed. A real assertion — if the
 * queue item is missing the test fails here (stronger than `!`, which would
 * silently pass `undefined` to the next property access).
 */
function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

describe("OfflineQueue — enqueue + persistence", () => {
  it("persists an enqueued item to chrome.storage.local under STORAGE_KEYS.QUEUE", async () => {
    const { OfflineQueue } = await loadQueue();
    const q = new OfflineQueue();

    const item = await q.enqueue(
      ...enqArgs("a".repeat(40), "magnet:?xt=urn:btih:" + "a".repeat(40), null, "Ubuntu ISO", "srv1"),
    );

    // user-observable: the returned item is well-formed
    expect(item.torrent.displayName).toBe("Ubuntu ISO");
    expect(item.attempts).toBe(0);
    expect(item.state).toBe("queued");

    // user-observable: it is actually written to storage (read it back)
    const persisted = persistedQueue();
    expect(persisted).toHaveLength(1);
    expect((persisted[0] as { torrent: { displayName: string } }).torrent.displayName).toBe("Ubuntu ISO");
    expect((persisted[0] as { state: string }).state).toBe("queued");
  });

  it("getItems / getSize reflect the enqueued items", async () => {
    const { OfflineQueue } = await loadQueue();
    const q = new OfflineQueue();
    await q.enqueue("a".repeat(40), "magnet:?one", null, "One", "srv1");
    await q.enqueue("b".repeat(40), "magnet:?two", null, "Two", "srv1");
    expect(q.getSize()).toBe(2);
    expect(q.getItems().map((i) => i.torrent.displayName)).toEqual(["One", "Two"]);
  });
});

describe("OfflineQueue — FIFO eviction at max size", () => {
  it("drops the OLDEST item when enqueuing past maxSize", async () => {
    const { OfflineQueue } = await loadQueue();
    const maxSize = 3;
    const q = new OfflineQueue(maxSize);

    // enqueue maxSize + 1 items
    for (let i = 0; i < maxSize + 1; i++) {
      await q.enqueue("h".repeat(40), `magnet:?n${i}`, null, `T${i}`, "srv1");
    }

    // size capped at maxSize, oldest (T0) evicted, newest (T3) retained
    expect(q.getSize()).toBe(maxSize);
    const names = q.getItems().map((i) => i.torrent.displayName);
    expect(names).toEqual(["T1", "T2", "T3"]);

    // eviction is persisted, not just in-memory
    const persistedNames = persistedQueue().map(
      (p) => (p as { torrent: { displayName: string } }).torrent.displayName,
    );
    expect(persistedNames).toEqual(["T1", "T2", "T3"]);
  });
});

describe("OfflineQueue — process in FIFO + priority order via injected send", () => {
  it("calls the injected send callback for each item, high priority first then FIFO", async () => {
    const { OfflineQueue } = await loadQueue();
    const q = new OfflineQueue();

    // enqueue: normal A, high B, normal C, low D, high E
    await q.enqueue("a".repeat(40), "m:A", null, "A", "srv1", "normal");
    await q.enqueue("a".repeat(40), "m:B", null, "B", "srv1", "high");
    await q.enqueue("a".repeat(40), "m:C", null, "C", "srv1", "normal");
    await q.enqueue("a".repeat(40), "m:D", null, "D", "srv1", "low");
    await q.enqueue("a".repeat(40), "m:E", null, "E", "srv1", "high");

    const sendOrder: string[] = [];
    const send = vi.fn((item) => {
      sendOrder.push(item.torrent.displayName);
      return Promise.resolve(true); // success
    });

    const result = await q.processQueue(send);

    // priority: high (B,E by FIFO) → normal (A,C by FIFO) → low (D)
    expect(sendOrder).toEqual(["B", "E", "A", "C", "D"]);
    expect(send).toHaveBeenCalledTimes(5);

    // all succeeded → removed from queue + persisted empty
    expect(result.succeeded).toBe(5);
    expect(result.failed).toBe(0);
    expect(q.getSize()).toBe(0);
    expect(persistedQueue()).toHaveLength(0);
  });

  it("keeps failed items in the queue and increments their attempt count", async () => {
    const { OfflineQueue } = await loadQueue();
    const q = new OfflineQueue();
    await q.enqueue("a".repeat(40), "m:A", null, "A", "srv1");

    const send = vi.fn(() => Promise.resolve(false)); // every send fails
    const result = await q.processQueue(send);

    expect(send).toHaveBeenCalledTimes(1);
    expect(result.succeeded).toBe(0);
    expect(result.failed).toBe(1);
    expect(q.getSize()).toBe(1); // still queued

    const item = mustExist(q.getItems()[0], "first queue item");
    expect(item.attempts).toBe(1);
    expect(item.state).toBe("retrying");

    // attempt increment is persisted
    expect((persistedQueue()[0] as { attempts: number }).attempts).toBe(1);
  });
});

describe("OfflineQueue — retry + dead-letter after N failures", () => {
  it("transitions an item to dead-letter once attempts reach maxRetries", async () => {
    const { OfflineQueue } = await loadQueue();
    const maxRetries = 3;
    const q = new OfflineQueue(50, maxRetries);
    await q.enqueue("a".repeat(40), "m:A", null, "A", "srv1");

    const send = vi.fn(() => Promise.reject(new Error("network down")));

    // process repeatedly until dead-letter
    for (let i = 0; i < maxRetries; i++) {
      await q.processQueue(send);
    }

    const item = mustExist(q.getItems()[0], "first queue item");
    expect(item.attempts).toBe(maxRetries);
    expect(item.state).toBe("dead-letter");
    expect(item.lastError).toContain("network down");

    // a dead-letter item is NOT sent again on subsequent processing
    send.mockClear();
    await q.processQueue(send);
    expect(send).not.toHaveBeenCalled();

    // dead-letter state persisted
    expect((persistedQueue()[0] as { state: string }).state).toBe("dead-letter");
  });

  it("retryItem resets a dead-letter item back to queued so it is retried again", async () => {
    const { OfflineQueue } = await loadQueue();
    const q = new OfflineQueue(50, 1);
    const item = await q.enqueue("a".repeat(40), "m:A", null, "A", "srv1");

    const failing = vi.fn(() => Promise.resolve(false));
    await q.processQueue(failing);
    expect(mustExist(q.getItems()[0], "first queue item").state).toBe("dead-letter");

    // operator-driven retry resets the item
    const reset = await q.retryItem(item.id);
    expect(reset).toBe(true);
    expect(mustExist(q.getItems()[0], "first queue item").state).toBe("queued");
    expect(mustExist(q.getItems()[0], "first queue item").attempts).toBe(0);

    // now a working sender drains it
    const ok = vi.fn(() => Promise.resolve(true));
    const result = await q.processQueue(ok);
    expect(ok).toHaveBeenCalledTimes(1);
    expect(result.succeeded).toBe(1);
    expect(q.getSize()).toBe(0);
  });
});

describe("OfflineQueue — remove + clear", () => {
  it("dequeue removes a single item by id and persists", async () => {
    const { OfflineQueue } = await loadQueue();
    const q = new OfflineQueue();
    const a = await q.enqueue("a".repeat(40), "m:A", null, "A", "srv1");
    await q.enqueue("b".repeat(40), "m:B", null, "B", "srv1");

    expect(await q.dequeue(a.id)).toBe(true);
    expect(q.getItems().map((i) => i.torrent.displayName)).toEqual(["B"]);
    expect(persistedQueue()).toHaveLength(1);

    expect(await q.dequeue("does-not-exist")).toBe(false);
  });

  it("clear empties the queue and persists the empty state", async () => {
    const { OfflineQueue } = await loadQueue();
    const q = new OfflineQueue();
    await q.enqueue("a".repeat(40), "m:A", null, "A", "srv1");
    await q.enqueue("b".repeat(40), "m:B", null, "B", "srv1");

    await q.clear();
    expect(q.getSize()).toBe(0);
    expect(persistedQueue()).toHaveLength(0);
  });
});

describe("OfflineQueue — persistence survives re-instantiation", () => {
  it("a fresh queue.init() loads the items the previous instance persisted", async () => {
    const { OfflineQueue } = await loadQueue();

    // first instance enqueues + persists
    const q1 = new OfflineQueue();
    await q1.enqueue("a".repeat(40), "m:A", null, "Persisted A", "srv1", "high");
    await q1.enqueue("b".repeat(40), "m:B", null, "Persisted B", "srv1");

    // brand-new instance over the SAME backing storage reads them back
    const q2 = new OfflineQueue();
    await q2.init();
    expect(q2.getSize()).toBe(2);
    expect(q2.getItems().map((i) => i.torrent.displayName)).toEqual([
      "Persisted A",
      "Persisted B",
    ]);
    expect(mustExist(q2.getItems()[0], "first queue item").priority).toBe("high");
  });
});

describe("OfflineQueue — auto-processing timer", () => {
  it("startAutoProcessing drains the queue on its interval and stop halts it", async () => {
    vi.useFakeTimers();
    try {
      const { OfflineQueue } = await loadQueue();
      const q = new OfflineQueue();
      await q.enqueue("a".repeat(40), "m:A", null, "A", "srv1");

      const send = vi.fn(() => Promise.resolve(true));
      q.startAutoProcessing(send, 1000);

      await vi.advanceTimersByTimeAsync(1000);
      expect(send).toHaveBeenCalledTimes(1);
      expect(q.getSize()).toBe(0);

      q.stopAutoProcessing();
      send.mockClear();
      await q.enqueue("b".repeat(40), "m:B", null, "B", "srv1");
      await vi.advanceTimersByTimeAsync(5000);
      expect(send).not.toHaveBeenCalled(); // timer stopped → no auto drain
    } finally {
      vi.useRealTimers();
    }
  });
});
