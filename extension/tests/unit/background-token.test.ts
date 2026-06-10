/**
 * @fileoverview Anti-bluff unit tests for the background service worker's
 * Phase-7 DECRYPT-before-send path (§11.4.10 / §11.4.43).
 *
 * The background SW must NOT send the stored ENCRYPTED `BOBA_API_TOKEN` bundle
 * straight to the wire as if it were plaintext — the Boba merge service would
 * reject ciphertext as a bearer token. Instead it must construct the client via
 * {@link BobaClient.create}, which decrypts the bundle with the session
 * passphrase and sends the resulting PLAINTEXT token.
 *
 * Passphrase source (the crux): the options page encrypts the token under a
 * USER-SUPPLIED session passphrase but never persisted that passphrase anywhere
 * the background could read it (`options.ts` carries a `TODO(Phase 7): wire a
 * session-passphrase prompt + unlock flow`). The honest minimal wiring chosen
 * here is `chrome.storage.session` (an in-memory, non-disk store cleared on
 * browser close) under the key `bobalink_session_passphrase` — set by the
 * unlock flow, read by the background at send time. NO passphrase is ever
 * hard-coded (§11.4.10).
 *
 * Anti-bluff assertions (captured wire headers, never logs):
 *  - encrypted token + session passphrase available → the request carries the
 *    DECRYPTED PLAINTEXT in `Authorization: Bearer <plaintext>` AND `X-Boba-Token`
 *    (NOT the ciphertext bundle). This FAILS against the pre-fix code that
 *    forwards the ciphertext bundle as the token.
 *  - encrypted token but NO session passphrase → default-open: NO auth header
 *    (the ciphertext is NEVER sent as a token).
 *  - no token configured at all → default-open: NO auth header.
 *  - the plaintext token AND the passphrase NEVER appear in any console line.
 *
 * @module tests/unit/background-token.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createChromeStorageFake } from "./chrome-fake";
import { STORAGE_KEYS } from "../../src/shared/constants";
import { encrypt } from "../../src/shared/crypto";
import { DEFAULT_CONFIG } from "../../src/types/config";
import type { ExtensionConfig, ServerConfig } from "../../src/types/config";

const INFOHASH_A = "1234567890abcdef1234567890abcdef12345678";
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu`;

// Synthetic secrets — never a real token / passphrase (§11.4.10). The plaintext
// token is what MUST reach the wire after decrypt; the ciphertext bundle MUST NOT.
const PLAINTEXT_TOKEN = `secret-token-${crypto.randomUUID()}`;
const SESSION_PASSPHRASE = `session-pass-${crypto.randomUUID()}`;

/** The session-storage key the background reads the unlock passphrase from. */
const SESSION_PASSPHRASE_KEY = "bobalink_session_passphrase";

// ─────────────────────────────────────────────────────────────────────────────
// MV3 chrome surface fake (local + session storage + the SW listener surfaces)
// ─────────────────────────────────────────────────────────────────────────────

type MessageHandler = (
  message: { type: string; payload?: Record<string, unknown> },
  sender: { tab?: { id?: number } },
  sendResponse: (response: unknown) => void,
) => boolean | undefined;

/** A listener registry that also lets a test FIRE the event. */
function listenerHub<F>() {
  const handlers: F[] = [];
  return {
    addListener: vi.fn((h: F) => {
      handlers.push(h);
    }),
    handlers,
  };
}

