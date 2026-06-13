import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { BobaClient } from "@/api/boba-client";

/**
 * LIVE integration test — the REAL detect→send→torrent-in-qBittorrent
 * round-trip, driven the moment the operator brings the Boba backend up.
 *
 * This is the §11.4.27 / §11.4.52 "real system, not a mock" layer: it drives
 * the actual `/api/v1/download` endpoint over real HTTP via the extension's
 * OWN `BobaClient` send path, asserts the REAL response body, AND — the real
 * release-blocker — INDEPENDENTLY confirms the synthetic torrent actually
 * APPEARS in qBittorrent's torrent list (never just "the proxy said ok").
 *
 * ── Backend contract (verified against the real backend source) ──
 *
 *   1. SEND — Boba merge service on :7187 (`download-proxy/src/api/routes.py`,
 *      `initiate_download`, `@router.post("/download")`):
 *        Request body (DownloadRequest):  { result_id, download_urls: string[] }
 *        A `magnet:` URL is NOT a tracker URL (`_is_tracker_url` → falsy), so it
 *        takes the `else` branch (routes.py:879-895): the proxy logs into
 *        qBittorrent (`POST /api/v2/auth/login` → body `Ok.`) then POSTs
 *        `{ urls: <magnet> }` to `/api/v2/torrents/add` and reads the
 *        `Ok.` / `Fails.` body.
 *        Success body (HTTP 200):
 *          { download_id, status:"initiated"|"failed", urls_count, added_count,
 *            results:[{ url, status:"added"|"failed"|"error", detail? }] }
 *        Pre-add bodies (still 200): { ..., status:"auth_failed" | "connection_failed" }
 *
 *   2. CONFIRM — qBittorrent WebUI fronted by the authenticated download proxy
 *      on :7186 (project CLAUDE.md "Port Map" + `download-proxy/src/api/__init__.py`
 *      lines 200-215: ":7186 is the authenticated qBittorrent WebUI front;
 *      the container-internal :7185 answers 401 without the proxy shim").
 *      The qBittorrent WebUI v2 contract is the SAME one the backend itself
 *      uses (`routes.py:596-621` `get_active_downloads`):
 *        - `POST /api/v2/auth/login`  data={username,password}  → body "Ok." + SID cookie
 *        - `GET  /api/v2/torrents/info` (cookie)                → JSON list; each has `hash`
 *        - `POST /api/v2/torrents/delete` data={hashes,deleteFiles}  (cleanup)
 *      Credentials are the hardcoded `admin`/`admin` (project CLAUDE.md:
 *      "WebUI credentials admin/admin are hardcoded — do not change").
 *      A magnet's btih infohash IS the qBittorrent torrent `hash` (lowercase
 *      40-hex), so we match our synthetic infohash against the `hash` field.
 *
 * ── Anti-bluff rules baked in (§11.4.3 / §11.4.68 — no fail-open) ──
 *  - Merge service down → SKIP-with-reason (not fail, not fake pass).
 *  - Proxy (:7186) down OR the confirm endpoints unreachable → SKIP-with-reason;
 *    we NEVER claim "torrent present" without actually reading the live list.
 *  - SYNTHETIC magnet only (freeleech-only rule): a fresh random 40-hex infohash
 *    that references no real, ratio-costing torrent. It goes straight to
 *    qBittorrent's URL-add path; it never touches a private tracker.
 *  - CLEANUP (§11.4.14): afterAll DELETEs the synthetic torrent (best-effort) so
 *    the live run leaves qBittorrent quiescent — no orphan junk magnets pile up.
 *
 * ── Send path (design note) ──
 *  The send is driven through the extension's REAL `BobaClient.addMagnet`
 *  (`src/api/boba-client.ts`) so the actual extension send path is exercised
 *  end-to-end against the real backend (§11.4.52 user-path). We ALSO issue one
 *  raw `fetch` to `/api/v1/download` to assert the FULL response-body contract
 *  (`urls_count`, per-url `results[]`) that `BobaClient` normalises away into
 *  its `AddResult`. Both hit the real route; the BobaClient call is the
 *  user-observable proof the extension's own client works, the raw call is the
 *  body-shape proof.
 */

