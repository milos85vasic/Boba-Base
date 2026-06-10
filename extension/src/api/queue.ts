/**
 * @fileoverview Offline FIFO retry queue for BobaLink (Phase 4 — F REFACTOR).
 *
 * When a torrent send fails (network down, server unavailable) the item is
 * queued here for later retry. The queue persists to `chrome.storage.local`
 * under `STORAGE_KEYS.QUEUE` via the committed `src/shared/storage` helper,
 * priority-orders pending items, FIFO-evicts the oldest when over `maxSize`,
 * tracks per-item retry count + lifecycle state, and dead-letters an item once
 * its attempts reach `maxRetries`.
 *
 * Refactor note (F disposition): the reference `queue.ts` imported
 * `qBitTorrentAdapter` + `BobaAPIClient` and performed the network SEND itself.
 * Here the SEND is the boba-client's job (a sibling builds it), so the queue
 * stays decoupled: the actual send is **INJECTED** as a `QueueSender` callback
 * (passed to `processQueue` / `startAutoProcessing`). The queue owns only the
 * enqueue / dequeue / persist / priority-order / FIFO-evict / retry-state /
 * dead-letter mechanics — it imports no boba-client and no qBittorrent code.
 *
 * @module api/queue
 */

import { RETRY_CONFIG, STORAGE_KEYS } from "../shared/constants";
import { createLogger } from "../shared/logger";
import { storageGet, storageSet } from "../shared/storage";
import type { QueueItem as BaseQueueItem, QueueProcessResult } from "../types/api";

const log = createLogger("OfflineQueue");

/**
 * Default maximum queue size to prevent unbounded growth (reference parity).
 */
export const DEFAULT_MAX_SIZE = 50;

/**
 * Default number of attempts before an item is dead-lettered. Reuses the shared
 * `RETRY_CONFIG.MAX_RETRIES` so backoff/retry policy stays single-sourced.
 */
export const DEFAULT_MAX_RETRIES = RETRY_CONFIG.MAX_RETRIES;

/**
 * Default interval between automatic queue-processing attempts (ms).
 */
export const PROCESS_INTERVAL_MS = 60000;

/**
 * Lifecycle state of a queued item.
 *
 * - `queued`     — waiting for its first send attempt.
 * - `retrying`   — failed at least once but still under the retry budget.
 * - `failed`     — terminal-for-this-pass failure (reserved; currently folded
 *                  into `retrying` until the budget is exhausted).
 * - `dead-letter`— exhausted `maxRetries`; will not be auto-sent again until an
 *                  operator calls `retryItem`.
 */
export type QueueItemState = "queued" | "retrying" | "failed" | "dead-letter";

/**
 * A persisted queue item: the committed `QueueItem` shape plus the mutable
 * lifecycle `state` this module tracks. Fields are writable here (the queue
 * mutates attempts / state / lastError in place) while the persisted JSON stays
 * structurally compatible with the base `QueueItem` consumers.
 */
export interface OfflineQueueItem {
  /** Unique ID for this queue item. */
  id: string;
  /** The torrent that should be sent. */
  torrent: {
    infohash: string;
    magnetUri: string | null;
    torrentUrl: string | null;
    displayName: string;
  };
  /** Server ID this should be sent to. */
  serverId: string;
  /** When this item was added to the queue (epoch ms). */
  addedAt: number;
  /** Number of send attempts made so far. */
  attempts: number;
  /** Last error message, if any. */
  lastError: string | null;
  /** When the last attempt was made (epoch ms), or null. */
  lastAttemptAt: number | null;
  /** Priority level. */
  priority: "high" | "normal" | "low";
  /** Lifecycle state. */
  state: QueueItemState;
}

/**
 * The injected network-send dependency. Receives the queue item and resolves
 * `true` on a successful send, `false` on a soft failure. Throwing is treated
 * as a hard failure (the thrown message is recorded as `lastError`).
 *
 * The queue NEVER imports the boba-client — the caller supplies this callback,
 * keeping the queue fully decoupled and unit-testable.
 */
export type QueueSender = (item: OfflineQueueItem) => Promise<boolean>;

/** Static type-compat assertion: an OfflineQueueItem satisfies the base shape. */
type _AssertBaseCompat = OfflineQueueItem extends BaseQueueItem ? true : never;
const _baseCompat: _AssertBaseCompat = true;
void _baseCompat;

/** Priority sort weight — lower sorts first. */
const PRIORITY_ORDER: Readonly<Record<OfflineQueueItem["priority"], number>> = {
  high: 0,
  normal: 1,
  low: 2,
};

/**
 * Persistent offline FIFO retry queue for failed torrent sends.
 */
