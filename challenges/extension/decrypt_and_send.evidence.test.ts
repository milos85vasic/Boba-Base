/**
 * @fileoverview Challenge-scoped evidence harness for the BobaLink
 * decrypt-before-send token path (Phase 8 — Challenges / §11.4.83).
 *
 * This is NOT a normal unit/integration spec — it is the Node harness invoked by
 * `challenges/extension/decrypt_and_send_challenge.sh`. It drives the REAL,
 * shipped extension modules end-to-end (no re-implementation) and PERSISTS the
 * captured runtime evidence to `challenges/extension/.evidence/<run>.json`. The
 * bash challenge then re-reads that evidence file and asserts on it, so the
 * PASS verdict is backed by an auditable artefact per §11.4.83 / §11.4.69
 * (feature class: `network_throughput` — the extension's authenticated request).
 *
 * The path exercised (identical to the operator's real shared-secret-token flow):
 *
 *   1. ENCRYPT — a SYNTHETIC token string is encrypted to a real
 *      {@link EncryptedBundle} via the REAL {@link encrypt} (AES-256-GCM / PBKDF2,
 *      `shared/crypto.ts`). The JSON-serialized bundle is what
 *      `ServerConfig.encryptedBobaApiToken` stores.
 *
 *   2. DECRYPT + CONSTRUCT — that encrypted bundle + the passphrase are handed to
 *      the REAL {@link BobaClient.create} (the decrypt-and-send factory), which
 *      DECRYPTS the token via the REAL {@link decrypt} and constructs a client
 *      carrying the resulting PLAINTEXT.
 *
 *   3. FORWARD — the client issues a real `addMagnet` with an injected capturing
 *      `fetchImpl`. We capture the ACTUAL `Authorization` + `X-Boba-Token`
 *      headers it emitted.
 *
 * The user-observable, anti-bluff assertion: the request carries the DECRYPTED
 * PLAINTEXT in `Authorization: Bearer <plaintext>` — NOT the ciphertext, NOT the
 * JSON bundle, NOT the passphrase. A no-op stub that "forgot" to decrypt and sent
 * the ciphertext on the wire would FAIL here (the captured header would contain
 * the bundle's base64 ciphertext, never the plaintext). The NEGATIVE half proves
 * the default-open contract: with NO passphrase, `create()` sends NO auth header
 * at all — the ciphertext is never leaked as a token.
 *
 * Only the network boundary (`fetchImpl`) is substituted — every other layer is
 * the real shipped code (`encrypt`, `decrypt`, `BobaClient.create`, `addMagnet`).
 *
 * §11.4.10: the token is a SYNTHETIC value generated in-process; it is NEVER
 * logged and NEVER written to the evidence file as plaintext — the evidence
 * records only its sha256 fingerprint + the booleans that prove the wire carried
 * the plaintext (header-equals-plaintext) and NOT the ciphertext
 * (header-not-equals-ciphertext).
 *
 * @module challenges/extension/decrypt_and_send.evidence
 */

import { describe, it, expect } from "vitest";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";
import { randomBytes, createHash } from "node:crypto";
import { dirname, resolve } from "node:path";

import { BobaClient } from "../../extension/src/api/boba-client";
import { encrypt } from "../../extension/src/shared/crypto";

// ─────────────────────────────────────────────────────────────────────────────
// Known-input fixture. A SYNTHETIC token (random, in-process) — no real
// credential, never persisted as plaintext, never logged (§11.4.10). A public-
// domain Sintel (CC-BY) magnet is the request payload (no private-tracker data).
// ─────────────────────────────────────────────────────────────────────────────
const SYNTHETIC_TOKEN = `bobalink-synthetic-${randomBytes(12).toString("hex")}`;
const PASSPHRASE = `challenge-passphrase-${randomBytes(8).toString("hex")}`;
const MAGNET_URI =
  "magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=helixqa-sintel-test";
const RESULT_ID = "bobalink-decrypt-challenge";
const EXPECTED_ENDPOINT = "http://localhost:7187/api/v1/download";

const EVIDENCE_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  ".evidence",
  "decrypt_and_send.json",
);

interface CapturedRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
}

