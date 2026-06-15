/**
 * @fileoverview Anti-bluff regression test for crash-risk S3 — `tabResults`
 * MUST survive an MV3 service-worker teardown (§11.4 / §11.4.115 / CONST-XII).
 *
 * BobaLink is an MV3 service worker: the SW idles out (~30s) and is torn down,
 * then re-spawned on the next event. The production background declared its
 * detected-results store as a top-level in-memory `Map` (`tabResults`). On
 * teardown that Map is LOST, so after an idle period the popup's `get-detected`
 * (and the context-menu "Send all" / `send-all` command paths) silently
 * no-op — a real, user-visible functional bug (the feature does nothing).
 *
 * The fix persists the per-tab scan results to `chrome.storage.session` — an
 * in-memory store that SURVIVES service-worker restarts WITHIN a browser
 * session and is cleared only when the browser closes (the correct lifetime for
 * per-tab search results). Reads rehydrate from `chrome.storage.session`.
 *
 * ## How a teardown is simulated (no real browser needed)
 * `chrome.storage.session` lives on the `globalThis.chrome` fake installed in
 * `beforeEach` and PERSISTS across a module re-import. The in-memory module
 * `Map`, by contrast, is re-created from scratch when the module is re-imported
 * via `vi.resetModules()`. So:
 *
 *   1. import the module, `initBackground()`, send a `scan-result` (tab 7),
 *   2. `vi.resetModules()` + re-import → a FRESH module instance whose
 *      `tabResults` Map is EMPTY (this IS the SW teardown — the in-memory state
 *      is gone), while `chrome.storage.session` still holds what step 1 wrote,
 *   3. `initBackground()` on the fresh instance, then `get-detected` for tab 7.
 *
 * Against the pre-fix code step 3 returns `null` (the Map was the only store and
 * it is gone) — the RED reproduction. After the fix the post-teardown
 * `get-detected` rehydrates from `chrome.storage.session` and returns the SAME
 * stored set — GREEN.
 *
 * @module tests/unit/background-sw-teardown.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createChromeStorageFake } from "./chrome-fake";

const INFOHASH_A = "1234567890abcdef1234567890abcdef12345678";
const INFOHASH_B = "abcdef1234567890abcdef1234567890abcdef12";
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu`;
const MAGNET_B = `magnet:?xt=urn:btih:${INFOHASH_B}&dn=Debian`;

// ─────────────────────────────────────────────────────────────────────────────
// MV3 chrome surface fake (storage.session is the load-bearing, survives-import part)
// ─────────────────────────────────────────────────────────────────────────────

type MessageHandler = (
  message: { type: string; payload?: Record<string, unknown> },
  sender: { tab?: { id?: number } },
  sendResponse: (response: unknown) => void,
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

/** A minimal in-memory chrome.storage.session fake (Map-backed, async API). */
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
        for (const k of list) {
          if (store.has(k)) out[k] = store.get(k);
        }
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

interface FakeChrome {
  storage: ReturnType<typeof createChromeStorageFake>["chrome"]["storage"] & {
    session: ReturnType<typeof sessionStorageFake>["api"];
  };
  runtime: {
    onMessage: ReturnType<typeof listenerHub<MessageHandler>>;
    onInstalled: ReturnType<typeof listenerHub<(d: { reason: string }) => void>>;
    onStartup: ReturnType<typeof listenerHub<() => void>>;
  };
  contextMenus: {
    create: ReturnType<typeof vi.fn>;
    onClicked: ReturnType<typeof listenerHub<(info: unknown, tab: unknown) => void>>;
  };
  commands: { onCommand: ReturnType<typeof listenerHub<(c: string, t?: { id?: number }) => void>> };
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
  store: Map<string, unknown>;
  sessionStore: Map<string, unknown>;
}

/**
 * Install a full MV3 chrome fake onto globalThis. The `storage.local` +
 * `storage.session` Maps are created ONCE and persist for the whole test — so a
 * module re-import (the simulated SW teardown) sees the SAME session store.
 */