export class OfflineQueue {
  private items: OfflineQueueItem[] = [];
  private readonly maxSize: number;
  private readonly maxRetries: number;
  private processing = false;
  private processTimer: ReturnType<typeof setInterval> | null = null;

  /**
   * @param maxSize - Maximum number of items retained (FIFO-evicted beyond it).
   * @param maxRetries - Attempts before an item is dead-lettered.
   */
  constructor(
    maxSize: number = DEFAULT_MAX_SIZE,
    maxRetries: number = DEFAULT_MAX_RETRIES,
  ) {
    this.maxSize = Math.max(1, maxSize);
    this.maxRetries = Math.max(1, maxRetries);
  }

  /**
   * Load any previously-persisted items from storage.
   */
  async init(): Promise<void> {
    try {
      const data = await storageGet<OfflineQueueItem[]>(STORAGE_KEYS.QUEUE);
      if (data && Array.isArray(data)) {
        this.items = data.map((raw) => this.normalize(raw));
        log.info(`Loaded ${this.items.length} queued items from storage`);
      }
    } catch (err) {
      log.error("Failed to load queue from storage", err);
    }
  }

  /**
   * Add a torrent to the queue for later sending. Evicts the OLDEST item(s)
   * (FIFO) while the queue is at or over `maxSize` before appending the new one.
   *
   * @param infohash - Torrent infohash.
   * @param magnetUri - Magnet URI (null for file-based torrents).
   * @param torrentUrl - .torrent file URL (null for magnet-based torrents).
   * @param displayName - Human-readable name.
   * @param serverId - Target server ID.
   * @param priority - Queue priority (default "normal").
   * @returns The created queue item.
   */
  async enqueue(
    infohash: string,
    magnetUri: string | null,
    torrentUrl: string | null,
    displayName: string,
    serverId: string,
    priority: "high" | "normal" | "low" = "normal",
  ): Promise<OfflineQueueItem> {
    while (this.items.length >= this.maxSize) {
      const removed = this.items.shift();
      log.warn(`Queue full, evicting oldest item: ${removed?.torrent.displayName}`);
    }

    const item: OfflineQueueItem = {
      id: this.generateItemId(),
      torrent: { infohash, magnetUri, torrentUrl, displayName },
      serverId,
      addedAt: Date.now(),
      attempts: 0,
      lastError: null,
      lastAttemptAt: null,
      priority,
      state: "queued",
    };

    this.items.push(item);
    await this.persist();
    log.info(`Enqueued: ${displayName} (queue size: ${this.items.length})`);
    return item;
  }

  /**
   * Remove an item from the queue by ID.
   *
   * @param itemId - ID of the item to remove.
   * @returns True if the item was found and removed.
   */
  async dequeue(itemId: string): Promise<boolean> {
    const index = this.items.findIndex((i) => i.id === itemId);
    if (index === -1) return false;
    const [removed] = this.items.splice(index, 1);
    await this.persist();
    log.debug(`Dequeued: ${removed?.torrent.displayName}`);
    return true;
  }

  /**
   * Reset a dead-letter (or any) item back to `queued` with a cleared attempt
   * count so the next processing pass retries it. Operator-driven "retry".
   *
   * @param itemId - ID of the item to reset.
   * @returns True if the item was found and reset.
   */
  async retryItem(itemId: string): Promise<boolean> {
    const item = this.items.find((i) => i.id === itemId);
    if (!item) return false;
    item.state = "queued";
    item.attempts = 0;
    item.lastError = null;
    item.lastAttemptAt = null;
    await this.persist();
    log.info(`Reset for retry: ${item.torrent.displayName}`);
    return true;
  }

