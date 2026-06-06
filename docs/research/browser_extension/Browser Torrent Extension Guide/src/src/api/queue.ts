/**
 * @fileoverview Offline queue system for BobaLink.
 *
 * When torrent sends fail due to network issues or server unavailability,
 * items are queued for later retry. The queue persists to chrome.storage.local
 * and is processed when connectivity is restored.
 *
 * @module api/queue
 */

import { createLogger } from "../shared/logger";
import { storageGet, storageSet } from "../shared/storage";
import { STORAGE_KEYS } from "../shared/constants";
import type { QueueItem, QueueProcessResult } from "../types/api";
import type { ServerConfig } from "../types/config";
import { qBitTorrentAdapter } from "./qbittorrent";
import { BobaAPIClient } from "./client";

const log = createLogger("OfflineQueue");

/**
 * Default maximum queue size to prevent unbounded growth.
 */
const DEFAULT_MAX_SIZE = 50;

/**
 * Interval between queue processing attempts (ms).
 */
const PROCESS_INTERVAL_MS = 60000;

/**
 * Delay between individual item sends during batch processing (ms).
 */
const ITEM_SEND_DELAY_MS = 500;

/**
 * Persistent offline queue for failed torrent sends.
 *
 * When a send operation fails due to network/server issues, the torrent
 * is added to this queue. The background script periodically attempts to
 * process the queue, sending queued items when the server is available.
 */
export class OfflineQueue {
  private items: QueueItem[] = [];
  private readonly maxSize: number;
  private processing = false;
  private processTimer: ReturnType<typeof setInterval> | null = null;

  /**
   * Create a new offline queue.
   *
   * @param maxSize - Maximum number of items in the queue
   */
  constructor(maxSize: number = DEFAULT_MAX_SIZE) {
    this.maxSize = maxSize;
  }

  /**
   * Initialize the queue from storage.
   * Loads any previously queued items.
   */
  async init(): Promise<void> {
    try {
      const data = await storageGet<QueueItem[]>(STORAGE_KEYS.QUEUE);
      if (data && Array.isArray(data)) {
        this.items = data;
        log.info(`Loaded ${this.items.length} queued items from storage`);
      }
    } catch (err) {
      log.error("Failed to load queue from storage", err);
    }
  }

  /**
   * Add a torrent to the queue for later sending.
   *
   * @param infohash - Torrent infohash
   * @param magnetUri - Magnet URI (null for file-based torrents)
   * @param torrentUrl - .torrent file URL (null for magnet-based torrents)
   * @param displayName - Human-readable name
   * @param serverId - Target server ID
   * @param priority - Queue priority
   * @returns The created queue item
   */
  async enqueue(
    infohash: string,
    magnetUri: string | null,
    torrentUrl: string | null,
    displayName: string,
    serverId: string,
    priority: "high" | "normal" | "low" = "normal",
  ): Promise<QueueItem> {
    // Remove oldest items if queue is full
    while (this.items.length >= this.maxSize) {
      const removed = this.items.shift();
      log.warn(`Queue full, removing oldest item: ${removed?.torrent.displayName}`);
    }

    const item: QueueItem = {
      id: this.generateItemId(),
      torrent: {
        infohash,
        magnetUri,
        torrentUrl,
        displayName,
      },
      serverId,
      addedAt: Date.now(),
      attempts: 0,
      lastError: null,
      lastAttemptAt: null,
      priority,
    };

    this.items.push(item);
    await this.persist();

    log.info(`Enqueued: ${displayName} (queue size: ${this.items.length})`);
    return item;
  }

  /**
   * Remove an item from the queue by ID.
   *
   * @param itemId - ID of the item to remove
   * @returns True if item was found and removed
   */
  async dequeue(itemId: string): Promise<boolean> {
    const index = this.items.findIndex((i) => i.id === itemId);
    if (index === -1) return false;

    const removed = this.items.splice(index, 1);
    await this.persist();
    log.debug(`Dequeued: ${removed[0]?.torrent.displayName}`);
    return true;
  }

