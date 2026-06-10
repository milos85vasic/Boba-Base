/**
 * @fileoverview Challenge-scoped evidence harness for the BobaLink
 * detection → payload pipeline (Phase 8 — Challenges / §11.4.83).
 *
 * This is NOT a normal unit/integration spec — it is the Node harness invoked by
 * `challenges/extension/detect_and_forward_challenge.sh`. It drives the REAL,
 * shipped extension modules end-to-end (no re-implementation) and PERSISTS the
 * captured runtime evidence to `challenges/extension/.evidence/<run>.json`. The
 * bash challenge then re-reads that evidence file and asserts on it, so the
 * PASS verdict is backed by an auditable artefact per §11.4.83 / §11.4.69
 * (feature class: `network_throughput` — the extension's add-to-Boba request).
 *
 * The pipeline exercised (identical wiring to the user's real add-button path):
 *
 *   1. DETECT — a real jsdom `document` carrying a known magnet (as an
 *      `<a href>` AND as bare text, to prove cross-scanner dedup) is scanned by
 *      the REAL {@link ScannerOrchestrator} (composing the committed Link + Text
 *      scanners + the real {@link parseMagnetUri}). We capture the EXACT 40-char
 *      infohash + magnet URI it detected.
 *
 *   2. FORWARD — the detected magnet URI is handed to the REAL {@link BobaClient}
 *      with an injected capturing `fetchImpl`. We capture the ACTUAL request the
 *      client emitted: URL, method, and the parsed JSON body
 *      `{result_id, download_urls:[...]}`.
 *
 * Only the network boundary (`fetchImpl`) is substituted — every other layer is
 * the real shipped code. The spec FAILS (and writes no `pass:true` evidence) if
 * detection or the payload contract is broken, so a no-op stub of either the
 * orchestrator (returns []) or the client (never POSTs / wrong URL / wrong body)
 * cannot produce a green run. NO real token, NO private-tracker payload — the
 * magnet is the public-domain Sintel (CC-BY) test infohash used across the
 * existing HelixQA bank + webtorrent fixtures (§11.4.10).
 *
 * @module challenges/extension/detect_and_forward.evidence
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { ScannerOrchestrator } from "../../extension/src/scanner/orchestrator";
import { BobaClient } from "../../extension/src/api/boba-client";
import { TypedEventEmitter } from "../../extension/src/shared/events";
import type { DetectedTorrent } from "../../extension/src/types/torrent";

// ─────────────────────────────────────────────────────────────────────────────
// Known-input fixture. Sintel (Blender CC-BY) public-domain test infohash —
// the SAME synthetic magnet the boba-bobalink HelixQA bank uses (BOBA-LINK-003).
// No private-tracker payload, no credentials (§11.4.10).
// ─────────────────────────────────────────────────────────────────────────────
const EXPECTED_INFOHASH = "08ada5a7a6183aae1e09d831df6748d566095a10";
const MAGNET_URI = `magnet:?xt=urn:btih:${EXPECTED_INFOHASH}&dn=helixqa-sintel-test`;
const RESULT_ID = "bobalink-challenge";
const EXPECTED_ENDPOINT = "http://localhost:7187/api/v1/download";

// The magnet appears TWICE on the page (anchor + bare text) so a working
// orchestrator must DEDUP it to a single detection.
const PAGE_HTML = `
  <h1>Phase 8 challenge fixture</h1>
  <a id="magnet-link" href="${MAGNET_URI}">Sintel via magnet</a>
  <p>Also mirrored as plain text: ${MAGNET_URI} — enjoy!</p>
  <a href="https://example.org/just-a-page.html">not a torrent</a>
`;

const EVIDENCE_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  ".evidence",
  "detect_and_forward.json",
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
      json: () => Promise.resolve({ status: "initiated", added_count: 1, download_id: RESULT_ID }),
    } as unknown as Response);
  }) as unknown as typeof fetch;
  return { fetchImpl, calls };
}

function need<T>(v: T | null | undefined, label: string): T {
  if (v == null) throw new Error(`expected ${label} to be present, got ${String(v)}`);
  return v;
}

describe("CHALLENGE: BobaLink detection → /api/v1/download payload (real modules)", () => {
  beforeEach(() => {
    document.body.innerHTML = PAGE_HTML;
  });
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("detects the exact infohash and forwards {result_id, download_urls:[magnet]} to :7187", async () => {
    // ── STAGE 1: REAL detection ───────────────────────────────────────────────
    const orchestrator = new ScannerOrchestrator(new TypedEventEmitter(), {
      observeMutations: false,
    });
    await orchestrator.scanNow();
    const detected: readonly DetectedTorrent[] = orchestrator.getDetectedTorrents();

    const magnets = detected.filter((d) => d.type === "magnet");
    // Dedup across scanners: the duplicated magnet collapses to ONE detection.
    expect(magnets).toHaveLength(1);
    const magnet = need(magnets[0], "magnet detection");
    const detectedInfohash = need(magnet.magnet, "magnet info").infohash;
    const detectedUri = need(magnet.magnet, "magnet info").uri;

    // User-observable identity: the EXACT 40-char infohash + magnet URI.
    expect(detectedInfohash).toBe(EXPECTED_INFOHASH);
    expect(detectedUri).toBe(MAGNET_URI);

    // ── STAGE 2: REAL forward through BobaClient ─────────────────────────────
    const { fetchImpl, calls } = makeCapturingFetch();
    const client = new BobaClient({
      baseUrl: "http://localhost:7187",
      fetchImpl,
      disableRateLimit: true,
    });
    const result = await client.addMagnet(detectedUri, { resultId: RESULT_ID });
    expect(result.accepted).toBe(true);

    // EXACTLY one request hit the wire.
    expect(calls).toHaveLength(1);
    const req = need(calls[0], "captured request");
    expect(req.url).toBe(EXPECTED_ENDPOINT);
    expect(req.method).toBe("POST");

    const body = JSON.parse(need(req.bodyText, "request body")) as {
      result_id: string;
      download_urls: string[];
    };
    expect(body.result_id).toBe(RESULT_ID);
    expect(body.download_urls).toEqual([MAGNET_URI]);
    // Cross-stage identity: the forwarded magnet carries the detected infohash.
    expect(body.download_urls[0]).toContain(detectedInfohash);

    // ── EVIDENCE: persist the captured runtime data for the bash challenge ────
    const evidence = {
      pass: true,
      capturedAt: new Date().toISOString(),
      feature: "network_throughput", // §11.4.69 taxonomy class
      detection: {
        detectedCount: detected.length,
        magnetCount: magnets.length,
        detectedInfohash,
        detectedUri,
        displayName: magnet.displayName,
      },
      forward: {
        requestCount: calls.length,
        url: req.url,
        method: req.method,
        requestBody: body, // the exact {result_id, download_urls:[...]} POSTed
      },
      expected: {
        infohash: EXPECTED_INFOHASH,
        magnetUri: MAGNET_URI,
        endpoint: EXPECTED_ENDPOINT,
        resultId: RESULT_ID,
      },
    };
    mkdirSync(dirname(EVIDENCE_PATH), { recursive: true });
    writeFileSync(EVIDENCE_PATH, JSON.stringify(evidence, null, 2) + "\n", "utf8");
  });
});
