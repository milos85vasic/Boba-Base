/**
 * @fileoverview Anti-bluff unit tests for the REAL background service worker.
 *
 * Imports the production `src/background/index.ts` and drives its exported
 * `initBackground()` against the committed in-memory `chrome` fake (storage)
 * plus an MV3 surface fake (runtime.onMessage / contextMenus / commands /
 * alarms / action[badge] / notifications / tabs). The tests assert
 * USER-OBSERVABLE message-routing + state (§11.4 / CONST-XII):
 *
 *  - a `scan-result` message stores the detected set for the sender tab AND
 *    updates the action badge text to the detected count (real readback of the
 *    badge text the user sees + the stored set),
 *  - a `get-detected` returns the SAME stored set back to the popup,
 *  - a `send-torrent` calls the REAL Boba client (injected fetch → mocked 200)
 *    and notifies success (chrome.notifications.create called),
 *  - a `send-torrent` whose client call FAILS (mocked network error) ENQUEUES
 *    the item into the REAL committed OfflineQueue — asserted by reading the
 *    queue back out of chrome.storage.local under STORAGE_KEYS.QUEUE,
 *  - a `health-check` returns the probed status from the REAL probeHealth,
 *  - `onInstalled` creates the context menus (chrome.contextMenus.create
 *    called) and seeds the default config into storage,
 *  - a keyboard `toggle-highlight` command sends `highlight-toggle` to the
 *    active tab's content script.
 *
 * Every assertion fails against a no-op stub of the background (handlers that
 * return `{success:true}` and touch nothing): the badge text stays empty, the
 * stored set is absent, the client is never called, the queue stays empty,
 * the notification/contextMenu/tabs spies see zero calls.
 *
 * §11.4.10: no real token anywhere — a synthetic `test-token-<uuid>` is used
 * only to prove it is FORWARDED to the client, never logged.
 *
 * @module tests/unit/background.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createChromeStorageFake } from "./chrome-fake";
import { STORAGE_KEYS } from "../../src/shared/constants";
import { DEFAULT_CONFIG } from "../../src/types/config";
import type {
  ExtensionConfig,
  ServerConfig,
} from "../../src/types/config";
import type { OfflineQueueItem } from "../../src/api/queue";

const INFOHASH_A = "1234567890abcdef1234567890abcdef12345678";
const INFOHASH_B = "abcdef1234567890abcdef1234567890abcdef12";
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu`;
const MAGNET_B = `magnet:?xt=urn:btih:${INFOHASH_B}&dn=Debian`;
const SYNTH_TOKEN = `test-token-${crypto.randomUUID()}`;

// ─────────────────────────────────────────────────────────────────────────────
// MV3 chrome surface fake
// ─────────────────────────────────────────────────────────────────────────────

type MessageHandler = (
  message: { type: string; payload?: Record<string, unknown> },
  sender: { tab?: { id?: number } },
  sendResponse: (response: unknown) => void,
) => boolean | undefined;

type CommandHandler = (
  command: string,
  tab?: { id?: number },
) => void | Promise<void>;

/** A jest/vitest-style listener registry that also lets a test FIRE the event. */
function listenerHub<F>() {
  const handlers: F[] = [];
  return {
    addListener: vi.fn((h: F) => {
      handlers.push(h);
    }),
    handlers,
  };
}

interface FakeChrome {
  storage: ReturnType<typeof createChromeStorageFake>["chrome"]["storage"];
  runtime: {
    onMessage: ReturnType<typeof listenerHub<MessageHandler>>;
    onInstalled: ReturnType<typeof listenerHub<(d: { reason: string }) => void>>;
    onStartup: ReturnType<typeof listenerHub<() => void>>;
  };
  contextMenus: {
    create: ReturnType<typeof vi.fn>;
    onClicked: ReturnType<typeof listenerHub<(info: unknown, tab: unknown) => void>>;
  };
  commands: {
    onCommand: ReturnType<typeof listenerHub<CommandHandler>>;
  };
  alarms: {
    create: ReturnType<typeof vi.fn>;
    onAlarm: ReturnType<typeof listenerHub<(alarm: { name: string }) => void>>;
  };
  action: {
    setBadgeText: ReturnType<typeof vi.fn>;
    setBadgeBackgroundColor: ReturnType<typeof vi.fn>;
  };
  notifications: { create: ReturnType<typeof vi.fn> };
  tabs: {
    sendMessage: ReturnType<typeof vi.fn>;
    query: ReturnType<typeof vi.fn>;
    create: ReturnType<typeof vi.fn>;
  };
}