  /**
   * Process the queue, attempting to send each non-dead-letter item via the
   * INJECTED `send` callback, high priority first then FIFO within a priority.
   *
   * On success the item is removed; on failure its attempt count increments and
   * it stays queued (transitioning to `retrying`, then `dead-letter` once the
   * attempt count reaches `maxRetries`).
   *
   * @param send - Injected network-send dependency (the queue imports no client).
   * @returns Processing result with success/failure counts.
   */
  async processQueue(send: QueueSender): Promise<QueueProcessResult> {
    if (this.processing) {
      log.debug("Queue processing already in progress");
      return this.emptyResult();
    }

    const pending = this.items.filter((i) => i.state !== "dead-letter");
    if (pending.length === 0) {
      return this.emptyResult();
    }

    this.processing = true;
    log.info(`Processing queue: ${pending.length} pending items`);

    try {
      const results: Array<{ itemId: string; success: boolean; error: string | null }> = [];
      const toRemove = new Set<string>();

      const sorted = [...pending].sort(
        (a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority],
      );

      for (const item of sorted) {
        item.attempts++;
        item.lastAttemptAt = Date.now();
        try {
          const success = await send(item);
          if (success) {
            item.lastError = null;
            toRemove.add(item.id);
            results.push({ itemId: item.id, success: true, error: null });
          } else {
            item.lastError = "Send failed";
            this.applyFailureState(item);
            results.push({ itemId: item.id, success: false, error: item.lastError });
          }
        } catch (err) {
          const error = err instanceof Error ? err.message : String(err);
          item.lastError = error;
          this.applyFailureState(item);
          results.push({ itemId: item.id, success: false, error });
          log.error(`Queue item failed: ${item.torrent.displayName}`, err);
        }
      }

      if (toRemove.size > 0) {
        this.items = this.items.filter((i) => !toRemove.has(i.id));
      }
      await this.persist();

      const succeeded = results.filter((r) => r.success).length;
      const failed = results.length - succeeded;
      log.info(
        `Queue processing complete: ${succeeded} sent, ${failed} failed, ${this.items.length} remaining`,
      );

      return {
        processed: results.length,
        succeeded,
        failed,
        remaining: this.items.length,
        results,
      };
    } finally {
      this.processing = false;
    }
  }

  /** Current queue size. */
  getSize(): number {
    return this.items.length;
  }

  /** Read-only snapshot of all queued items. */
  getItems(): readonly OfflineQueueItem[] {
    return this.items.map((i) => ({ ...i, torrent: { ...i.torrent } }));
  }

  /** Items that have exhausted their retry budget. */
  getDeadLetterItems(): readonly OfflineQueueItem[] {
    return this.getItems().filter((i) => i.state === "dead-letter");
  }

  /** Clear all items and persist the empty state. */
  async clear(): Promise<void> {
    this.items = [];
    await this.persist();
    log.info("Queue cleared");
  }

  /**
   * Start automatic processing on a timer using the injected `send`.
   *
   * @param send - Injected network-send dependency.
   * @param intervalMs - Processing interval (default {@link PROCESS_INTERVAL_MS}).
   */
  startAutoProcessing(send: QueueSender, intervalMs: number = PROCESS_INTERVAL_MS): void {
    this.stopAutoProcessing();
    this.processTimer = setInterval(() => {
      this.processQueue(send).catch((err) => {
        log.error("Auto queue processing failed", err);
      });
    }, intervalMs);
    log.debug(`Auto-processing started (${intervalMs}ms interval)`);
  }

  /** Stop automatic processing. */
  stopAutoProcessing(): void {
    if (this.processTimer) {
      clearInterval(this.processTimer);
      this.processTimer = null;
      log.debug("Auto-processing stopped");
    }
  }

  /** Apply the post-failure lifecycle transition (retrying → dead-letter). */
  private applyFailureState(item: OfflineQueueItem): void {
    item.state = item.attempts >= this.maxRetries ? "dead-letter" : "retrying";
  }

  /** Coerce a raw persisted record into a well-formed item with a valid state. */
  private normalize(raw: OfflineQueueItem): OfflineQueueItem {
    const validStates: readonly QueueItemState[] = ["queued", "retrying", "failed", "dead-letter"];
    const state: QueueItemState = validStates.includes(raw.state) ? raw.state : "queued";
    return {
      id: raw.id,
      torrent: {
        infohash: raw.torrent?.infohash ?? "",
        magnetUri: raw.torrent?.magnetUri ?? null,
        torrentUrl: raw.torrent?.torrentUrl ?? null,
        displayName: raw.torrent?.displayName ?? "",
      },
      serverId: raw.serverId,
      addedAt: raw.addedAt ?? Date.now(),
      attempts: raw.attempts ?? 0,
      lastError: raw.lastError ?? null,
      lastAttemptAt: raw.lastAttemptAt ?? null,
      priority: raw.priority ?? "normal",
      state,
    };
  }

  /** Persist the current items to storage (best-effort, logs on failure). */
  private async persist(): Promise<void> {
    try {
      await storageSet(STORAGE_KEYS.QUEUE, this.items);
    } catch (err) {
      log.error("Failed to persist queue", err);
    }
  }

  /** Empty processing result (no-op passes). */
  private emptyResult(): QueueProcessResult {
    return {
      processed: 0,
      succeeded: 0,
      failed: 0,
      remaining: this.items.length,
      results: [],
    };
  }

  /** Generate a unique queue item ID (`queue_<ts>_<rand6>`). */
  private generateItemId(): string {
    return `queue_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  }
}