/** Normalize a fetch HeadersInit into a plain lowercased-key map. */
function headersToRecord(init?: HeadersInit): Record<string, string> {
  const out: Record<string, string> = {};
  if (!init) return out;
  if (init instanceof Headers) {
    init.forEach((v, k) => {
      out[k] = v;
    });
  } else if (Array.isArray(init)) {
    for (const [k, v] of init) out[k] = v;
  } else {
    for (const [k, v] of Object.entries(init)) out[k] = v as string;
  }
  return out;
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
      headers: headersToRecord(init?.headers),
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

function sha256(s: string): string {
  return createHash("sha256").update(s, "utf8").digest("hex");
}

describe("CHALLENGE: BobaLink decrypt-before-send token path (real crypto + client)", () => {
  it("sends the DECRYPTED plaintext in Authorization (never the ciphertext); no passphrase ⇒ no auth header", async () => {
    // ── STAGE 1: REAL encrypt — produce the stored EncryptedBundle ─────────────
    const bundle = await encrypt(SYNTHETIC_TOKEN, PASSPHRASE);
    // Sanity: the ciphertext must differ from the plaintext (real encryption).
    expect(bundle.ciphertext).not.toBe(SYNTHETIC_TOKEN);
    const encryptedToken = JSON.stringify(bundle);

    // ── STAGE 2: REAL decrypt-and-construct via BobaClient.create ──────────────
    const { fetchImpl, calls } = makeCapturingFetch();
    const client = await BobaClient.create({
      baseUrl: "http://localhost:7187",
      encryptedToken,
      passphrase: PASSPHRASE,
      fetchImpl,
      disableRateLimit: true,
    });

    // ── STAGE 3: REAL forward — capture the exact headers on the wire ──────────
    const result = await client.addMagnet(MAGNET_URI, { resultId: RESULT_ID });
    expect(result.accepted).toBe(true);

    expect(calls).toHaveLength(1);
    const req = need(calls[0], "captured request");
    expect(req.url).toBe(EXPECTED_ENDPOINT);
    expect(req.method).toBe("POST");

    const authHeader = need(req.headers.Authorization, "Authorization header");
    const xBobaHeader = need(req.headers["X-Boba-Token"], "X-Boba-Token header");

    // USER-OBSERVABLE, ANTI-BLUFF: the wire carries the DECRYPTED plaintext —
    // NOT the ciphertext, NOT the JSON bundle, NOT the passphrase.
    expect(authHeader).toBe(`Bearer ${SYNTHETIC_TOKEN}`);
    expect(xBobaHeader).toBe(SYNTHETIC_TOKEN);
    // The ciphertext (and the whole stored bundle) MUST NOT appear on the wire.
    expect(authHeader).not.toContain(bundle.ciphertext);
    expect(authHeader).not.toContain(encryptedToken);
    expect(authHeader).not.toContain(PASSPHRASE);

    // ── STAGE 4 (NEGATIVE): no passphrase ⇒ default-open, NO auth header ───────
    const { fetchImpl: noPassFetch, calls: noPassCalls } = makeCapturingFetch();
    const openClient = await BobaClient.create({
      baseUrl: "http://localhost:7187",
      encryptedToken, // same encrypted bundle present…
      // …but NO passphrase → must NOT decrypt and must NOT send the ciphertext.
      fetchImpl: noPassFetch,
      disableRateLimit: true,
    });
    await openClient.addMagnet(MAGNET_URI, { resultId: RESULT_ID });
    const openReq = need(noPassCalls[0], "captured open request");
    const openHasAuth = "Authorization" in openReq.headers;
    const openHasXBoba = "X-Boba-Token" in openReq.headers;
    expect(openHasAuth).toBe(false);
    expect(openHasXBoba).toBe(false);

    // ── EVIDENCE: persist booleans + fingerprints, NEVER the plaintext ─────────
    const evidence = {
      pass: true,
      capturedAt: new Date().toISOString(),
      feature: "network_throughput", // §11.4.69 taxonomy class
      // §11.4.10: only fingerprints, never the secret values themselves.
      fingerprints: {
        tokenSha256: sha256(SYNTHETIC_TOKEN),
        ciphertextSha256: sha256(bundle.ciphertext),
      },
      decryptAndSend: {
        url: req.url,
        method: req.method,
        // Proof the wire carried the DECRYPTED plaintext, by fingerprint match…
        authHeaderSha256: sha256(authHeader),
        // …Bearer <plaintext> ⇒ sha256("Bearer " + plaintext).
        expectedAuthHeaderSha256: sha256(`Bearer ${SYNTHETIC_TOKEN}`),
        authHeaderEqualsPlaintextBearer: authHeader === `Bearer ${SYNTHETIC_TOKEN}`,
        xBobaTokenEqualsPlaintext: xBobaHeader === SYNTHETIC_TOKEN,
        // …and that it did NOT carry the ciphertext / bundle / passphrase.
        authHeaderContainsCiphertext: authHeader.includes(bundle.ciphertext),
        authHeaderContainsBundle: authHeader.includes(encryptedToken),
        authHeaderContainsPassphrase: authHeader.includes(PASSPHRASE),
      },
      negativeNoPassphrase: {
        url: openReq.url,
        method: openReq.method,
        hasAuthHeader: openHasAuth,
        hasXBobaHeader: openHasXBoba,
      },
      expected: {
        endpoint: EXPECTED_ENDPOINT,
        resultId: RESULT_ID,
      },
    };
    mkdirSync(dirname(EVIDENCE_PATH), { recursive: true });
    writeFileSync(EVIDENCE_PATH, JSON.stringify(evidence, null, 2) + "\n", "utf8");
  });
});