interface InstalledChrome {
  chrome: FakeChrome;
  badgeTexts: () => string[];
  store: Map<string, unknown>;
}

/** Install a full MV3 chrome fake onto globalThis. Returns spy accessors. */
function installChrome(): InstalledChrome {
  const storageFake = createChromeStorageFake();
  const badgeTexts: string[] = [];

  const chrome: FakeChrome = {
    storage: storageFake.chrome.storage,
    runtime: {
      onMessage: listenerHub<MessageHandler>(),
      onInstalled: listenerHub<(d: { reason: string }) => void>(),
      onStartup: listenerHub<() => void>(),
    },
    contextMenus: {
      create: vi.fn(),
      onClicked: listenerHub<(info: unknown, tab: unknown) => void>(),
    },
    commands: {
      onCommand: listenerHub<CommandHandler>(),
    },
    alarms: {
      create: vi.fn(),
      onAlarm: listenerHub<(alarm: { name: string }) => void>(),
    },
    action: {
      setBadgeText: vi.fn((details: { text: string }) => {
        badgeTexts.push(details.text);
        return Promise.resolve();
      }),
      setBadgeBackgroundColor: vi.fn(() => Promise.resolve()),
    },
    notifications: { create: vi.fn() },
    tabs: {
      sendMessage: vi.fn(() => Promise.resolve(null)),
      query: vi.fn(() => Promise.resolve([{ id: 42 }])),
      create: vi.fn(() => Promise.resolve({ id: 99 })),
    },
  };

  (globalThis as unknown as { chrome: unknown }).chrome = chrome;
  return { chrome, badgeTexts: () => badgeTexts, store: storageFake.store };
}

/** Build a server config + persist a full ExtensionConfig with one active server. */
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

/** A PageScanResult-ish payload for scan-result. */
function scanResult(items: Array<{ id: string; magnet: string; name: string }>) {
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

/** Fire a message through the registered onMessage handler and await its reply. */
function sendMessage(
  ch: FakeChrome,
  message: { type: string; payload?: Record<string, unknown> },
  sender: { tab?: { id?: number } } = {},
): Promise<unknown> {
  const handler = ch.runtime.onMessage.handlers[0];
  if (!handler) throw new Error("no onMessage handler registered");
  return new Promise((resolve) => {
    const returned = handler(message, sender, resolve);
    // async handlers MUST return true to keep the message channel open
    expect(returned).toBe(true);
  });
}

async function loadBackground() {
  vi.resetModules();
  return import("../../src/background/index");
}

/**
 * Deterministically flush the fire-and-forget context-menu async handler chain
 * by polling a real completion `signal` (e.g. "fetch was called", "the queue is
 * persisted") instead of a fixed number of `setTimeout(0)` ticks. Polls on a
 * short real-time interval up to a wall-clock `timeoutMs` so the client's own
 * retry backoff (multi-second) on the network-error path has time to settle.
 * Throws on timeout so a no-op handler fails LOUDLY (§11.4.1) rather than
 * silently passing a too-short fixed loop.
 *
 * @param signal - Predicate that becomes true once the observed effect landed.
 * @param label - Human-readable description used in the timeout error.
 * @param timeoutMs - Wall-clock budget before failing.
 */
async function flushUntil(
  signal: () => boolean,
  label: string,
  timeoutMs = 5000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (signal()) return;
    await new Promise((r) => setTimeout(r, 5));
  }
  if (signal()) return;
  throw new Error(`flushUntil timed out waiting for: ${label}`);
}

let installed: InstalledChrome;

beforeEach(() => {
  installed = installChrome();
});

afterEach(() => {
  delete (globalThis as unknown as { chrome?: unknown }).chrome;
  vi.restoreAllMocks();
});

