/**
 * @fileoverview Challenge-scoped evidence harness for the BobaLink
 * offline-queue failure→recover→drain path (Phase 8 — Challenges / §11.4.83).
 *
 * This is NOT a normal unit/integration spec — it is the Node harness invoked by
 * `challenges/extension/offline_queue_recovery_challenge.sh`. It drives the REAL,
 * shipped {@link OfflineQueue} module end-to-end (no re-implementation) against
 * the SAME in-memory chrome.storage fake the production storage layer uses, and
 * PERSISTS the captured runtime evidence to
 * `challenges/extension/.evidence/<run>.json`. The bash challenge then re-reads
 * that evidence file and asserts on it, so the PASS verdict is backed by an
 * auditable artefact per §11.4.83 / §11.4.69 (feature class: `storage_write`
 * — the queue's persisted retry state).
 *
 * The path exercised (the operator's real "Boba was offline, then came back"):
 *
 *   1. FAIL — N items are enqueued into the REAL OfflineQueue. A FAILING injected
 *      sender (throws on every call) is processed against the queue MAX_RETRIES
 *      times. We assert the items PERSIST to chrome.storage.local across the
 *      failure window (read the backing store back) and DEAD-LETTER once their
 *      attempts reach the retry budget — nothing is silently lost.
 *
 *   2. RECOVER + DRAIN — the dead-lettered items are reset for retry
 *      (`retryItem`, the operator-driven "Boba is back" action), then a WORKING
 *      injected sender is processed. We capture which items the sender actually
 *      received (the real POST surrogate) and assert ALL of them drained and the
 *      queue (and its persisted state) is empty afterward.
 *
 * Only the network SEND is injected (the queue imports no boba-client by design)
 * — every queue mechanic (enqueue / persist / FIFO / priority / retry-state /
 * dead-letter / drain / clear) is the real shipped code. The spec FAILS (and
 * writes no `pass:true` evidence) if the queue silently drops items, never
 * dead-letters, or never drains — so a no-op stub of the queue cannot produce a
 * green run. NO real credentials, NO private-tracker payload (§11.4.10).
 *
 * @module challenges/extension/offline_queue_recovery.evidence
 */

import { describe, it, expect, beforeEach } from "vitest";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { createChromeStorageFake } from "../../extension/tests/unit/chrome-fake";
import { OfflineQueue, DEFAULT_MAX_RETRIES } from "../../extension/src/api/queue";
import type { OfflineQueueItem, QueueSender } from "../../extension/src/api/queue";

const N_ITEMS = 4;
const SERVER_ID = "boba-merge-7187";
const STORAGE_KEY = "bobalink_queue";

const EVIDENCE_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  ".evidence",
  "offline_queue_recovery.json",
);

let fake: ReturnType<typeof createChromeStorageFake>;

beforeEach(() => {
  fake = createChromeStorageFake();
  (globalThis as unknown as { chrome: unknown }).chrome = fake.chrome;
});

/**
 * Read the persisted queue array straight out of the fake backing store, as a
 * DEEP snapshot. The OfflineQueue persists its live item objects by reference,
 * so a shallow read would later reflect Stage-2 mutations (retryItem resets
 * attempts/state, drain removes items). Deep-copying here freezes the bytes at
 * read time — the evidence we capture is what was persisted at that moment.
 */
function persistedQueue(): OfflineQueueItem[] {
  const raw = fake.store.get(STORAGE_KEY);
  if (!Array.isArray(raw)) return [];
  return JSON.parse(JSON.stringify(raw)) as OfflineQueueItem[];
}

/** A sender that always throws — simulates Boba being unreachable. */
function makeFailingSender(): { send: QueueSender; getCalls: () => number } {
  let calls = 0;
  const send: QueueSender = () => {
    calls++;
    return Promise.reject(new Error("network down: Boba unreachable"));
  };
  return { send, getCalls: () => calls };
}

/** A sender that always succeeds and records which item infohashes it drained. */
function makeWorkingSender(): { send: QueueSender; drained: string[] } {
  const drained: string[] = [];
  const send: QueueSender = (item: OfflineQueueItem) => {
    drained.push(item.torrent.infohash);
    return Promise.resolve(true);
  };
  return { send, drained };
}

