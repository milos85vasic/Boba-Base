/**
 * @fileoverview Challenge-scoped evidence harness for the BobaLink Phase 5
 * tab-group batch flow (Challenges / HelixQA — §11.4.83 captured-evidence,
 * §11.4.69 feature class `network_throughput`).
 *
 * This is NOT a normal unit/integration spec — it is the Node harness invoked by
 * `challenges/extension/tab_group_batch_challenge.sh`. It drives the REAL,
 * shipped Phase 5 tab-group modules end-to-end (no re-implementation) and
 * PERSISTS the captured runtime evidence to
 * `challenges/extension/.evidence/<run>.json`. The bash challenge then re-reads
 * that evidence file and asserts on it, so the PASS verdict is backed by an
 * auditable artefact per §11.4.83 / §11.4.69 (`network_throughput` — the
 * extension's one batched add-to-Boba request for a whole tab group).
 *
 * The flow exercised (identical wiring to the user's "send this tab group" path):
 *
 *   1. CROSS-TAB DEDUP — a FAKE Chrome tab group of THREE tabs is built via the
 *      injected {@link GroupBatchDeps}: tab A carries magnet-1, tab B carries the
 *      SAME magnet-1 (duplicate, different tab) PLUS magnet-2, tab C is empty. We
 *      run the REAL {@link batchGroupTorrents} and capture the deduped unique set
 *      — the duplicated infohash across two tabs collapses to ONE detection, so
 *      the group's unique set is exactly {magnet-1, magnet-2}.
 *
 *   2. BATCHED DISPATCH — the deduped set is handed to the REAL
 *      {@link dispatchGroupBatch} with a capturing sender, then that sender drives
 *      the REAL {@link BobaClient.addMagnets} (the one batched POST). We capture
 *      the ACTUAL request the client emitted: URL, method, and the parsed JSON
 *      body `{result_id, download_urls:[magnet-1, magnet-2]}` — proving ONE POST
 *      carries BOTH unique magnets, NOT the three raw tab occurrences.
 *
 * Only the Chrome surfaces (`queryGroupTabIds` / `getTabDetections`) and the
 * network boundary (`fetchImpl`) are substituted — every batching/dedup/payload
 * decision is the real shipped code. The spec FAILS (and writes no `pass:true`
 * evidence) if dedup is broken (the duplicate would survive → 3 urls) or the
 * batch payload contract is broken, so a no-op stub of either the batcher or the
 * client cannot produce a green run.
 *
 * Mutation self-check (demonstrated once in the challenge script): if the
 * cross-tab dedup were removed from {@link batchGroupTorrents} (the `seen`
 * Set / `identityKey` guard), the duplicate magnet-1 on tab B would NOT collapse,
 * the unique set would be 3 (not 2), the batched `download_urls` would carry
 * magnet-1 TWICE, and BOTH the harness assertion (`magnets.length === 2`) and the
 * bash re-assertion (`uniqueCount === 2`, `download_urls deduped`) FAIL.
 *
 * NO real token, NO private-tracker payload — both magnets are public-domain
 * test infohashes (Sintel CC-BY family) used across the existing HelixQA bank +
 * webtorrent fixtures (§11.4.10).
 *
 * @module challenges/extension/tab_group_batch.evidence
 */

import { describe, it, expect } from "vitest";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import {
  batchGroupTorrents,
  dispatchGroupBatch,
  type GroupBatchDeps,
  type GroupSendPayload,
} from "../../extension/src/tabgroups/index";
import { BobaClient } from "../../extension/src/api/boba-client";
import { parseMagnetUri } from "../../extension/src/parser/magnet";
import type { DetectedTorrent } from "../../extension/src/types/torrent";

