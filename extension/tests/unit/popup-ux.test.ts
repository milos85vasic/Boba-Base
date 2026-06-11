/**
 * @fileoverview UI/UX render-correctness + state-rendering tests for the REAL
 * popup module (the 13-type-matrix UI/UX cells — §11.4 anti-bluff).
 *
 * Sibling to `popup.test.ts` (which covers basic row render, send dispatch and
 * Connected/Disconnected status). This file ADDS the UX-specific render + state
 * cases that file does NOT cover:
 *
 *   - XSS-safe rendering: a torrent name containing HTML markup renders as TEXT
 *     (no injected DOM elements appear in the list);
 *   - the connection-status dot/text reflects EVERY state (warning / "No server"
 *     visibility, degraded), not just online/offline;
 *   - clicking Send disables the button DURING the send (no double-send), then a
 *     successful send flips the row into its visual "sent" state ("✓ Sent" badge,
 *     `torrent-sent` class, disabled "Sent" button);
 *   - a torrent pre-marked `sent` renders its sent visual state on first paint;
 *   - Send-All is disabled when EVERY torrent is already sent;
 *   - a very long name renders contained (truncated via the real markup, full
 *     name preserved in the row's `title` for the user).
 *
 * Every assertion inspects user-observable DOM (textContent / visibility /
 * disabled-state / classes) and fails if the UX behaviour broke. The real
 * `src/entrypoints/popup/index.html` body + the real `initPopup()` are used —
 * no UI logic is re-implemented in the test.
 *
 * @module tests/unit/popup-ux.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import type { DetectedTorrent } from "../../src/types/torrent";

const HERE = dirname(fileURLToPath(import.meta.url));
const POPUP_HTML = resolve(HERE, "../../src/entrypoints/popup/index.html");

/** Assert a value is present, returning it narrowed (stronger than `!`). */
function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

/** Flush the microtask queue a few times so the async click handlers settle. */
async function flush(): Promise<void> {
  for (let i = 0; i < 4; i++) await Promise.resolve();
}

const INFOHASH_A = "1234567890abcdef1234567890abcdef12345678";
const INFOHASH_B = "abcdef1234567890abcdef1234567890abcdef12";

function makeTorrent(over: Partial<DetectedTorrent>): DetectedTorrent {
  return {
    id: "id-x",
    type: "magnet",
    magnet: null,
    torrentFile: null,
    displayName: "Sample",
    selected: false,
    sent: false,
    sendStatus: null,
    detectedAt: 1000,
    ...over,
  };
}

