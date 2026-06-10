/**
 * @fileoverview OPTIONS ↔ BACKGROUND integration tests for BobaLink.
 *
 * Fills the options/background integration-coverage gap (the "—" cells in the
 * ledger): the options unit tests drive `saveOptions` against the storage fake;
 * the background unit tests seed config directly into the store. NEITHER proves
 * that what the REAL options page PERSISTS is the SAME config the REAL
 * background READS on its next operation. This file wires them through ONE
 * shared `chrome.storage.local` (the committed in-memory storage fake) so the
 * persistence round-trip is genuine, and a chrome fake whose
 * `runtime.sendMessage` REALLY dispatches into the background's registered
 * `onMessage` listener (routing the listener's `sendResponse` back as the
 * awaited promise). The ONLY substituted boundaries are the network
 * (`globalThis.fetch`, captured) and `chrome.storage.local`:
 *
 *   1. options.saveOptions writes a config (real `storageSet`) → the REAL
 *      background reads the SAME config back via a `get-config` message (real
 *      `storageGet`) — asserting field-for-field identity, NOT a status code.
 *   2. options changes the server URL + a checkbox → the background's next
 *      send-torrent targets the EXACT new URL (captured POST host:port) and its
 *      health-check probes the EXACT new /health — proving the background acts
 *      on the persisted config, not a stale copy.
 *
 * §11.4 / §11.4.69 ANTI-BLUFF: assertions inspect USER-OBSERVABLE outcomes —
 * the read-back config fields and the captured request URL — and the bridge
 * REALLY invokes the registered handler (not a stub). Each test's no-op-stub
 * catch is noted inline.
 *
 * §11.4.10: no real token anywhere — the round-tripped server is token-less.
 *
 * @module tests/integration/options-background
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

const OPTIONS_HTML_PATH = resolve(
  process.cwd(),
  "src/entrypoints/options/index.html",
);

const TAB_ID = 7;
const INFOHASH_A = "1234567890abcdef1234567890abcdef12345678";
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu`;

/**
 * Assert a value is present, returning it narrowed (stronger than `!`).
 */
function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

// ─────────────────────────────────────────────────────────────────────────────
// Bridge chrome fake (shared storage + a sendMessage that reaches the router)
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

/**
 * THE BRIDGE. `runtime.sendMessage` REALLY routes into the background's
 * registered `onMessage` listener and resolves with whatever the listener's
 * `sendResponse` is called with — a genuine cross-component round-trip. The
 * SAME `storage.local` backing store is shared with the options page, so a
 * config the options page persists is the one the background reads.
 */
