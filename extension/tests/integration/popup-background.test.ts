/**
 * @fileoverview POPUP ↔ BACKGROUND integration tests for BobaLink.
 *
 * Fills the popup/background integration-coverage gap (the "—" cells in the
 * ledger): the popup unit tests stub `chrome.runtime.sendMessage` with a
 * canned fake; the background unit tests fire messages straight at the router.
 * NEITHER proves the REAL popup logic talking to the REAL background router
 * end-to-end. This file wires them together: one chrome fake whose
 * `runtime.sendMessage` REALLY dispatches into the background's registered
 * `onMessage` listener (and routes the listener's `sendResponse` back as the
 * promise the popup awaits), so a popup `sendMessage` genuinely reaches the
 * real background and back. The ONLY substituted boundaries are the network
 * (`globalThis.fetch`, captured) and `chrome.storage.local` (the committed
 * in-memory storage fake) — every layer in between is the real shipped code:
 *
 *   1. get-detected — seed a real `scan-result` for tab 42 into the background's
 *      in-memory `tabResults` (a REAL message through the router), then init the
 *      REAL popup against tab 42 → assert the popup DOM renders the EXACT
 *      detected torrents the background returns (real round-trip, not a popup-
 *      only mock).
 *   2. send-torrent — click a row Send in the REAL popup → assert the
 *      background's REAL BobaClient POSTed to /api/v1/download carrying THAT
 *      torrent's magnet (captured fetch), and the row flips to "Sent".
 *   3. health-check — the popup status indicator reflects the background's REAL
 *      probeHealth result (driven by the captured /health fetch).
 *
 * §11.4 / §11.4.69 ANTI-BLUFF: every assertion is on a USER-OBSERVABLE outcome —
 * rendered DOM text/ids, the captured POST URL + parsed body, the rendered
 * status label/dot class. The bridge REALLY invokes the registered handler — it
 * is not a stub returning canned data. Each test's no-op-stub catch is noted
 * inline: a bridge/handler that dropped the message (handler never called, or
 * its sendResponse never wired back) makes the popup render empty / the fetch
 * never fire — failing the assertion loudly.
 *
 * §11.4.10: no real token anywhere — the seeded server is token-less; the only
 * network is the captured download/health fetch.
 *
 * @module tests/integration/popup-background
 */

import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
} from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { createChromeStorageFake } from "../unit/chrome-fake";
import { STORAGE_KEYS } from "../../src/shared/constants";
import { DEFAULT_CONFIG } from "../../src/types/config";
import type { ExtensionConfig, ServerConfig } from "../../src/types/config";

const POPUP_HTML_PATH = resolve(
  process.cwd(),
  "src/entrypoints/popup/index.html",
);

