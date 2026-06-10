/**
 * @fileoverview Anti-bluff unit tests for the REAL popup UI module.
 *
 * Imports the production `src/popup/popup.ts` and drives its exported
 * `initPopup()` against a jsdom-loaded copy of the real `index.html` body.
 * `chrome.runtime.sendMessage` and `chrome.tabs.query` are stubbed so the
 * popup queries a fake background for detected torrents + health, then the
 * tests assert USER-OBSERVABLE outcomes (§11.4 anti-bluff):
 *
 *  - after init, the DOM contains one row per detected torrent, with the
 *    rendered name + short-infohash text actually present (textContent),
 *  - clicking a row Send button dispatches a `send-torrent` message carrying
 *    THAT torrent's id (real spy on sendMessage),
 *  - clicking Send-All dispatches `send-torrent` for ALL torrent ids,
 *  - an empty detected list renders the empty-state message and hides the list,
 *  - the connection status text is driven from the health-check response.
 *
 * Each assertion fails against a no-op stub of the feature it covers.
 *
 * @module tests/unit/popup.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import type { DetectedTorrent } from "../../src/types/torrent";

const HERE = dirname(fileURLToPath(import.meta.url));
const POPUP_HTML = resolve(HERE, "../../src/entrypoints/popup/index.html");

/**
 * Assert a value is present, returning it narrowed. A real assertion — if the
 * element / row / message is missing the test fails here (stronger than `!`,
 * which would silently pass a `null` to the next access).
 */
function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

// ─────────────────────────────────────────────────────────────────────────────
// Sample data + chrome fake
// ─────────────────────────────────────────────────────────────────────────────

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
  });
}

const SAMPLE: DetectedTorrent[] = [
  makeMagnetTorrent("id-a", "Ubuntu 24.04 ISO", INFOHASH_A),
  makeMagnetTorrent("id-b", "Debian 12 netinst", INFOHASH_B),
];

interface SendMessageSpy {
  (msg: { type: string; payload?: Record<string, unknown> }): Promise<unknown>;
  calls: Array<{ type: string; payload?: Record<string, unknown> }>;
}

/**
 * Build a chrome stub whose sendMessage answers get-detected with the supplied
 * list and health-check with the supplied status, recording every call so the
 * test can assert dispatch. chrome.tabs.query returns a single active tab.
 */
