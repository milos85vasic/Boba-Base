/**
 * @fileoverview SECURITY — sender-trust + external-message attack surface (Phase 7).
 *
 * Two trust boundaries are audited here:
 *
 *  (A) MANIFEST surface — what can reach the extension AT ALL, and where it can
 *      exfiltrate TO. Parsed from the REAL `wxt.config.ts`:
 *        1. `externally_connectable` is ABSENT — a WEB PAGE must NOT be able to
 *           `chrome.runtime.sendMessage`/`connect` into the extension. Adding it
 *           (even scoped to localhost) would open the message router to arbitrary
 *           web origins; the analysis (Dim) explicitly says do NOT add it, so we
 *           assert it stays absent.
 *        2. CSP `connect-src` is scoped to the merge service on :7187 only — the
 *           extension can fetch ONLY localhost:7187 (+ 'self'), so a compromised
 *           extension page cannot exfiltrate to an arbitrary origin.
 *
 *  (B) ROUTER sender-trust — the `chrome.runtime.onMessage` router funnels
 *      messages from THREE surfaces with DIFFERENT trust: content scripts (on an
 *      arbitrary, possibly hostile page → `sender.tab` is set), and the
 *      popup/options extension pages (trusted → NO `sender.tab`). For the
 *      tab-scoped ops (`get-detected`, `send-torrent`, `scan-page`) the handler
 *      resolves a target tab. The SECURITY question: can a content script on tab
 *      A read/affect tab B by forging `payload.tabId = B`?
 *
 *      A content script must only ever read/act on ITS OWN tab — it scans its own
 *      page and has nothing to do with any other tab. The popup/options pages, by
 *      contrast, have NO `sender.tab` and LEGITIMATELY pass `payload.tabId` to
 *      target the active tab (see `src/popup/popup.ts` get-detected / send-torrent
 *      call sites). So the safe rule is: when `sender.tab?.id` is present (the
 *      message came from a content script) prefer it and IGNORE a forged
 *      `payload.tabId`; only an extension page (no `sender.tab`) may steer by
 *      `payload.tabId`. These tests assert that boundary holds for all three ops.
 *
 * ANTI-BLUFF (§11.4 / §11.4.1 / §11.4.107): the router tests drive the REAL
 * production router through the installed `chrome` fake (same harness as
 * `tests/security/message-router-robustness.test.ts`) and assert USER-OBSERVABLE
 * outcomes — a content script forging another tab's id reads NULL / does NOT
 * trigger a cross-tab send, while the popup path (no sender.tab) still resolves
 * the tab it asked for. Against the un-guarded code (raw
 * `payload.tabId ?? sender.tab.id`) the forged-tabId tests FAIL: the content
 * script reads tab B's set. The manifest tests FAIL the moment
 * `externally_connectable` is added or `connect-src` is widened.
 *
 * @module tests/security/sender-trust.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createChromeStorageFake } from "../unit/chrome-fake";
import { STORAGE_KEYS } from "../../src/shared/constants";
import { DEFAULT_CONFIG } from "../../src/types/config";
import type { ExtensionConfig, ServerConfig } from "../../src/types/config";

// ─────────────────────────────────────────────────────────────────────────────
// (A) MANIFEST surface — parsed from the REAL wxt.config.ts
// ─────────────────────────────────────────────────────────────────────────────

// `wxt.config.ts` does `import { defineConfig } from "wxt"`, which eagerly loads
// esbuild (breaks under jsdom's TextEncoder). Stub it to identity so the real
// manifest literal is returned unchanged (same pattern as the sibling
// manifest-least-privilege / csp security suites).
vi.mock("wxt", () => ({
  defineConfig: <T>(config: T): T => config,
}));

const wxtConfig = (await import("../../wxt.config")).default;

const manifest = wxtConfig.manifest as {
  manifest_version: number;
  externally_connectable?: { matches?: string[]; ids?: string[] };
  content_security_policy?: { extension_pages?: string } | string;
};

/** Parse a CSP string into directive → sources (mirrors csp.test.ts). */
function parseCsp(csp: string): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const segment of csp.split(";")) {
    const parts = segment.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) continue;
    const directive = (parts[0] as string).toLowerCase();
    map.set(directive, parts.slice(1));
  }
  return map;
}

describe("sender-trust (manifest) — externally_connectable is ABSENT", () => {
  it("is a real Manifest V3 manifest object", () => {
    // Guard so the externally_connectable assertions below are not tautologies
    // (if `manifest` were undefined, `.externally_connectable` would be undefined
    // for the wrong reason). FAILs loudly if the import shape changes.
    expect(manifest.manifest_version).toBe(3);
    expect(typeof manifest).toBe("object");
  });

  it("does NOT declare externally_connectable — no web page can message the extension", () => {
    // SECURITY: with `externally_connectable` absent, ONLY the extension's own
    // surfaces (content scripts it injects, popup, options) can reach the message
    // router. The analysis (Dim) explicitly warns against adding it (even matching
    // localhost) — a web page on a matched origin could then drive `send-torrent`
    // / read `get-detected`. The moment someone adds `externally_connectable`,
    // this FAILs.
    expect(manifest.externally_connectable).toBeUndefined();
    expect("externally_connectable" in manifest).toBe(false);
  });

  it("declares no externally_connectable.matches web-origin allowlist", () => {
    // Belt-and-suspenders: even an EMPTY externally_connectable object subtly
    // changes connect semantics; assert there is no `matches` array at all.
    const ext = manifest.externally_connectable;
    expect(ext?.matches).toBeUndefined();
  });
});

