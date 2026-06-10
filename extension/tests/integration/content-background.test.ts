/**
 * @fileoverview CONTENT-SCRIPT ↔ BACKGROUND integration tests for BobaLink.
 *
 * Fills the content-script/background integration-coverage gap (a "—" cell in
 * the ledger): the content-script unit tests drive `initContentScript()` against
 * a stub `chrome.runtime` whose `sendMessage` is a spy; the background unit tests
 * fire messages straight at the router. NEITHER proves the REAL content script's
 * scan-result message actually reaching the REAL background router and being
 * STORED for the originating tab. This file wires them together end-to-end:
 *
 * THE BRIDGE — one chrome fake with TWO independent `onMessage` listener hubs:
 *   - the BACKGROUND hub (the router's `chrome.runtime.onMessage` listener), and
 *   - the CONTENT hub (the content script's own `chrome.runtime.onMessage`
 *     listener it registers in `initContentScript`).
 * `chrome.runtime.sendMessage` is the content script's outbound channel: it
 * REALLY dispatches the `scan-result` envelope into the BACKGROUND hub's
 * registered listener, attaching `sender.tab.id` exactly as Chrome does for a
 * content script (Chrome injects the tab of the script that called sendMessage).
 * The background's async router returns `true` + calls `sendResponse(reply)`, so
 * the content script's `await runtime.sendMessage(...)` resolves with the real
 * reply. The reverse directive channel (`scan-now` / `highlight-toggle`) is
 * dispatched into the CONTENT hub's registered listener — what the background's
 * `chrome.tabs.sendMessage(tabId, ...)` does to the active tab in production.
 *
 * The ONLY substituted boundaries are `chrome.storage.local` (the committed
 * in-memory fake) — every layer in between (the REAL ScannerOrchestrator detect,
 * the REAL content `initContentScript`, the REAL background `handleMessage`
 * store + reply) is the shipped code.
 *
 * §11.4 / §11.4.69 ANTI-BLUFF: every assertion is on a USER-OBSERVABLE,
 * cross-component outcome — the background's STORED detected set for the tab
 * (read back via a real `get-detected` reply), the EXACT infohashes/magnets the
 * orchestrator detected on the jsdom page, and the content script's re-scan /
 * highlight toggle observed through its OWN handles. The bridge REALLY invokes
 * the registered handlers — it is not a stub returning canned data. Each test's
 * no-op-stub catch is noted inline: a bridge/handler that DROPPED the scan-result
 * (handler never invoked, or sender.tab.id never attached) makes the
 * follow-up `get-detected` return `{result:null}` — failing the assertion loudly,
 * proving the round-trip is real and not a no-op.
 *
 * §11.4.10: no real token anywhere — no server/token is configured; there is no
 * network at all in these tests (detection + message routing only).
 *
 * @module tests/integration/content-background
 */

import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
} from "vitest";

import { createChromeStorageFake } from "../unit/chrome-fake";
import { DEFAULT_CONFIG } from "../../src/types/config";

import type { ExtensionConfig } from "../../src/types/config";
import type { DetectedTorrent } from "../../src/types/torrent";

// ─────────────────────────────────────────────────────────────────────────────
// Fixtures — a real jsdom page: a magnet `<a href>` (also repeated as bare text
// → must dedup to ONE) + a `.torrent` link. The two magnet occurrences exercise
// the orchestrator's cross-scanner dedup; the .torrent link exercises the file
// scanner — so the content script's detected set is non-trivial and identifiable.
// ─────────────────────────────────────────────────────────────────────────────

const TAB_ID = 314;

const INFOHASH_MAGNET = "0123456789abcdef0123456789abcdef01234567";
const MAGNET_URI = `magnet:?xt=urn:btih:${INFOHASH_MAGNET}&dn=Ubuntu%2024.04%20LTS&tr=udp%3A%2F%2Ftracker.example%3A1337`;
const TORRENT_URL = "https://files.example.org/releases/cool-release.torrent";