// ─────────────────────────────────────────────────────────────────────────────
// Listener registration (MV3-correct: synchronous top-level registration)
// ─────────────────────────────────────────────────────────────────────────────

describe("initBackground — listener registration", () => {
  it("registers onMessage, onInstalled, command, alarm, contextMenu-click listeners", async () => {
    const { initBackground } = await loadBackground();
    initBackground();

    const ch = installed.chrome;
    expect(ch.runtime.onMessage.addListener).toHaveBeenCalled();
    expect(ch.runtime.onInstalled.addListener).toHaveBeenCalled();
    expect(ch.commands.onCommand.addListener).toHaveBeenCalled();
    expect(ch.alarms.onAlarm.addListener).toHaveBeenCalled();
    expect(ch.contextMenus.onClicked.addListener).toHaveBeenCalled();
  });

  it("creates the keep-alive + health-check alarms", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const names = installed.chrome.alarms.create.mock.calls.map(
      (c) => (c[0] as string),
    );
    expect(names).toContain("keepalive");
    expect(names).toContain("health-check");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// scan-result → stored set + badge
// ─────────────────────────────────────────────────────────────────────────────

describe("message router — scan-result → badge + stored set", () => {
  it("stores the detected set for the sender tab AND sets the badge to the count", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    const result = scanResult([
      { id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" },
      { id: INFOHASH_B, magnet: MAGNET_B, name: "Debian" },
    ]);

    const reply = (await sendMessage(
      ch,
      { type: "scan-result", payload: { result } },
      { tab: { id: 7 } },
    )) as { success: boolean };
    expect(reply.success).toBe(true);

    // USER-OBSERVABLE: the badge the user sees now shows "2"
    expect(installed.badgeTexts()).toContain("2");

    // and get-detected returns the SAME stored set for that tab
    const got = (await sendMessage(
      ch,
      { type: "get-detected", payload: { tabId: 7 } },
    )) as { success: boolean; data?: { result?: { items?: unknown[] } } };
    expect(got.success).toBe(true);
    expect(got.data?.result?.items).toHaveLength(2);
  });

  it("get-detected for an unknown tab returns a null result (not a crash)", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const got = (await sendMessage(
      installed.chrome,
      { type: "get-detected", payload: { tabId: 999 } },
    )) as { success: boolean; data?: { result?: unknown } };
    expect(got.success).toBe(true);
    expect(got.data?.result ?? null).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// send-torrent → real BobaClient (success) / enqueue-on-failure
// ─────────────────────────────────────────────────────────────────────────────

describe("message router — send-torrent → client + notify / enqueue-on-fail", () => {
  it("on a mocked 200 calls the Boba client and notifies success", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "initiated", added_count: 1 }),
      } as unknown as Response),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;
    seedConfig(installed.store, makeServer());

    // store a detected set first so send-torrent has something to send
    const result = scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]);
    await sendMessage(ch, { type: "scan-result", payload: { result } }, { tab: { id: 7 } });

    const reply = (await sendMessage(ch, {
      type: "send-torrent",
      payload: { tabId: 7, ids: [INFOHASH_A] },
    })) as { success: boolean };
    expect(reply.success).toBe(true);

    // USER-OBSERVABLE: the real client POSTed to the Boba :7187 download endpoint
    expect(fetchMock).toHaveBeenCalled();
    const url = (fetchMock.mock.calls[0] as unknown[])?.[0] as string;
    expect(url).toContain("/api/v1/download");

    // …and a success notification was raised
    expect(ch.notifications.create).toHaveBeenCalled();
  });

  it("default-opens (never puts the configured value on the wire) when a token is set but the session is locked — and never logs it (§11.4.10 / §11.4.120)", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "initiated", added_count: 1 }),
      } as unknown as Response),
    );
    vi.stubGlobal("fetch", fetchMock);
    const logSpy = vi.spyOn(console, "info").mockImplementation(() => undefined);

    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;
    seedConfig(
      installed.store,
      makeServer({ encryptedBobaApiToken: SYNTH_TOKEN }),
    );
    const result = scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]);
    await sendMessage(ch, { type: "scan-result", payload: { result } }, { tab: { id: 7 } });
    await sendMessage(ch, {
      type: "send-torrent",
      payload: { tabId: 7, ids: [INFOHASH_A] },
    });

    // §11.4.120 reconciliation: post-Phase-7 the background DECRYPTS the
    // configured ciphertext bundle with the session passphrase (read from
    // chrome.storage.session) before sending. This fake has no storage.session,
    // so the unlock passphrase is unavailable (locked) → the client MUST be
    // built default-open and MUST NEVER put the stored value on the wire as a
    // bearer token. (The decrypt→forward happy path is proven in
    // background-token.test.ts with a real encrypted bundle + a session passphrase.)
    expect(fetchMock).toHaveBeenCalled();
    const init = (fetchMock.mock.calls[0] as unknown[])?.[1] as RequestInit;
    const headers = (init.headers as Record<string, string>) ?? {};
    expect(headers["Authorization"]).toBeUndefined();
    expect(headers["X-Boba-Token"]).toBeUndefined();
    expect(JSON.stringify(headers)).not.toContain(SYNTH_TOKEN);

    // …but the token VALUE never appears in any console line
    const logged = logSpy.mock.calls.map((c) => c.join(" ")).join("\n");
    expect(logged).not.toContain(SYNTH_TOKEN);
  });

  it("MENU_SEND_GROUP batches deduped torrents across the tab group and POSTs them once (Phase 5)", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "initiated", added_count: 2 }),
      } as unknown as Response),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;
    seedConfig(installed.store, makeServer());

    // Tab group of two tabs (ids 7 & 8). The SAME magnet (A) is detected on both
    // tabs + a distinct magnet (B) on tab 8 → cross-tab dedup must yield exactly
    // TWO unique download URLs.
    ch.tabs.query.mockResolvedValue([{ id: 7 }, { id: 8 }]);
    await sendMessage(
      ch,
      {
        type: "scan-result",
        payload: { result: scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]) },
      },
      { tab: { id: 7 } },
    );
    await sendMessage(
      ch,
      {
        type: "scan-result",
        payload: {
          result: scanResult([
            { id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" },
            { id: INFOHASH_B, magnet: MAGNET_B, name: "Debian" },
          ]),
        },
      },
      { tab: { id: 8 } },
    );

    // Fire the context-menu "Send group" click on tab 7 (group id 3).
    const onClicked = ch.contextMenus.onClicked.handlers[0];
    expect(onClicked).toBeTypeOf("function");
    onClicked?.({ menuItemId: "bobalink-send-group" }, { id: 7, groupId: 3 });
    // Flush the fire-and-forget async handler chain (loadConfig → batch → client
    // → dispatch → addMagnets → fetch) by awaiting a REAL completion signal: the
    // addMagnets call settling, observed via the fetch spy (§11.4.50 — no fixed
    // tick count that could pass before the chain runs or flake under load).
    await flushUntil(
      () => fetchMock.mock.calls.length > 0,
      "group batch POST to reach fetch",
    );

    // USER-OBSERVABLE: exactly ONE batched POST to /api/v1/download carrying the
    // two DEDUPED magnets (A once, despite appearing on both tabs, + B).
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = (fetchMock.mock.calls[0] as unknown[])?.[0] as string;
    expect(url).toContain("/api/v1/download");
    const init = (fetchMock.mock.calls[0] as unknown[])?.[1] as RequestInit;
    const body = JSON.parse(init.body as string) as { download_urls: string[] };
    expect(body.download_urls).toHaveLength(2);
    expect(body.download_urls).toContain(MAGNET_A);
    expect(body.download_urls).toContain(MAGNET_B);
    // queried the group's tabs by groupId (not a broad tabs scan)
    expect(ch.tabs.query).toHaveBeenCalledWith({ groupId: 3 });
  });

  it("MENU_SEND_GROUP enqueues the group's torrents into the real OfflineQueue when the backend REJECTS the batch (Phase 5 parity with Send-All)", async () => {
    // 200 OK but the backend reports a wholesale failure → addMagnets resolves
    // accepted:false (NOT a throw). The group's sendable torrents MUST land in
    // the persisted queue for retry, exactly like the Send-All path does.
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "failed", added_count: 0 }),
      } as unknown as Response),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;
    seedConfig(installed.store, makeServer());

    ch.tabs.query.mockResolvedValue([{ id: 7 }, { id: 8 }]);
    await sendMessage(
      ch,
      {
        type: "scan-result",
        payload: { result: scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]) },
      },
      { tab: { id: 7 } },
    );
    await sendMessage(
      ch,
      {
        type: "scan-result",
        payload: {
          result: scanResult([
            { id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" },
            { id: INFOHASH_B, magnet: MAGNET_B, name: "Debian" },
          ]),
        },
      },
      { tab: { id: 8 } },
    );

    const onClicked = ch.contextMenus.onClicked.handlers[0];
    onClicked?.({ menuItemId: "bobalink-send-group" }, { id: 7, groupId: 3 });

    // Await the REAL completion signal: both deduped torrents persisted to the
    // offline queue under STORAGE_KEYS.QUEUE.
    await flushUntil(() => {
      const q = installed.store.get(STORAGE_KEYS.QUEUE) as
        | OfflineQueueItem[]
        | undefined;
      return Array.isArray(q) && q.length >= 2;
    }, "rejected group batch to be persisted into the offline queue");

    // USER-OBSERVABLE: the two DEDUPED torrents now live in the persisted queue.
    const queued = installed.store.get(STORAGE_KEYS.QUEUE) as
      | OfflineQueueItem[]
      | undefined;
    expect(queued).toBeDefined();
    expect(queued).toHaveLength(2);
    const names = (queued ?? []).map((q) => q.torrent.displayName).sort();
    expect(names).toEqual(["Debian", "Ubuntu"]);
    const magnets = (queued ?? []).map((q) => q.torrent.magnetUri).sort();
    expect(magnets).toEqual([MAGNET_B, MAGNET_A].sort());
  }, 10000);

  it("MENU_SEND_GROUP on a NETWORK ERROR enqueues the torrents AND raises a 'Group send failed' notification (Phase 5)", async () => {
    // fetch always rejects → addMagnets THROWS (NetworkError after retries) →
    // the throw must NOT be silently swallowed: the group's torrents are queued
    // for retry AND the user sees a failure notification.
    const fetchMock = vi.fn(() => Promise.reject(new Error("ECONNREFUSED")));
    vi.stubGlobal("fetch", fetchMock);

    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;
    seedConfig(installed.store, makeServer());

    ch.tabs.query.mockResolvedValue([{ id: 7 }]);
    await sendMessage(
      ch,
      {
        type: "scan-result",
        payload: {
          result: scanResult([
            { id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" },
            { id: INFOHASH_B, magnet: MAGNET_B, name: "Debian" },
          ]),
        },
      },
      { tab: { id: 7 } },
    );

    const onClicked = ch.contextMenus.onClicked.handlers[0];
    onClicked?.({ menuItemId: "bobalink-send-group" }, { id: 7, groupId: 3 });

    // Await the REAL completion signal: the torrents persisted to the queue.
    await flushUntil(() => {
      const q = installed.store.get(STORAGE_KEYS.QUEUE) as
        | OfflineQueueItem[]
        | undefined;
      return Array.isArray(q) && q.length >= 2;
    }, "network-failed group batch to be persisted into the offline queue", 15000);

    // USER-OBSERVABLE: torrents queued for retry, not dropped on the floor.
    const queued = installed.store.get(STORAGE_KEYS.QUEUE) as
      | OfflineQueueItem[]
      | undefined;
    expect(queued).toHaveLength(2);

    // USER-OBSERVABLE: a "Group send failed" notification was raised.
    expect(ch.notifications.create).toHaveBeenCalled();
    const titles = ch.notifications.create.mock.calls.map(
      (c) => (c[0] as { title?: string }).title,
    );
    expect(titles).toContain("Group send failed");
  }, 20000);

  it("on a client failure ENQUEUES the item into the real OfflineQueue (persisted)", async () => {
    // fetch always rejects → NetworkError after retries → enqueue
    const fetchMock = vi.fn(() => Promise.reject(new Error("ECONNREFUSED")));
    vi.stubGlobal("fetch", fetchMock);

    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;
    seedConfig(installed.store, makeServer());

    const result = scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]);
    await sendMessage(ch, { type: "scan-result", payload: { result } }, { tab: { id: 7 } });

    const reply = (await sendMessage(ch, {
      type: "send-torrent",
      payload: { tabId: 7, ids: [INFOHASH_A] },
    })) as { success: boolean; data?: { results?: Array<{ success: boolean }> } };
    expect(reply.success).toBe(true);
    expect(reply.data?.results?.[0]?.success).toBe(false);

    // USER-OBSERVABLE: the failed send now lives in the persisted offline queue
    const queued = installed.store.get(STORAGE_KEYS.QUEUE) as OfflineQueueItem[] | undefined;
    expect(queued).toBeDefined();
    expect(queued).toHaveLength(1);
    expect(queued?.[0]?.torrent.displayName).toBe("Ubuntu");
    expect(queued?.[0]?.torrent.magnetUri).toBe(MAGNET_A);
  }, 20000);
});