// ─────────────────────────────────────────────────────────────────────────────
// Known-input fixtures. Two distinct public-domain test infohashes. The first is
// the SAME synthetic magnet the boba-bobalink HelixQA bank uses (BOBA-LINK-003 /
// BOBA-LINK-007). No private-tracker payload, no credentials (§11.4.10).
// ─────────────────────────────────────────────────────────────────────────────
const INFOHASH_1 = "08ada5a7a6183aae1e09d831df6748d566095a10";
const INFOHASH_2 = "deadbeef00112233445566778899aabbccddeeff";
const MAGNET_1 = `magnet:?xt=urn:btih:${INFOHASH_1}&dn=helixqa-sintel-test`;
const MAGNET_2 = `magnet:?xt=urn:btih:${INFOHASH_2}&dn=helixqa-second-test`;
const RESULT_ID = "bobalink-group-challenge";
const EXPECTED_ENDPOINT = "http://localhost:7187/api/v1/download";

// The Chrome tab group under test: 3 tabs. Magnet-1 appears on BOTH tab 101 and
// tab 102 (cross-tab duplicate) so a working batcher MUST collapse it to one.
const GROUP_ID = 7;
const TAB_A = 101;
const TAB_B = 102;
const TAB_C = 103;

/**
 * Build a REAL {@link DetectedTorrent} for a magnet by running the REAL
 * {@link parseMagnetUri} (the same parser the scanner uses) — so the dedup key
 * (`item.magnet.infohash`) and the download URL (`item.magnet.uri`) come from the
 * shipped code, not hand-faked.
 */
function detectedFor(magnetUri: string): DetectedTorrent {
  const magnet = parseMagnetUri(magnetUri);
  return {
    id: `ih-${magnet.infohash}`,
    type: "magnet",
    magnet,
    torrentFile: null,
    displayName: magnet.displayName ?? magnet.infohash,
    selected: false,
    sent: false,
    sendStatus: null,
    detectedAt: magnet.detectedAt,
  };
}

const EVIDENCE_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  ".evidence",
  "tab_group_batch.json",
);

interface CapturedRequest {
  url: string;
  method: string;
  bodyText: string | undefined;
}

/** Resolve a fetch input (Request | string | URL) to its URL string. */
function resolveRequestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

/** A capturing fetch that records what BobaClient sent and replies 200. */
function makeCapturingFetch(): {
  fetchImpl: typeof fetch;
  calls: CapturedRequest[];
} {
  const calls: CapturedRequest[] = [];
  const fetchImpl = ((input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    calls.push({
      url: resolveRequestUrl(input),
      method: init?.method ?? "GET",
      bodyText: typeof init?.body === "string" ? init.body : undefined,
    });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({ status: "initiated", added_count: 2, download_id: RESULT_ID }),
    } as unknown as Response);
  }) as unknown as typeof fetch;
  return { fetchImpl, calls };
}

function need<T>(v: T | null | undefined, label: string): T {
  if (v == null) throw new Error(`expected ${label} to be present, got ${String(v)}`);
  return v;
}

