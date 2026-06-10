/**
 * @fileoverview SECURITY — background message-router robustness under hostile input.
 *
 * The background service worker's `chrome.runtime.onMessage` router
 * ({@link registerMessageRouter} → {@link handleMessage} in
 * `src/background/index.ts`) is the central trust boundary of the extension:
 * EVERY message from a content script (running on an arbitrary, possibly
 * attacker-controlled page), the popup, and the options page funnels through
 * it. A content script on a hostile page can `chrome.runtime.sendMessage(...)`
 * ANYTHING — a wrong/absent `type`, a `null` body, a non-object, a 1 MB string,
 * a payload whose shape violates the declared {@link ExtensionMessage} contract,
 * or prototype-pollution-shaped keys (`__proto__` / `constructor`). The router
 * MUST degrade gracefully: it must NOT throw uncaught (which under MV3 would
 * surface as an unhandled rejection / broken sendResponse channel), must NOT
 * corrupt the per-tab detected-set state, and must STAY ALIVE to serve the next
 * VALID message.
 *
 * These are ADDITIVE, SAFETY-FIRST tests (constitution §11.4.85 stress/chaos
 * mandate, §11.4.107 robustness): they drive the REAL production router via the
 * installed `chrome` fake (same harness as `tests/unit/background.test.ts`) with
 * hostile/malformed messages and assert USER-OBSERVABLE robustness — the router
 * resolves a sane response (or ignores), the in-memory state is not corrupted,
 * and a SUBSEQUENT valid message still works end-to-end (proving the SW survived
 * the hostile input rather than merely "not erroring" on the bad call).
 *
 * ANTI-BLUFF (§11.4 / §11.4.1): every test's survival assertion is a REAL
 * round-trip of a follow-up valid `scan-result` → `get-detected` that returns
 * the stored set. If the router had crashed (the SW listener threw uncaught, or
 * the channel broke), the follow-up `sendMessage` would never resolve and the
 * test would hang/fail — these tests fail LOUDLY against a crashed router, not
 * silently pass on "no error". A no-op stub that ignores every message would
 * also fail: the follow-up `get-detected` would return null, not the 1-item set.
 *
 * @module tests/security/message-router-robustness.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createChromeStorageFake } from "../unit/chrome-fake";

// ─────────────────────────────────────────────────────────────────────────────
// MV3 chrome surface fake (mirrors tests/unit/background.test.ts — the canonical
// harness for driving the REAL router). Kept self-contained so this security
// suite does not depend on a non-exported helper.
// ─────────────────────────────────────────────────────────────────────────────

const INFOHASH_A = "1234567890abcdef1234567890abcdef12345678";
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu`;

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
  badgeTexts: () => string[];
  store: Map<string, unknown>;
}

/** Install a full MV3 chrome fake onto globalThis. */
function installChrome(): InstalledChrome {
  const storageFake = createChromeStorageFake();
  const session = sessionStorageFake();
  const badgeTexts: string[] = [];

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
  return {
    chrome,
    badgeTexts: () => badgeTexts,
    store: storageFake.store,
  };
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

/**
 * Fire a message through the registered onMessage handler and resolve with the
 * router's reply. Resolves with a sentinel when the handler synchronously
 * returns WITHOUT keeping the channel open (returned !== true) AND never calls
 * sendResponse — so a test can distinguish "ignored cleanly" from "replied".
 *
 * Throws ONLY if the listener itself threw synchronously (a real router crash —
 * §11.4.1 fail-loud), which is exactly the robustness defect we are probing for.
 */
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
      // A synchronous throw HERE is the router crashing on hostile input —
      // surface it so the test FAILs loudly rather than hanging.
      returned = handler(message, sender, reply);
    } catch (err) {
      reject(err instanceof Error ? err : new Error(String(err)));
      return;
    }
    // If the handler did not keep the channel open (returned !== true) and never
    // replied synchronously, treat it as a clean ignore after a microtask tick.
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

/**
 * The robustness contract, asserted after every hostile input: the router is
 * STILL ALIVE and serves a fresh VALID message end-to-end. Stores a 1-item set
 * via scan-result then reads it back via get-detected — a real round-trip that
 * would NOT resolve (or would return null) if the SW had crashed or been
 * corrupted. This is the user-observable "survived" proof (§11.4 anti-bluff).
 *
 * @param ch - The installed chrome fake.
 * @param tabId - A fresh tab id so this probe is independent of prior state.
 */