  /**
   * Process the queue, attempting to send all pending items.
   *
   * @param config - Server configuration for sending
   * @returns Processing result with success/failure counts
   */
  async processQueue(config: ServerConfig): Promise<QueueProcessResult> {
    if (this.processing) {
      log.debug("Queue processing already in progress");
      return {
        processed: 0,
        succeeded: 0,
        failed: 0,
        remaining: this.items.length,
        results: [],
      };
    }

    if (this.items.length === 0) {
      return {
        processed: 0,
        succeeded: 0,
        failed: 0,
        remaining: 0,
        results: [],
      };
    }

    this.processing = true;
    log.info(`Processing queue: ${this.items.length} items`);

    try {
      const client = new BobaAPIClient(config.url, config.requestTimeout);
      const adapter = new qBitTorrentAdapter(client);
      const results: QueueProcessResult["results"] = [];
      const toRemove: string[] = [];

      // Sort by priority (high first)
      const sorted = [...this.items].sort((a, b) => {
        const priorityOrder = { high: 0, normal: 1, low: 2 };
        return priorityOrder[a.priority] - priorityOrder[b.priority];
      });

      for (const item of sorted) {
        try {
          // Update attempt tracking
          item.attempts++;
          item.lastAttemptAt = Date.now();

          // Send the torrent
          const success = await this.sendQueuedItem(item, adapter);

          results.push({
            itemId: item.id,
            success,
            error: success ? null : "Send failed",
          });

          if (success) {
            toRemove.push(item.id);
          }

          // Delay between sends
          if (sorted.indexOf(item) < sorted.length - 1) {
            await this.delay(ITEM_SEND_DELAY_MS);
          }
        } catch (err) {
          const error = err instanceof Error ? err.message : String(err);
          item.lastError = error;

          results.push({
            itemId: item.id,
            success: false,
            error,
          });

          log.error(`Queue item failed: ${item.torrent.displayName}`, err);
        }
      }

      // Remove successfully sent items
      this.items = this.items.filter((i) => !toRemove.includes(i.id));
      await this.persist();

      const succeeded = results.filter((r) => r.success).length;
      const failed = results.filter((r) => !r.success).length;

      log.info(
        `Queue processing complete: ${succeeded} sent, ${failed} failed, ${this.items.length} remaining`,
      );

      return {
        processed: sorted.length,
        succeeded,
        failed,
        remaining: this.items.length,
        results,
      };
    } catch (err) {
      log.error("Queue processing failed", err);
      return {
        processed: 0,
        succeeded: 0,
        failed: 0,
        remaining: this.items.length,
        results: [],
      };
    } finally {
      this.processing = false;
    }
  }

  /**
   * Get the current queue size.
   *
   * @returns Number of items in the queue
   */
  getSize(): number {
    return this.items.length;
  }

  /**
   * Get all items in the queue.
   *
   * @returns Array of queue items (read-only copy)
   */
  getItems(): readonly QueueItem[] {
    return [...this.items];
  }

  /**
   * Clear all items from the queue.
   */
  async clear(): Promise<void> {
    this.items = [];
    await this.persist();
    log.info("Queue cleared");
  }

  /**
   * Start automatic queue processing at regular intervals.
   *
   * @param config - Server configuration
   * @param intervalMs - Processing interval in milliseconds
   */
  startAutoProcessing(
    config: ServerConfig,
    intervalMs: number = PROCESS_INTERVAL_MS,
  ): void {
    this.stopAutoProcessing();

    this.processTimer = setInterval(() => {
      this.processQueue(config).catch((err) => {
        log.error("Auto queue processing failed", err);
      });
    }, intervalMs);

    log.debug(`Auto-processing started (${intervalMs}ms interval)`);
  }

  /**
   * Stop automatic queue processing.
   */
  stopAutoProcessing(): void {
    if (this.processTimer) {
      clearInterval(this.processTimer);
      this.processTimer = null;
      log.debug("Auto-processing stopped");
    }
  }

  /**
   * Send a single queued item.
   *
   * @param item - Queue item to send
   * @param adapter - qBitTorrent adapter
   * @returns True if sent successfully
   */
  private async sendQueuedItem(
    item: QueueItem,
    adapter: qBitTorrentAdapter,
  ): Promise<boolean> {
    const { BobaAPIClient } = await import("./client");

    if (item.torrent.magnetUri) {
      return adapter
        .getClient()
        .addTorrentFromMagnet(item.torrent.magnetUri);
    } else if (item.torrent.torrentUrl) {
      return adapter
        .getClient()
        .addTorrentFromFile(
          await this.urlToFile(item.torrent.torrentUrl),
        );
    }

    return false;
  }

  /**
   * Download a .torrent file from URL and convert to File object.
   *
   * @param url - .torrent file URL
   * @returns File object
   */
  private async urlToFile(url: string): Promise<File> {
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status} downloading torrent file`);
    }

    const blob = await response.blob();
    const filename = url.split("/").pop() || "download.torrent";
    return new File([blob], decodeURIComponent(filename), {
      type: "application/x-bittorrent",
    });
  }

  /**
   * Persist the queue to storage.
   */
  private async persist(): Promise<void> {
    try {
      await storageSet(STORAGE_KEYS.QUEUE, this.items);
    } catch (err) {
      log.error("Failed to persist queue", err);
    }
  }

  /**
   * Generate a unique queue item ID.
   *
   * @returns Unique ID string
   */
  private generateItemId(): string {
    return `queue_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  }

  /**
   * Delay for a specified number of milliseconds.
   *
   * @param ms - Milliseconds to delay
   * @returns Promise that resolves after the delay
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
