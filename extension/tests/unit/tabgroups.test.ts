/**
 * @fileoverview Unit tests for the Phase-5 tab-group batcher (`src/tabgroups`).
 *
 * Anti-bluff (§11.4): every assertion inspects a USER-OBSERVABLE outcome —
 *   - the exact deduped set of infohashes/ids batched across a MULTI-TAB fake
 *     group (a torrent on two tabs of the group is sent ONCE),
 *   - the exact payload (`download_urls` / per-item identity) handed to the
 *     INJECTED sender.
 * Each test fails against a no-op stub (a batcher that returns `[]`, or one that
 * does NOT dedupe across tabs, or a dispatcher that drops the payload).
 *
 * The module takes its chrome surfaces (`tabGroups.query` analogue via
 * `tabs.query({ groupId })`) and its per-tab detection fetcher by INJECTION, so
 * jsdom can drive a fully in-memory fake — no real `chrome` global needed.
 *
 * @module tests/unit/tabgroups
 */

import { describe, expect, it, vi } from "vitest";

import {
  batchGroupTorrents,
  dispatchGroupBatch,
  type GroupBatchDeps,
  type GroupBatchSender,
  type GroupSendPayload,
} from "../../src/tabgroups";
import type {
  DetectedTorrent,
  MagnetInfo,
  PageScanResult,
} from "../../src/types/torrent";

// ─────────────────────────────────────────────────────────────────────────────
// Fixture builders
// ─────────────────────────────────────────────────────────────────────────────

function magnet(infohash: string, name: string): MagnetInfo {
  return {
    uri: `magnet:?xt=urn:btih:${infohash}&dn=${encodeURIComponent(name)}`,
    infohash,
    displayName: name,
    trackers: [],
    webSeeds: [],
    exactLength: null,
    exactSource: null,
    keywords: [],
    acceptableSource: null,
    manifest: null,
    detectedAt: 1,
    sourceElement: null,
  };
}

/** A magnet DetectedTorrent. `id` mirrors the orchestrator's infohash-first id. */
function magnetTorrent(infohash: string, name: string): DetectedTorrent {
  return {
    id: infohash,
    type: "magnet",
    magnet: magnet(infohash, name),
    torrentFile: null,
    displayName: name,
    selected: false,
    sent: false,
    sendStatus: null,
    detectedAt: 1,
  };
}

/** A .torrent-file DetectedTorrent (no magnet → identity falls back to `id`). */
function fileTorrent(id: string, url: string, name: string): DetectedTorrent {
  return {
    id,
    type: "torrent-file",
    magnet: null,
    torrentFile: {
      url,
      filename: name,
      size: null,
      sameOrigin: true,
      detectedAt: 1,
      sourceElement: null,
    },
    displayName: name,
    selected: false,
    sent: false,
    sendStatus: null,
    detectedAt: 1,
  };
}

function scan(items: DetectedTorrent[]): PageScanResult {
  return {
    pageUrl: "https://example.test/",
    pageTitle: "t",
    items,
    magnetCount: items.filter((i) => i.type === "magnet").length,
    torrentFileCount: items.filter((i) => i.type === "torrent-file").length,
    scannedAt: 1,
    scanDurationMs: 0,
  };
}

/**
 * Build injected deps over a fake group: `tabIdsByGroup` maps groupId → tab ids,
 * `detectionsByTab` maps tab id → its stored PageScanResult (or absent).
 */