function makeMagnetTorrent(
  id: string,
  name: string,
  infohash: string,
  over: Partial<DetectedTorrent> = {},
): DetectedTorrent {
  return makeTorrent({
    id,
    type: "magnet",
    displayName: name,
    magnet: {
      uri: `magnet:?xt=urn:btih:${infohash}&dn=${encodeURIComponent(name)}`,
      infohash,
      displayName: name,
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
    ...over,
  });
}

interface SendMessageSpy {
  (msg: { type: string; payload?: Record<string, unknown> }): Promise<unknown>;
  calls: Array<{ type: string; payload?: Record<string, unknown> }>;
}

/**
 * Install a chrome stub. `sendDeferred` lets a test pause the send-torrent
 * resolution so it can observe the in-flight (button-disabled) state before the
 * promise settles. `sendOk` decides which ids the fake background marks sent.
 */
function installChrome(opts: {
  detected: DetectedTorrent[];
  health?: string;
  sendDeferred?: { promise: Promise<unknown>; resolve: (v: unknown) => void };
  sendOk?: (id: string) => boolean;
}): SendMessageSpy {
  const calls: Array<{ type: string; payload?: Record<string, unknown> }> = [];
  const ok = opts.sendOk ?? (() => true);
  const sendMessage = vi.fn(
    (msg: { type: string; payload?: Record<string, unknown> }) => {
      calls.push(msg);
      switch (msg.type) {
        case "get-detected":
          return Promise.resolve({
            success: true,
            data: {
              result: {
                items: opts.detected,
                magnetCount: opts.detected.length,
                torrentFileCount: 0,
              },
            },
          });
        case "health-check":
          return Promise.resolve({
            success: true,
            data: {
              results: [
                { status: opts.health ?? "healthy", url: "http://localhost:7187" },
              ],
            },
          });
        case "send-torrent": {
          const result = {
            success: true,
            data: {
              results: (msg.payload?.ids as string[]).map((id) => ({
                id,
                success: ok(id),
                displayName: id,
                error: null,
              })),
            },
          };
          // When a deferred is supplied, hold the resolution so the test can
          // observe the in-flight disabled state before the send completes.
          if (opts.sendDeferred) {
            return opts.sendDeferred.promise.then(() => result);
          }
          return Promise.resolve(result);
        }
        default:
          return Promise.resolve({ success: false });
      }
    },
  ) as unknown as SendMessageSpy;
  (sendMessage as unknown as { calls: typeof calls }).calls = calls;

  const chrome = {
    runtime: {
      sendMessage,
      openOptionsPage: vi.fn(() => Promise.resolve()),
    },
    tabs: {
      query: vi.fn(() => Promise.resolve([{ id: 42 }])),
      sendMessage: vi.fn(() => Promise.resolve(null)),
    },
  };
  (globalThis as unknown as { chrome: unknown }).chrome = chrome;
  return sendMessage;
}

/** Load the real popup markup into the jsdom body (stripping the module script). */
function loadPopupDom(): void {
  const html = readFileSync(POPUP_HTML, "utf8");
  const bodyMatch = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
  document.body.innerHTML = bodyMatch
    ? mustExist(bodyMatch[1], "body content")
    : html;
  for (const s of Array.from(document.querySelectorAll("script"))) s.remove();
}

async function loadPopupModule() {
  vi.resetModules();
  return import("../../src/popup/popup");
}

beforeEach(() => {
  loadPopupDom();
});

afterEach(() => {
  document.body.innerHTML = "";
  delete (globalThis as unknown as { chrome?: unknown }).chrome;
});

// ─────────────────────────────────────────────────────────────────────────────
// XSS-safe rendering — a name with markup renders as TEXT, not DOM
// ─────────────────────────────────────────────────────────────────────────────

describe("popup UX — XSS-safe rendering of untrusted names", () => {
  it("renders a name containing HTML markup as text with no injected elements", async () => {
    const hostile = '<img src=x onerror="alert(1)"><b>boom</b>';
    installChrome({
      detected: [makeMagnetTorrent("id-x", hostile, INFOHASH_A)],
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const list = mustExist(document.getElementById("torrent-list"), "#torrent-list");
    const nameEl = mustExist(
      list.querySelector<HTMLElement>(".torrent-name"),
      ".torrent-name",
    );

    // The literal markup is shown to the user as text…
    expect(nameEl.textContent).toContain("<img");
    expect(nameEl.textContent).toContain("<b>boom</b>");
    // …and NO element was injected: no <img>/<b> exist anywhere in the list.
    expect(list.querySelector("img")).toBeNull();
    expect(list.querySelector("b")).toBeNull();
    // The name node has no element children (text-only, via textContent).
    expect(nameEl.children.length).toBe(0);
  });

  it("renders a markup infohash safely (text, no element injected)", async () => {
    // Defensive: even a hostile infohash string is rendered as text.
    const t = makeTorrent({
      id: "id-h",
      displayName: "Safe Name",
      magnet: {
        uri: "magnet:?xt=urn:btih:x",
        infohash: '<script>x</script>abcd',
        displayName: "Safe Name",
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
    });
    installChrome({ detected: [t] });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const list = mustExist(document.getElementById("torrent-list"), "#torrent-list");
    expect(list.querySelector("script")).toBeNull();
    const hashEl = mustExist(
      list.querySelector<HTMLElement>(".torrent-hash"),
      ".torrent-hash",
    );
    expect(hashEl.children.length).toBe(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Connection-status states beyond online/offline
// ─────────────────────────────────────────────────────────────────────────────

describe("popup UX — connection-status state rendering", () => {
  it("shows a No-server warning + warning dot when the background reports no results", async () => {
    // Override health-check to return zero results (no server configured).
    const calls: Array<{ type: string; payload?: Record<string, unknown> }> = [];
    const sendMessage = vi.fn(
      (msg: { type: string; payload?: Record<string, unknown> }) => {
        calls.push(msg);
        if (msg.type === "get-detected") {
          return Promise.resolve({
            success: true,
            data: { result: { items: [], magnetCount: 0, torrentFileCount: 0 } },
          });
        }
        if (msg.type === "health-check") {
          return Promise.resolve({ success: true, data: { results: [] } });
        }
        return Promise.resolve({ success: false });
      },
    );
    (globalThis as unknown as { chrome: unknown }).chrome = {
      runtime: { sendMessage, openOptionsPage: vi.fn(() => Promise.resolve()) },
      tabs: { query: vi.fn(() => Promise.resolve([{ id: 1 }])), sendMessage: vi.fn() },
    };

    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const statusText = mustExist(document.getElementById("status-text"), "#status-text");
    expect(statusText.textContent).toBe("No server");
    const dot = mustExist(document.getElementById("status-dot"), "#status-dot");
    expect(dot.classList.contains("status-warning")).toBe(true);
    // The connection-warning banner becomes visible (it starts display:none).
    const warning = mustExist(
      document.getElementById("connection-warning"),
      "#connection-warning",
    );
    expect(warning.style.display).not.toBe("none");
  });

  it("shows Degraded + warning dot when a server reports degraded health", async () => {
    installChrome({ detected: [], health: "degraded" });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const statusText = mustExist(document.getElementById("status-text"), "#status-text");
    expect(statusText.textContent).toBe("Degraded");
    const dot = mustExist(document.getElementById("status-dot"), "#status-dot");
    expect(dot.classList.contains("status-warning")).toBe(true);
    // The dot carries exactly one status-* state class (no stale online/offline).
    expect(dot.classList.contains("status-online")).toBe(false);
    expect(dot.classList.contains("status-offline")).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Send button in-flight + sent visual state
// ─────────────────────────────────────────────────────────────────────────────

describe("popup UX — Send button in-flight + sent state", () => {
  it("disables the row Send button during the send (no double-send)", async () => {
    let resolveSend: (v: unknown) => void = () => {};
    const promise = new Promise<unknown>((r) => {
      resolveSend = r;
    });
    const spy = installChrome({
      detected: [makeMagnetTorrent("id-a", "Ubuntu", INFOHASH_A)],
      sendDeferred: { promise, resolve: resolveSend },
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const sendBtn = mustExist(
      document.querySelector<HTMLButtonElement>(".torrent-item .btn-send-one"),
      ".btn-send-one",
    );
    expect(sendBtn.disabled).toBe(false);

    // First click starts the send — the button is disabled while in flight.
    sendBtn.click();
    await flush();
    expect(sendBtn.disabled).toBe(true);

    // A second click while disabled must NOT dispatch a second send.
    sendBtn.click();
    await flush();
    const sendCalls = spy.calls.filter((c) => c.type === "send-torrent");
    expect(sendCalls.length).toBe(1);

    // Complete the send so the test leaves no pending promise.
    resolveSend({});
    await flush();
  });

  it("flips a row into its visual sent state after a successful send", async () => {
    installChrome({
      detected: [makeMagnetTorrent("id-a", "Ubuntu", INFOHASH_A)],
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const row = mustExist(
      document.querySelector<HTMLElement>(".torrent-item"),
      ".torrent-item",
    );
    expect(row.classList.contains("torrent-sent")).toBe(false);

    const sendBtn = mustExist(
      row.querySelector<HTMLButtonElement>(".btn-send-one"),
      ".btn-send-one",
    );
    sendBtn.click();
    await flush();

    // After the send the list re-renders the row in its sent state.
    const sentRow = mustExist(
      document.querySelector<HTMLElement>(".torrent-item"),
      ".torrent-item (post-send)",
    );
    expect(sentRow.classList.contains("torrent-sent")).toBe(true);
    expect(sentRow.querySelector(".torrent-status")?.textContent).toContain("Sent");
    const postBtn = mustExist(
      sentRow.querySelector<HTMLButtonElement>(".btn-send-one"),
      ".btn-send-one (post-send)",
    );
    expect(postBtn.disabled).toBe(true);
    expect(postBtn.textContent).toBe("Sent");
  });

  it("renders the sent visual state on first paint for an already-sent torrent", async () => {
    installChrome({
      detected: [makeMagnetTorrent("id-a", "Ubuntu", INFOHASH_A, { sent: true })],
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const row = mustExist(
      document.querySelector<HTMLElement>(".torrent-item"),
      ".torrent-item",
    );
    expect(row.classList.contains("torrent-sent")).toBe(true);
    expect(row.querySelector(".torrent-status")?.textContent).toContain("Sent");
    const btn = mustExist(
      row.querySelector<HTMLButtonElement>(".btn-send-one"),
      ".btn-send-one",
    );
    expect(btn.disabled).toBe(true);
  });

  it("disables Send-All when every detected torrent is already sent", async () => {
    installChrome({
      detected: [
        makeMagnetTorrent("id-a", "A", INFOHASH_A, { sent: true }),
        makeMagnetTorrent("id-b", "B", INFOHASH_B, { sent: true }),
      ],
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    // Rows still render (not empty-state), but Send-All has nothing to send.
    expect(document.querySelectorAll(".torrent-item").length).toBe(2);
    const sendAll = mustExist(
      document.getElementById("btn-send-all"),
      "#btn-send-all",
    ) as HTMLButtonElement;
    expect(sendAll.disabled).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Long content / overflow containment
// ─────────────────────────────────────────────────────────────────────────────

describe("popup UX — long name containment", () => {
  it("truncates a very long name in the row but preserves the full name in title", async () => {
    const longName = "X".repeat(300);
    installChrome({
      detected: [makeMagnetTorrent("id-a", longName, INFOHASH_A)],
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const nameEl = mustExist(
      document.querySelector<HTMLElement>(".torrent-name"),
      ".torrent-name",
    );
    const shown = nameEl.textContent ?? "";
    // The visible text is contained (truncated well under the raw length).
    expect(shown.length).toBeLessThan(longName.length);
    expect(shown.length).toBeLessThanOrEqual(80); // EXT.MAX_DISPLAY_NAME_LENGTH
    expect(shown.endsWith("...")).toBe(true);
    // The full name is preserved for the user via the hover title.
    expect(nameEl.title).toBe(longName);
  });
});