async function expectRouterStillAlive(
  ch: FakeChrome,
  tabId: number,
): Promise<void> {
  const result = scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]);
  const stored = (await sendMessage(
    ch,
    { type: "scan-result", payload: { result } },
    { tab: { id: tabId } },
  )) as { success?: boolean };
  expect(stored.success).toBe(true);

  const got = (await sendMessage(ch, {
    type: "get-detected",
    payload: { tabId },
  })) as { success?: boolean; data?: { result?: { items?: unknown[] } } };
  expect(got.success).toBe(true);
  expect(got.data?.result?.items).toHaveLength(1);
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

// ─────────────────────────────────────────────────────────────────────────────
// Malformed top-level message shapes
// ─────────────────────────────────────────────────────────────────────────────

describe("message-router robustness — malformed top-level message", () => {
  it("an UNKNOWN type degrades to a sane {success:false} and the router survives", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    const reply = (await sendMessage(ch, {
      type: "totally-bogus-type-xyz",
      payload: {},
    })) as { success?: boolean; error?: string };

    // sane structured rejection — NOT a thrown crash
    expect(reply.success).toBe(false);
    expect(typeof reply.error).toBe("string");

    // USER-OBSERVABLE: a subsequent valid message still works end-to-end
    await expectRouterStillAlive(ch, 101);
  });

  it("a MISSING type degrades cleanly and the router survives", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // no `type` field at all → falls through the switch to `default`
    const reply = (await sendMessage(ch, { payload: { foo: "bar" } })) as {
      success?: boolean;
      __ignored?: boolean;
    };
    // either a structured {success:false} reply or a clean ignore — never a crash
    expect(reply.success === false || reply.__ignored === true).toBe(true);

    await expectRouterStillAlive(ch, 102);
  });

  it("a NULL message body does not crash the router (no `Cannot read properties of null`)", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // Reading `.type` off null would throw synchronously; because handleMessage
    // is async the throw becomes a rejected promise the listener's .catch turns
    // into a structured {success:false}. Assert that — NOT a sync listener throw.
    const reply = (await sendMessage(ch, null)) as {
      success?: boolean;
      __ignored?: boolean;
    };
    expect(reply.success === false || reply.__ignored === true).toBe(true);

    await expectRouterStillAlive(ch, 103);
  });

  it("an UNDEFINED message body does not crash the router", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    const reply = (await sendMessage(ch, undefined)) as {
      success?: boolean;
      __ignored?: boolean;
    };
    expect(reply.success === false || reply.__ignored === true).toBe(true);

    await expectRouterStillAlive(ch, 104);
  });

  it("NON-OBJECT message bodies (string / number / boolean / array) do not crash the router", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    for (const body of ["a string message", 42, true, [1, 2, 3]]) {
      const reply = (await sendMessage(ch, body)) as {
        success?: boolean;
        __ignored?: boolean;
      };
      expect(reply.success === false || reply.__ignored === true).toBe(true);
    }

    await expectRouterStillAlive(ch, 105);
  });

  it("a HUGE type string (1 MB) is rejected cleanly without crashing or hanging", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    const hugeType = "x".repeat(1024 * 1024); // 1 MB unknown type
    const reply = (await sendMessage(ch, { type: hugeType })) as {
      success?: boolean;
      error?: string;
    };
    expect(reply.success).toBe(false);
    expect(typeof reply.error).toBe("string");

    await expectRouterStillAlive(ch, 106);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Malformed payloads for KNOWN types (the shape-validation seam)
// ─────────────────────────────────────────────────────────────────────────────

describe("message-router robustness — malformed payloads for known types", () => {
  it("send-torrent with MISSING ids → structured {success:false} (no throw, no state damage)", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    const reply = (await sendMessage(ch, {
      type: "send-torrent",
      payload: { tabId: 7 }, // ids absent
    })) as { success?: boolean; error?: string };
    expect(reply.success).toBe(false);
    expect(reply.error).toMatch(/tabId|ids/i);

    await expectRouterStillAlive(ch, 201);
  });

  it("send-torrent with ids of the WRONG TYPE (a string, not string[]) does not crash the router", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // `ids` is truthy but NOT an array. The handler casts it as string[]; any
    // .includes/.filter path over it must not throw a router-killing error.
    const reply = (await sendMessage(ch, {
      type: "send-torrent",
      payload: { tabId: 7, ids: "not-an-array" },
    })) as { success?: boolean; __ignored?: boolean };
    // Either a clean failure ("No active server" / "No torrents detected") or a
    // structured error — never an uncaught listener throw.
    expect(reply.success === false || reply.__ignored === true).toBe(true);

    await expectRouterStillAlive(ch, 202);
  });

  it("send-torrent with an EMPTY ids array degrades cleanly (no matching torrents)", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // store a real detected set first, then ask to send NONE
    const result = scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]);
    await sendMessage(ch, { type: "scan-result", payload: { result } }, { tab: { id: 7 } });

    const reply = (await sendMessage(ch, {
      type: "send-torrent",
      payload: { tabId: 7, ids: [] },
    })) as { success?: boolean; error?: string; __ignored?: boolean };
    // empty ids hits "No active server configured" (no seedConfig) or
    // "No matching torrents found" — both are structured, neither is a crash.
    expect(reply.success === false || reply.__ignored === true).toBe(true);

    await expectRouterStillAlive(ch, 203);
  });

  it("scan-result with a NON-ARRAY items field does not crash AND does not overwrite a tab's good set", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // Seed a GOOD 1-item detected set for tab 7 first.
    await sendMessage(
      ch,
      {
        type: "scan-result",
        payload: {
          result: scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]),
        },
      },
      { tab: { id: 7 } },
    );

    // Then a hostile scan-result whose `items` is a STRING (not an array). With no
    // shape-guard this overwrites tab 7's good set with garbage that flows to the
    // popup (result.items.length → undefined; popup iterates a string).
    const reply = (await sendMessage(
      ch,
      {
        type: "scan-result",
        payload: { result: { items: "not-an-array", pageUrl: "x" } },
      },
      { tab: { id: 7 } },
    )) as { success?: boolean; __ignored?: boolean };
    expect(reply.success === true || reply.success === false || reply.__ignored === true).toBe(true);

    // USER-OBSERVABLE: the corrupt scan was REJECTED — tab 7 STILL holds the good
    // 1-item ARRAY, never the "not-an-array" string. Against the un-guarded code
    // get-detected returns the corrupt string → these assertions fail (the string
    // is not an array and has length 12, not 1).
    const got = (await sendMessage(ch, {
      type: "get-detected",
      payload: { tabId: 7 },
    })) as { success?: boolean; data?: { result?: { items?: unknown } | null } };
    expect(got.success).toBe(true);
    expect(Array.isArray(got.data?.result?.items)).toBe(true);
    expect(got.data?.result?.items).toHaveLength(1);

    await expectRouterStillAlive(ch, 204);
  });

  it("scan-result whose items array holds entries MISSING required fields does not crash the router", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // items is a real array, but each entry is a bare object missing id/magnet/
    // displayName. The badge counts items.length; get-detected returns them as-is.
    // Neither path should throw.
    const reply = (await sendMessage(
      ch,
      {
        type: "scan-result",
        payload: { result: { items: [{}, { id: "x" }, null], pageUrl: "x" } },
      },
      { tab: { id: 7 } },
    )) as { success?: boolean };
    expect(reply.success).toBe(true);

    await expectRouterStillAlive(ch, 205);
  });

  it("set-config with a MISSING config → structured {success:false} and the router survives", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    const reply = (await sendMessage(ch, {
      type: "set-config",
      payload: {},
    })) as { success?: boolean; error?: string };
    expect(reply.success).toBe(false);
    expect(reply.error).toMatch(/config/i);

    await expectRouterStillAlive(ch, 206);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Prototype-pollution-shaped keys + deeply-nested payloads
// ─────────────────────────────────────────────────────────────────────────────

describe("message-router robustness — prototype-pollution-ish + deep payloads", () => {
  it("a payload carrying __proto__ / constructor keys does not crash the router NOR pollute Object.prototype", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // A JSON.parse'd hostile payload: plain-data keys named __proto__ / constructor.
    // (JSON.parse assigns these as OWN properties, it does not walk the prototype
    // chain — so this is the realistic on-the-wire shape a content script sends.)
    const hostile = JSON.parse(
      '{"type":"scan-result","payload":{"__proto__":{"polluted":"yes"},"constructor":{"x":1},"result":{"items":[]}}}',
    ) as unknown;

    const before = ({} as Record<string, unknown>)["polluted"];
    const reply = (await sendMessage(ch, hostile, { tab: { id: 7 } })) as {
      success?: boolean;
    };
    expect(reply.success).toBe(true);

    // SECURITY: Object.prototype was NOT polluted by routing the message.
    const after = ({} as Record<string, unknown>)["polluted"];
    expect(after).toBe(before);
    expect(after).toBeUndefined();

    await expectRouterStillAlive(ch, 301);
  });

  it("a send-torrent payload with a __proto__-shaped key does not crash the router", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    const hostile = JSON.parse(
      '{"type":"send-torrent","payload":{"tabId":7,"ids":["a"],"__proto__":{"isAdmin":true}}}',
    ) as unknown;

    const reply = (await sendMessage(ch, hostile)) as {
      success?: boolean;
      __ignored?: boolean;
    };
    // no active server seeded → structured failure, never a crash
    expect(reply.success === false || reply.__ignored === true).toBe(true);
    // prototype untouched
    expect(({} as Record<string, unknown>)["isAdmin"]).toBeUndefined();

    await expectRouterStillAlive(ch, 302);
  });

  it("a DEEPLY-NESTED payload (1000-level) is routed without a stack-overflow crash", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // Build a 1000-deep nested object as the payload. The router does not recurse
    // into payload, so this must route cleanly — assert it does + survives.
    let deep: Record<string, unknown> = { leaf: true };
    for (let i = 0; i < 1000; i++) deep = { nested: deep };

    const reply = (await sendMessage(ch, {
      type: "get-detected",
      payload: { tabId: 7, junk: deep },
    })) as { success?: boolean };
    expect(reply.success).toBe(true);

    await expectRouterStillAlive(ch, 303);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Survival under a BURST of mixed hostile inputs (state-integrity stress)
// ─────────────────────────────────────────────────────────────────────────────

describe("message-router robustness — survives a burst of mixed hostile inputs", () => {
  it("after a barrage of malformed messages the router STILL serves valid traffic + keeps prior state", async () => {
    const { initBackground } = await loadBackground();
    initBackground();
    const ch = installed.chrome;

    // Seed real state for tab 7 BEFORE the barrage.
    const seed = scanResult([{ id: INFOHASH_A, magnet: MAGNET_A, name: "Ubuntu" }]);
    await sendMessage(ch, { type: "scan-result", payload: { result: seed } }, { tab: { id: 7 } });

    // Fire a barrage of hostile inputs — none may crash the listener.
    const hostile: unknown[] = [
      null,
      undefined,
      "raw string",
      12345,
      [],
      {},
      { type: 123 },
      { type: "unknown" },
      { type: "send-torrent", payload: null },
      { type: "scan-result", payload: { result: { items: 5 } } },
      { type: "set-config", payload: { config: null } },
      { type: "x".repeat(50000) },
    ];
    for (const m of hostile) {
      const reply = (await sendMessage(ch, m, { tab: { id: 7 } })) as {
        success?: boolean;
        __ignored?: boolean;
      };
      // every one resolves to SOMETHING (structured or ignore) — never a throw
      expect(reply !== undefined && reply !== null).toBe(true);
    }

    // STATE INTEGRITY: the tab-7 set seeded BEFORE the barrage is intact.
    const got = (await sendMessage(ch, {
      type: "get-detected",
      payload: { tabId: 7 },
    })) as { success?: boolean; data?: { result?: { items?: unknown[] } } };
    expect(got.success).toBe(true);
    expect(got.data?.result?.items).toHaveLength(1);

    // …and the router still accepts fresh valid traffic on a new tab.
    await expectRouterStillAlive(ch, 401);
  });
});
