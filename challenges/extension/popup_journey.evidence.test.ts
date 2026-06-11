/**
 * @fileoverview Challenge-scoped evidence harness for the BobaLink POPUP
 * user-journey (Phase 8 — Challenges / §11.4.83).
 *
 * This is NOT a normal unit/integration spec — it is the Node harness invoked by
 * `challenges/extension/popup_journey_challenge.sh`. It drives the REAL, shipped
 * extension modules end-to-end (no re-implementation) and PERSISTS the captured
 * runtime evidence to `challenges/extension/.evidence/popup_journey.json`. The
 * bash challenge then re-reads that evidence file and asserts on it, so the PASS
 * verdict is backed by an auditable artefact per §11.4.83 / §11.4.69 (feature
 * class: `network_throughput` — the extension's add-to-Boba request triggered
 * from the real popup UI).
 *
 * The full popup journey exercised (identical wiring to the user's real path —
 * the SAME real sendMessage→onMessage bridge the production
 * `tests/integration/popup-background.test.ts` uses, reused verbatim here):
 *
 *   1. DETECT/SEED — a real `scan-result` message (as if from a content script
 *      on tab 42) is dispatched THROUGH the REAL background router, seeding the
 *      background's in-memory `tabResults` with two known magnets.
 *
 *   2. POPUP-RENDER — the REAL {@link initPopup} runs against the REAL popup
 *      index.html DOM; it queries the active tab + asks the REAL background for
 *      that tab's detected set over the bridge and renders one accessible row
 *      per detection. We capture the EXACT rendered row ids + names.
 *
 *   3. SEND — a click on a row's REAL Send button drives the popup → REAL
 *      background router → REAL {@link BobaClient} → POST
 *      http://localhost:7187/api/v1/download (captured via an injected fetch).
 *
 *   4. ROW-SENT — the popup reads the background's flat `SendOutcome.id` (the
 *      `r.id` contract fix, not `r.torrent.id`) and flips THAT row to
 *      `torrent-sent` with its Send button disabled. We capture the post-send
 *      DOM state.
 *
 * The ONLY substituted boundaries are the network (`globalThis.fetch`, captured)
 * and `chrome.*` (the in-memory storage/runtime bridge) — every layer in between
 * (popup logic, background router, BobaClient, parseMagnetUri) is the real
 * shipped code. The spec FAILS (and writes no `pass:true` evidence) if the popup
 * renders nothing, the click never reaches the client, the wrong magnet is sent,
 * or the row does not flip — so a no-op stub of any layer cannot produce a green
 * run. NO real token, NO private-tracker payload — synthetic CC-BY-class magnets
 * (§11.4.10).
 *
 * @module challenges/extension/popup_journey.evidence
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { createChromeStorageFake } from "../../extension/tests/unit/chrome-fake";
import { STORAGE_KEYS } from "../../extension/src/shared/constants";
import { DEFAULT_CONFIG } from "../../extension/src/types/config";
import type {
  ExtensionConfig,
  ServerConfig,
} from "../../extension/src/types/config";

// ─────────────────────────────────────────────────────────────────────────────
// Known-input fixtures (synthetic, public, no credentials — §11.4.10).
// ─────────────────────────────────────────────────────────────────────────────
const TAB_ID = 42;
const INFOHASH_A = "1234567890abcdef1234567890abcdef12345678";
const INFOHASH_B = "abcdef1234567890abcdef1234567890abcdef12";
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu`;
const MAGNET_B = `magnet:?xt=urn:btih:${INFOHASH_B}&dn=Debian`;
const NAME_A = "Ubuntu 24.04 ISO";
const NAME_B = "Debian 12 netinst";
const DOWNLOAD_ENDPOINT = "http://localhost:7187/api/v1/download";

const POPUP_HTML_PATH = resolve(
  process.cwd(),
  "src/entrypoints/popup/index.html",
);

const EVIDENCE_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  ".evidence",
  "popup_journey.json",
);

/** Assert a value is present, returning it narrowed (a real assertion). */
function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

// ─────────────────────────────────────────────────────────────────────────────
// The chrome bridge (mirrors tests/integration/popup-background.test.ts):
// runtime.sendMessage REALLY routes into the background's registered onMessage
// listener and wires its sendResponse back as the awaited promise — a genuine
// popup↔background round-trip, not a stub returning canned data.
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

function listenerHub<F>() {
  const handlers: F[] = [];
  return {
    addListener: vi.fn((h: F) => {
      handlers.push(h);
    }),
    handlers,
  };
}

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

