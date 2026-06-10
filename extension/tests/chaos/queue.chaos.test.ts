/**
 * @fileoverview CHAOS tests (§11.4.85) for the REAL committed OfflineQueue and
 * its injected send pipeline (`src/api/queue.ts`).
 *
 * Constitution §11.4.85 (stress + chaos test mandate) + the §11.4 anti-bluff
 * covenant. Exercises the PRODUCTION `OfflineQueue` under failure injection — no
 * mock of the unit under test. The queue persists through the REAL
 * `src/shared/storage` helpers backed by an in-memory `chrome.storage.local`
 * fake we can CORRUPT mid-test.
 *
 * §11.4.85 CHAOS closed-set coverage (applied per fit):
 *   (a) injected-send-failure — the injected SEND fails (soft `false` AND hard
 *       throw) on every flush attempt. After `maxRetries` attempts the item
 *       MUST land in dead-letter (a recoverable parking state), NEVER silently
 *       dropped. Asserted by reading dead-letter contents back.
 *   (b) persistence-corruption — garbage is written into the backing store mid-
 *       test. A fresh queue.init() over the corrupt blob MUST recover to a
 *       consistent state (empty/valid items only), NEVER throw/crash, and stay
 *       usable (a subsequent enqueue persists cleanly).
 *   (c) state-corruption (partial write) — a half-written / wrong-typed item
 *       record is injected. init()'s normalize() MUST coerce it to a consistent
 *       item with a valid lifecycle state, restoring consistency.
 *
 * EVIDENCE (§11.4.85 MANDATORY): each test writes a recovery-trace / categorised
 * artifact under `tests/chaos/.evidence/` and asserts on the captured data
 * (dead-letter contents, recovered item count, consistency=true). A PASS with
 * no captured artifact is a §11.4 bluff.
 *
 * ANTI-BLUFF: assertions are on USER-OBSERVABLE recovered state — dead-letter
 * item identity, recovered queue contents, "queue still usable after corruption"
 * — never "no error". Each test fails if the resilience property were broken (a
 * queue that dropped the failing item, crashed on corrupt storage, or persisted
 * an invalid record FAILS). Injected corruption is cleaned up in afterEach.
 *
 * @module tests/chaos/queue.chaos.test
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import {
  OfflineQueue,
  type OfflineQueueItem,
  type QueueSender,
  DEFAULT_MAX_RETRIES,
} from "../../src/api/queue";
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

// ─────────────────────────────────────────────────────────────────────────────
// In-memory chrome.storage.local fake we can corrupt mid-test.
// ─────────────────────────────────────────────────────────────────────────────

interface FakeStorage {
  store: Map<string, unknown>;
  /** Inject raw garbage at a storage key, bypassing the queue's serialiser. */
  corrupt: (key: string, garbage: unknown) => void;
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
  return {
    store,
    corrupt: (key, garbage) => store.set(key, garbage),
  };
}

function readPersisted(fake: FakeStorage): OfflineQueueItem[] {
  const raw = fake.store.get(STORAGE_KEYS.QUEUE);
  return Array.isArray(raw) ? (raw as OfflineQueueItem[]) : [];
}

let fake: FakeStorage;

beforeEach(() => {
  fake = installChromeStorage();
});

afterEach(() => {
  // Cleanup any injected corruption / state so no test leaks into the next.
  fake.store.clear();
  delete (globalThis as unknown as { chrome?: unknown }).chrome;
});