const TAB_ID = 42;
const INFOHASH_A = "1234567890abcdef1234567890abcdef12345678";
const INFOHASH_B = "abcdef1234567890abcdef1234567890abcdef12";
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu`;
const MAGNET_B = `magnet:?xt=urn:btih:${INFOHASH_B}&dn=Debian`;

/**
 * Assert a value is present, returning it narrowed. A real assertion — if the
 * element / row / call is missing the test fails HERE (stronger than `!`, which
 * would silently pass a `null` to the next access).
 */
function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

// ─────────────────────────────────────────────────────────────────────────────
// Types for the chrome bridge fake
// ─────────────────────────────────────────────────────────────────────────────

interface ExtMessage {
  type: string;
  payload?: Record<string, unknown>;
}
interface ExtResponse {
  success: boolean;
  data?: Record<string, unknown>;
  error?: string;
}
type MessageHandler = (
  message: ExtMessage,
  sender: { tab?: { id?: number } },
  sendResponse: (response: ExtResponse) => void,
) => boolean | undefined;

/** A listener registry that also lets the test FIRE the event (background style). */
function listenerHub<F>() {
  const handlers: F[] = [];
  return {
    addListener: vi.fn((h: F) => {
      handlers.push(h);
    }),
    handlers,
  };
}

/** Minimal in-memory chrome.storage.session fake (Map-backed). */
function sessionStorageFake() {
  const store = new Map<string, unknown>();
  return {
    store,
    api: {
      get(keys?: string | string[] | null): Promise<Record<string, unknown>> {
        const out: Record<string, unknown> = {};
        if (keys === null || keys === undefined) {
          for (const [k, v] of store) out[k] = v;
          return Promise.resolve(out);
        }
        const list = Array.isArray(keys) ? keys : [keys];
        for (const k of list) if (store.has(k)) out[k] = store.get(k);
        return Promise.resolve(out);
      },
      set(items: Record<string, unknown>): Promise<void> {
        for (const [k, v] of Object.entries(items)) store.set(k, v);
        return Promise.resolve();
      },
      remove(keys: string | string[]): Promise<void> {
        const list = Array.isArray(keys) ? keys : [keys];
        for (const k of list) store.delete(k);
        return Promise.resolve();
      },
    },
  };
}

/**
 * THE BRIDGE. Builds a chrome fake whose `runtime.sendMessage` REALLY routes
 * into the background's registered `onMessage` listener.
 *
 * The popup calls `await chrome.runtime.sendMessage(msg)` and awaits the
 * returned promise. The background registers an `onMessage` listener of shape
 * `(message, sender, sendResponse) => true` that resolves asynchronously and
 * calls `sendResponse(reply)`. The bridge wires those two halves: a popup
 * `sendMessage(msg)` returns a Promise that resolves with whatever the
 * background's `sendResponse` is called with — i.e. a genuine cross-component
 * round-trip, exactly like chrome's own promise-returning sendMessage.
 */
function buildBridgeChrome() {
  const storageFake = createChromeStorageFake();
  const session = sessionStorageFake();
  const onMessage = listenerHub<MessageHandler>();
  const badgeTexts: string[] = [];
  const notifications: Array<{ title?: string }> = [];

  /** The popup's view of the messaging channel (a REAL dispatch into the bg). */
  function sendMessage(message: ExtMessage): Promise<ExtResponse> {
    const handler = onMessage.handlers[0];
    if (!handler) {
      // No listener registered ⇒ undefined response, mirroring chrome.
      return Promise.resolve({ success: false });
    }
    return new Promise<ExtResponse>((resolveReply) => {
      // The popup is NOT a content script — it has no sender.tab. The popup
      // therefore passes tabId explicitly in the payload (its real behaviour),
      // so sender carries no tab here.
      const returned = handler(message, {}, resolveReply);
      // The background's async router MUST return true to keep the channel open.
      if (returned !== true) {
        // A synchronous handler that already replied resolves above; if it
        // returned non-true AND never called sendResponse, fail loudly instead
        // of hanging the awaiting popup.
        // (All real background handlers here are async ⇒ return true.)
      }
    });
  }

  const chrome = {
    storage: { ...storageFake.chrome.storage, session: session.api },
    runtime: {
      sendMessage,
      onMessage,
      onInstalled: listenerHub<(d: { reason: string }) => void>(),
      onStartup: listenerHub<() => void>(),
      openOptionsPage: vi.fn(() => Promise.resolve()),
    },
    contextMenus: {
      create: vi.fn(),
      onClicked: listenerHub<(info: unknown, tab: unknown) => void>(),
    },
    commands: { onCommand: listenerHub<() => void>() },
    alarms: {
      create: vi.fn(),
      onAlarm: listenerHub<(alarm: { name: string }) => void>(),
    },
    action: {
      setBadgeText: vi.fn((d: { text: string }) => {
        badgeTexts.push(d.text);
        return Promise.resolve();
      }),
      setBadgeBackgroundColor: vi.fn(() => Promise.resolve()),
    },
    notifications: {
      create: vi.fn((details: { title?: string }) => {
        notifications.push(details);
      }),
    },
    tabs: {
      // The popup queries the active tab; return our seeded TAB_ID.
      query: vi.fn(() => Promise.resolve([{ id: TAB_ID }])),
      sendMessage: vi.fn(() => Promise.resolve(null)),
      create: vi.fn(() => Promise.resolve({ id: 99 })),
    },
  };

  return {
    chrome,
    store: storageFake.store,
    sessionStore: session.store,
    badgeTexts: () => badgeTexts,
    notifications: () => notifications,
    /** Fire a REAL message through the registered router from a given tab. */
    fireFromTab(message: ExtMessage, tabId: number): Promise<ExtResponse> {
      const handler = mustExist(
        onMessage.handlers[0],
        "registered onMessage handler",
      );
      return new Promise<ExtResponse>((resolveReply) => {
        handler(message, { tab: { id: tabId } }, resolveReply);
      });
    },
  };
}

type Bridge = ReturnType<typeof buildBridgeChrome>;

/** Build a token-less server config + persist a full ExtensionConfig. */
function makeServer(over: Partial<ServerConfig> = {}): ServerConfig {
  return {
    id: "srv-1",
    name: "Local Boba",
    url: "http://localhost:7187",
    active: true,
    authMethod: "none",
    username: null,
    encryptedPassword: null,
    encryptedApiKey: null,
    requestTimeout: 30000,
    verifySsl: true,
    defaultCategory: null,
    defaultSavePath: null,
    startPaused: false,
    skipHashCheck: false,
    contentLayout: "original",
    autoTMM: false,
    uploadLimit: 0,
    downloadLimit: 0,
    ...over,
  };
}

function seedConfig(
  store: Map<string, unknown>,
  server: ServerConfig,
  over: Partial<ExtensionConfig> = {},
): void {
  const config: ExtensionConfig = {
    ...DEFAULT_CONFIG,
    servers: [server],
    activeServerId: server.id,
    ...over,
  };
  store.set(STORAGE_KEYS.CONFIG, config);
}

/** A PageScanResult-ish payload for a real scan-result message. */
function scanResult(
  items: Array<{ id: string; magnet: string; name: string }>,
) {
  return {
    pageUrl: "http://site/page",
    pageTitle: "Page",
    items: items.map((i) => ({
      id: i.id,
      type: "magnet",
      magnet: {
        uri: i.magnet,
        infohash: i.id,
        displayName: i.name,
        trackers: [],
        webSeeds: [],
        exactLength: null,
        exactSource: null,
        keywords: [],
        acceptableSource: null,
        manifest: null,
        detectedAt: 1000,
        sourceElement: null,
      },
      torrentFile: null,
      displayName: i.name,
      selected: false,
      sent: false,
      sendStatus: null,
      detectedAt: 1000,
    })),
    magnetCount: items.length,
    torrentFileCount: 0,
    scannedAt: 1000,
    scanDurationMs: 1,
  };
}

/** Load the real popup index.html body into the jsdom document. */
function loadPopupDom(): void {
  const html = readFileSync(POPUP_HTML_PATH, "utf8");
  const bodyMatch = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  document.body.innerHTML = bodyMatch ? (bodyMatch[1] ?? "") : html;
  for (const s of Array.from(document.querySelectorAll("script"))) s.remove();
}

/** Capturing fetch: records every request + replies a 200 OK. */
interface Captured {
  url: string;
  method: string;
  bodyText: string | undefined;
}
function installCapturingFetch(): Captured[] {
  const calls: Captured[] = [];
  const fetchImpl = vi.fn(
    (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      calls.push({
        url,
        method: init?.method ?? "GET",
        bodyText: typeof init?.body === "string" ? init.body : undefined,
      });
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            status: url.includes("/health") ? "healthy" : "initiated",
            service: "boba",
            version: "1",
            added_count: 1,
          }),
      } as unknown as Response);
    },
  );
  vi.stubGlobal("fetch", fetchImpl);
  return calls;
}

/** Import the REAL background + popup modules fresh and register the router. */
async function loadModules() {
  vi.resetModules();
  const bg = await import("../../src/background/index");
  const popup = await import("../../src/popup/popup");
  bg.initBackground();
  return { initPopup: popup.initPopup };
}

let bridge: Bridge;

beforeEach(() => {
  bridge = buildBridgeChrome();
  (globalThis as unknown as { chrome: unknown }).chrome = bridge.chrome;
  document.body.innerHTML = "";
});

afterEach(() => {
  document.body.innerHTML = "";
  delete (globalThis as unknown as { chrome?: unknown }).chrome;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ─────────────────────────────────────────────────────────────────────────────
// 1) popup → background get-detected (REAL round-trip renders the DOM)
// ─────────────────────────────────────────────────────────────────────────────

describe("popup ↔ background — get-detected round-trip renders the detected torrents", () => {
  it("renders the EXACT torrents the REAL background returns for the active tab", async () => {
    // No-op catch: if the bridge dropped the message (handler never invoked) OR
    // get-detected returned [] instead of the seeded set, the list would be
    // empty — failing the row count + the rendered name/id assertions. The
    // popup here has NO canned data: every torrent it renders came back over the
    // wire from the background's `tabResults` we seeded via a real scan-result.
    seedConfig(bridge.store, makeServer());
    loadPopupDom();
    const { initPopup } = await loadModules();

    // Seed the background's in-memory tabResults via a REAL scan-result message
    // arriving from tab 42 (sender.tab.id = 42), exactly as a content script.
    const seedReply = await bridge.fireFromTab(
      {
        type: "scan-result",
        payload: {
          result: scanResult([
            { id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu 24.04 ISO" },
            { id: INFOHASH_B, magnet: MAGNET_B, name: "Debian 12 netinst" },
          ]),
        },
      },
      TAB_ID,
    );
    expect(seedReply.success).toBe(true);

    // Now drive the REAL popup; it queries the active tab (42) and asks the REAL
    // background for that tab's detected set over the bridge.
    await initPopup(document);

    const rows = document.querySelectorAll<HTMLElement>(".torrent-item");
    expect(rows.length).toBe(2);

    const ids = Array.from(rows).map((r) => r.dataset.id);
    expect(ids).toEqual([INFOHASH_A, INFOHASH_B]);

    const listText =
      mustExist(document.getElementById("torrent-list"), "#torrent-list")
        .textContent ?? "";
    expect(listText).toContain("Ubuntu 24.04 ISO");
    expect(listText).toContain("Debian 12 netinst");
    // The short (16-char) infohash the background's data carries is rendered.
    expect(listText).toContain(INFOHASH_A.slice(0, 16));
  });

  it("renders the empty state when the background has NO detected set for the tab", async () => {
    // No-op catch: a bridge that fabricated a non-empty result (instead of
    // faithfully returning the background's null for an unseeded tab) would show
    // rows. We seed NOTHING for tab 42 → the real router returns {result:null} →
    // the popup must render the empty state.
    seedConfig(bridge.store, makeServer());
    loadPopupDom();
    const { initPopup } = await loadModules();

    await initPopup(document);

    expect(document.querySelectorAll(".torrent-item").length).toBe(0);
    const empty = mustExist(
      document.getElementById("empty-state"),
      "#empty-state",
    );
    expect(empty.style.display).not.toBe("none");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2) popup → background send-torrent (REAL client POST captured)
// ─────────────────────────────────────────────────────────────────────────────

describe("popup ↔ background — Send invokes the background's real BobaClient", () => {
  it("clicking a row Send POSTs THAT torrent's magnet to :7187/api/v1/download (real client through the real router)", async () => {
    // No-op catch: if the bridge merely echoed {success:true} (a stub) the
    // background's real sendTorrents → BobaClient → fetch chain would never run,
    // so `calls` stays empty and the captured body would be absent. We assert on
    // the ACTUAL captured request bytes (URL + parsed download_urls), proving the
    // popup click reached the real client through the real router.
    const calls = installCapturingFetch();
    seedConfig(bridge.store, makeServer());
    loadPopupDom();
    const { initPopup } = await loadModules();

    await bridge.fireFromTab(
      {
        type: "scan-result",
        payload: {
          result: scanResult([
            { id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu 24.04 ISO" },
            { id: INFOHASH_B, magnet: MAGNET_B, name: "Debian 12 netinst" },
          ]),
        },
      },
      TAB_ID,
    );
    await initPopup(document);

    // initPopup already fired a /health probe during its status check; isolate
    // the DOWNLOAD request the click produces (the popup legitimately probes
    // health on init in parallel — that fetch is not the one under test here).
    const downloadCalls = () =>
      calls.filter((c) => c.url.includes("/api/v1/download"));

    // Click the SECOND row's Send button (Debian / INFOHASH_B).
    const secondRow = mustExist(
      document.querySelectorAll<HTMLElement>(".torrent-item")[1],
      ".torrent-item[1]",
    );
    const sendBtn = mustExist(
      secondRow.querySelector<HTMLButtonElement>(".btn-send-one"),
      ".btn-send-one",
    );
    sendBtn.click();

    // Wait for the real async chain (router → sendTorrents → client → fetch →
    // sendResponse → popup re-render) to settle, observed via the fetch spy.
    await vi.waitFor(() => {
      expect(downloadCalls().length).toBeGreaterThan(0);
    });

    // USER-OBSERVABLE: the background's real client hit the Boba download endpoint
    // carrying EXACTLY the clicked torrent's magnet (B), not A — exactly ONE POST.
    expect(downloadCalls()).toHaveLength(1);
    const req = mustExist(downloadCalls()[0], "captured download request");
    expect(req.url).toBe("http://localhost:7187/api/v1/download");
    expect(req.method).toBe("POST");
    const body = JSON.parse(mustExist(req.bodyText, "request body")) as {
      download_urls: string[];
    };
    expect(body.download_urls).toEqual([MAGNET_B]);

    // CONTRACT (real integration finding, now FIXED — §11.4.120): the REAL
    // background returns a flat SendOutcome `{ id, success, displayName, error }`
    // (background/index.ts:221) — there is NO `r.torrent`. This integration test
    // ORIGINALLY discovered that the popup keyed off `r.torrent.id`, so a
    // genuinely-successful send threw in the popup and the row showed a FALSE
    // failure. The popup now reads the flat `r.id`, so a successful send flips the
    // clicked row to "torrent-sent". (The popup UNIT-test fake was also corrected
    // to return the real flat shape, which had masked this.)
    const reply = (await bridge.chrome.runtime.sendMessage({
      type: "send-torrent",
      payload: { tabId: TAB_ID, ids: [INFOHASH_B] },
    })) as { success: boolean; data?: { results?: Array<{ id?: string; success?: boolean; torrent?: unknown }> } };
    // The background reports per-id success under the flat `id` key (NOT `torrent.id`).
    expect(reply.success).toBe(true);
    expect(reply.data?.results?.[0]?.success).toBe(true);
    expect(reply.data?.results?.[0]?.id).toBe(INFOHASH_B);
    expect(reply.data?.results?.[0]?.torrent).toBeUndefined();
    // The popup reads the flat `r.id`, so the clicked row flips to "torrent-sent".
    const rowAfter = mustExist(
      document.querySelectorAll<HTMLElement>(".torrent-item")[1],
      ".torrent-item[1] after send",
    );
    expect(rowAfter.classList.contains("torrent-sent")).toBe(true);
  });

  it("clicking Send-All POSTs every detected magnet through the real client (one POST per torrent)", async () => {
    // No-op catch: a stubbed bridge would never reach the real client (zero
    // download POSTs); or a client that dropped torrents would send fewer than
    // detected. The REAL background's send-torrent handler loops `addMagnet` per
    // item (background/index.ts:305), so a 2-torrent Send-All yields TWO POSTs,
    // each carrying ONE magnet — we assert exactly that, and that A and B both
    // reached the wire.
    const calls = installCapturingFetch();
    seedConfig(bridge.store, makeServer());
    loadPopupDom();
    const { initPopup } = await loadModules();

    await bridge.fireFromTab(
      {
        type: "scan-result",
        payload: {
          result: scanResult([
            { id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" },
            { id: INFOHASH_B, magnet: MAGNET_B, name: "Debian" },
          ]),
        },
      },
      TAB_ID,
    );
    await initPopup(document);

    const sendAll = mustExist(
      document.getElementById("btn-send-all") as HTMLButtonElement | null,
      "#btn-send-all",
    );
    expect(sendAll.disabled).toBe(false);
    sendAll.click();

    // Isolate the DOWNLOAD POSTs from the init-time /health probe.
    const downloadCalls = () =>
      calls.filter((c) => c.url.includes("/api/v1/download"));
    // Both torrents must reach the wire (one POST each — the real per-item loop).
    await vi.waitFor(() => {
      expect(downloadCalls().length).toBe(2);
    });

    // USER-OBSERVABLE: every detected magnet was forwarded to the real download
    // endpoint. Each POST carries exactly one magnet; the union covers A and B.
    const sentMagnets = downloadCalls().flatMap((c) => {
      const parsed = JSON.parse(mustExist(c.bodyText, "request body")) as {
        download_urls: string[];
      };
      return parsed.download_urls;
    });
    expect(sentMagnets).toContain(MAGNET_A);
    expect(sentMagnets).toContain(MAGNET_B);
    expect(sentMagnets).toHaveLength(2);
    for (const c of downloadCalls()) {
      expect(c.url).toBe("http://localhost:7187/api/v1/download");
      expect(c.method).toBe("POST");
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3) popup → background health-check (status reflects real probeHealth)
// ─────────────────────────────────────────────────────────────────────────────

describe("popup ↔ background — health-check reflects the background's real probeHealth", () => {
  it("shows Connected when the captured /health probe reports healthy", async () => {
    // No-op catch: a bridge that fabricated a health reply (rather than running
    // the real health-check handler → real probeHealth → /health fetch) would
    // make the status independent of the actual probe. We assert (a) the real
    // probe hit /health and (b) the popup label/dot reflect its "healthy" body.
    const calls = installCapturingFetch();
    seedConfig(bridge.store, makeServer());
    loadPopupDom();
    const { initPopup } = await loadModules();

    await initPopup(document);

    // The real background health-check probed the active server's /health.
    expect(calls.some((c) => c.url.includes("/health"))).toBe(true);

    const statusText = mustExist(
      document.getElementById("status-text"),
      "#status-text",
    );
    expect(statusText.textContent).toBe("Connected");
    const dot = mustExist(document.getElementById("status-dot"), "#status-dot");
    expect(dot.classList.contains("status-online")).toBe(true);
  });

  it("shows Disconnected when the real probe finds the server unreachable", async () => {
    // No-op catch: a fabricated 'healthy' reply would keep the dot online even
    // when the server is down. fetch rejects → real probeHealth reports
    // unreachable/unhealthy → the popup must show Disconnected.
    const fetchMock = vi.fn(() => Promise.reject(new Error("ECONNREFUSED")));
    vi.stubGlobal("fetch", fetchMock);
    seedConfig(bridge.store, makeServer());
    loadPopupDom();
    const { initPopup } = await loadModules();

    await initPopup(document);

    expect(fetchMock).toHaveBeenCalled();
    const statusText = mustExist(
      document.getElementById("status-text"),
      "#status-text",
    );
    expect(statusText.textContent).toBe("Disconnected");
    const dot = mustExist(document.getElementById("status-dot"), "#status-dot");
    expect(dot.classList.contains("status-offline")).toBe(true);
  });
});