function buildBridgeChrome() {
  const storageFake = createChromeStorageFake();
  const session = sessionStorageFake();
  const onMessage = listenerHub<MessageHandler>();

  function sendMessage(message: ExtMessage): Promise<ExtResponse> {
    const handler = onMessage.handlers[0];
    if (!handler) return Promise.resolve({ success: false });
    return new Promise<ExtResponse>((resolveReply) => {
      handler(message, {}, resolveReply);
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
      setBadgeText: vi.fn(() => Promise.resolve()),
      setBadgeBackgroundColor: vi.fn(() => Promise.resolve()),
    },
    notifications: { create: vi.fn() },
    tabs: {
      query: vi.fn(() => Promise.resolve([{ id: TAB_ID }])),
      sendMessage: vi.fn(() => Promise.resolve(null)),
      create: vi.fn(() => Promise.resolve({ id: 99 })),
    },
  };

  return {
    chrome,
    store: storageFake.store,
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

function seedConfig(store: Map<string, unknown>, server: ServerConfig): void {
  const config: ExtensionConfig = {
    ...DEFAULT_CONFIG,
    servers: [server],
    activeServerId: server.id,
  };
  store.set(STORAGE_KEYS.CONFIG, config);
}

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
  const bg = await import("../../extension/src/background/index");
  const popup = await import("../../extension/src/popup/popup");
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

describe("CHALLENGE: BobaLink popup user-journey (detect→render→send→row-sent, real modules)", () => {
  it("renders the detected rows, sends the clicked one to :7187, and flips it to Sent", async () => {
    const calls = installCapturingFetch();
    seedConfig(bridge.store, makeServer());
    loadPopupDom();
    const { initPopup } = await loadModules();

    // ── STAGE 1: DETECT/SEED — real scan-result through the real router ───────
    const seedReply = await bridge.fireFromTab(
      {
        type: "scan-result",
        payload: {
          result: scanResult([
            { id: INFOHASH_A, magnet: MAGNET_A, name: NAME_A },
            { id: INFOHASH_B, magnet: MAGNET_B, name: NAME_B },
          ]),
        },
      },
      TAB_ID,
    );
    expect(seedReply.success).toBe(true);

    // ── STAGE 2: POPUP-RENDER — real initPopup against the real DOM ───────────
    await initPopup(document);

    const rows = document.querySelectorAll<HTMLElement>(".torrent-item");
    expect(rows.length).toBe(2);
    const renderedIds = Array.from(rows).map((r) => r.dataset.id);
    expect(renderedIds).toEqual([INFOHASH_A, INFOHASH_B]);
    const listEl = mustExist(
      document.getElementById("torrent-list"),
      "#torrent-list",
    );
    const listTextBefore = listEl.textContent ?? "";
    expect(listTextBefore).toContain(NAME_A);
    expect(listTextBefore).toContain(NAME_B);

    // ── STAGE 3: SEND — click the SECOND row's real Send button (Debian / B) ───
    const downloadCalls = () =>
      calls.filter((c) => c.url.includes("/api/v1/download"));
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

    // USER-OBSERVABLE: exactly ONE download POST carrying the clicked magnet (B).
    expect(downloadCalls()).toHaveLength(1);
    const req = mustExist(downloadCalls()[0], "captured download request");
    expect(req.url).toBe(DOWNLOAD_ENDPOINT);
    expect(req.method).toBe("POST");
    const body = JSON.parse(mustExist(req.bodyText, "request body")) as {
      download_urls: string[];
    };
    expect(body.download_urls).toEqual([MAGNET_B]);

    // ── STAGE 4: ROW-SENT — the clicked row flips to torrent-sent (the r.id fix)
    const rowAfter = mustExist(
      document.querySelectorAll<HTMLElement>(".torrent-item")[1],
      ".torrent-item[1] after send",
    );
    expect(rowAfter.classList.contains("torrent-sent")).toBe(true);
    expect(rowAfter.dataset.id).toBe(INFOHASH_B);
    const sentBtn = mustExist(
      rowAfter.querySelector<HTMLButtonElement>(".btn-send-one"),
      ".btn-send-one after send",
    );
    // The first (unclicked) row must remain unsent.
    const firstRow = mustExist(
      document.querySelectorAll<HTMLElement>(".torrent-item")[0],
      ".torrent-item[0] after send",
    );
    expect(firstRow.classList.contains("torrent-sent")).toBe(false);

    // ── EVIDENCE: persist the captured runtime data for the bash challenge ─────
    const evidence = {
      pass: true,
      capturedAt: new Date().toISOString(),
      feature: "network_throughput", // §11.4.69 taxonomy class
      detect: {
        seedAccepted: seedReply.success,
        tabId: TAB_ID,
      },
      render: {
        renderedRowCount: rows.length,
        renderedIds,
        renderedNames: [NAME_A, NAME_B].filter((n) =>
          listTextBefore.includes(n),
        ),
      },
      send: {
        clickedId: INFOHASH_B,
        requestCount: downloadCalls().length,
        url: req.url,
        method: req.method,
        downloadUrls: body.download_urls,
      },
      rowSent: {
        sentRowId: rowAfter.dataset.id ?? null,
        sentRowHasSentClass: rowAfter.classList.contains("torrent-sent"),
        sentButtonDisabled: sentBtn.disabled,
        otherRowStillUnsent: !firstRow.classList.contains("torrent-sent"),
      },
      expected: {
        renderedIds: [INFOHASH_A, INFOHASH_B],
        sentMagnet: MAGNET_B,
        endpoint: DOWNLOAD_ENDPOINT,
      },
    };
    mkdirSync(dirname(EVIDENCE_PATH), { recursive: true });
    writeFileSync(EVIDENCE_PATH, JSON.stringify(evidence, null, 2) + "\n", "utf8");
  });
});
