/**
 * @fileoverview FULL-PIPELINE INTEGRATION tests for BobaLink: the assembled
 * detection → send → (offline-queue on failure) path, driven through the REAL
 * production modules wired together. Only the NETWORK boundary (the BobaClient's
 * injectable `fetchImpl`) and `chrome.storage.local` (the committed unit
 * chrome-fake) are substituted — every other layer is the real shipped code:
 *
 *   1. DETECTION — a real jsdom `document` containing a real magnet `<a href>`
 *      AND a link to a `.torrent` is scanned by the REAL {@link ScannerOrchestrator}
 *      (composing the committed Link + Text scanners). We assert the EXACT,
 *      deduplicated detections the user would see forwarded: the precise
 *      40-char infohash parsed from the magnet, the sanitized display name, and
 *      the resolved `.torrent` URL.
 *
 *   2. SEND — those real detections are fed to the REAL {@link BobaClient} with a
 *      `fetchImpl` stub that CAPTURES the request. We assert on the ACTUAL
 *      captured request: the URL is `http://localhost:7187/api/v1/download` and
 *      the JSON body is exactly `{result_id, download_urls:[<the detected magnet>]}`
 *      — the magnet string in the body is byte-for-byte the one the scanner
 *      produced (the user-observable "what gets forwarded").
 *
 *   3. FAILURE → QUEUE — when the client's send fails (fetch rejects → real
 *      NetworkError surfaces out of BobaClient), the failed detection is handed
 *      to the REAL {@link OfflineQueue} (queue.ts), which persists it to
 *      `chrome.storage.local` under `STORAGE_KEYS.QUEUE`. We assert by reading
 *      the persisted bytes back out of the fake store: the queued item carries
 *      the detected infohash + magnet URI + display name.
 *
 * §11.4 ANTI-BLUFF: every assertion is on a USER-OBSERVABLE outcome — the exact
 * infohash string, the captured request URL + parsed body `download_urls`, and
 * the persisted queue contents — never "no error" / status-code-only. Each test
 * is annotated with the no-op stub it would catch (see per-test comments).
 *
 * §11.4.10: no real token anywhere — the client is constructed token-less for
 * the detection/send tests; the one token-forwarding probe uses a synthetic
 * `test-token-<uuid>` purely to prove FORWARDING (never logged).
 *
 * @module tests/integration/pipeline
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { ScannerOrchestrator } from "../../src/scanner/orchestrator";
import { BobaClient } from "../../src/api/boba-client";
import { OfflineQueue } from "../../src/api/queue";
import { TypedEventEmitter } from "../../src/shared/events";
import { STORAGE_KEYS } from "../../src/shared/constants";
import { createChromeStorageFake } from "../unit/chrome-fake";
import type { DetectedTorrent } from "../../src/types/torrent";
import type { OfflineQueueItem } from "../../src/api/queue";

/**
 * Narrowing helper used in place of forbidden `!` non-null assertions
 * (@typescript-eslint/no-non-null-assertion). Throws — failing the test loudly —
 * if the value is null/undefined, so the assertions it guards still prove the
 * exact same user-observable outcome (the value MUST be present). It narrows
 * `T | null | undefined` to `T` without weakening any downstream expectation.
 */
function need<T>(v: T | null | undefined, label = "value"): T {
  if (v == null) {
    throw new Error(`expected ${label} to be present, got ${String(v)}`);
  }
  return v;
}

/** Resolve a fetch `input` (Request | string | URL) to its URL string without
 *  the `[object Object]` default-stringification of a Request object. */
function resolveRequestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

// ─────────────────────────────────────────────────────────────────────────────
// Fixtures — real magnet + real .torrent link (generic localhost host → generic
// site selectors: magnet: + .torrent). Spaces in `dn` are %20-encoded so the
// committed parser decodes them via decodeURIComponent.
// ─────────────────────────────────────────────────────────────────────────────

const INFOHASH_MAGNET = "0123456789abcdef0123456789abcdef01234567";
const MAGNET_URI = `magnet:?xt=urn:btih:${INFOHASH_MAGNET}&dn=Ubuntu%2024.04%20LTS&tr=udp%3A%2F%2Ftracker.example%3A1337`;
const MAGNET_DISPLAY_NAME = "Ubuntu 24.04 LTS";

const TORRENT_URL = "https://files.example.org/releases/cool-release.torrent";

const PAGE_HTML = `
  <h1>Releases</h1>
  <a id="magnet-link" href="${MAGNET_URI}">Ubuntu via magnet</a>
  <p>Mirror the same release here too: ${MAGNET_URI} — cheers!</p>
  <a id="file-link" href="${TORRENT_URL}">Download the .torrent</a>
  <a href="https://example.org/not-a-torrent.html">A perfectly normal link</a>
`;