/** A minimal in-memory chrome.storage.session fake (Map-backed). */
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
  storage: {
    local: ReturnType<typeof createChromeStorageFake>["chrome"]["storage"]["local"];
    onChanged: ReturnType<typeof createChromeStorageFake>["chrome"]["storage"]["onChanged"];
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
  commands: { onCommand: ReturnType<typeof listenerHub<(c: string, t?: unknown) => void>> };
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

function installChrome(): InstalledChrome {
  const storageFake = createChromeStorageFake();
  const session = sessionStorageFake();

  const chrome: FakeChrome = {
    storage: {
      local: storageFake.chrome.storage.local,
      onChanged: storageFake.chrome.storage.onChanged,
      session: session.api,
    },
    runtime: {
      onMessage: listenerHub<MessageHandler>(),
      onInstalled: listenerHub<(d: { reason: string }) => void>(),
      onStartup: listenerHub<() => void>(),
    },
    contextMenus: {
      create: vi.fn(),
      onClicked: listenerHub<(info: unknown, tab: unknown) => void>(),
    },
    commands: { onCommand: listenerHub<(c: string, t?: unknown) => void>() },
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

function sendMessage(
  ch: FakeChrome,
  message: { type: string; payload?: Record<string, unknown> },
  sender: { tab?: { id?: number } } = {},
): Promise<unknown> {
  const handler = ch.runtime.onMessage.handlers[0];
  if (!handler) throw new Error("no onMessage handler registered");
  return new Promise((resolve) => {
    const returned = handler(message, sender, resolve);
    expect(returned).toBe(true);
  });
}

async function loadBackground() {
  vi.resetModules();
  return import("../../src/background/index");
}

/** Capture all four console channels into one string for §11.4.10 never-logged checks. */
function spyConsole(): { dump: () => string; restore: () => void } {
  const channels: Array<keyof Console> = ["log", "info", "warn", "error", "debug"];
  const spies = channels.map((c) =>
    vi.spyOn(console, c as "log").mockImplementation(() => undefined),
  );
  return {
    dump: () =>
      spies
        .flatMap((s) => s.mock.calls.map((args) => args.join(" ")))
        .join("\n"),
    restore: () => {
      for (const s of spies) s.mockRestore();
    },
  };
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
// DECRYPT-before-send: the encrypted token bundle must be decrypted with the
// session passphrase and the PLAINTEXT sent — not the ciphertext bundle.
// ─────────────────────────────────────────────────────────────────────────────

describe("background — Phase-7 decrypt-before-send (§11.4.10)", () => {
  it("decrypts the encrypted BOBA_API_TOKEN with the session passphrase and sends the PLAINTEXT on the wire", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "initiated", added_count: 1 }),
      } as unknown as Response),
    );
    vi.stubGlobal("fetch", fetchMock);
    const log = spyConsole();

    // Encrypt the token EXACTLY as the options page does (real crypto), and put
    // the JSON bundle into the server config.
    const bundle = await encrypt(PLAINTEXT_TOKEN, SESSION_PASSPHRASE);
    const encryptedToken = JSON.stringify(bundle);

    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    seedConfig(installed.store, makeServer({ encryptedBobaApiToken: encryptedToken }));
    // The unlock flow puts the session passphrase into chrome.storage.session.
    installed.sessionStore.set(SESSION_PASSPHRASE_KEY, SESSION_PASSPHRASE);

    const result = scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]);
    await sendMessage(ch, { type: "scan-result", payload: { result } }, { tab: { id: 7 } });
    await sendMessage(ch, {
      type: "send-torrent",
      payload: { tabId: 7, ids: [INFOHASH_A] },
    });

    expect(fetchMock).toHaveBeenCalled();
    const init = (fetchMock.mock.calls[0] as unknown[])?.[1] as RequestInit;
    const headers = (init.headers as Record<string, string>) ?? {};

    // USER-OBSERVABLE WIRE: the DECRYPTED plaintext reached the bearer header…
    expect(headers["Authorization"]).toBe(`Bearer ${PLAINTEXT_TOKEN}`);
    expect(headers["X-Boba-Token"]).toBe(PLAINTEXT_TOKEN);

    // …and the ciphertext bundle JSON NEVER did (the pre-fix bug forwarded this).
    expect(headers["Authorization"]).not.toContain(bundle.ciphertext);
    expect(headers["Authorization"]).not.toContain("salt");

    // §11.4.10: neither the plaintext token NOR the passphrase ever hit any log.
    const logged = log.dump();
    log.restore();
    expect(logged).not.toContain(PLAINTEXT_TOKEN);
    expect(logged).not.toContain(SESSION_PASSPHRASE);
  });

  it("default-open: encrypted token present but NO session passphrase → NO auth header (never sends ciphertext)", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "initiated", added_count: 1 }),
      } as unknown as Response),
    );
    vi.stubGlobal("fetch", fetchMock);

    const bundle = await encrypt(PLAINTEXT_TOKEN, SESSION_PASSPHRASE);
    const encryptedToken = JSON.stringify(bundle);

    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    seedConfig(installed.store, makeServer({ encryptedBobaApiToken: encryptedToken }));
    // NB: no passphrase in chrome.storage.session → locked → default-open.

    const result = scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]);
    await sendMessage(ch, { type: "scan-result", payload: { result } }, { tab: { id: 7 } });
    await sendMessage(ch, {
      type: "send-torrent",
      payload: { tabId: 7, ids: [INFOHASH_A] },
    });

    expect(fetchMock).toHaveBeenCalled();
    const init = (fetchMock.mock.calls[0] as unknown[])?.[1] as RequestInit;
    const headers = (init.headers as Record<string, string>) ?? {};

    // No passphrase → no token of any kind on the wire (NOT the ciphertext).
    expect(headers["Authorization"]).toBeUndefined();
    expect(headers["X-Boba-Token"]).toBeUndefined();
  });

  it("default-open: no token configured at all → NO auth header", async () => {
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

    seedConfig(installed.store, makeServer()); // encryptedBobaApiToken undefined
    installed.sessionStore.set(SESSION_PASSPHRASE_KEY, SESSION_PASSPHRASE); // even if unlocked

    const result = scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]);
    await sendMessage(ch, { type: "scan-result", payload: { result } }, { tab: { id: 7 } });
    await sendMessage(ch, {
      type: "send-torrent",
      payload: { tabId: 7, ids: [INFOHASH_A] },
    });

    expect(fetchMock).toHaveBeenCalled();
    const init = (fetchMock.mock.calls[0] as unknown[])?.[1] as RequestInit;
    const headers = (init.headers as Record<string, string>) ?? {};
    expect(headers["Authorization"]).toBeUndefined();
    expect(headers["X-Boba-Token"]).toBeUndefined();
  });
});
