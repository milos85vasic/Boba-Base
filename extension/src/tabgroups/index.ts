/**
 * @fileoverview Phase 5 — tab-group torrent batcher (STANDALONE, injected deps).
 *
 * Lets the user "send all torrents in this tab group" at once. This module is
 * self-contained: it does NOT import `background/index.ts` (another stream owns
 * that file) and registers no listeners. The background imports it later and
 * wires the two injected dependencies to its OWN state + client (the one-line
 * integration point is documented at {@link GroupBatchDeps} below).
 *
 * ## What it does
 *   1. {@link batchGroupTorrents} — given a `groupId`, query the tab ids in that
 *      Chrome tab group, collect each tab's detected torrents (via the SAME
 *      per-tab detection contract the background already exposes through its
 *      `get-detected` message / `tabResults` map), and DEDUPE across tabs so the
 *      same torrent appearing on two tabs of the group is batched ONCE.
 *   2. {@link dispatchGroupBatch} — resolve each unique torrent's download URL
 *      (magnet URI → `.torrent` URL) and hand the exact batched payload to an
 *      INJECTED sender, so the caller (and the unit test) controls/asserts the
 *      precise URLs that reach the backend.
 *
 * ## Dedup contract (matches the scanner orchestrator, §scanner/base.ts)
 * Identity is infohash-first: a magnet's `infohash` is the canonical BitTorrent
 * identity; a `.torrent`-file item (no infohash) falls back to the
 * orchestrator's already-stable `DetectedTorrent.id`. The same identity across
 * tabs collapses to a single entry, first-seen order preserved.
 *
 * ## Chrome surfaces by injection
 * `chrome.tabGroups` / `chrome.tabs` are taken as injected callbacks
 * ({@link GroupBatchDeps}) so jsdom unit tests drive an in-memory fake and this
 * module never touches a missing `chrome` global. A real adapter binding those
 * callbacks to `chrome.tabs.query({ groupId })` is provided as
 * {@link chromeGroupBatchDeps} for the background to use once the manifest gains
 * the `tabGroups` + `tabs` permissions.
 *
 * @module tabgroups
 */

import { createLogger } from "../shared/logger";
import type { DetectedTorrent } from "../types/torrent";

const log = createLogger("TabGroups");

// ─────────────────────────────────────────────────────────────────────────────
// Injected dependency contracts
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The two surfaces {@link batchGroupTorrents} needs, injected so tests drive a
 * fake and the background wires its real sources.
 *
 * Background integration (Phase 5): bind `queryGroupTabIds` to
 * `chrome.tabs.query({ groupId })` (mapping to `tab.id`) and `getTabDetections`
 * to the background's existing per-tab `tabResults.get(tabId)` lookup — the same
 * `PageScanResult` it already returns for the `get-detected` message.
 */
export interface GroupBatchDeps {
  /**
   * Resolve the tab ids that belong to a Chrome tab group.
   *
   * @param groupId - The `chrome.tabGroups` group id.
   * @returns The ids of the tabs in that group (order = group order).
   */
  readonly queryGroupTabIds: (groupId: number) => Promise<readonly number[]>;

  /**
   * Resolve the detected torrents stored for a single tab, or null when the tab
   * has no scan result yet. Returns the SAME `{ items }` shape the background's
   * `get-detected` exposes; only `items` is consumed here.
   *
   * @param tabId - The tab whose detections to fetch.
   * @returns The tab's detection snapshot, or null.
   */
  readonly getTabDetections: (
    tabId: number,
  ) => Promise<{ readonly items: readonly DetectedTorrent[] } | null>;
}

/** The exact batched payload handed to the injected sender. */
export interface GroupSendPayload {
  /** Resolved, ordered, deduped download URLs (magnet URI or `.torrent` URL). */
  readonly downloadUrls: readonly string[];

  /** Number of URLs in {@link downloadUrls} (convenience for the caller). */
  readonly count: number;

  /** The unique detected torrents the URLs were resolved from (same order). */
  readonly torrents: readonly DetectedTorrent[];
}

/** What an injected sender reports back to {@link dispatchGroupBatch}. */
export interface GroupBatchSendResult {
  /** Whether the backend accepted the batched download. */
  readonly accepted: boolean;
}

/**
 * Sends a batched group payload to the backend. The background binds this to a
 * single `BobaClient` call (e.g. `client.addMagnets(payload.downloadUrls)`); the
 * unit test binds it to a capture so it asserts the exact payload.
 */
export type GroupBatchSender = (
  payload: GroupSendPayload,
) => Promise<GroupBatchSendResult>;

/** Outcome of {@link dispatchGroupBatch}. */
export interface GroupDispatchResult {
  /** Whether the sender accepted the batch (false when nothing was sent). */
  readonly accepted: boolean;

  /** Number of URLs actually dispatched. */
  readonly sent: number;