/** A fetch stub that records exactly what BobaClient sent and replies 200. */
interface CapturedRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  bodyText: string | undefined;
}

function makeCapturingFetch(): {
  fetchImpl: typeof fetch;
  calls: CapturedRequest[];
} {
  const calls: CapturedRequest[] = [];
  const fetchImpl: typeof fetch = (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const headers = (init?.headers as Record<string, string>) ?? {};
    calls.push({
      url: resolveRequestUrl(input),
      method: init?.method ?? "GET",
      headers,
      bodyText: typeof init?.body === "string" ? init.body : undefined,
    });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: "initiated", added_count: 1 }),
    } as unknown as Response);
  };
  return { fetchImpl, calls };
}

/** Run the REAL orchestrator over the current jsdom document and return the
 *  deduped detected set the user would see. */
async function scanCurrentPage(): Promise<readonly DetectedTorrent[]> {
  const orchestrator = new ScannerOrchestrator(new TypedEventEmitter(), {
    observeMutations: false,
  });
  await orchestrator.scanNow();
  return orchestrator.getDetectedTorrents();
}

describe("FULL PIPELINE — detection → send → offline-queue (real modules, jsdom)", () => {
  beforeEach(() => {
    document.body.innerHTML = PAGE_HTML;
  });

  afterEach(() => {
    document.body.innerHTML = "";
    delete (globalThis as unknown as { chrome?: unknown }).chrome;
  });

  // ───────────────────────────────────────────────────────────────────────────
  // STAGE 1 — detection yields the EXACT deduplicated detections + infohashes
  // ───────────────────────────────────────────────────────────────────────────
  it("STAGE 1: scans the page → exact deduped magnet (one) + .torrent with correct infohash/url", async () => {
    // No-op-stub this catches: a ScannerOrchestrator whose scan() returns [] (or
    // whose mergeResults drops dedup) would yield 0 detections, or 2 magnet
    // entries (link + text duplicate), or a magnet whose infohash !== the parsed
    // 40-char hash. We assert the EXACT user-forwarded identity, so none pass.
    const detected = await scanCurrentPage();

    const magnets = detected.filter((d) => d.type === "magnet");
    const files = detected.filter((d) => d.type === "torrent-file");

    // The magnet appears TWICE on the page (anchor + bare text) but dedups to ONE.
    expect(magnets).toHaveLength(1);
    expect(files).toHaveLength(1);

    const magnet = need(magnets[0], "first magnet detection");
    // User-observable: the EXACT 40-char infohash that gets forwarded.
    expect(magnet.magnet?.infohash).toBe(INFOHASH_MAGNET);
    // User-observable: the exact magnet URI the client will POST.
    expect(magnet.magnet?.uri).toBe(MAGNET_URI);
    // Sanitized display name the user reads.
    expect(magnet.displayName).toBe(MAGNET_DISPLAY_NAME);

    const file = need(files[0], "first .torrent-file detection");
    expect(file.torrentFile?.url).toBe(TORRENT_URL);
  });

  // ───────────────────────────────────────────────────────────────────────────
  // STAGE 2 — feed detections to the REAL client; assert the CAPTURED request
  // ───────────────────────────────────────────────────────────────────────────
  it("STAGE 2: real BobaClient POSTs to :7187/api/v1/download with the detected magnet in the body", async () => {
    // No-op-stub this catches: a client whose addMagnets() returns {accepted:true}
    // without calling fetch (calls.length === 0), or POSTs to the wrong URL, or
    // sends a body missing the detected magnet, all FAIL — we assert on the
    // ACTUAL captured request bytes, not "it resolved".
    const detected = await scanCurrentPage();
    const magnet = need(
      detected.find((d) => d.type === "magnet"),
      "magnet detection",
    );
    const magnetUri = need(magnet.magnet, "magnet info").uri;

    const { fetchImpl, calls } = makeCapturingFetch();
    const client = new BobaClient({
      // explicit default base so the assertion on host:port is meaningful
      baseUrl: "http://localhost:7187",
      fetchImpl,
      disableRateLimit: true,
    });

    const result = await client.addMagnet(magnetUri, { resultId: "bobalink" });
    expect(result.accepted).toBe(true);

    // EXACTLY one request was made.
    expect(calls).toHaveLength(1);
    const req = need(calls[0], "captured request");

    // User-observable: the request hit the Boba merge-service download endpoint.
    expect(req.url).toBe("http://localhost:7187/api/v1/download");
    expect(req.method).toBe("POST");
    expect(req.headers["Content-Type"]).toBe("application/json");

    // User-observable: the ACTUAL JSON body shape {result_id, download_urls:[...]}.
    expect(req.bodyText).toBeTypeOf("string");
    const body = JSON.parse(need(req.bodyText, "request body")) as {
      result_id: string;
      download_urls: string[];
    };
    expect(body.result_id).toBe("bobalink");
    expect(Array.isArray(body.download_urls)).toBe(true);
    expect(body.download_urls).toHaveLength(1);
    // The forwarded magnet is byte-for-byte the one the SCANNER produced.
    expect(body.download_urls[0]).toBe(MAGNET_URI);
    // …carrying the exact detected infohash (cross-stage identity check).
    expect(body.download_urls[0]).toContain(INFOHASH_MAGNET);
  });

  it("STAGE 2b: batching multiple detections sends ALL detected download URLs in one request", async () => {
    // No-op-stub this catches: a client that drops/loses URLs (sends fewer than
    // detected) or only ever sends the first. We assert the body carries BOTH
    // the magnet URI and the .torrent file URL the scanner found.
    const detected = await scanCurrentPage();
    const downloadUrls = detected.map(
      (d) => d.magnet?.uri ?? d.torrentFile?.url ?? "",
    );
    expect(downloadUrls).toContain(MAGNET_URI);
    expect(downloadUrls).toContain(TORRENT_URL);

    const { fetchImpl, calls } = makeCapturingFetch();
    const client = new BobaClient({ fetchImpl, disableRateLimit: true });

    await client.addMagnets(downloadUrls, { resultId: "bobalink" });

    expect(calls).toHaveLength(1);
    const body = JSON.parse(
      need(need(calls[0], "captured request").bodyText, "request body"),
    ) as { download_urls: string[] };
    // Both detected items survive into the request the backend receives.
    expect(body.download_urls).toContain(MAGNET_URI);
    expect(body.download_urls).toContain(TORRENT_URL);
    expect(body.download_urls).toHaveLength(downloadUrls.length);
  });

  it("STAGE 2c: a configured token is FORWARDED on the captured request (never the value-only path) (§11.4.10)", async () => {
    // No-op-stub this catches: a client that ignores the token (no Authorization
    // header on the captured request). We assert the synthetic token reached the
    // wire as a bearer header.
    const synthToken = `test-token-${crypto.randomUUID()}`;
    const detected = await scanCurrentPage();
    const magnetUri = need(
      need(
        detected.find((d) => d.type === "magnet"),
        "magnet detection",
      ).magnet,
      "magnet info",
    ).uri;

    const { fetchImpl, calls } = makeCapturingFetch();
    const client = new BobaClient({
      fetchImpl,
      token: synthToken,
      disableRateLimit: true,
    });

    await client.addMagnet(magnetUri);

    expect(calls).toHaveLength(1);
    const tokenReq = need(calls[0], "captured request");
    expect(tokenReq.headers["Authorization"]).toBe(`Bearer ${synthToken}`);
    // X-Boba-Token alternative header also carries it.
    expect(tokenReq.headers["X-Boba-Token"]).toBe(synthToken);
  });

  // ───────────────────────────────────────────────────────────────────────────
  // STAGE 3 — client failure → the detection lands in the REAL persisted queue
  // ───────────────────────────────────────────────────────────────────────────
  it("STAGE 3: when the client send FAILS, the detection is enqueued + PERSISTED to storage", async () => {
    // No-op-stub this catches: an OfflineQueue.enqueue() that never persists (the
    // STORAGE_KEYS.QUEUE entry would be absent), or a pipeline that silently
    // drops the failed send. We read the persisted bytes back out and assert the
    // queued item carries the detected infohash + magnet + name.
    const fake = createChromeStorageFake();
    (globalThis as unknown as { chrome: unknown }).chrome = fake.chrome;

    // Real detection.
    const detected = await scanCurrentPage();
    const magnet = need(
      detected.find((d) => d.type === "magnet"),
      "magnet detection",
    );
    const magnetInfo = need(magnet.magnet, "magnet info");
    const magnetUri = magnetInfo.uri;
    const infohash = magnetInfo.infohash;
    const displayName = magnet.displayName;

    // Real client whose fetch always rejects → real NetworkError out of send.
    // maxRetries:0 makes the hard-fail immediate (no backoff sleeps).
    const failingFetch = (() =>
      Promise.reject(new Error("ECONNREFUSED"))) as unknown as typeof fetch;
    const client = new BobaClient({
      fetchImpl: failingFetch,
      maxRetries: 0,
      disableRateLimit: true,
    });

    // The assembled send path: try the client; on failure, enqueue for retry.
    const queue = new OfflineQueue();
    await queue.init();

    let sendFailed = false;
    try {
      await client.addMagnet(magnetUri);
    } catch {
      sendFailed = true;
      await queue.enqueue(
        infohash,
        magnetUri,
        null,
        displayName,
        "srv-1",
      );
    }

    // The client genuinely failed (not a silent success).
    expect(sendFailed).toBe(true);

    // USER-OBSERVABLE: the failed send now lives in the PERSISTED offline queue.
    const persisted = fake.store.get(STORAGE_KEYS.QUEUE) as
      | OfflineQueueItem[]
      | undefined;
    expect(persisted).toBeDefined();
    expect(persisted).toHaveLength(1);
    const persistedItem = need(need(persisted, "persisted queue")[0], "queued item");
    expect(persistedItem.torrent.infohash).toBe(INFOHASH_MAGNET);
    expect(persistedItem.torrent.magnetUri).toBe(MAGNET_URI);
    expect(persistedItem.torrent.displayName).toBe(MAGNET_DISPLAY_NAME);
    expect(persistedItem.state).toBe("queued");
    expect(persistedItem.serverId).toBe("srv-1");
  });

  it("STAGE 3b: a fresh OfflineQueue.init() reloads the persisted item from storage (round-trip)", async () => {
    // No-op-stub this catches: an OfflineQueue.init() that ignores persisted
    // storage (a fresh queue would be empty). We persist via one queue instance,
    // then prove a SECOND instance reads the same item back out of storage and
    // exposes it via the public getItems() — the user's queued torrent survives
    // a service-worker restart.
    const fake = createChromeStorageFake();
    (globalThis as unknown as { chrome: unknown }).chrome = fake.chrome;

    const detected = await scanCurrentPage();
    const magnet = need(
      detected.find((d) => d.type === "magnet"),
      "magnet detection",
    );
    const magnetInfo = need(magnet.magnet, "magnet info");

    const q1 = new OfflineQueue();
    await q1.init();
    await q1.enqueue(
      magnetInfo.infohash,
      magnetInfo.uri,
      null,
      magnet.displayName,
      "srv-1",
    );

    // A brand-new queue (simulating a worker restart) must reload from storage.
    const q2 = new OfflineQueue();
    await q2.init();

    const items = q2.getItems();
    expect(items).toHaveLength(1);
    const reloaded = need(items[0], "reloaded queue item");
    expect(reloaded.torrent.infohash).toBe(INFOHASH_MAGNET);
    expect(reloaded.torrent.magnetUri).toBe(MAGNET_URI);
  });

  it("STAGE 3c: a recovered (now-reachable) backend drains the queued item via the REAL client send", async () => {
    // No-op-stub this catches: an OfflineQueue.processQueue() that never invokes
    // the injected sender, OR a sender wired to the client that doesn't actually
    // POST. We process the queue with a sender backed by the REAL BobaClient and
    // a capturing fetch, and assert (a) the captured request carries the queued
    // magnet, and (b) the now-sent item is removed from the persisted queue.
    const fake = createChromeStorageFake();
    (globalThis as unknown as { chrome: unknown }).chrome = fake.chrome;

    const detected = await scanCurrentPage();
    const magnet = need(
      detected.find((d) => d.type === "magnet"),
      "magnet detection",
    );
    const magnetInfo = need(magnet.magnet, "magnet info");

    const queue = new OfflineQueue();
    await queue.init();
    await queue.enqueue(
      magnetInfo.infohash,
      magnetInfo.uri,
      null,
      magnet.displayName,
      "srv-1",
    );

    // Backend is back: a real client + capturing fetch behind the queue's sender.
    const { fetchImpl, calls } = makeCapturingFetch();
    const client = new BobaClient({ fetchImpl, disableRateLimit: true });

    const result = await queue.processQueue(async (item) => {
      const url = item.torrent.magnetUri ?? item.torrent.torrentUrl ?? "";
      const res = await client.addMagnet(url);
      return res.accepted;
    });

    // The send actually happened through the real client.
    expect(calls).toHaveLength(1);
    const body = JSON.parse(
      need(need(calls[0], "captured request").bodyText, "request body"),
    ) as { download_urls: string[] };
    expect(body.download_urls[0]).toBe(MAGNET_URI);

    // The drained item left the queue and the persisted store is now empty.
    expect(result.succeeded).toBe(1);
    expect(result.remaining).toBe(0);
    const persisted = fake.store.get(STORAGE_KEYS.QUEUE) as OfflineQueueItem[];
    expect(persisted).toHaveLength(0);
  });
});