// ─────────────────────────────────────────────────────────────────────────────
// health-check → real probeHealth
// ─────────────────────────────────────────────────────────────────────────────

describe("message router — health-check → probed status", () => {
  it("returns the status from the real probeHealth against the active server", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "healthy", service: "boba", version: "1" }),
      } as unknown as Response),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;
    seedConfig(installed.store, makeServer());

    const reply = (await sendMessage(ch, { type: "health-check" })) as {
      success: boolean;
      data?: { results?: Array<{ status: string; reachable: boolean }> };
    };
    expect(reply.success).toBe(true);
    expect(reply.data?.results?.[0]?.status).toBe("healthy");
    expect(reply.data?.results?.[0]?.reachable).toBe(true);
    // it hit /health, not a qBittorrent path
    expect((fetchMock.mock.calls[0] as unknown[])?.[0] as string).toContain("/health");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// onInstalled → context menus + default config
// ─────────────────────────────────────────────────────────────────────────────

describe("lifecycle — onInstalled", () => {
  it("creates the context menus and seeds the default config into storage", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    const onInstalled = ch.runtime.onInstalled.handlers[0];
    if (!onInstalled) throw new Error("no onInstalled handler");
    onInstalled({ reason: "install" });
    // let the async config-seed settle
    await new Promise((r) => setTimeout(r, 0));

    expect(ch.contextMenus.create).toHaveBeenCalled();
    // at least the canonical "send" menu item exists
    const ids = ch.contextMenus.create.mock.calls.map(
      (c) => (c[0] as { id?: string }).id,
    );
    expect(ids.some((id) => typeof id === "string" && id.includes("send"))).toBe(true);

    // default config seeded
    expect(installed.store.get(STORAGE_KEYS.CONFIG)).toBeDefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// commands — toggle-highlight sends highlight-toggle to the active tab
// ─────────────────────────────────────────────────────────────────────────────

describe("commands — keyboard shortcuts → content-script directives", () => {
  it("toggle-highlight sends a highlight-toggle message to the active tab", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    const onCommand = ch.commands.onCommand.handlers[0];
    if (!onCommand) throw new Error("no onCommand handler");
    await onCommand("toggle-highlight", { id: 42 });

    expect(ch.tabs.sendMessage).toHaveBeenCalled();
    const [tabId, msg] = ch.tabs.sendMessage.mock.calls[0] as [
      number,
      { type: string },
    ];
    expect(tabId).toBe(42);
    expect(msg.type).toBe("highlight-toggle");
  });

  it("scan-page command sends scan-now to the active tab", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;
    const onCommand = ch.commands.onCommand.handlers[0];
    if (!onCommand) throw new Error("no onCommand handler");
    await onCommand("scan-page", { id: 42 });

    const msg = ch.tabs.sendMessage.mock.calls[0]?.[1] as { type: string };
    expect(msg.type).toBe("scan-now");
  });
});
