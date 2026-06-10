/**
 * @fileoverview Anti-bluff unit tests for the REAL Boba :7187 API client.
 *
 * Imports the production `src/api/boba-client.ts` and drives it against a
 * mocked `fetch`. Asserts USER-OBSERVABLE outcomes (§11.4 / CONST-XII):
 *   - addMagnet POSTs to the RIGHT url (.../api/v1/download) — proves :7187,
 *     NOT 8080 / qBittorrent /api/v2/torrents.
 *   - the body shape is {result_id, download_urls:[magnet]} (batch = array).
 *   - WHEN a token is set, the request carries `Authorization: Bearer <token>`
 *     (and `X-Boba-Token`) — the load-bearing security-item proof.
 *   - WHEN no token is set, NO auth header is sent (default-open contract).
 *   - retry-on-5xx: fetch called N times then succeeds.
 *   - timeout aborts (AbortError → NetworkError).
 *   - health / authStatus parse the body.
 *   - §11.4.10: the token VALUE never appears in any console log line.
 *
 * Every assertion fails against a no-op stub of BobaClient (a class whose
 * methods return `{}` and never call fetch): the URL/body/header inspections
 * have nothing to read, and the fetch-call-count assertions see 0 calls.
 *
 * NEVER embeds a real token — uses a synthetic `test-token-<uuid>`.
 *
 * @module tests/unit/boba-client.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { BobaClient } from "../../src/api/boba-client";
import { NetworkError } from "../../src/shared/errors";

const MAGNET =
  "magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678&dn=Test";
const SYNTH_TOKEN = `test-token-${crypto.randomUUID()}`;
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

describe("BobaClient.addMagnet — POST target + body shape (:7187, not 8080/qBt)", () => {
  it("POSTs to <base>/api/v1/download with {result_id, download_urls:[magnet]}", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { download_id: "dl-1", status: "initiated", added_count: 1 }),
    );
    const client = new BobaClient({ baseUrl: BASE, fetchImpl: fetchMock as unknown as typeof fetch });

    const res = await client.addMagnet(MAGNET, { resultId: "r-42" });

    const { url, init } = lastCall(fetchMock);
    // Right port + right path — proves merge service, NOT :8080 /api/v2/torrents.
    expect(url).toBe("http://localhost:7187/api/v1/download");
    expect(url).not.toContain(":8080");
    expect(url).not.toContain("/api/v2/torrents");
    expect(init.method).toBe("POST");

    const sent = JSON.parse(init.body as string) as {
      result_id: string;
      download_urls: string[];
    };
    expect(sent.result_id).toBe("r-42");
    expect(sent.download_urls).toEqual([MAGNET]);

    // User-observable outcome.
    expect(res.accepted).toBe(true);
    expect(res.downloadId).toBe("dl-1");
    expect(res.addedCount).toBe(1);
  });

  it("addMagnets batches all urls into download_urls[]", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "initiated", added_count: 2 }));
    const client = new BobaClient({ baseUrl: BASE, fetchImpl: fetchMock as unknown as typeof fetch });

    const m2 = "magnet:?xt=urn:btih:abcdefabcdefabcdefabcdefabcdefabcdefabcd";
    await client.addMagnets([MAGNET, m2]);

    const sent = JSON.parse(lastCall(fetchMock).init.body as string) as {
      download_urls: string[];
    };
    expect(sent.download_urls).toEqual([MAGNET, m2]);
  });

  it("defaults to base URL :7187 when none is supplied", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "initiated" }));
    const client = new BobaClient({ fetchImpl: fetchMock as unknown as typeof fetch });
    await client.addMagnet(MAGNET);
    expect(lastCall(fetchMock).url).toBe("http://localhost:7187/api/v1/download");
  });

  it("reports accepted:false when the backend reports status:failed", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "failed", added_count: 0 }));
    const client = new BobaClient({ baseUrl: BASE, fetchImpl: fetchMock as unknown as typeof fetch });
    const res = await client.addMagnet(MAGNET);
    expect(res.accepted).toBe(false);
  });
});

describe("BobaClient auth header — the env-gated-token security proof (§ Plan E)", () => {
  it("WHEN a token is set: request carries Authorization: Bearer <token> (+ X-Boba-Token)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "initiated" }));
    const client = new BobaClient({
      baseUrl: BASE,
      token: SYNTH_TOKEN,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await client.addMagnet(MAGNET);

    const headers = headersOf(lastCall(fetchMock).init);
    expect(headers["Authorization"]).toBe(`Bearer ${SYNTH_TOKEN}`);
    expect(headers["X-Boba-Token"]).toBe(SYNTH_TOKEN);
  });

  it("WHEN no token is set: NO auth header is sent (default-open contract)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "initiated" }));
    const client = new BobaClient({ baseUrl: BASE, fetchImpl: fetchMock as unknown as typeof fetch });

    await client.addMagnet(MAGNET);

    const headers = headersOf(lastCall(fetchMock).init);
    expect(headers["Authorization"]).toBeUndefined();
    expect(headers["X-Boba-Token"]).toBeUndefined();
  });

  it("an empty-string token is treated as no token (no auth header)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "initiated" }));
    const client = new BobaClient({ baseUrl: BASE, token: "", fetchImpl: fetchMock as unknown as typeof fetch });
    await client.addMagnet(MAGNET);
    const headers = headersOf(lastCall(fetchMock).init);
    expect(headers["Authorization"]).toBeUndefined();
  });

  it("§11.4.10: the token VALUE never appears in any console log line", async () => {
    const logged: string[] = [];
    for (const m of ["debug", "info", "warn", "error"] as const) {
      vi.spyOn(console, m).mockImplementation((...args: unknown[]) => {
        logged.push(args.map((a) => String(a)).join(" "));
      });
    }
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "initiated" }));

    const client = new BobaClient({
      baseUrl: BASE,
      token: SYNTH_TOKEN,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    await client.addMagnet(MAGNET);

    const all = logged.join("\n");
    // The constructor + request logs must say "[token: set]" but never the value.
    expect(all).toContain("[token: set]");
    expect(all).not.toContain(SYNTH_TOKEN);
  });
});

describe("BobaClient retry + timeout", () => {
  it("retries on 5xx then succeeds (fetch called N times)", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(503, { detail: "unavailable" }))
      .mockResolvedValueOnce(jsonResponse(502, { detail: "bad gateway" }))
      .mockResolvedValueOnce(jsonResponse(200, { status: "initiated", added_count: 1 }));

    const client = new BobaClient({
      baseUrl: BASE,
      maxRetries: 3,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    const res = await client.addMagnet(MAGNET);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(res.accepted).toBe(true);
  });

  it("retries on a network error then succeeds", async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse(200, { status: "initiated" }));

    const client = new BobaClient({
      baseUrl: BASE,
      maxRetries: 2,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    const res = await client.addMagnet(MAGNET);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(res.accepted).toBe(true);
  });

  it("does NOT retry a 4xx and surfaces a ServerError", async () => {
    fetchMock.mockResolvedValue(jsonResponse(400, { detail: "bad request" }));
    const client = new BobaClient({
      baseUrl: BASE,
      maxRetries: 3,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    await expect(client.addMagnet(MAGNET)).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("aborts on timeout and raises a NetworkError", async () => {
    // fetch that rejects with an AbortError once the signal aborts.
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          const signal = init.signal;
          if (signal) {
            signal.addEventListener("abort", () => {
              const e = new Error("aborted");
              e.name = "AbortError";
              reject(e);
            });
          }
        }),
    );

    const client = new BobaClient({
      baseUrl: BASE,
      timeoutMs: 20,
      maxRetries: 0,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await expect(client.addMagnet(MAGNET)).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("BobaClient.health / authStatus", () => {
  it("health() parses {status:'healthy'} → ok:true", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { status: "healthy", service: "merge", version: "1.0" }),
    );
    const client = new BobaClient({ baseUrl: BASE, fetchImpl: fetchMock as unknown as typeof fetch });
    const h = await client.health();
    expect(lastCall(fetchMock).url).toBe("http://localhost:7187/health");
    expect(h.ok).toBe(true);
    expect(h.status).toBe("healthy");
  });

  it("health() returns ok:false (not throw) when the server is unreachable", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const client = new BobaClient({ baseUrl: BASE, maxRetries: 0, fetchImpl: fetchMock as unknown as typeof fetch });
    const h = await client.health();
    expect(h.ok).toBe(false);
  });

  it("authStatus() GETs /api/v1/auth/status and returns the raw body", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { require_api_token: false, open: true }));
    const client = new BobaClient({ baseUrl: BASE, fetchImpl: fetchMock as unknown as typeof fetch });
    const body = (await client.authStatus()) as { open: boolean };
    expect(lastCall(fetchMock).url).toBe("http://localhost:7187/api/v1/auth/status");
    expect(body.open).toBe(true);
  });
});