function installChrome(opts: {
  detected: DetectedTorrent[];
  health?: string;
}): SendMessageSpy {
  const calls: Array<{ type: string; payload?: Record<string, unknown> }> = [];
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
        case "send-torrent":
          return Promise.resolve({
            success: true,
            data: {
              results: (msg.payload?.ids as string[]).map((id) => ({
                success: true,
                torrent: { id, displayName: id },
                error: null,
              })),
            },
          });
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

/** Load the real index.html into the jsdom document body. */
function loadPopupDom(): void {
  const html = readFileSync(POPUP_HTML, "utf8");
  const bodyMatch = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
  document.body.innerHTML = bodyMatch ? mustExist(bodyMatch[1], "body content") : html;
  // strip the module <script> so jsdom doesn't try to fetch popup.ts
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
// Rendering
// ─────────────────────────────────────────────────────────────────────────────

describe("initPopup — rendering detected torrents", () => {
  it("renders one row per detected torrent with name + short infohash", async () => {
    installChrome({ detected: SAMPLE });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const rows = document.querySelectorAll<HTMLElement>(".torrent-item");
    expect(rows.length).toBe(2);

    const text = mustExist(document.getElementById("torrent-list"), "#torrent-list").textContent ?? "";
    expect(text).toContain("Ubuntu 24.04 ISO");
    expect(text).toContain("Debian 12 netinst");
    // short infohash (first 16 chars) is rendered, not the full 40
    expect(text).toContain(INFOHASH_A.slice(0, 16));
    expect(text).toContain(INFOHASH_B.slice(0, 16));

    // each row carries its id so dispatch can target it
    const ids = Array.from(rows).map((r) => r.dataset.id);
    expect(ids).toEqual(["id-a", "id-b"]);
  });

  it("each row has a Send button labelled for that torrent", async () => {
    installChrome({ detected: SAMPLE });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const sendBtns = document.querySelectorAll<HTMLButtonElement>(
      ".torrent-item .btn-send-one",
    );
    expect(sendBtns.length).toBe(2);
    for (const b of sendBtns) {
      expect(b.tagName).toBe("BUTTON");
      expect(b.textContent?.toLowerCase()).toContain("send");
    }
  });

  it("renders the empty-state message and hides the list when nothing detected", async () => {
    installChrome({ detected: [] });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    expect(document.querySelectorAll(".torrent-item").length).toBe(0);
    const empty = mustExist(document.getElementById("empty-state"), "#empty-state");
    expect(empty.style.display).not.toBe("none");
    expect(empty.textContent?.toLowerCase()).toContain("no torrents");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Send dispatch
// ─────────────────────────────────────────────────────────────────────────────

describe("initPopup — Send dispatch", () => {
  it("clicking a row Send button dispatches send-torrent with THAT torrent id", async () => {
    const spy = installChrome({ detected: SAMPLE });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const secondRow = mustExist(
      document.querySelectorAll<HTMLElement>(".torrent-item")[1],
      ".torrent-item[1]",
    );
    const sendBtn = mustExist(
      secondRow.querySelector<HTMLButtonElement>(".btn-send-one"),
      ".btn-send-one",
    );
    sendBtn.click();
    await Promise.resolve();
    await Promise.resolve();

    const sendCalls = spy.calls.filter((c) => c.type === "send-torrent");
    expect(sendCalls.length).toBe(1);
    expect(mustExist(sendCalls[0], "first send call").payload?.ids).toEqual(["id-b"]);
  });

  it("Send-All dispatches send-torrent for every detected torrent id", async () => {
    const spy = installChrome({ detected: SAMPLE });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const sendAll = document.getElementById("btn-send-all") as HTMLButtonElement;
    expect(sendAll).toBeTruthy();
    expect(sendAll.disabled).toBe(false);
    sendAll.click();
    await Promise.resolve();
    await Promise.resolve();

    const sendCalls = spy.calls.filter((c) => c.type === "send-torrent");
    expect(sendCalls.length).toBe(1);
    expect(mustExist(sendCalls[0], "first send call").payload?.ids).toEqual(["id-a", "id-b"]);
  });

  it("Send-All is disabled when there are no detected torrents", async () => {
    installChrome({ detected: [] });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const sendAll = document.getElementById("btn-send-all") as HTMLButtonElement;
    expect(sendAll.disabled).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Connection status
// ─────────────────────────────────────────────────────────────────────────────

describe("initPopup — connection status", () => {
  it("shows Connected when the background reports a healthy server", async () => {
    installChrome({ detected: SAMPLE, health: "healthy" });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const statusText = mustExist(document.getElementById("status-text"), "#status-text");
    expect(statusText.textContent).toBe("Connected");
    const dot = mustExist(document.getElementById("status-dot"), "#status-dot");
    expect(dot.classList.contains("status-online")).toBe(true);
  });

  it("shows Disconnected when no server is healthy", async () => {
    installChrome({ detected: SAMPLE, health: "unhealthy" });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const statusText = mustExist(document.getElementById("status-text"), "#status-text");
    expect(statusText.textContent).toBe("Disconnected");
    const dot = mustExist(document.getElementById("status-dot"), "#status-dot");
    expect(dot.classList.contains("status-offline")).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Options link
// ─────────────────────────────────────────────────────────────────────────────

describe("initPopup — options link", () => {
  it("clicking the options link opens the options page", async () => {
    installChrome({ detected: SAMPLE });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const link = document.getElementById("open-options") as HTMLAnchorElement;
    expect(link).toBeTruthy();
    link.click();
    await Promise.resolve();

    const openOptions = (
      globalThis as unknown as {
        chrome: { runtime: { openOptionsPage: ReturnType<typeof vi.fn> } };
      }
    ).chrome.runtime.openOptionsPage;
    expect(openOptions).toHaveBeenCalledTimes(1);
  });
});