describe("CHALLENGE: BobaLink offline-queue failure → recover → drain (real OfflineQueue)", () => {
  it(`persists + dead-letters ${String(N_ITEMS)} items under a failing sender, then drains them all under a working sender`, async () => {
    const queue = new OfflineQueue();

    // ── STAGE 1: enqueue N items → assert they PERSIST to chrome.storage ───────
    for (let i = 0; i < N_ITEMS; i++) {
      const infohash = `infohash${String(i).padStart(40 - "infohash".length, "0")}`.slice(0, 40);
      await queue.enqueue(
        infohash,
        `magnet:?xt=urn:btih:${infohash}&dn=helixqa-queue-${String(i)}`,
        null,
        `Queued item ${String(i)}`,
        SERVER_ID,
      );
    }
    expect(queue.getSize()).toBe(N_ITEMS);
    // Read the backing store back — real persisted bytes, not a mock that agrees.
    const persistedAfterEnqueue = persistedQueue();
    expect(persistedAfterEnqueue).toHaveLength(N_ITEMS);

    // ── STAGE 1b: process against a FAILING sender MAX_RETRIES times ───────────
    const failing = makeFailingSender();
    for (let attempt = 0; attempt < DEFAULT_MAX_RETRIES; attempt++) {
      await queue.processQueue(failing.send);
    }
    // The failing sender was actually invoked (no silent skip).
    expect(failing.getCalls()).toBeGreaterThanOrEqual(N_ITEMS);

    // Nothing lost: all N items still present, all dead-lettered.
    const deadLettered = queue.getDeadLetterItems();
    expect(deadLettered).toHaveLength(N_ITEMS);
    expect(queue.getSize()).toBe(N_ITEMS);
    // Dead-letter state survived to chrome.storage (read a DEEP snapshot back so
    // Stage-2 mutations cannot retroactively change these captured facts).
    const persistedAfterFail = persistedQueue();
    // Snapshot the failure-phase facts NOW, before Stage 2 resets/drains items.
    const failingSenderCalls = failing.getCalls();
    const deadLetteredCount = deadLettered.length;
    const persistedAfterFailCount = persistedAfterFail.length;
    const allDeadLettered = persistedAfterFail.every((i) => i.state === "dead-letter");
    const allReachedRetryBudget = persistedAfterFail.every(
      (i) => i.attempts >= DEFAULT_MAX_RETRIES,
    );
    expect(persistedAfterFail).toHaveLength(N_ITEMS);
    expect(allDeadLettered).toBe(true);
    expect(allReachedRetryBudget).toBe(true);

    // ── STAGE 2: RECOVER (reset dead-letter → queued) + DRAIN (working sender) ──
    for (const item of deadLettered) {
      const ok = await queue.retryItem(item.id);
      expect(ok).toBe(true);
    }
    const working = makeWorkingSender();
    const drainResult = await queue.processQueue(working.send);

    // ALL items drained: the working sender received every one, queue is empty.
    expect(working.drained).toHaveLength(N_ITEMS);
    expect(drainResult.succeeded).toBe(N_ITEMS);
    expect(drainResult.failed).toBe(0);
    expect(queue.getSize()).toBe(0);
    // Persisted state is now empty (read it back).
    expect(persistedQueue()).toHaveLength(0);

    // ── EVIDENCE: persist the captured counts for the bash challenge ───────────
    const evidence = {
      pass: true,
      capturedAt: new Date().toISOString(),
      feature: "storage_write", // §11.4.69 taxonomy class
      config: {
        enqueued: N_ITEMS,
        maxRetries: DEFAULT_MAX_RETRIES,
        serverId: SERVER_ID,
      },
      failurePhase: {
        failingSenderCalls,
        persistedAfterEnqueue: persistedAfterEnqueue.length,
        persistedAfterFail: persistedAfterFailCount,
        deadLetteredCount,
        allDeadLettered,
        allReachedRetryBudget,
      },
      recoverPhase: {
        drainedCount: working.drained.length,
        succeeded: drainResult.succeeded,
        failed: drainResult.failed,
        remaining: drainResult.remaining,
        persistedAfterDrain: persistedQueue().length,
        queueSizeAfterDrain: queue.getSize(),
      },
    };
    mkdirSync(dirname(EVIDENCE_PATH), { recursive: true });
    writeFileSync(EVIDENCE_PATH, JSON.stringify(evidence, null, 2) + "\n", "utf8");
  });
});