function buildBridgeChrome() {
  const storageFake = createChromeStorageFake();
  const session = sessionStorageFake();
  const onMessage = listenerHub<MessageHandler>();
  const notifications: Array<{ title?: string }> = [];

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
    notifications: {
      create: vi.fn((details: { title?: string }) => {
        notifications.push(details);
      }),
    },
    tabs: {
      query: vi.fn(() => Promise.resolve([{ id: TAB_ID }])),
      sendMessage: vi.fn(() => Promise.resolve(null)),
      create: vi.fn(() => Promise.resolve({ id: 99 })),
    },
  };

  return {
    chrome,
    store: storageFake.store,
    notifications: () => notifications,
    /** Popup/options-style sendMessage that REALLY reaches the router. */
    send: sendMessage,
    /** Fire a REAL message through the router from a given tab (content-script). */
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

function loadOptionsDom(): void {
  const html = readFileSync(OPTIONS_HTML_PATH, "utf8");
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

/** Import the REAL background + options modules fresh; register the router. */
async function loadModules() {
  vi.resetModules();
  const bg = await import("../../src/background/index");
  const options = await import("../../src/options/options");
  bg.initBackground();
  return {
    populateForm: options.populateForm,
    saveOptions: options.saveOptions,
  };
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
// 1) options saves config → background reads the SAME config back
// ─────────────────────────────────────────────────────────────────────────────

describe("options ↔ background — saved config is the config the background reads", () => {
  it("the background's get-config returns the EXACT config options.saveOptions persisted", async () => {
    // No-op catch: if options.saveOptions did not actually persist (or the
    // background read a default/stale config instead of the stored one), the
    // read-back fields below would differ from what the user entered. We assert
    // field-for-field identity through a REAL get-config message round-trip — no
    // status-code-only pass.
    loadOptionsDom();
    const { populateForm, saveOptions } = await loadModules();
    await populateForm(document);

    // User edits several fields across tabs.
    (document.getElementById("opt-server-name") as HTMLInputElement).value =
      "Edited Boba";
    (document.getElementById("opt-server-url") as HTMLInputElement).value =
      "http://localhost:7187";
    (document.getElementById("opt-auto-send") as HTMLInputElement).checked =
      true;
    (document.getElementById("opt-max-queue") as HTMLInputElement).value =
      "321";
    (document.getElementById("opt-debug-mode") as HTMLInputElement).checked =
      true;

    const saved = await saveOptions(document);

    // The REAL background reads config back over a real get-config message.
    const reply = (await bridge.send({ type: "get-config" })) as {
      success: boolean;
      data?: { config?: ExtensionConfig };
    };
    expect(reply.success).toBe(true);
    const bgConfig = mustExist(reply.data?.config, "background-read config");

    // USER-OBSERVABLE: every field the user set survives into what the
    // background sees — identical to what saveOptions returned.
    expect(bgConfig.servers[0]?.name).toBe("Edited Boba");
    expect(bgConfig.servers[0]?.url).toBe("http://localhost:7187");
    expect(bgConfig.autoSend).toBe(true);
    expect(bgConfig.maxOfflineQueueSize).toBe(321);
    expect(bgConfig.debugMode).toBe(true);
    expect(bgConfig.servers[0]?.name).toBe(saved.servers[0]?.name);
    expect(bgConfig.activeServerId).toBe(saved.activeServerId);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2) options changes the server URL → background acts on the new URL
// ─────────────────────────────────────────────────────────────────────────────

describe("options ↔ background — the background sends/probes the URL options persisted", () => {
  it("after options saves a new server URL, send-torrent POSTs to THAT new host:port", async () => {
    // No-op catch: if the background sent to a stale/default URL (instead of the
    // one the options page just persisted), the captured request host:port would
    // not match. We assert the captured POST URL is the NEW base + /api/v1/download.
    const calls = installCapturingFetch();
    loadOptionsDom();
    const { populateForm, saveOptions } = await loadModules();
    await populateForm(document);

    const NEW_URL = "http://127.0.0.1:9999";
    (document.getElementById("opt-server-url") as HTMLInputElement).value =
      NEW_URL;
    await saveOptions(document);

    // Seed a detected torrent for the tab the popup would target, then send it
    // through the REAL router — the background must use the just-saved URL.
    await bridge.fireFromTab(
      {
        type: "scan-result",
        payload: {
          result: scanResult([
            { id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" },
          ]),
        },
      },
      TAB_ID,
    );
    const reply = (await bridge.send({
      type: "send-torrent",
      payload: { tabId: TAB_ID, ids: [INFOHASH_A] },
    })) as { success: boolean; data?: { results?: Array<{ success: boolean }> } };
    expect(reply.success).toBe(true);
    expect(reply.data?.results?.[0]?.success).toBe(true);

    // USER-OBSERVABLE: the background POSTed to the NEW base the user saved.
    const download = mustExist(
      calls.find((c) => c.url.includes("/api/v1/download")),
      "download request",
    );
    expect(download.url).toBe(`${NEW_URL}/api/v1/download`);
    const body = JSON.parse(
      mustExist(download.bodyText, "request body"),
    ) as { download_urls: string[] };
    expect(body.download_urls).toEqual([MAGNET_A]);
  });

  it("after options saves a new server URL, health-check probes THAT new /health", async () => {
    // No-op catch: a background reading a stale config would probe the old
    // /health host. We assert the captured /health request targets the new base.
    const calls = installCapturingFetch();
    loadOptionsDom();
    const { populateForm, saveOptions } = await loadModules();
    await populateForm(document);

    const NEW_URL = "http://127.0.0.1:8123";
    (document.getElementById("opt-server-url") as HTMLInputElement).value =
      NEW_URL;
    await saveOptions(document);

    const reply = (await bridge.send({ type: "health-check" })) as {
      success: boolean;
      data?: { results?: Array<{ status: string; url: string }> };
    };
    expect(reply.success).toBe(true);
    expect(reply.data?.results?.[0]?.status).toBe("healthy");
    expect(reply.data?.results?.[0]?.url).toBe(NEW_URL);

    // USER-OBSERVABLE: the real probe hit the NEW server's /health.
    expect(calls.some((c) => c.url === `${NEW_URL}/health`)).toBe(true);
  });

  it("a non-http URL is REJECTED by options and the background keeps the prior config", async () => {
    // No-op catch: if saveOptions silently persisted an invalid URL, the
    // background would read the bad value. We assert saveOptions throws AND the
    // background still reads the original seeded URL (nothing corrupted).
    seedConfig(bridge.store, makeServer());
    loadOptionsDom();
    const { populateForm, saveOptions } = await loadModules();
    await populateForm(document);

    (document.getElementById("opt-server-url") as HTMLInputElement).value =
      "ftp://nope";
    await expect(saveOptions(document)).rejects.toThrow(/invalid server url/i);

    const reply = (await bridge.send({ type: "get-config" })) as {
      success: boolean;
      data?: { config?: ExtensionConfig };
    };
    const bgConfig = mustExist(reply.data?.config, "background-read config");
    // The background still sees the original, valid URL — not the rejected one.
    expect(bgConfig.servers[0]?.url).toBe("http://localhost:7187");
  });
});