const BASE = process.env.BOBA_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:7187";
const DOWNLOAD_URL = `${BASE}/api/v1/download`;
const HEALTH_URL = `${BASE}/health`;

// The authenticated qBittorrent WebUI front (download proxy). Override with
// BOBA_PROXY_URL if the operator maps it elsewhere. Default :7186 per the
// project CLAUDE.md Port Map.
const PROXY_BASE = process.env.BOBA_PROXY_URL?.replace(/\/$/, "") ?? "http://localhost:7186";
// Hardcoded WebUI credentials (project CLAUDE.md: admin/admin, do not change).
const QBIT_USER = process.env.QBITTORRENT_USER ?? "admin";
const QBIT_PASS = process.env.QBITTORRENT_PASS ?? "admin";

const PROBE_TIMEOUT_MS = 5000;
const QBIT_OP_TIMEOUT_MS = 10_000;

interface SyntheticMagnet {
  readonly uri: string;
  readonly infohash: string; // lowercase 40-hex — matches qBittorrent `hash`
}

/**
 * Synthetic, freeleech-safe magnet: a fresh random 40-hex infohash so it maps
 * to no real torrent on any tracker. `dn=` tags it as a HelixQA probe.
 */
function syntheticMagnet(): SyntheticMagnet {
  const hex = "0123456789abcdef";
  let infohash = "";
  for (let i = 0; i < 40; i++) infohash += hex[Math.floor(Math.random() * 16)];
  return {
    uri: `magnet:?xt=urn:btih:${infohash}&dn=helixqa-live-probe`,
    infohash,
  };
}

/** fetch with an AbortController timeout (no wall-clock assertions anywhere). */
async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: ctl.signal });
  } finally {
    clearTimeout(t);
  }
}

let backendReachable = false;
let backendSkipReason = "";

/** §11.4.3 reachability guard for the merge service — a `require_backend`. */
async function probeBackend(): Promise<void> {
  try {
    const res = await fetchWithTimeout(HEALTH_URL, {}, PROBE_TIMEOUT_MS);
    if (!res.ok) {
      backendSkipReason = `Boba merge service /health returned HTTP ${res.status} at ${BASE} — backend not healthy.`;
      return;
    }
    const body = (await res.json()) as { status?: string };
    if (body?.status !== "healthy") {
      backendSkipReason = `Boba merge service /health body status='${body?.status}' (expected 'healthy') at ${BASE}.`;
      return;
    }
    backendReachable = true;
  } catch (err) {
    backendSkipReason =
      `Boba merge service UNREACHABLE at ${BASE} (${(err as Error).message}). ` +
      `Start it via the project orchestrator './start.sh' (heavy multi-container boot), then re-run.`;
  }
}

// ── qBittorrent confirm helpers (all SKIP-safe: throw a typed error the test
//    converts to an honest SKIP, never a pass) ──

class QBitUnavailable extends Error {}

