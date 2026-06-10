/**
 * @fileoverview Anti-bluff unit tests for the Boba client's DECRYPT-and-send
 * path (Phase 7 residual from the security review).
 *
 * The existing `boba-client.test.ts` proves the client attaches the auth
 * headers from a *plaintext* token. THIS file proves the load-bearing residual:
 * the client can take the operator's *encrypted* `BOBA_API_TOKEN` bundle (the
 * JSON-serialized `EncryptedBundle` stored in `ServerConfig.encryptedBobaApiToken`)
 * plus the session passphrase, DECRYPT it via the adopted `shared/crypto.ts`,
 * and send the resulting PLAINTEXT token on the wire as
 * `Authorization: Bearer <plaintext>` (+ `X-Boba-Token: <plaintext>`).
 *
 * USER-OBSERVABLE assertions (§11.4 / CONST-XII): we read the captured request
 * headers from the fetch stub and assert the DECRYPTED plaintext is what hit the
 * wire — NOT the encrypted bundle text, NOT a status code.
 *
 * Anti-bluff (§11.4.10): a dedicated test proves the plaintext token NEVER
 * appears in any console log line AND the encrypted-bundle ciphertext is what
 * was stored (so a regression that "logs the token" or "sends the bundle as the
 * token" fails loudly).
 *
 * Every assertion fails against the pre-fix code (no `create()` / no decrypt):
 * the static factory does not exist, so the test cannot even construct a client.
 *
 * NEVER embeds a real token — encrypts a synthetic `test-token-<uuid>` at
 * runtime with a synthetic passphrase.
 *
 * @module tests/unit/boba-client-token.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { BobaClient } from "../../src/api/boba-client";
import { encrypt } from "../../src/shared/crypto";

const MAGNET =
  "magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678&dn=Test";
const PLAINTEXT_TOKEN = `test-token-${crypto.randomUUID()}`;
const PASSPHRASE = `test-pass-${crypto.randomUUID()}`;
const BASE = "http://localhost:7187";

/** Build a Response-like object good enough for the client's `.ok`/`.json()`. */
function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

/** Capture the (url, init) of the most recent fetch call. */
function lastCall(mock: ReturnType<typeof vi.fn>): {
  url: string;
  init: RequestInit;
} {
  const calls = mock.mock.calls;
  const [url, init] = calls[calls.length - 1] as [string, RequestInit];
  return { url, init };
}

function headersOf(init: RequestInit): Record<string, string> {
  return (init.headers as Record<string, string>) ?? {};
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("BobaClient.create — decrypts the encrypted BOBA_API_TOKEN and sends plaintext", () => {
  it("WHEN an encrypted token + passphrase are given: the request carries the DECRYPTED plaintext as Authorization: Bearer (+ X-Boba-Token)", async () => {
    // Operator stored the token encrypted; this is exactly what lives in
    // ServerConfig.encryptedBobaApiToken (options.ts: JSON.stringify(bundle)).
    const encryptedToken = JSON.stringify(
      await encrypt(PLAINTEXT_TOKEN, PASSPHRASE),
    );

    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "initiated" }));

    const client = await BobaClient.create({
      baseUrl: BASE,
      encryptedToken,
      passphrase: PASSPHRASE,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await client.addMagnet(MAGNET);

    const headers = headersOf(lastCall(fetchMock).init);
    // The DECRYPTED plaintext must hit the wire — not the encrypted bundle text.
    expect(headers["Authorization"]).toBe(`Bearer ${PLAINTEXT_TOKEN}`);
    expect(headers["X-Boba-Token"]).toBe(PLAINTEXT_TOKEN);
    // The encrypted-bundle JSON (ciphertext) must NEVER be what we sent.
    expect(headers["Authorization"]).not.toContain(encryptedToken);
    expect(headers["X-Boba-Token"]).not.toBe(encryptedToken);
  });

  it("WHEN no encrypted token is configured: NO auth header is sent (default-open contract preserved)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "initiated" }));

    const client = await BobaClient.create({
      baseUrl: BASE,
      passphrase: PASSPHRASE, // passphrase present but no token to decrypt
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await client.addMagnet(MAGNET);

    const headers = headersOf(lastCall(fetchMock).init);
    expect(headers["Authorization"]).toBeUndefined();
    expect(headers["X-Boba-Token"]).toBeUndefined();
  });

  it("WHEN an encrypted token is present but NO passphrase is available: NO auth header (cannot decrypt → default-open, never sends ciphertext)", async () => {
    const encryptedToken = JSON.stringify(
      await encrypt(PLAINTEXT_TOKEN, PASSPHRASE),
    );
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "initiated" }));

    const client = await BobaClient.create({
      baseUrl: BASE,
      encryptedToken,
      // no passphrase
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await client.addMagnet(MAGNET);

    const headers = headersOf(lastCall(fetchMock).init);
    expect(headers["Authorization"]).toBeUndefined();
    expect(headers["X-Boba-Token"]).toBeUndefined();
    // Must NOT degrade to sending the raw bundle as a token.
    expect(JSON.stringify(headers)).not.toContain(encryptedToken);
  });

  it("a wrong passphrase fails to decrypt → rejects (never sends a garbage/ciphertext token)", async () => {
    const encryptedToken = JSON.stringify(
      await encrypt(PLAINTEXT_TOKEN, PASSPHRASE),
    );

    await expect(
      BobaClient.create({
        baseUrl: BASE,
        encryptedToken,
        passphrase: `wrong-${PASSPHRASE}`,
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    ).rejects.toThrow();

    // No request should have been issued with a bogus token.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("§11.4.10: the DECRYPTED plaintext token never appears in any console log line", async () => {
    const logged: string[] = [];
    for (const m of ["debug", "info", "warn", "error"] as const) {
      vi.spyOn(console, m).mockImplementation((...args: unknown[]) => {
        logged.push(args.map((a) => String(a)).join(" "));
      });
    }

    const encryptedToken = JSON.stringify(
      await encrypt(PLAINTEXT_TOKEN, PASSPHRASE),
    );
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "initiated" }));

    const client = await BobaClient.create({
      baseUrl: BASE,
      encryptedToken,
      passphrase: PASSPHRASE,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    await client.addMagnet(MAGNET);

    const all = logged.join("\n");
    expect(all).toContain("[token: set]");
    // The plaintext token AND the passphrase must never leak into logs.
    expect(all).not.toContain(PLAINTEXT_TOKEN);
    expect(all).not.toContain(PASSPHRASE);
  });
});