describe("sender-trust (manifest) — CSP connect-src is scoped to :7187 (no exfil)", () => {
  const cspObject = manifest.content_security_policy;
  const csp =
    typeof cspObject === "object" && cspObject
      ? (cspObject.extension_pages ?? "")
      : "";
  const directives = parseCsp(csp);

  it("ships a non-empty extension_pages CSP (guard against tautology)", () => {
    expect(csp.length).toBeGreaterThan(0);
    expect(directives.has("connect-src")).toBe(true);
  });

  it("connect-src allows ONLY 'self' + localhost:7187 — never a wildcard or foreign origin", () => {
    // SECURITY: bounds the exfiltration surface. A compromised extension page can
    // fetch ONLY the merge service; `*` or any other host would let a stolen
    // token / detected set be POSTed to an attacker origin. Any extra source FAILs.
    const sources = directives.get("connect-src") ?? [];
    expect(sources.length).toBeGreaterThan(0);
    expect(sources).not.toContain("*");
    for (const src of sources) {
      const allowed = src === "'self'" || src === "http://localhost:7187";
      expect(allowed).toBe(true);
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (B) ROUTER sender-trust — drive the REAL background router via the chrome fake
// ─────────────────────────────────────────────────────────────────────────────

const INFOHASH_A = "1234567890abcdef1234567890abcdef12345678";
const INFOHASH_B = "abcdef1234567890abcdef1234567890abcdef12";
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu`;
const MAGNET_B = `magnet:?xt=urn:btih:${INFOHASH_B}&dn=Debian`;

type MessageHandler = (
  message: unknown,
  sender: { tab?: { id?: number } },
  sendResponse: (response: unknown) => void,
) => boolean | undefined;

/** A vitest-style listener registry that also lets a test FIRE the event. */
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
  commands: { onCommand: ReturnType<typeof listenerHub<unknown>> };
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
}

/** Install a full MV3 chrome fake onto globalThis. */
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
    commands: { onCommand: listenerHub<unknown>() },
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
  return { chrome, store: storageFake.store };
}

/**
 * Build an active (auth-none) ServerConfig — mirrors background.test.ts's
 * makeServer so the send-torrent path has a real server to resolve and POST to.
 */
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

/** Persist a full ExtensionConfig with one active server (background.test.ts pattern). */
function seedConfig(store: Map<string, unknown>, server: ServerConfig): void {
  const config: ExtensionConfig = {
    ...DEFAULT_CONFIG,
    servers: [server],
    activeServerId: server.id,
  };
  store.set(STORAGE_KEYS.CONFIG, config);
}

/** A minimal valid PageScanResult-shaped payload for scan-result. */
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

/** Fire a message through the registered router and resolve with its reply. */
function sendMessage(
  ch: FakeChrome,
  message: unknown,
  sender: { tab?: { id?: number } } = {},
): Promise<unknown> {
  const handler = ch.runtime.onMessage.handlers[0];
  if (!handler) throw new Error("no onMessage handler registered");
  return new Promise((resolve, reject) => {
    let settled = false;
    const reply = (response: unknown): void => {
      if (settled) return;
      settled = true;
      resolve(response);
    };
    let returned: boolean | undefined;
    try {
      returned = handler(message, sender, reply);
    } catch (err) {
      reject(err instanceof Error ? err : new Error(String(err)));
      return;
    }
    if (returned !== true) {
      queueMicrotask(() => {
        if (!settled) {
          settled = true;
          resolve({ __ignored: true });
        }
      });
    }
  });
}

async function loadBackground() {
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

describe("sender-trust (router) — content script CANNOT read another tab via forged payload.tabId", () => {
  it("a content script on tab A forging payload.tabId=B does NOT receive tab B's detected set", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // Seed tab B (id 2) with a real 1-item set, as a content script on tab B would.
    await sendMessage(
      ch,
      { type: "scan-result", payload: { result: scanResult([{ id: INFOHASH_B, magnet: MAGNET_B, name: "Debian" }]) } },
      { tab: { id: 2 } },
    );
    // Tab A (id 1) has NOTHING detected.

    // A content script ON TAB A (sender.tab.id === 1) forges payload.tabId = 2 to
    // try to read tab B's private detected set. With the sender-trust guard the
    // router resolves the SENDER's tab (1, which is empty) and returns null — the
    // forged tabId is ignored. Against the un-guarded `payload.tabId ?? sender.tab.id`
    // it would return tab B's 1-item set: an info-leak. This assertion FAILs there.
    const got = (await sendMessage(
      ch,
      { type: "get-detected", payload: { tabId: 2 } },
      { tab: { id: 1 } },
    )) as { success?: boolean; data?: { result?: { items?: unknown[] } | null } };

    expect(got.success).toBe(true);
    expect(got.data?.result).toBeNull();
  });

  it("a content script's own get-detected (no forged tabId) still reads its OWN tab", async () => {
    // Counter-test proving the guard does not over-block: a content script that
    // does NOT forge a tabId still resolves its own sender tab and reads its set.
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    await sendMessage(
      ch,
      { type: "scan-result", payload: { result: scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]) } },
      { tab: { id: 1 } },
    );

    const got = (await sendMessage(
      ch,
      { type: "get-detected", payload: {} },
      { tab: { id: 1 } },
    )) as { success?: boolean; data?: { result?: { items?: unknown[] } | null } };

    expect(got.success).toBe(true);
    expect(got.data?.result?.items).toHaveLength(1);
  });

  it("the POPUP path (no sender.tab) legitimately resolves the tab it asks for via payload.tabId", async () => {
    // The popup/options pages have NO sender.tab and MUST steer by payload.tabId
    // (see src/popup/popup.ts). The guard must NOT break this trusted path.
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    await sendMessage(
      ch,
      { type: "scan-result", payload: { result: scanResult([{ id: INFOHASH_B, magnet: MAGNET_B, name: "Debian" }]) } },
      { tab: { id: 2 } },
    );

    // Popup query for tab 2 — sender has NO tab (extension page).
    const got = (await sendMessage(
      ch,
      { type: "get-detected", payload: { tabId: 2 } },
      {}, // no sender.tab → trusted extension page
    )) as { success?: boolean; data?: { result?: { items?: unknown[] } | null } };

    expect(got.success).toBe(true);
    expect(got.data?.result?.items).toHaveLength(1);
  });
});

describe("sender-trust (router) — content script CANNOT trigger cross-tab send / scan via forged tabId", () => {
  it("a content script on tab A forging payload.tabId=B for send-torrent does NOT POST tab B's magnet", async () => {
    // TIGHTENED (Phase-7 reviewer finding): the earlier form seeded NO active
    // server, so `sendTorrents` threw "No active server configured" BEFORE the
    // tab-resolve — the test would have PASSed against the VULNERABLE code too
    // (the server short-circuit masked the cross-tab read). Here we SEED an
    // active server AND install a capturing fetch so that against the vulnerable
    // `payload.tabId ?? sender.tab.id` precedence the forged send WOULD resolve
    // tab B's set and POST tab B's magnet (MAGNET_B) to /api/v1/download. The
    // guard instead resolves the SENDER's tab (1, empty) → structured failure,
    // and crucially NO fetch ever carries MAGNET_B. RED-on-vuln.
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

    // Tab B (id 2) has a sendable set; tab A (id 1) has nothing.
    await sendMessage(
      ch,
      { type: "scan-result", payload: { result: scanResult([{ id: INFOHASH_B, magnet: MAGNET_B, name: "Debian" }]) } },
      { tab: { id: 2 } },
    );

    // Content script on tab A forges tabId=2 to trigger a send of tab B's torrents.
    const reply = (await sendMessage(
      ch,
      { type: "send-torrent", payload: { tabId: 2, ids: [INFOHASH_B] } },
      { tab: { id: 1 } },
    )) as { success?: boolean; error?: string };

    // USER-OBSERVABLE (the tight assertion): NO fetch — and certainly none to the
    // download endpoint — carried tab B's magnet. We scan EVERY captured fetch's
    // method + URL + body for MAGNET_B / INFOHASH_B. Against the vulnerable code a
    // POST /api/v1/download whose body's download_urls includes MAGNET_B fires;
    // here it must not. This is the real cross-tab-exfil proof.
    for (const call of fetchMock.mock.calls as unknown[][]) {
      const url = typeof call[0] === "string" ? call[0] : "";
      const init = (call[1] ?? {}) as { body?: unknown };
      const body = typeof init.body === "string" ? init.body : "";
      const haystack = `${url} ${body}`;
      expect(haystack).not.toContain(MAGNET_B);
      expect(haystack).not.toContain(INFOHASH_B);
    }

    // …and the reply is the guard's structured failure (resolved empty tab 1),
    // never a success. No cross-tab send occurred.
    expect(reply.success).toBe(false);
    expect(reply.error).toMatch(/No torrents detected|No matching/i);
  });

  it("a content script on tab A forging payload.tabId=B for scan-page does NOT scan tab B", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // Content script on tab A (id 1) forges scan-page for tab B (id 2).
    await sendMessage(
      ch,
      { type: "scan-page", payload: { tabId: 2 } },
      { tab: { id: 1 } },
    );

    // The guard resolves the SENDER's tab (1), so the directive is sent to tab 1
    // — NEVER tab 2. Against the un-guarded code chrome.tabs.sendMessage(2, …) would
    // fire: a content script poking a DIFFERENT tab's content script.
    expect(ch.tabs.sendMessage).toHaveBeenCalled();
    const sentTabIds = ch.tabs.sendMessage.mock.calls.map((c) => c[0] as number);
    expect(sentTabIds).toContain(1);
    expect(sentTabIds).not.toContain(2);
  });
});