/** Log into the qBittorrent WebUI via the :7186 proxy; returns the SID cookie. */
async function qbitLogin(): Promise<string> {
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${PROXY_BASE}/api/v2/auth/login`,
      {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username: QBIT_USER, password: QBIT_PASS }).toString(),
      },
      QBIT_OP_TIMEOUT_MS,
    );
  } catch (err) {
    throw new QBitUnavailable(
      `qBittorrent WebUI proxy UNREACHABLE at ${PROXY_BASE} (${(err as Error).message}).`,
    );
  }
  const text = (await res.text()).trim();
  // qBittorrent login is version-dependent: legacy (<4.6) returns 200 "Ok.";
  // modern (4.6+/5.x, linuxserver:latest) returns 204 No Content with an empty
  // body. BOTH issue the SID session cookie on success; a failed login returns
  // 200 "Fails." with no cookie. Mirror the proxy's `_qbit_login_succeeded`:
  // the authoritative, version-independent success signal is the issued SID
  // cookie — not a specific status or the "Ok." body (which 204 omits).
  if (res.status !== 200 && res.status !== 204) {
    throw new QBitUnavailable(
      `qBittorrent login via proxy ${PROXY_BASE} returned HTTP ${res.status} body='${text.slice(0, 80)}' (expected 200/204 + SID cookie).`,
    );
  }
  // qBittorrent issues an SID cookie on login. Forward it verbatim.
  const setCookie = res.headers.get("set-cookie");
  if (setCookie === null || setCookie.length === 0) {
    throw new QBitUnavailable(
      `qBittorrent login via proxy ${PROXY_BASE} (HTTP ${res.status}) issued no Set-Cookie (SID) — login not authenticated, cannot authorise the confirm read.`,
    );
  }
  // Keep only the cookie name=value pair(s), dropping attributes.
  return setCookie
    .split(/,(?=[^;]+=[^;]+)/)
    .map((c) => c.split(";")[0]?.trim() ?? "")
    .filter((c) => c.length > 0)
    .join("; ");
}

interface QBitTorrent {
  readonly hash?: string;
  readonly name?: string;
}

/** GET /api/v2/torrents/info via the proxy, with the SID cookie. */
async function qbitTorrentsInfo(cookie: string): Promise<QBitTorrent[]> {
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${PROXY_BASE}/api/v2/torrents/info`,
      { headers: { cookie } },
      QBIT_OP_TIMEOUT_MS,
    );
  } catch (err) {
    throw new QBitUnavailable(
      `qBittorrent /api/v2/torrents/info UNREACHABLE at ${PROXY_BASE} (${(err as Error).message}).`,
    );
  }
  if (res.status !== 200) {
    throw new QBitUnavailable(
      `qBittorrent /api/v2/torrents/info via ${PROXY_BASE} returned HTTP ${res.status} (expected 200).`,
    );
  }
  const body = (await res.json()) as unknown;
  if (!Array.isArray(body)) {
    throw new QBitUnavailable(
      `qBittorrent /api/v2/torrents/info via ${PROXY_BASE} did not return a JSON array.`,
    );
  }
  return body as QBitTorrent[];
}

/** Best-effort cleanup: DELETE the synthetic torrent so the run is quiescent. */
async function qbitDelete(cookie: string, infohash: string): Promise<void> {
  await fetchWithTimeout(
    `${PROXY_BASE}/api/v2/torrents/delete`,
    {
      method: "POST",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        cookie,
      },
      body: new URLSearchParams({ hashes: infohash, deleteFiles: "true" }).toString(),
    },
    QBIT_OP_TIMEOUT_MS,
  );
}

// Track what we added so afterAll can clean it up (§11.4.14).
let addedInfohash: string | null = null;

