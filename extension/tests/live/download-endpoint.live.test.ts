import { describe, it, expect, beforeAll } from "vitest";

/**
 * LIVE integration test — POST a magnet to the REAL Boba merge service.
 *
 * This is the §11.4.27 / §11.4.52 "real system, not a mock" layer: it drives
 * the actual `/api/v1/download` endpoint over real HTTP and asserts the REAL
 * response body the route returns — never a stub.
 *
 * ── Backend contract (read from `download-proxy/src/api/routes.py`
 *    `initiate_download`, the `@router.post("/download")` handler) ──
 *
 *   Request body (DownloadRequest):
 *     { result_id: string, download_urls: string[] }
 *
 *   A magnet URL is NOT a tracker URL (`_is_tracker_url` returns falsy for
 *   `magnet:`), so it takes the `else` branch: the proxy logs into
 *   qBittorrent (`/api/v2/auth/login`) then POSTs `{ urls: <magnet> }` to
 *   `/api/v2/torrents/add` and reads qBittorrent's `Ok.` / `Fails.` body.
 *
 *   Success response (HTTP 200) body shape:
 *     {
 *       download_id: string (uuid),
 *       status: "initiated" | "failed",   // "initiated" iff added_count > 0
 *       urls_count: number,
 *       added_count: number,
 *       results: Array<{ url, status: "added"|"failed", detail? }>,
 *     }
 *
 *   Failure-before-add response bodies (still HTTP 200, status differs):
 *     { download_id, status: "auth_failed", results: [] }       // qBit login bad
 *     { download_id, status: "connection_failed", error: ... }  // qBit unreachable
 *
 * ── Anti-bluff rules baked in ──
 *  - Backend down (§11.4.3): SKIP with a clear reason — NOT a fail, NOT a fake pass.
 *  - SYNTHETIC magnet only (freeleech-only rule): a random throwaway infohash that
 *    references no real, ratio-costing private-tracker torrent. The magnet goes
 *    straight to qBittorrent's URL-add path; it never touches a private tracker's
 *    download endpoint, so it cannot cost ratio.
 *  - PASS asserts a user-observable field of the REAL body (`status`, the echoed
 *    `urls_count`, and a per-url `results` entry) — never "just HTTP 200".
 */

const BASE = process.env.BOBA_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:7187";
const DOWNLOAD_URL = `${BASE}/api/v1/download`;
const HEALTH_URL = `${BASE}/health`;

// Synthetic, freeleech-safe magnet: a fresh random 40-hex-char infohash so it
// maps to no real torrent on any tracker. `dn=` tags it as a HelixQA probe.
function syntheticMagnet(): string {
  const hex = "0123456789abcdef";
  let infohash = "";
  for (let i = 0; i < 40; i++) infohash += hex[Math.floor(Math.random() * 16)];
  return `magnet:?xt=urn:btih:${infohash}&dn=helixqa-live-probe`;
}

let backendReachable = false;
let skipReason = "";

/** §11.4.3 reachability guard — like a `require_backend` precondition. */
async function probeBackend(): Promise<void> {
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 5000);
    const res = await fetch(HEALTH_URL, { signal: ctl.signal }).finally(() => clearTimeout(t));
    if (!res.ok) {
      skipReason = `Boba merge service /health returned HTTP ${res.status} at ${BASE} — backend not healthy.`;
      return;
    }
    const body = (await res.json()) as { status?: string };
    if (body?.status !== "healthy") {
      skipReason = `Boba merge service /health body status='${body?.status}' (expected 'healthy') at ${BASE}.`;
      return;
    }
    backendReachable = true;
  } catch (err) {
    skipReason =
      `Boba merge service UNREACHABLE at ${BASE} (${(err as Error).message}). ` +
      `Start it via the project orchestrator './start.sh' (heavy multi-container boot), then re-run.`;
  }
}

describe("LIVE /api/v1/download (real Boba merge service :7187)", () => {
  beforeAll(probeBackend);

  it("POSTs a synthetic magnet and returns the real download response body", async (ctx) => {
    if (!backendReachable) {
      // Honest SKIP with a precise reason — never a green-without-backend pass.
      console.warn(`SKIP (§11.4.3): ${skipReason}`);
      ctx.skip();
      return;
    }

    const magnet = syntheticMagnet();
    const reqBody = {
      result_id: `helixqa-live-${Date.now()}`,
      download_urls: [magnet],
    };

    const res = await fetch(DOWNLOAD_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(reqBody),
    });

    // The route returns 200 on every non-validation outcome (success AND the
    // auth_failed / connection_failed bodies). A 401 means BOBA_API_TOKEN is
    // set and we lack it; a 422 means the body shape drifted — both are real
    // findings, so assert the contract explicitly.
    expect(res.status, "download endpoint should accept the request (200)").toBe(200);

    const body = (await res.json()) as {
      download_id?: string;
      status?: string;
      urls_count?: number;
      added_count?: number;
      results?: Array<{ url: string; status: string; detail?: string }>;
      error?: string;
    };

    // ── User-observable assertions on the REAL response (not just status code) ──

    // Every download response carries a server-minted download_id.
    expect(body.download_id, "real response must carry a download_id").toBeTruthy();

    // status is drawn from the route's closed vocabulary.
    expect(
      ["initiated", "failed", "auth_failed", "connection_failed"],
      `unexpected status '${body.status}' (real body: ${JSON.stringify(body)})`,
    ).toContain(body.status);

    if (body.status === "auth_failed" || body.status === "connection_failed") {
      // qBittorrent itself was down / mis-credentialed behind the proxy. The
      // BobaLink->proxy contract was still exercised end-to-end (we got the
      // real proxy verdict), but we cannot assert a successful add. Honest SKIP
      // rather than a misleading pass — the proxy is up, qBit is not usable.
      console.warn(
        `SKIP (§11.4.3): proxy reachable but qBittorrent backend status='${body.status}'. ` +
          `Real proxy body: ${JSON.stringify(body)}`,
      );
      ctx.skip();
      return;
    }

    // ── Success / failed-add path: assert the real echoed + computed fields. ──
    expect(body.urls_count, "proxy must echo the count of urls we sent").toBe(1);
    const results = body.results;
    expect(Array.isArray(results), "results must be an array").toBe(true);
    if (!Array.isArray(results)) return;
    expect(results.length, "one result per submitted url").toBe(1);

    const r0 = results[0];
    expect(r0, "one result must be present").toBeDefined();
    if (r0 === undefined) return;
    expect(r0.url, "result must reference the magnet we sent").toBe(magnet);
    // The per-url status is the real qBittorrent add verdict.
    expect(
      ["added", "failed", "error"],
      `unexpected per-url status '${r0.status}'`,
    ).toContain(r0.status);

    // Cross-check the computed top-level status against the per-url verdict —
    // proves the body is internally consistent (a stubbed handler would not be).
    if (r0.status === "added") {
      expect(body.added_count, "added_count must reflect the added url").toBeGreaterThanOrEqual(1);
      expect(body.status, "top status must be 'initiated' when a url was added").toBe("initiated");
    } else {
      expect(body.status, "top status must be 'failed' when no url was added").toBe("failed");
    }
  });
});