function makeDeps(
  tabIdsByGroup: Record<number, number[]>,
  detectionsByTab: Record<number, PageScanResult>,
): GroupBatchDeps {
  return {
    queryGroupTabIds: (groupId: number) =>
      Promise.resolve(tabIdsByGroup[groupId] ?? []),
    getTabDetections: (tabId: number) =>
      Promise.resolve(detectionsByTab[tabId] ?? null),
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// batchGroupTorrents
// ─────────────────────────────────────────────────────────────────────────────

describe("batchGroupTorrents", () => {
  it("collects the union of detected torrents across every tab in the group", async () => {
    const deps = makeDeps(
      { 42: [1, 2] },
      {
        1: scan([magnetTorrent("a".repeat(40), "Alpha")]),
        2: scan([magnetTorrent("b".repeat(40), "Bravo")]),
      },
    );

    const batch = await batchGroupTorrents(42, deps);

    // user-observable: BOTH torrents from the two-tab group are present.
    expect(batch.map((t) => t.displayName).sort()).toEqual(["Alpha", "Bravo"]);
    expect(batch).toHaveLength(2);
  });

  it("dedupes the SAME torrent (same infohash) found on two tabs to ONE entry", async () => {
    const shared = "c".repeat(40);
    const deps = makeDeps(
      { 7: [10, 11] },
      {
        10: scan([magnetTorrent(shared, "Shared")]),
        11: scan([magnetTorrent(shared, "Shared (mirror)")]),
      },
    );

    const batch = await batchGroupTorrents(7, deps);

    // user-observable: the duplicate across tabs collapses to a single send.
    expect(batch).toHaveLength(1);
    expect(batch[0]?.magnet?.infohash).toBe(shared);
  });

  it("dedupes by infohash even when only the magnet URI casing/name differs", async () => {
    const ih = "d".repeat(40);
    const deps = makeDeps(
      { 1: [1, 2] },
      {
        1: scan([magnetTorrent(ih, "lower")]),
        2: scan([
          {
            ...magnetTorrent(ih, "Upper"),
            id: `dup-${ih}`, // a different id, but SAME infohash
          },
        ]),
      },
    );

    const batch = await batchGroupTorrents(1, deps);

    expect(batch).toHaveLength(1);
  });

  it("dedupes .torrent-file items (no infohash) by stable id across tabs", async () => {
    const deps = makeDeps(
      { 3: [20, 21] },
      {
        20: scan([fileTorrent("file-1", "https://x.test/a.torrent", "A")]),
        21: scan([fileTorrent("file-1", "https://x.test/a.torrent", "A")]),
      },
    );

    const batch = await batchGroupTorrents(3, deps);

    expect(batch).toHaveLength(1);
    expect(batch[0]?.torrentFile?.url).toBe("https://x.test/a.torrent");
  });

  it("tolerates tabs in the group with NO detections (skips them, no crash)", async () => {
    const deps = makeDeps(
      { 9: [1, 2, 3] },
      {
        1: scan([magnetTorrent("e".repeat(40), "Echo")]),
        // tab 2 absent (no detections), tab 3 empty scan
        3: scan([]),
      },
    );

    const batch = await batchGroupTorrents(9, deps);

    expect(batch).toHaveLength(1);
    expect(batch[0]?.displayName).toBe("Echo");
  });

  it("returns an empty batch for an empty group", async () => {
    const deps = makeDeps({ 100: [] }, {});
    const batch = await batchGroupTorrents(100, deps);
    expect(batch).toEqual([]);
  });

  it("preserves first-seen order across tabs (tab 1 before tab 2)", async () => {
    const deps = makeDeps(
      { 1: [1, 2] },
      {
        1: scan([
          magnetTorrent("a".repeat(40), "First"),
          magnetTorrent("b".repeat(40), "Second"),
        ]),
        2: scan([magnetTorrent("c".repeat(40), "Third")]),
      },
    );

    const batch = await batchGroupTorrents(1, deps);
    expect(batch.map((t) => t.displayName)).toEqual([
      "First",
      "Second",
      "Third",
    ]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// dispatchGroupBatch
// ─────────────────────────────────────────────────────────────────────────────

describe("dispatchGroupBatch", () => {
  it("hands the injected sender the EXACT batched download_urls (magnet URIs)", async () => {
    const a = magnetTorrent("a".repeat(40), "Alpha");
    const b = magnetTorrent("b".repeat(40), "Bravo");
    const captured: GroupSendPayload[] = [];
    const sender: GroupBatchSender = (p) => {
      captured.push(p);
      return Promise.resolve({ accepted: true });
    };

    const result = await dispatchGroupBatch([a, b], sender);

    expect(captured).toHaveLength(1);
    // user-observable: the precise URLs that reach the backend.
    expect(captured[0]?.downloadUrls).toEqual([a.magnet?.uri, b.magnet?.uri]);
    expect(captured[0]?.count).toBe(2);
    expect(result.sent).toBe(2);
    expect(result.accepted).toBe(true);
  });

  it("uses the .torrent-file URL when an item has no magnet", async () => {
    const f = fileTorrent("file-9", "https://x.test/z.torrent", "Zed");
    const captured: GroupSendPayload[] = [];
    const sender: GroupBatchSender = (p) => {
      captured.push(p);
      return Promise.resolve({ accepted: true });
    };

    await dispatchGroupBatch([f], sender);

    expect(captured[0]?.downloadUrls).toEqual(["https://x.test/z.torrent"]);
  });

  it("drops items carrying neither a magnet nor a .torrent URL from the payload", async () => {
    const broken: DetectedTorrent = {
      ...magnetTorrent("f".repeat(40), "Broken"),
      magnet: null,
      torrentFile: null,
    };
    const ok = magnetTorrent("a".repeat(40), "Alpha");
    const captured: GroupSendPayload[] = [];
    const sender: GroupBatchSender = (p) => {
      captured.push(p);
      return Promise.resolve({ accepted: true });
    };

    const result = await dispatchGroupBatch([broken, ok], sender);

    // only the resolvable URL is sent; broken item counted as skipped.
    expect(captured[0]?.downloadUrls).toEqual([ok.magnet?.uri]);
    expect(result.sent).toBe(1);
    expect(result.skipped).toBe(1);
  });

  it("does NOT call the sender when there is nothing to send", async () => {
    const sender = vi.fn(() => Promise.resolve({ accepted: true }));
    const result = await dispatchGroupBatch([], sender);

    expect(sender).not.toHaveBeenCalled();
    expect(result.sent).toBe(0);
    expect(result.accepted).toBe(false);
  });

  it("reports accepted=false when the sender rejects the batch", async () => {
    const a = magnetTorrent("a".repeat(40), "Alpha");
    const sender: GroupBatchSender = () => Promise.resolve({ accepted: false });

    const result = await dispatchGroupBatch([a], sender);

    expect(result.accepted).toBe(false);
    expect(result.sent).toBe(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// End-to-end: batch a multi-tab group, then dispatch
// ─────────────────────────────────────────────────────────────────────────────

describe("tab-group batch → dispatch (end to end)", () => {
  it("batches a deduped multi-tab group and dispatches the exact unique URLs", async () => {
    const shared = "c".repeat(40);
    const deps = makeDeps(
      { 5: [1, 2] },
      {
        1: scan([
          magnetTorrent("a".repeat(40), "Alpha"),
          magnetTorrent(shared, "Shared"),
        ]),
        2: scan([
          magnetTorrent(shared, "Shared (dup)"),
          magnetTorrent("b".repeat(40), "Bravo"),
        ]),
      },
    );

    const batch = await batchGroupTorrents(5, deps);
    // 4 detections across 2 tabs, but "Shared" is one torrent → 3 unique.
    expect(batch).toHaveLength(3);

    const captured: GroupSendPayload[] = [];
    const result = await dispatchGroupBatch(batch, (p) => {
      captured.push(p);
      return Promise.resolve({ accepted: true });
    });

    expect(captured[0]?.downloadUrls).toEqual([
      `magnet:?xt=urn:btih:${"a".repeat(40)}&dn=Alpha`,
      `magnet:?xt=urn:btih:${shared}&dn=Shared`,
      `magnet:?xt=urn:btih:${"b".repeat(40)}&dn=Bravo`,
    ]);
    expect(result.sent).toBe(3);
  });
});