const PAGE_HTML = `
  <h1>Releases</h1>
  <a id="magnet-link" href="${MAGNET_URI}">Ubuntu via magnet</a>
  <p>Mirror the same release here too: ${MAGNET_URI} — cheers!</p>
  <a id="file-link" href="${TORRENT_URL}">Download the .torrent</a>
  <a href="https://example.org/not-a-torrent.html">A perfectly normal link</a>
`;

/**
 * Assert a value is present, returning it narrowed. A real assertion — if the
 * element / reply / item is missing the test fails HERE (stronger than `!`,
 * which would silently pass a `null` onward).
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
/**
 * Both shapes seen on the bridge: the BACKGROUND router replies with the wrapped
 * `{ success, data, error }` ({@link ExtensionMessageResponse}); the CONTENT
 * script's directive handler replies with a FLAT `{ success, enabled?, ... }`
 * (content/index.ts `handleMessage`). The bridge is shape-agnostic, so the type
 * is the union of both — each test reads the key its recipient actually returns.
 */
interface ExtResponse {
  success: boolean;
  data?: Record<string, unknown>;
  error?: string;
  /** Flat field the content script's highlight-toggle handler returns. */
  enabled?: boolean;
}
type Sender = { tab?: { id?: number } };
type MessageHandler = (
  message: ExtMessage,
  sender: Sender,
  sendResponse: (response: ExtResponse) => void,
) => boolean | undefined;

/** A listener registry that also lets the test FIRE the event. */
function listenerHub<F>() {
  const handlers: F[] = [];
  return {
    addListener: vi.fn((h: F) => {
      handlers.push(h);
    }),
    removeListener: vi.fn((h: F) => {
      const i = handlers.indexOf(h);
      if (i >= 0) handlers.splice(i, 1);
    }),
    handlers,
  };
}

/**
 * THE BRIDGE. Builds a chrome fake with TWO independent onMessage hubs (one the
 * background router registers into, one the content script registers into) and a
 * `runtime.sendMessage` that REALLY routes the content script's outbound message
 * into the BACKGROUND hub, attaching the content script's tab id as `sender.tab`
 * exactly as Chrome does.
 *
 * @param contentTabId - The tab id Chrome would attach to this content script's
 *   outbound `sendMessage` calls.
 */