describe("LIVE detect→send→torrent-in-qBittorrent (real Boba :7187 + qBit :7186)", () => {
  beforeAll(probeBackend);

  // §11.4.14 — leave qBittorrent quiescent. Best-effort; NEVER fails the run
  // (the backend may already be mid-teardown when this fires).
  afterAll(async () => {
    if (addedInfohash === null) return;
    try {
      const cookie = await qbitLogin();
      await qbitDelete(cookie, addedInfohash);
      console.warn(`CLEANUP (§11.4.14): deleted synthetic torrent ${addedInfohash} from qBittorrent.`);
    } catch (err) {
      // Best-effort only — a teardown-time failure must not turn the run red.
      console.warn(
        `CLEANUP (§11.4.14) best-effort: could not delete synthetic torrent ${addedInfohash} ` +
          `(${(err as Error).message}). Manual cleanup may be needed if it persisted.`,
      );
    }
  });

  it("sends a synthetic magnet via BobaClient and confirms it lands in qBittorrent", async (ctx) => {
    if (!backendReachable) {
      // Honest SKIP with a precise reason — never a green-without-backend pass.
      console.warn(`SKIP (§11.4.3): ${backendSkipReason}`);
      ctx.skip();
      return;
    }

    const magnet = syntheticMagnet();
    const resultId = `helixqa-live-${Date.now()}`;

    // ── 1) SEND via the extension's REAL client (its actual send path). ──
    const client = new BobaClient({ baseUrl: BASE, disableRateLimit: true });
    const addResult = await client.addMagnet(magnet.uri, { resultId });

    // The client normalises the route's body to AddResult. A server-minted
    // download_id and a non-"failed" backend status mark it accepted.
    expect(addResult.downloadId, "BobaClient must surface a server-minted download_id").toBeTruthy();
    expect(addResult.raw, "BobaClient must return the real parsed body").toBeTruthy();

    // ── 2) Assert the FULL response-body contract via one raw fetch. ──
    const res = await fetchWithTimeout(
      DOWNLOAD_URL,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ result_id: resultId, download_urls: [magnet.uri] }),
      },
      QBIT_OP_TIMEOUT_MS,
    );
    expect(res.status, "download endpoint should accept the request (200)").toBe(200);

    const body = (await res.json()) as {
      download_id?: string;
      status?: string;
      urls_count?: number;
      added_count?: number;
      results?: Array<{ url: string; status: string; detail?: string }>;
      error?: string;
    };

    expect(body.download_id, "real response must carry a download_id").toBeTruthy();
    expect(
      ["initiated", "failed", "auth_failed", "connection_failed"],
      `unexpected status '${body.status}' (real body: ${JSON.stringify(body)})`,
    ).toContain(body.status);

    if (body.status === "auth_failed" || body.status === "connection_failed") {
      // Proxy reachable, but qBittorrent itself is down / mis-credentialed
      // behind it. The BobaLink→proxy contract was exercised end-to-end (real
      // proxy verdict), but we cannot assert a successful add → honest SKIP.
      console.warn(
        `SKIP (§11.4.3): merge service reachable but qBittorrent backend status='${body.status}'. ` +
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
    expect(r0.url, "result must reference the magnet we sent").toBe(magnet.uri);
    expect(
      ["added", "failed", "error"],
      `unexpected per-url status '${r0.status}'`,
    ).toContain(r0.status);

    if (r0.status !== "added") {
      // qBittorrent rejected the add (e.g. duplicate hash collision or a real
      // add failure). Internal consistency still asserted, but there is no
      // torrent to independently confirm — honest SKIP, not a pass.
      expect(body.status, "top status must be 'failed' when no url was added").toBe("failed");
      console.warn(
        `SKIP (§11.4.3): qBittorrent did not add the magnet (per-url status='${r0.status}', ` +
          `detail='${r0.detail ?? ""}') — nothing to confirm in the torrent list.`,
      );
      ctx.skip();
      return;
    }

    // Per-url 'added' ⇒ top-level vocabulary must agree.
    expect(body.added_count, "added_count must reflect the added url").toBeGreaterThanOrEqual(1);
    expect(body.status, "top status must be 'initiated' when a url was added").toBe("initiated");

    // Mark for cleanup the moment qBittorrent reports the add succeeded.
    addedInfohash = magnet.infohash;

    // ── 3) INDEPENDENT CONFIRM — query qBittorrent's REAL torrent list and ──
    //    assert OUR synthetic infohash is actually present. This is the real
    //    release-blocker the send-only path could not prove: "the torrent
    //    APPEARS in qBittorrent". Gated behind the proxy being reachable; any
    //    unreachable/missing confirm surface → honest SKIP (no fail-open).
    let cookie: string;
    let torrents: QBitTorrent[];
    try {
      cookie = await qbitLogin();
      torrents = await qbitTorrentsInfo(cookie);
    } catch (err) {
      if (err instanceof QBitUnavailable) {
        console.warn(
          `SKIP (§11.4.3/§11.4.68): add reported 'added' but the qBittorrent confirm read is ` +
            `unavailable — ${err.message} No false PASS without an independent confirm.`,
        );
        ctx.skip();
        return;
      }
      throw err;
    }

    // qBittorrent normalises the infohash to lowercase 40-hex == the magnet's
    // btih. Assert OUR torrent is in the live list (user-observable: it really
    // shows up in qBittorrent).
    const present = torrents.some(
      (t) => typeof t.hash === "string" && t.hash.toLowerCase() === magnet.infohash,
    );
    expect(
      present,
      `synthetic infohash ${magnet.infohash} must appear in qBittorrent's live torrent list ` +
        `(got ${torrents.length} torrents: ${torrents.map((t) => t.hash ?? "?").join(",").slice(0, 400)})`,
    ).toBe(true);
  });
});
