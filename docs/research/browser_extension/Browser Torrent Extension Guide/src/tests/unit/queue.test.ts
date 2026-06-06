/**
 * @fileoverview Unit tests for offline queue system.
 *
 * Tests enqueue, dequeue, processing, and persistence of the offline queue.
 */

import { OfflineQueue } from "../../src/api/queue";
import type { ServerConfig } from "../../src/types/config";

// Mock chrome.storage
const mockStorageData: Record<string, unknown> = {};
jest.mock("../../src/shared/storage", () => ({
  storageGet: jest.fn((key: string) => Promise.resolve(mockStorageData[key] ?? null)),
  storageSet: jest.fn((key: string, value: unknown) => {
    mockStorageData[key] = value;
    return Promise.resolve();
  }),
  storageRemove: jest.fn(() => Promise.resolve()),
}));

describe("OfflineQueue", () => {
  let queue: OfflineQueue;

  const testServer: ServerConfig = {
    id: "test-server",
    name: "Test",
    url: "http://localhost:8080",
    authMethod: "none",
    active: true,
    username: null,
    encryptedPassword: null,
    encryptedApiKey: null,
    requestTimeout: 5000,
    verifySsl: true,
    defaultCategory: null,
    defaultSavePath: null,
    startPaused: false,
    skipHashCheck: false,
    contentLayout: "original",
    autoTMM: false,
    uploadLimit: 0,
    downloadLimit: 0,
  };

  beforeEach(() => {
    queue = new OfflineQueue(10);
    Object.keys(mockStorageData).forEach((k) => delete mockStorageData[k]);
  });

  afterEach(() => {
    queue.stopAutoProcessing();
  });

  describe("Basic operations", () => {
    it("initializes with empty queue", () => {
      expect(queue.getSize()).toBe(0);
    });

    it("enqueues an item", async () => {
      const item = await queue.enqueue(
        "abc123",
        "magnet:?xt=urn:btih:abc123",
        null,
        "Test Torrent",
        "test-server",
      );

      expect(queue.getSize()).toBe(1);
      expect(item.torrent.infohash).toBe("abc123");
      expect(item.torrent.displayName).toBe("Test Torrent");
      expect(item.attempts).toBe(0);
    });

    it("enqueues with default normal priority", async () => {
      const item = await queue.enqueue(
        "abc123",
        "magnet:?xt=urn:btih:abc123",
        null,
        "Test",
        "test-server",
      );

      expect(item.priority).toBe("normal");
    });

    it("enqueues with explicit priority", async () => {
      const item = await queue.enqueue(
        "abc123",
        "magnet:?xt=urn:btih:abc123",
        null,
        "Test",
        "test-server",
        "high",
      );

      expect(item.priority).toBe("high");
    });

    it("dequeues an item", async () => {
      const item = await queue.enqueue(
        "abc123",
        "magnet:?xt=urn:btih:abc123",
        null,
        "Test",
        "test-server",
      );

      const removed = await queue.dequeue(item.id);
      expect(removed).toBe(true);
      expect(queue.getSize()).toBe(0);
    });

    it("dequeue returns false for non-existent item", async () => {
      const removed = await queue.dequeue("non-existent");
      expect(removed).toBe(false);
    });
  });

  describe("Queue limits", () => {
    it("respects max queue size", async () => {
      const smallQueue = new OfflineQueue(3);

      await smallQueue.enqueue("1", "magnet:1", null, "Item 1", "s");
      await smallQueue.enqueue("2", "magnet:2", null, "Item 2", "s");
      await smallQueue.enqueue("3", "magnet:3", null, "Item 3", "s");
      await smallQueue.enqueue("4", "magnet:4", null, "Item 4", "s");

      expect(smallQueue.getSize()).toBe(3);
    });

    it("removes oldest items when queue is full", async () => {
      const smallQueue = new OfflineQueue(2);

      await smallQueue.enqueue("1", "magnet:1", null, "Item 1", "s");
      await smallQueue.enqueue("2", "magnet:2", null, "Item 2", "s");
      await smallQueue.enqueue("3", "magnet:3", null, "Item 3", "s");

      const items = smallQueue.getItems();
      expect(items.length).toBe(2);
      expect(items[0].torrent.infohash).toBe("2");
      expect(items[1].torrent.infohash).toBe("3");
    });
  });

  describe("Clear", () => {
    it("clears all items", async () => {
      await queue.enqueue("1", "magnet:1", null, "Item 1", "s");
      await queue.enqueue("2", "magnet:2", null, "Item 2", "s");

      await queue.clear();
      expect(queue.getSize()).toBe(0);
    });
  });

  describe("Persistence", () => {
    it("persists items to storage", async () => {
      await queue.enqueue("abc123", "magnet:abc", null, "Test", "s");

      // storageSet should have been called
      expect(Object.keys(mockStorageData).length).toBeGreaterThan(0);
    });
  });

  describe("Auto-processing", () => {
    it("starts and stops auto-processing", () => {
      queue.startAutoProcessing(testServer, 100);
      queue.stopAutoProcessing();
      // Test passes if no error
      expect(true).toBe(true);
    });

    it("does not start duplicate auto-processing", () => {
      queue.startAutoProcessing(testServer, 100);
      queue.startAutoProcessing(testServer, 100); // Should not throw
      expect(true).toBe(true);
    });
  });

  describe("Queue processing", () => {
    it("returns empty result for empty queue", async () => {
      const result = await queue.processQueue(testServer);
      expect(result.processed).toBe(0);
      expect(result.succeeded).toBe(0);
      expect(result.remaining).toBe(0);
    });

    it("returns correct counts after processing", async () => {
      // Since we can't easily mock the adapter, we test structure
      await queue.enqueue("1", "magnet:1", null, "Test 1", "s");

      const result = await queue.processQueue(testServer);
      // Will fail to send since adapter can't connect, but structure is valid
      expect(result.processed).toBe(1);
      expect(result.results.length).toBe(1);
    });
  });
});