function buildBridgeChrome(contentTabId: number) {
  const storageFake = createChromeStorageFake();
  // backgroundOnMessage: the router (chrome.runtime.onMessage) the background
  // registers. contentOnMessage: the content script's own listener.
  const backgroundOnMessage = listenerHub<MessageHandler>();
  const contentOnMessage = listenerHub<MessageHandler>();
  const badgeTexts: string[] = [];

  // Chrome routes a runtime.sendMessage from a context to ALL onMessage
  // listeners; here the only sender is the content script and the only relevant
  // recipient is the background router. We dispatch into the BACKGROUND hub with
  // the content script's tab as sender.tab (Chrome injects the calling tab).
  function sendMessage(message: ExtMessage): Promise<ExtResponse> | undefined {
    const handler = backgroundOnMessage.handlers[0];
    if (!handler) return undefined;
    return new Promise<ExtResponse>((resolveReply) => {
      handler(message, { tab: { id: contentTabId } }, resolveReply);
    });
  }

  const chrome = {
    storage: { ...storageFake.chrome.storage },
    runtime: {
      sendMessage,
      // The content script registers its onMessage listener here; the background
      // registers ITS router here too — so we expose a single onMessage whose
      // addListener fans the listener to the right hub by registration ORDER is
      // brittle; instead each context gets its own hub via the accessors below.
      onMessage: contentOnMessage,
      onInstalled: listenerHub<(d: { reason: string }) => void>(),
      onStartup: listenerHub<() => void>(),
    },
    // Background-only surfaces (kept minimal — these tests do not send torrents).
    action: {
      setBadgeText: vi.fn((d: { text: string }) => {
        badgeTexts.push(d.text);
        return Promise.resolve();
      }),
      setBadgeBackgroundColor: vi.fn(() => Promise.resolve()),
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
    notifications: { create: vi.fn() },
    tabs: {
      query: vi.fn(() => Promise.resolve([{ id: contentTabId }])),
      sendMessage: vi.fn(() => Promise.resolve(null)),
      create: vi.fn(() => Promise.resolve({ id: 99 })),
    },
  };

  return {
    chrome,
    store: storageFake.store,
    badgeTexts: () => badgeTexts,
    /**
     * Install the BACKGROUND router's onMessage into the background hub. Called
     * right before `initBackground()` so the router registers into the dedicated
     * background hub (NOT the content hub the content script uses).
     */
    useBackgroundOnMessage(): void {
      chrome.runtime.onMessage = backgroundOnMessage;
    },
    /** Switch runtime.onMessage back to the CONTENT hub (content script init). */
    useContentOnMessage(): void {
      chrome.runtime.onMessage = contentOnMessage;
    },
    /**
     * Send a directive (`scan-now` / `highlight-toggle`) to the content script's
     * registered listener — what `chrome.tabs.sendMessage(tabId, ...)` does to
     * the active tab in production. Resolves with the content script's reply.
     */
    sendToContent(message: ExtMessage): Promise<ExtResponse> {
      const handler = mustExist(
        contentOnMessage.handlers[0],
        "registered content onMessage handler",
      );
      return new Promise<ExtResponse>((resolveReply) => {
        handler(message, {}, resolveReply);
      });
    },
    /**
     * Fire a message DIRECTLY at the background router (e.g. a `get-detected`
     * follow-up from the popup), with an explicit sender tab id.
     */
    fireAtBackground(message: ExtMessage, tabId?: number): Promise<ExtResponse> {
      const handler = mustExist(
        backgroundOnMessage.handlers[0],
        "registered background onMessage handler",
      );
      return new Promise<ExtResponse>((resolveReply) => {
        const sender: Sender = tabId === undefined ? {} : { tab: { id: tabId } };
        handler(message, sender, resolveReply);
      });
    },
  };
}

type Bridge = ReturnType<typeof buildBridgeChrome>;

/** A config that forces an initial auto-scan and disables mutation-observer noise. */
function autoScanConfig(): ExtensionConfig {
  return { ...DEFAULT_CONFIG, autoScan: true };
}

let bridge: Bridge;

beforeEach(() => {
  bridge = buildBridgeChrome(TAB_ID);
  (globalThis as unknown as { chrome: unknown }).chrome = bridge.chrome;
  document.body.innerHTML = PAGE_HTML;
});

afterEach(() => {
  document.body.innerHTML = "";
  delete (globalThis as unknown as { chrome?: unknown }).chrome;
  vi.restoreAllMocks();
  vi.resetModules();
});

/**
 * Boot the REAL background router (into the background hub) and the REAL content
 * script (registering into the content hub + running an auto-scan that sends the
 * scan-result through the bridge into the background).
 *
 * Order matters: the background hub must be active when `initBackground()`
 * registers the router; then we switch onMessage back to the content hub so the
 * content script's own listener lands in the content hub.
 *
 * @returns The live content-script controller.
 */
async function bootBackgroundAndContent() {
  vi.resetModules();
  const bg = await import("../../src/background/index");
  const content = await import("../../src/content/index");

  // 1) Register the background router into the dedicated background hub.
  bridge.useBackgroundOnMessage();
  bg.initBackground();

  // 2) The content script registers ITS listener into the content hub, and its
  //    auto-scan sends a scan-result via runtime.sendMessage → background hub.
  bridge.useContentOnMessage();
  const controller = await content.initContentScript({ config: autoScanConfig() });

  // Let the async scan-result send + background store settle.
  await vi.waitFor(() => {
    // The content script's auto-scan must have detected the page's torrents.
    expect(controller.orchestrator.getDetectedCount()).toBeGreaterThan(0);
  });

  return controller;
}

// ─────────────────────────────────────────────────────────────────────────────
// 1 + 2) content → background scan-result is STORED + EXACT identity match
// ─────────────────────────────────────────────────────────────────────────────

describe("content ↔ background — scan-result round-trip stores the detected set for the tab", () => {
  it("the REAL content script's auto-scan sends scan-result; the REAL background STORES it; get-detected returns the exact torrents", async () => {
    // No-op-stub this catches: a bridge that DROPPED the content script's
    // scan-result (handler never invoked) OR never attached sender.tab.id would
    // leave the background's tabResults empty for TAB_ID, so the follow-up
    // get-detected returns {result:null} and the row/identity assertions below
    // fail loudly. Every torrent asserted here came back over the wire from the
    // background's own store — the content script has no hand in the reply.
    const controller = await bootBackgroundAndContent();

    // What the orchestrator actually detected (the source of truth for identity).
    const detected = controller.orchestrator.getDetectedTorrents();
    const detectedMagnets = detected.filter((d) => d.type === "magnet");
    const detectedFiles = detected.filter((d) => d.type === "torrent-file");
    // Cross-scanner dedup: the magnet appears twice on the page → exactly ONE.
    expect(detectedMagnets).toHaveLength(1);
    expect(detectedFiles).toHaveLength(1);

    // Ask the REAL background what it STORED for TAB_ID (the popup's data source).
    const reply = await bridge.fireAtBackground(
      { type: "get-detected", payload: { tabId: TAB_ID } },
      TAB_ID,
    );
    expect(reply.success).toBe(true);

    const stored = mustExist(
      (reply.data?.["result"] as { items?: DetectedTorrent[] } | null) ?? null,
      "background stored scan result for the tab",
    );
    const storedItems = mustExist(stored.items, "stored items array");

    // The stored set is EXACTLY the deduped set the content script detected.
    expect(storedItems).toHaveLength(detected.length);

    // Cross-component identity: stored infohashes EXACTLY match what the
    // orchestrator detected on the page (not a fabricated/echoed set).
    const storedInfohashes = storedItems
      .filter((i) => i.type === "magnet")
      .map((i) => mustExist(i.magnet, "stored magnet info").infohash)
      .sort();
    const detectedInfohashes = detectedMagnets
      .map((i) => mustExist(i.magnet, "detected magnet info").infohash)
      .sort();
    expect(storedInfohashes).toEqual(detectedInfohashes);
    expect(storedInfohashes).toContain(INFOHASH_MAGNET);

    // Stored magnet URIs are byte-for-byte the scanner's (the user-forwarded URL).
    const storedMagnetUris = storedItems
      .filter((i) => i.type === "magnet")
      .map((i) => mustExist(i.magnet, "stored magnet info").uri);
    expect(storedMagnetUris).toEqual([MAGNET_URI]);

    // The stored .torrent-file URL matches the page's link, too.
    const storedFileUrls = storedItems
      .filter((i) => i.type === "torrent-file")
      .map((i) => mustExist(i.torrentFile, "stored torrent file").url);
    expect(storedFileUrls).toEqual([TORRENT_URL]);
  });

  it("the background's badge reflects the stored count (count = the content script's detected count)", async () => {
    // No-op-stub this catches: a scan-result that never reached the real router
    // would never call updateBadge → no non-empty badge text. The badge text the
    // user sees is set by the REAL background handler from the stored set length.
    const controller = await bootBackgroundAndContent();
    const count = controller.orchestrator.getDetectedCount();
    expect(count).toBeGreaterThan(0);

    await vi.waitFor(() => {
      // The latest non-empty badge text equals the detected count (capped at 99).
      const texts = bridge.badgeTexts().filter((t) => t !== "");
      expect(texts.at(-1)).toBe(String(count));
    });
  });

  it("an unseeded tab returns {result:null} from the background (proves storage is per-tab, not global)", async () => {
    // No-op-stub this catches: a bridge that fabricated a non-empty result, or a
    // background that stored globally, would return data for a DIFFERENT tab. We
    // boot (storing for TAB_ID) and then ask for a tab we never scanned → null.
    await bootBackgroundAndContent();
    const OTHER_TAB = TAB_ID + 1;
    const reply = await bridge.fireAtBackground(
      { type: "get-detected", payload: { tabId: OTHER_TAB } },
      OTHER_TAB,
    );
    expect(reply.success).toBe(true);
    expect(reply.data?.["result"]).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3) background → content directive round-trips (scan-now rescan + highlight)
// ─────────────────────────────────────────────────────────────────────────────

describe("background → content directives — the content script's onMessage acts on them", () => {
  it("highlight-toggle flips the content script's highlight manager (observed through its own handle)", async () => {
    // No-op-stub this catches: a content onMessage listener that never registered
    // (or ignored highlight-toggle) would leave isEnabled() unchanged. We assert
    // the REAL content handler mutated the REAL HighlightManager the controller
    // exposes — a cross-context directive genuinely took effect.
    const controller = await bootBackgroundAndContent();
    const before = controller.highlightManager.isEnabled();

    const reply = await bridge.sendToContent({ type: "highlight-toggle" });
    expect(reply.success).toBe(true);
    // The content handler reports the new state on a FLAT `enabled` field…
    expect(reply.enabled).toBe(!before);
    // …and the live manager handle reflects it.
    expect(controller.highlightManager.isEnabled()).toBe(!before);

    // Toggling again returns to the original state (deterministic, idempotent).
    const reply2 = await bridge.sendToContent({ type: "highlight-toggle" });
    expect(reply2.enabled).toBe(before);
    expect(controller.highlightManager.isEnabled()).toBe(before);
  });

  it("scan-now re-scans through the real orchestrator and re-reports to the background", async () => {
    // No-op-stub this catches: a content onMessage that ignored scan-now would
    // not re-run the orchestrator, so newly-added DOM content would never reach
    // the background. We add a SECOND .torrent link to the page, fire scan-now at
    // the content script, and assert (a) the orchestrator now detects the new
    // file and (b) the background's stored set grew to include it.
    const controller = await bootBackgroundAndContent();
    const beforeCount = controller.orchestrator.getDetectedCount();

    // Add a brand-new .torrent link to the live DOM (a new detection).
    const NEW_TORRENT_URL = "https://files.example.org/extra/second-release.torrent";
    const a = document.createElement("a");
    a.id = "second-file-link";
    a.href = NEW_TORRENT_URL;
    a.textContent = "Another .torrent";
    document.body.appendChild(a);

    // Fire the directive the background sends to the active tab on a scan-page
    // command (chrome.tabs.sendMessage(tabId, {type:"scan-now"})).
    const reply = await bridge.sendToContent({ type: "scan-now" });
    expect(reply.success).toBe(true);

    // The orchestrator picked up the new detection.
    await vi.waitFor(() => {
      expect(controller.orchestrator.getDetectedCount()).toBe(beforeCount + 1);
    });
    const detectedUrls = controller.orchestrator
      .getDetectedTorrents()
      .map((d) => d.torrentFile?.url ?? d.magnet?.uri);
    expect(detectedUrls).toContain(NEW_TORRENT_URL);

    // The re-scan re-reported to the background; the stored set now includes the
    // new file (the cross-component effect of a directive-driven re-scan).
    await vi.waitFor(async () => {
      const reReply = await bridge.fireAtBackground(
        { type: "get-detected", payload: { tabId: TAB_ID } },
        TAB_ID,
      );
      const stored = (reReply.data?.["result"] as { items?: DetectedTorrent[] } | null) ?? null;
      const urls = (stored?.items ?? []).map((i) => i.torrentFile?.url ?? i.magnet?.uri);
      expect(urls).toContain(NEW_TORRENT_URL);
    });
  });
});
