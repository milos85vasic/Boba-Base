/**
 * @fileoverview Anti-bluff unit tests for OfflineQueue PERSISTENCE + RECOVERY
 * across a simulated browser/service-worker RESTART (src/api/queue.ts).
 *
 * GAP THIS FILE CLOSES (verified against the existing queue suites):
 *   - tests/unit/api-queue.test.ts proves a fresh `init()` restores 2 freshly
 *     ENQUEUED ("queued") items — but never restores a DEAD-LETTERED item, a
 *     PARTIALLY-DRAINED remainder, or a multi-priority/attempt-bearing snapshot
 *     through a fresh instance.
 *   - tests/chaos/queue.chaos.test.ts asserts dead-letter is written to storage
 *     via `readPersisted` (raw bytes) but never re-loads it into a FRESH
 *     OfflineQueue + init() to prove the restored instance treats it as
 *     dead-letter (and does NOT re-send it).
 *   - tests/stress/queue.stress.test.ts checks storage is EMPTY after a full
 *     flush, but never proves a fresh instance after a PARTIAL drain restores
 *     exactly the un-sent remainder, in order, and does not re-send the sent
 *     items.
 *
 * So the genuinely-untested behaviours are the cross-RESTART ones, driven through
 * a real second `new OfflineQueue().init()` over the SAME persisted bytes:
 *   1. enqueue persists to storage under STORAGE_KEYS.QUEUE (raw read-back).
 *   2. a FRESH instance restores persisted items in correct order (survives
 *      "restart").
 *   3. drain on reconnect sends FIFO and removes sent items from storage; a fresh
 *      instance after a FULL drain restores nothing (sent items are NOT re-sent).
 *   4. a PARTIALLY-drained queue persists ONLY the remainder; a fresh instance
 *      restores that remainder in order and re-sends ONLY it (the already-sent
 *      items are not re-sent — the "sent items not removed → re-sent" defect).
 *   5. dead-lettered items are RETAINED across restart (not lost) AND the
 *      restored instance does not auto-send them.
 *
 * BOUNDARY STUB: chrome.storage is faked (the only legitimate boundary). To make
 * the "restart" faithful — a fresh instance re-parsing persisted BYTES, not
 * aliasing the previous instance's in-memory array — this fake DEEP-CLONES on
 * both set and get (chrome.storage serialises across the worker boundary, so a
 * real restart never shares object identity). The unit-under-test is the REAL
 * production OfflineQueue + the REAL src/shared/storage round-trip.
 *
 * ANTI-BLUFF (§11.4 / §11.4.69): every assertion targets user-observable restored
 * state (restored item identity, order, lifecycle state, what the injected sender
 * is/ISN'T called with). Each test fails against a no-op stub of the persist/
 * restore path — e.g. a queue that dropped dead-letters on restart, re-sent
 * already-drained items, or scrambled order would FAIL. Per §11.4.50 no
 * absolute-wall-clock thresholds are asserted.
 *
 * @module tests/unit/offline-queue-persistence.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  OfflineQueue,
  type OfflineQueueItem,
  type QueueSender,
} from "../../src/api/queue";
import { STORAGE_KEYS } from "../../src/shared/constants";

// ─────────────────────────────────────────────────────────────────────────────
// Clone-on-read/write chrome.storage.local fake (faithful restart boundary).
// ─────────────────────────────────────────────────────────────────────────────

interface RestartFake {
  store: Map<string, unknown>;
  /** Raw, deep-cloned read of the persisted queue array (what a restart sees). */
  persisted(): OfflineQueueItem[];
}

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