  /** Number of input torrents dropped (no resolvable download URL). */
  readonly skipped: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Identity / URL helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The dedup key for a detected torrent: infohash-first (canonical BitTorrent
 * identity), falling back to the orchestrator's already-stable id for
 * `.torrent`-file items that carry no infohash.
 *
 * @param item - A detected torrent.
 * @returns The cross-tab dedup key.
 */
function identityKey(item: DetectedTorrent): string {
  const infohash = item.magnet?.infohash;
  if (infohash !== undefined && infohash !== null && infohash !== "") {
    return `ih:${infohash.toLowerCase()}`;
  }
  return `id:${item.id}`;
}

/**
 * Resolve the download URL the backend should receive for a torrent: its magnet
 * URI, else its `.torrent`-file URL, else null when it carries neither.
 *
 * @param item - A detected torrent.
 * @returns The download URL, or null.
 */
function downloadUrlOf(item: DetectedTorrent): string | null {
  return item.magnet?.uri ?? item.torrentFile?.url ?? null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Batching
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Collect and dedupe every detected torrent across the tabs of a Chrome tab
 * group.
 *
 * Tabs are queried via {@link GroupBatchDeps.queryGroupTabIds}; each tab's
 * detections via {@link GroupBatchDeps.getTabDetections}. A torrent appearing on
 * more than one tab of the group is included ONCE (infohash-first identity).
 * Tabs with no detections are skipped silently. First-seen order is preserved.
 *
 * @param groupId - The `chrome.tabGroups` group id to batch.
 * @param deps - Injected chrome/detection surfaces.
 * @returns The deduped, ordered set of torrents across the group.
 */
export async function batchGroupTorrents(
  groupId: number,
  deps: GroupBatchDeps,
): Promise<readonly DetectedTorrent[]> {
  const tabIds = await deps.queryGroupTabIds(groupId);

  const seen = new Set<string>();
  const batch: DetectedTorrent[] = [];

  for (const tabId of tabIds) {
    let snapshot: { readonly items: readonly DetectedTorrent[] } | null;
    try {
      snapshot = await deps.getTabDetections(tabId);
    } catch (err) {
      // A single unreachable tab must not sink the whole group batch.
      log.warn(`detections fetch failed for tab ${String(tabId)}; skipping`);
      log.debug("fetch error", err);
      continue;
    }

    if (snapshot === null) continue;

    for (const item of snapshot.items) {
      const key = identityKey(item);
      if (seen.has(key)) continue;
      seen.add(key);
      batch.push(item);
    }
  }

  log.info(
    `batched ${String(batch.length)} unique torrent(s) from group ${String(groupId)} (${String(tabIds.length)} tab(s))`,
  );
  return batch;
}

// ─────────────────────────────────────────────────────────────────────────────
// Dispatch
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Resolve the download URLs for a batched torrent set and hand the exact payload
 * to the injected sender. Torrents carrying neither a magnet nor a `.torrent`
 * URL are dropped (counted as skipped). When nothing is resolvable the sender is
 * NOT called and the result reports `accepted=false`.
 *
 * @param torrents - The (already deduped) torrents to send.
 * @param sender - The injected batch sender (a `BobaClient` call in production).
 * @returns The dispatch outcome.
 */
export async function dispatchGroupBatch(
  torrents: readonly DetectedTorrent[],
  sender: GroupBatchSender,
): Promise<GroupDispatchResult> {
  const sendable: DetectedTorrent[] = [];
  const downloadUrls: string[] = [];
  let skipped = 0;

  for (const item of torrents) {
    const url = downloadUrlOf(item);
    if (url === null) {
      skipped += 1;
      continue;
    }
    sendable.push(item);
    downloadUrls.push(url);
  }

  if (downloadUrls.length === 0) {
    return { accepted: false, sent: 0, skipped };
  }

  const payload: GroupSendPayload = {
    downloadUrls,
    count: downloadUrls.length,
    torrents: sendable,
  };

  const result = await sender(payload);
  return {
    accepted: result.accepted,
    sent: downloadUrls.length,
    skipped,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Real chrome adapter (used by the background once permissions are granted)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Build {@link GroupBatchDeps} from a real `chrome.tabs` surface plus the
 * background's per-tab detection lookup.
 *
 * NOT used by the unit tests (which inject a fake). The background calls this in
 * Phase 5 wiring once the manifest declares the `tabGroups` + `tabs`
 * permissions. The detection lookup is the background's existing
 * `tabResults.get(tabId)` source (the same one `get-detected` returns).
 *
 * @param getTabDetections - The background's per-tab detection lookup.
 * @returns Deps that query the live tab group via `chrome.tabs.query`.
 */
export function chromeGroupBatchDeps(
  getTabDetections: GroupBatchDeps["getTabDetections"],
): GroupBatchDeps {
  return {
    queryGroupTabIds: async (groupId: number): Promise<readonly number[]> => {
      const tabs = await chrome.tabs.query({ groupId });
      const ids: number[] = [];
      for (const tab of tabs) {
        if (typeof tab.id === "number") ids.push(tab.id);
      }
      return ids;
    },
    getTabDetections,
  };
}