function installChrome(): InstalledChrome {
  const storageFake = createChromeStorageFake();
  const session = sessionStorageFake();

  const chrome: FakeChrome = {
    storage: { ...storageFake.chrome.storage, session: session.api },
    runtime: {
      onMessage: listenerHub<MessageHandler>(),
      onInstalled: listenerHub<(d: { reason: string }) => void>(),
      onStartup: listenerHub<() => void>(),
    },
    contextMenus: {
      create: vi.fn(),
      onClicked: listenerHub<(info: unknown, tab: unknown) => void>(),
    },
    commands: { onCommand: listenerHub<(c: string, t?: { id?: number }) => void>() },
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
      sendMessage: vi.fn(() => Promise.resolve(null)),
      query: vi.fn(() => Promise.resolve([{ id: 42 }])),
      create: vi.fn(() => Promise.resolve({ id: 99 })),
    },
  };

  (globalThis as unknown as { chrome: unknown }).chrome = chrome;
  return { chrome, store: storageFake.store, sessionStore: session.store };
}

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

/** Fire a message through the freshest registered onMessage handler. */
function sendMessage(
  ch: FakeChrome,
  message: { type: string; payload?: Record<string, unknown> },
  sender: { tab?: { id?: number } } = {},
): Promise<unknown> {
  const handlers = ch.runtime.onMessage.handlers;
  const handler = handlers[handlers.length - 1];
  if (!handler) throw new Error("no onMessage handler registered");
  return new Promise((resolve) => {
    const returned = handler(message, sender, resolve);
    expect(returned).toBe(true);
  });
}

/** (Re)import the production background module fresh — simulates SW (re)spawn. */
async function loadBackgroundFresh() {
  vi.resetModules();
  return import("../../src/background/index");
}

let installed: InstalledChrome;

beforeEach(() => {
  installed = installChrome();
});

afterEach(() => {
  delete (globalThis as unknown as { chrome?: unknown }).chrome;
  vi.restoreAllMocks();
});

describe("crash-risk S3 — tabResults survives MV3 service-worker teardown", () => {
  it("get-detected returns the stored set AFTER a simulated SW teardown (rehydrated from chrome.storage.session)", async () => {
    // ── SW instance #1: scan a page; the result is stored for tab 7 ──────────
    const ch = installed.chrome;
    const { initBackground } = await loadBackgroundFresh();
    initBackground();

    const result = scanResult([
      { id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" },
      { id: INFOHASH_B, magnet: MAGNET_B, name: "Debian" },
    ]);
    const stored = (await sendMessage(
      ch,
      { type: "scan-result", payload: { result } },
      { tab: { id: 7 } },
    )) as { success: boolean };
    expect(stored.success).toBe(true);

    // Sanity: BEFORE teardown the same instance returns the set (proves the
    // happy path works and isolates the failure to the teardown).
    const before = (await sendMessage(ch, {
      type: "get-detected",
      payload: { tabId: 7 },
    })) as { success: boolean; data?: { result?: { items?: unknown[] } } };
    expect(before.data?.result?.items).toHaveLength(2);

    // ── Simulated SW TEARDOWN: re-import the module → FRESH, EMPTY in-memory
    //    state. chrome.storage.session (on the persistent chrome fake) is the
    //    ONLY store that survives this boundary. ──────────────────────────────
    const { initBackground: initBackground2 } = await loadBackgroundFresh();
    initBackground2();

    // The new SW instance MUST still find the result — rehydrated from session
    // storage. Pre-fix (in-memory Map only) this is null → the bug reproduces.
    const after = (await sendMessage(ch, {
      type: "get-detected",
      payload: { tabId: 7 },
    })) as { success: boolean; data?: { result?: { items?: { displayName?: string }[] } } };

    expect(after.success).toBe(true);
    expect(after.data?.result).not.toBeNull();
    expect(after.data?.result?.items).toHaveLength(2);
    const names = (after.data?.result?.items ?? [])
      .map((i) => i.displayName)
      .sort();
    expect(names).toEqual(["Debian", "Ubuntu"]);
  });

  it("the per-tab scan result is actually written to chrome.storage.session (the durable store)", async () => {
    const ch = installed.chrome;
    const { initBackground } = await loadBackgroundFresh();
    initBackground();

    await sendMessage(
      ch,
      {
        type: "scan-result",
        payload: { result: scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]) },
      },
      { tab: { id: 7 } },
    );

    // USER-OBSERVABLE durability: something keyed to tab 7 now lives in the
    // session store (the store the browser preserves across SW restarts). The
    // pre-fix code touches only the in-memory Map → this store stays empty.
    const allSession = Array.from(installed.sessionStore.entries());
    const blob = JSON.stringify(allSession);
    expect(allSession.length).toBeGreaterThan(0);
    expect(blob).toContain(MAGNET_A);
  });
});