function installRestartStorage(): RestartFake {
  const store = new Map<string, unknown>();
  const local = {
    get(keys?: string | string[] | null): Promise<Record<string, unknown>> {
      const out: Record<string, unknown> = {};
      if (keys === null || keys === undefined) {
        for (const [k, v] of store) out[k] = clone(v);
        return Promise.resolve(out);
      }
      const list = Array.isArray(keys) ? keys : [keys];
      for (const k of list) if (store.has(k)) out[k] = clone(store.get(k));
      return Promise.resolve(out);
    },
    set(items: Record<string, unknown>): Promise<void> {
      for (const [k, v] of Object.entries(items)) store.set(k, clone(v));
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
  return {
    store,
    persisted(): OfflineQueueItem[] {
      const raw = store.get(STORAGE_KEYS.QUEUE);
      return Array.isArray(raw) ? clone(raw as OfflineQueueItem[]) : [];
    },
  };
}

let fake: RestartFake;

beforeEach(() => {
  fake = installRestartStorage();
});

afterEach(() => {
  fake.store.clear();
  delete (globalThis as unknown as { chrome?: unknown }).chrome;
});

/** "Restart": construct a brand-new queue over the SAME backing store + init(). */
async function restart(maxSize?: number, maxRetries?: number): Promise<OfflineQueue> {
  const q = maxSize !== undefined ? new OfflineQueue(maxSize, maxRetries) : new OfflineQueue();
  await q.init();
  return q;
}

// ─────────────────────────────────────────────────────────────────────────────

describe("OfflineQueue persistence — enqueue writes through to storage", () => {
  it("persists an enqueued item under STORAGE_KEYS.QUEUE (raw bytes read back)", async () => {
    // Regression: if enqueue did not persist (no-op stub), a fresh restart would
    // restore nothing — the offline queue's whole point (survive a restart) breaks.
    const q = new OfflineQueue();
    await q.init();
    await q.enqueue("a".repeat(40), "magnet:?xt=urn:btih:" + "a".repeat(40), null, "Ubuntu ISO", "srv1", "high");

    const persisted = fake.persisted();
    expect(persisted).toHaveLength(1);
    expect(persisted[0]?.torrent.displayName).toBe("Ubuntu ISO");
    expect(persisted[0]?.priority).toBe("high");
    expect(persisted[0]?.state).toBe("queued");
    expect(persisted[0]?.attempts).toBe(0);
  });
});

describe("OfflineQueue recovery — fresh instance restores persisted items in order", () => {
  it("a fresh init() restores a multi-item snapshot in exact insertion order, identity intact", async () => {
    // Regression: a restore that scrambled order (e.g. re-sorted, or rebuilt from
    // a Set) would break FIFO drain ordering after a restart — assert the exact
    // sequence + per-item identity is preserved across the instance boundary.
    const q1 = new OfflineQueue();
    await q1.init();
    const names = ["First", "Second", "Third", "Fourth", "Fifth"];
    for (let i = 0; i < names.length; i++) {
      await q1.enqueue(String(i).repeat(40), `magnet:?n${i}`, null, names[i] as string, "srv1");
    }
    const idsBefore = q1.getItems().map((i) => i.id);

    const q2 = await restart();

    expect(q2.getSize()).toBe(names.length);
    expect(q2.getItems().map((i) => i.torrent.displayName)).toEqual(names);
    // Item IDs survive the round-trip (restore preserves identity, not just shape).
    expect(q2.getItems().map((i) => i.id)).toEqual(idsBefore);
  });

  it("restores per-item lifecycle fields (attempts, lastError, priority) across restart", async () => {
    // Regression: a restore that reset attempts/lastError to defaults would lose
    // a partly-retried item's progress, re-spending its retry budget after a
    // restart. Drive one failed pass, then restore and assert the progress survived.
    const q1 = new OfflineQueue(50, 5);
    await q1.init();
    await q1.enqueue("h".repeat(40), "m:A", null, "Retried", "srv1", "low");

    const softFail: QueueSender = () => Promise.resolve(false);
    await q1.processQueue(softFail); // attempts -> 1, state -> retrying

    const q2 = await restart(50, 5);
    const restored = q2.getItems()[0] as OfflineQueueItem;
    expect(restored.torrent.displayName).toBe("Retried");
    expect(restored.attempts).toBe(1);
    expect(restored.state).toBe("retrying");
    expect(restored.lastError).toBe("Send failed");
    expect(restored.priority).toBe("low");
  });
});

describe("OfflineQueue drain-on-reconnect — sent items removed from storage", () => {
  it("FULL drain sends FIFO, empties storage, and a fresh restart re-sends NOTHING", async () => {
    // Regression: the named defect — sent items not removed from storage → a
    // restart re-sends them. Drain everything, then restart with a tripwire
    // sender that MUST NOT be called (storage is empty → nothing to re-send).
    const q1 = new OfflineQueue();
    await q1.init();
    const order = ["X", "Y", "Z"];
    for (const n of order) await q1.enqueue(n.repeat(40), `m:${n}`, null, n, "srv1");

    const sent: string[] = [];
    const ok: QueueSender = (i) => {
      sent.push(i.torrent.displayName);
      return Promise.resolve(true);
    };
    await q1.processQueue(ok); // reconnect → drain

    expect(sent).toEqual(order); // FIFO
    expect(q1.getSize()).toBe(0);
    expect(fake.persisted()).toHaveLength(0); // sent items removed from storage

    // Restart over the (now empty) store: tripwire sender proves no re-send.
    const q2 = await restart();
    expect(q2.getSize()).toBe(0);
    const tripwire = vi.fn(() => Promise.resolve(true));
    await q2.processQueue(tripwire);
    expect(tripwire).not.toHaveBeenCalled();
  });

  it("PARTIAL drain persists ONLY the remainder; a fresh restart re-sends ONLY it (sent items not re-sent)", async () => {
    // Regression: this is the precise "sent items not removed from storage →
    // re-sent" hazard at PARTIAL granularity. A sender that succeeds for the
    // first two items and fails the third leaves a one-item remainder. After a
    // restart, ONLY that remainder must be re-attempted — never the two already
    // sent (which would double-send the torrent for the user).
    const q1 = new OfflineQueue(50, 5);
    await q1.init();
    const names = ["Done-1", "Done-2", "Stuck-3"];
    for (const n of names) await q1.enqueue(n.repeat(8), `m:${n}`, null, n, "srv1");

    const firstPassSent: string[] = [];
    const partial: QueueSender = (i) => {
      firstPassSent.push(i.torrent.displayName);
      return Promise.resolve(i.torrent.displayName !== "Stuck-3"); // Stuck-3 soft-fails
    };
    await q1.processQueue(partial);

    // First pass attempted all three (FIFO), but only the remainder persists.
    expect(firstPassSent).toEqual(names);
    const remainderDisk = fake.persisted();
    expect(remainderDisk.map((i) => i.torrent.displayName)).toEqual(["Stuck-3"]);
    expect(remainderDisk[0]?.attempts).toBe(1);

    // Restart: a fresh instance restores ONLY the stuck remainder.
    const q2 = await restart(50, 5);
    expect(q2.getItems().map((i) => i.torrent.displayName)).toEqual(["Stuck-3"]);

    // Now reconnect succeeds: the restored instance re-sends ONLY Stuck-3.
    const secondPassSent: string[] = [];
    const reconnect: QueueSender = (i) => {
      secondPassSent.push(i.torrent.displayName);
      return Promise.resolve(true);
    };
    await q2.processQueue(reconnect);
    expect(secondPassSent).toEqual(["Stuck-3"]); // Done-1/Done-2 NOT re-sent
    expect(q2.getSize()).toBe(0);
    expect(fake.persisted()).toHaveLength(0);
  });
});

describe("OfflineQueue recovery — dead-lettered items retained across restart", () => {
  it("a dead-lettered item is restored as dead-letter after restart and is NOT auto-sent", async () => {
    // Regression: dead-letters must survive a restart (operator can still inspect
    // / retry them) AND the restored instance must not auto-re-attempt them — a
    // queue that dropped dead-letters on restart, or re-sent them, would FAIL.
    const maxRetries = 2;
    const q1 = new OfflineQueue(50, maxRetries);
    await q1.init();
    const dead = await q1.enqueue("d".repeat(40), "m:dead", null, "Dead Letter", "srv1");
    const live = await q1.enqueue("l".repeat(40), "m:live", null, "Still Queued", "srv1");

    // Exhaust the dead item's budget while the live item is dequeued out of the
    // way first, so only the target item is driven to dead-letter.
    await q1.dequeue(live.id);
    const hardFail: QueueSender = () => Promise.reject(new Error("offline"));
    for (let i = 0; i < maxRetries; i++) await q1.processQueue(hardFail);
    expect(q1.getDeadLetterItems().map((d) => d.id)).toEqual([dead.id]);

    // Re-enqueue a fresh live item so the post-restart store has BOTH classes.
    await q1.enqueue("e".repeat(40), "m:e", null, "Fresh Queued", "srv1");

    // Restart.
    const q2 = await restart(50, maxRetries);
    const byName = new Map(q2.getItems().map((i) => [i.torrent.displayName, i]));
    expect(byName.get("Dead Letter")?.state).toBe("dead-letter");
    expect(byName.get("Dead Letter")?.id).toBe(dead.id); // identity retained
    expect(byName.get("Dead Letter")?.attempts).toBe(maxRetries);
    expect(byName.get("Fresh Queued")?.state).toBe("queued");

    // A processing pass on the restored instance sends ONLY the live item; the
    // dead-letter is left untouched (sender never sees it).
    const seen: string[] = [];
    const sender: QueueSender = (i) => {
      seen.push(i.torrent.displayName);
      return Promise.resolve(true);
    };
    await q2.processQueue(sender);
    expect(seen).toEqual(["Fresh Queued"]);

    // The dead-letter remains parked + persisted (not lost, not sent).
    expect(q2.getDeadLetterItems().map((d) => d.id)).toEqual([dead.id]);
    expect(fake.persisted().some((p) => p.id === dead.id && p.state === "dead-letter")).toBe(true);
  });
});