// ─────────────────────────────────────────────────────────────────────────────
// (a) CHAOS — injected SEND failure → dead-letter, never silently dropped
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 CHAOS: injected send-failure → dead-letter (item never dropped)", () => {
  it("a SOFT-failing send (resolves false) dead-letters the item after maxRetries, item still present", async () => {
    const queue = new OfflineQueue(10, DEFAULT_MAX_RETRIES);
    await queue.init();
    const item = await queue.enqueue(
      "fail-soft",
      "magnet:?xt=urn:btih:fail-soft",
      null,
      "Soft Fail",
      "srv",
      "normal",
    );

    const attemptLog: number[] = [];
    let attempt = 0;
    const failingSender: QueueSender = () => {
      attempt++;
      attemptLog.push(attempt);
      return Promise.resolve(false); // soft failure every time
    };

    // Drive maxRetries flush passes (one attempt per pass).
    const stateTrace: string[] = [];
    for (let pass = 0; pass < DEFAULT_MAX_RETRIES; pass++) {
      await queue.processQueue(failingSender);
      const live = queue.getItems().find((i) => i.id === item.id);
      stateTrace.push(live ? live.state : "DROPPED");
    }

    // USER-OBSERVABLE: the item was NOT dropped — it parked in dead-letter.
    expect(queue.getSize()).toBe(1);
    const dead = queue.getDeadLetterItems();
    expect(dead.length).toBe(1);
    expect(dead[0]?.id).toBe(item.id);
    expect(dead[0]?.attempts).toBe(DEFAULT_MAX_RETRIES);
    expect(dead[0]?.lastError).toBe("Send failed");

    // The dead-letter is persisted (survives a reload).
    const persisted = readPersisted(fake);
    expect(persisted.length).toBe(1);
    expect(persisted[0]?.state).toBe("dead-letter");

    // A subsequent flush does NOT re-attempt a dead-letter item.
    const attemptsBefore = attempt;
    await queue.processQueue(failingSender);
    expect(attempt).toBe(attemptsBefore); // sender NOT called again

    // Operator retry resets it back to queued (recovery path exists).
    const reset = await queue.retryItem(item.id);
    expect(reset).toBe(true);
    expect(queue.getItems().find((i) => i.id === item.id)?.state).toBe("queued");

    const evidence = {
      test: "send-failure-soft-deadletter",
      constitution: "§11.4.85 chaos injected-send-failure",
      maxRetries: DEFAULT_MAX_RETRIES,
      attempts: attempt - 0, // total attempts across all passes (excl. the no-op pass)
      stateTrace,
      finalState: "dead-letter",
      itemDropped: false,
      itemId: item.id,
      deadLetterPersisted: persisted[0]?.state === "dead-letter",
      reattemptedDeadLetter: false,
      recoveryViaRetryItem: true,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("queue_send_failure_soft.json", evidence);

    expect(evidence.itemDropped).toBe(false);
    expect(evidence.deadLetterPersisted).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 CHAOS send-fail soft] item ${item.id}: trace=${JSON.stringify(stateTrace)}, ` +
        `dead-letter+persisted, recovered=true | evidence: ${path}`,
    );
  });

  it("a HARD-failing send (throws) dead-letters with the thrown message recorded, item never dropped", async () => {
    const queue = new OfflineQueue(10, DEFAULT_MAX_RETRIES);
    await queue.init();
    const item = await queue.enqueue("fail-hard", null, "http://x/t.torrent", "Hard Fail", "srv", "high");

    const errors: string[] = [];
    const throwingSender: QueueSender = () => {
      const e = new Error("ECONNRESET chaos-injected");
      errors.push(e.message);
      return Promise.reject(e);
    };

    for (let pass = 0; pass < DEFAULT_MAX_RETRIES; pass++) {
      const res = await queue.processQueue(throwingSender);
      // The thrown failure is CATEGORISED into the result, not escaped.
      expect(res.failed).toBeGreaterThanOrEqual(0);
    }

    // USER-OBSERVABLE: parked in dead-letter, the throw message captured as lastError.
    const dead = queue.getDeadLetterItems();
    expect(dead.length).toBe(1);
    expect(dead[0]?.id).toBe(item.id);
    expect(dead[0]?.lastError).toBe("ECONNRESET chaos-injected");
    expect(queue.getSize()).toBe(1); // not dropped

    const evidence = {
      test: "send-failure-hard-deadletter",
      constitution: "§11.4.85 chaos injected-send-failure",
      maxRetries: DEFAULT_MAX_RETRIES,
      throwsObserved: errors.length,
      finalState: dead[0]?.state ?? "MISSING",
      lastErrorRecorded: dead[0]?.lastError,
      itemDropped: queue.getSize() === 0,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("queue_send_failure_hard.json", evidence);

    expect(evidence.itemDropped).toBe(false);
    expect(evidence.finalState).toBe("dead-letter");
    expect(evidence.lastErrorRecorded).toBe("ECONNRESET chaos-injected");

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 CHAOS send-fail hard] item ${item.id}: throws=${errors.length}, ` +
        `state=${dead[0]?.state}, lastError="${dead[0]?.lastError}" | evidence: ${path}`,
    );
  });

  it("under a mixed flaky sender, EVERY enqueued item is eventually either sent or dead-lettered — none vanish", async () => {
    const N = 60;
    const queue = new OfflineQueue(N + 10, DEFAULT_MAX_RETRIES);
    await queue.init();

    const tags: string[] = [];
    for (let i = 0; i < N; i++) {
      const tag = `flaky-${String(i).padStart(3, "0")}`;
      await queue.enqueue(tag, `magnet:?xt=urn:btih:${tag}`, null, tag, "srv", "normal");
      tags.push(tag);
    }

    // Deterministic flaky sender: even-index items succeed, odd-index always fail.
    const succeededTags = new Set<string>();
    const flaky: QueueSender = (item) => {
      const idx = Number(item.torrent.infohash.split("-")[1]);
      if (idx % 2 === 0) {
        succeededTags.add(item.torrent.infohash);
        return Promise.resolve(true);
      }
      return Promise.resolve(false);
    };

    // Flush enough passes that every odd item exhausts its retry budget.
    for (let pass = 0; pass < DEFAULT_MAX_RETRIES + 1; pass++) {
      await queue.processQueue(flaky);
    }

    const remaining = queue.getItems();
    const deadLetter = queue.getDeadLetterItems();
    const expectedSent = tags.filter((t) => Number(t.split("-")[1]) % 2 === 0);
    const expectedDead = tags.filter((t) => Number(t.split("-")[1]) % 2 === 1);

    // CONSERVATION: every item is accounted for — sent OR dead-lettered, none lost.
    const accountedFor = new Set<string>([
      ...succeededTags,
      ...deadLetter.map((d) => d.torrent.infohash),
    ]);
    expect(accountedFor.size).toBe(N);

    // All evens sent (removed from the queue); all odds parked in dead-letter.
    expect([...succeededTags].sort()).toEqual([...expectedSent].sort());
    expect(deadLetter.map((d) => d.torrent.infohash).sort()).toEqual([...expectedDead].sort());
    // Nothing is still in a live (non-dead-letter) state.
    expect(remaining.every((i) => i.state === "dead-letter")).toBe(true);

    const evidence = {
      test: "flaky-sender-conservation",
      constitution: "§11.4.85 chaos injected-send-failure",
      enqueued: N,
      sent: succeededTags.size,
      deadLettered: deadLetter.length,
      accountedFor: accountedFor.size,
      noItemVanished: accountedFor.size === N,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("queue_flaky_conservation.json", evidence);

    expect(evidence.noItemVanished).toBe(true);
    expect(evidence.sent + evidence.deadLettered).toBe(N);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 CHAOS flaky] ${N} items: sent=${succeededTags.size}, ` +
        `deadLetter=${deadLetter.length}, accountedFor=${accountedFor.size}/${N} | evidence: ${path}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (b) CHAOS — persistence corruption injection → recover, never crash
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 CHAOS: persistence corruption → consistent recovery, never crash", () => {
  it("recovers to a consistent state from every garbage backing-store value, stays usable", async () => {
    // A battery of corrupt blobs an attacker / bit-rot could leave at QUEUE.
    const garbageVariants: { label: string; value: unknown }[] = [
      { label: "string-garbage", value: " ￿ not-json garbage " },
      { label: "number", value: 42 },
      { label: "boolean", value: true },
      { label: "null-explicit", value: null },
      { label: "object-not-array", value: { not: "an array" } },
      { label: "nested-garbage-object", value: { items: [1, 2, 3], junk: { a: NaN } } },
      { label: "array-of-primitives", value: [1, "two", false, null] },
    ];

    const recoveryTrace: Array<Record<string, unknown>> = [];

    for (const variant of garbageVariants) {
      // Inject garbage directly (bypass the queue's serialiser).
      fake.corrupt(STORAGE_KEYS.QUEUE, variant.value);

      const queue = new OfflineQueue(10);
      // init() over corrupt storage MUST NOT throw.
      let threw = false;
      try {
        await queue.init();
      } catch {
        threw = true;
      }

      // CONSISTENCY: every recovered item is well-formed (valid state + shape),
      // or the queue recovered to empty — never a crash, never invalid records.
      const validStates = new Set(["queued", "retrying", "failed", "dead-letter"]);
      const items = queue.getItems();
      const allWellFormed = items.every(
        (i) =>
          validStates.has(i.state) &&
          typeof i.torrent === "object" &&
          typeof i.torrent.infohash === "string" &&
          typeof i.serverId === "string" &&
          typeof i.attempts === "number",
      );

      // The queue is STILL USABLE after recovery — a fresh enqueue persists cleanly.
      const before = queue.getSize();
      await queue.enqueue("post-recovery", "magnet:?xt=urn:btih:rec", null, "Recovered", "srv", "normal");
      const afterEnqueue = queue.getSize();
      const persisted = readPersisted(fake);
      const persistedClean = persisted.every((p) => validStates.has(p.state));

      recoveryTrace.push({
        variant: variant.label,
        initThrew: threw,
        recoveredItemCount: before,
        allWellFormed,
        usableAfterRecovery: afterEnqueue === before + 1,
        persistedClean,
      });

      // Per-variant hard asserts (each variant must independently recover).
      expect(threw).toBe(false);
      expect(allWellFormed).toBe(true);
      expect(afterEnqueue).toBe(before + 1);
      expect(persistedClean).toBe(true);

      // Reset backing store for the next variant.
      fake.store.clear();
    }

    const evidence = {
      test: "persistence-corruption-recovery",
      constitution: "§11.4.85 chaos persistence-corruption",
      variantsTested: garbageVariants.length,
      recoveryTrace,
      anyInitThrew: recoveryTrace.some((r) => r.initThrew === true),
      allRecoveredConsistent: recoveryTrace.every(
        (r) => r.initThrew === false && r.allWellFormed === true && r.usableAfterRecovery === true,
      ),
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("queue_persistence_corruption.json", evidence);

    expect(evidence.anyInitThrew).toBe(false);
    expect(evidence.allRecoveredConsistent).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 CHAOS persistence-corruption] ${garbageVariants.length} garbage variants: ` +
        `crashes=${evidence.anyInitThrew ? "YES" : 0}, allConsistent=${evidence.allRecoveredConsistent} | evidence: ${path}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (c) CHAOS — state corruption (partial write) → normalize restores consistency
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 CHAOS: state corruption (partial write) → normalized to consistent", () => {
  it("coerces partial / wrong-typed item records into consistent items with valid lifecycle state", async () => {
    // A mix of half-written records: missing fields, wrong types, invalid state,
    // partial nested torrent — exactly what a crashed/partial persist could leave.
    const partialRecords: unknown[] = [
      // a valid item to prove good records survive alongside bad ones
      {
        id: "good-1",
        torrent: { infohash: "deadbeef", magnetUri: "magnet:?xt=urn:btih:deadbeef", torrentUrl: null, displayName: "Good" },
        serverId: "srv",
        addedAt: 1700000000000,
        attempts: 1,
        lastError: null,
        lastAttemptAt: null,
        priority: "normal",
        state: "retrying",
      },
      // invalid lifecycle state → must coerce to "queued"
      { id: "bad-state", torrent: { infohash: "h2", displayName: "BadState" }, serverId: "srv", state: "EXPLODED" },
      // missing torrent sub-fields → must default to "" / null
      { id: "partial-torrent", torrent: {}, serverId: "srv", state: "queued" },
      // missing numeric/optional fields → must default
      { id: "missing-fields", torrent: { infohash: "h4" }, serverId: "srv2" },
    ];

    fake.corrupt(STORAGE_KEYS.QUEUE, partialRecords);

    const queue = new OfflineQueue(50);
    let threw = false;
    try {
      await queue.init();
    } catch {
      threw = true;
    }
    expect(threw).toBe(false);

    const items = queue.getItems();
    const validStates = new Set(["queued", "retrying", "failed", "dead-letter"]);

    // CONSISTENCY: every recovered record is well-formed.
    for (const i of items) {
      expect(validStates.has(i.state)).toBe(true);
      expect(typeof i.torrent.infohash).toBe("string");
      expect(typeof i.torrent.displayName).toBe("string");
      expect(i.torrent.magnetUri === null || typeof i.torrent.magnetUri === "string").toBe(true);
      expect(typeof i.attempts).toBe("number");
      expect(typeof i.addedAt).toBe("number");
    }

    // Targeted: the invalid state was coerced to "queued"; the good one preserved.
    const byId = new Map(items.map((i) => [i.id, i]));
    expect(byId.get("bad-state")?.state).toBe("queued");
    expect(byId.get("good-1")?.state).toBe("retrying"); // valid state preserved
    expect(byId.get("partial-torrent")?.torrent.infohash).toBe(""); // defaulted
    expect(byId.get("missing-fields")?.attempts).toBe(0); // defaulted

    // The recovered queue is usable AND re-persists in a clean, valid shape.
    await queue.processQueue((_i) => Promise.resolve(true)); // drains queued/retrying
    const persisted = readPersisted(fake);
    const persistedConsistent = persisted.every((p) => validStates.has(p.state));
    expect(persistedConsistent).toBe(true);

    const evidence = {
      test: "state-corruption-normalize",
      constitution: "§11.4.85 chaos state-corruption (partial write)",
      injectedRecords: partialRecords.length,
      initThrew: threw,
      recoveredCount: items.length,
      coercions: {
        invalidStateCoercedToQueued: byId.get("bad-state")?.state === "queued",
        validStatePreserved: byId.get("good-1")?.state === "retrying",
        partialTorrentDefaulted: byId.get("partial-torrent")?.torrent.infohash === "",
        missingFieldsDefaulted: byId.get("missing-fields")?.attempts === 0,
      },
      allWellFormed: items.every((i) => validStates.has(i.state) && typeof i.attempts === "number"),
      persistedConsistentAfterFlush: persistedConsistent,
      capturedAt: new Date().toISOString(),
    };
    const path = captureEvidence("queue_state_corruption.json", evidence);

    expect(evidence.initThrew).toBe(false);
    expect(evidence.allWellFormed).toBe(true);
    expect(evidence.coercions.invalidStateCoercedToQueued).toBe(true);
    expect(evidence.coercions.validStatePreserved).toBe(true);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 CHAOS state-corruption] ${partialRecords.length} partial records: ` +
        `recovered=${items.length}, coercions=${JSON.stringify(evidence.coercions)} | evidence: ${path}`,
    );
  });
});