describe("CHALLENGE: BobaLink tab-group batch — cross-tab dedup → one batched POST (real modules)", () => {
  it("dedups the same magnet across two tabs and forwards {result_id, download_urls:[m1,m2]} once to :7187", async () => {
    // ── In-memory fake of the Chrome tab-group + per-tab detection surfaces ───
    // Tab A: magnet-1.   Tab B: magnet-1 (DUPLICATE across tabs) + magnet-2.
    // Tab C: no detections.   The REAL batcher must collapse magnet-1 to one.
    const perTab: Record<number, readonly DetectedTorrent[]> = {
      [TAB_A]: [detectedFor(MAGNET_1)],
      [TAB_B]: [detectedFor(MAGNET_1), detectedFor(MAGNET_2)],
      [TAB_C]: [],
    };
    const deps: GroupBatchDeps = {
      queryGroupTabIds: (groupId: number): Promise<readonly number[]> => {
        expect(groupId).toBe(GROUP_ID);
        return Promise.resolve([TAB_A, TAB_B, TAB_C]);
      },
      getTabDetections: (
        tabId: number,
      ): Promise<{ readonly items: readonly DetectedTorrent[] } | null> => {
        const items = perTab[tabId];
        return Promise.resolve(items === undefined ? null : { items });
      },
    };

    // ── STAGE 1: REAL cross-tab dedup ────────────────────────────────────────
    const unique = await batchGroupTorrents(GROUP_ID, deps);
    const magnets = unique.filter((d) => d.type === "magnet");

    // The duplicated magnet-1 (tab A + tab B) collapses to ONE; magnet-2 stays.
    // Raw occurrences across the 3 tabs = 3, deduped unique set = 2.
    expect(magnets).toHaveLength(2);
    const uniqueInfohashes = magnets.map((m) => need(m.magnet, "magnet info").infohash);
    expect(uniqueInfohashes).toEqual([INFOHASH_1, INFOHASH_2]);
    // First-seen order preserved: magnet-1 (tab A) before magnet-2 (tab B).
    const uniqueUris = magnets.map((m) => need(m.magnet, "magnet info").uri);
    expect(uniqueUris).toEqual([MAGNET_1, MAGNET_2]);

    // ── STAGE 2: REAL batched dispatch through BobaClient ─────────────────────
    const { fetchImpl, calls } = makeCapturingFetch();
    const client = new BobaClient({
      baseUrl: "http://localhost:7187",
      fetchImpl,
      disableRateLimit: true,
    });

    let capturedPayload: GroupSendPayload | null = null;
    const dispatch = await dispatchGroupBatch(unique, async (payload) => {
      // The injected sender forwards the EXACT batched URLs to the REAL client
      // in ONE request (the production wiring: client.addMagnets(urls)).
      capturedPayload = payload;
      const result = await client.addMagnets(payload.downloadUrls, { resultId: RESULT_ID });
      return { accepted: result.accepted };
    });

    expect(dispatch.accepted).toBe(true);
    expect(dispatch.sent).toBe(2);
    expect(dispatch.skipped).toBe(0);

    const payload = need(capturedPayload, "captured batch payload");
    expect(payload.count).toBe(2);
    expect(payload.downloadUrls).toEqual([MAGNET_1, MAGNET_2]);

    // EXACTLY one request hit the wire — the whole group batched into ONE POST.
    expect(calls).toHaveLength(1);
    const req = need(calls[0], "captured request");
    expect(req.url).toBe(EXPECTED_ENDPOINT);
    expect(req.method).toBe("POST");

    const body = JSON.parse(need(req.bodyText, "request body")) as {
      result_id: string;
      download_urls: string[];
    };
    expect(body.result_id).toBe(RESULT_ID);
    // The batched body carries the TWO unique magnets — NOT the three raw tab
    // occurrences (which would mean dedup is broken).
    expect(body.download_urls).toEqual([MAGNET_1, MAGNET_2]);

    // ── EVIDENCE: persist the captured runtime data for the bash challenge ────
    const evidence = {
      pass: true,
      capturedAt: new Date().toISOString(),
      feature: "network_throughput", // §11.4.69 taxonomy class
      group: {
        groupId: GROUP_ID,
        tabIds: [TAB_A, TAB_B, TAB_C],
        // Raw torrent occurrences across all tabs BEFORE dedup (1 + 2 + 0 = 3).
        rawOccurrenceCount:
          perTab[TAB_A].length + perTab[TAB_B].length + perTab[TAB_C].length,
      },
      dedup: {
        uniqueCount: magnets.length, // MUST be 2 — magnet-1 collapsed
        uniqueInfohashes,
        uniqueUris,
      },
      forward: {
        requestCount: calls.length, // MUST be 1 — one batched POST
        url: req.url,
        method: req.method,
        requestBody: body, // the exact {result_id, download_urls:[m1,m2]} POSTed
        sent: dispatch.sent,
        skipped: dispatch.skipped,
      },
      expected: {
        infohashes: [INFOHASH_1, INFOHASH_2],
        magnetUris: [MAGNET_1, MAGNET_2],
        endpoint: EXPECTED_ENDPOINT,
        resultId: RESULT_ID,
        rawOccurrenceCount: 3,
        uniqueCount: 2,
      },
    };
    mkdirSync(dirname(EVIDENCE_PATH), { recursive: true });
    writeFileSync(EVIDENCE_PATH, JSON.stringify(evidence, null, 2) + "\n", "utf8");
  });
});
