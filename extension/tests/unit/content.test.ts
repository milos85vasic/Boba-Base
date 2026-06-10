/**
 * @fileoverview Anti-bluff unit tests for the REAL content-script layer
 * (content/index.ts + content/highlight.ts).
 *
 * These tests import the PRODUCTION content modules and drive them against a
 * REAL jsdom DOM with a REAL committed {@link ScannerOrchestrator}. The chrome
 * extension API is unavailable under Vitest/jsdom, so we install a small
 * `chrome.runtime` fake (sendMessage spy + onMessage listener registry) onto the
 * global so the production `chrome.runtime.sendMessage` / `onMessage` calls hit
 * an observable surface — exactly the §11.4 anti-bluff posture used by the
 * orchestrator/storage tests.
 *
 * USER-OBSERVABLE assertions (not just "no error"):
 *   - Running the content entry over a page with magnet links SCANS via the real
 *     orchestrator AND SENDS a message to the background containing the detected
 *     torrent set (the spy captured the `scan-result` envelope; we assert the
 *     infohashes of the detected items are present in what was sent).
 *   - A `scan-now` (rescan) message from background triggers a re-scan that picks
 *     up a magnet added AFTER the first scan, and re-sends the grown set.
 *   - HighlightManager adds a marker element into a detected magnet anchor's
 *     vicinity, and removes it on toggle-off / destroy.
 *
 * Each assertion FAILS against a no-op stub of the feature it tests — the
 * send-to-background test fails if the entry never calls sendMessage; the
 * highlight test fails if no marker element is added.
 *
 * @module tests/unit/content.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { initContentScript } from "../../src/content/index";
import { HighlightManager } from "../../src/content/highlight";
import { TypedEventEmitter } from "../../src/shared/events";
import type { ExtensionMessage } from "../../src/types/api";

const INFOHASH_A = "0123456789abcdef0123456789abcdef01234567";
const INFOHASH_B = "fedcba9876543210fedcba9876543210fedcba98";
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu%2024.04%20LTS`;
const MAGNET_B = `magnet:?xt=urn:btih:${INFOHASH_B}&dn=Debian%2012`;

// ─────────────────────────────────────────────────────────────────────────────
// chrome.runtime fake
// ─────────────────────────────────────────────────────────────────────────────

type RuntimeListener = (
  message: unknown,
  sender: unknown,
  sendResponse: (response?: unknown) => void,
) => boolean | undefined;

interface RuntimeFake {
  sendMessage: ReturnType<typeof vi.fn>;
  onMessage: {
    addListener: (l: RuntimeListener) => void;
    removeListener: (l: RuntimeListener) => void;
  };
  /** Dispatch a message to all registered onMessage listeners (simulates background → content). */
  dispatch: (message: unknown) => Promise<unknown>;
  listeners: Set<RuntimeListener>;
}

/** Install a fresh chrome.runtime fake onto globalThis and return its handle. */
function installRuntimeFake(): RuntimeFake {
  const listeners = new Set<RuntimeListener>();
  const sendMessage = vi.fn(() => Promise.resolve(undefined));

  const fake: RuntimeFake = {
    sendMessage,
    onMessage: {
      addListener: (l: RuntimeListener): void => {
        listeners.add(l);
      },
      removeListener: (l: RuntimeListener): void => {
        listeners.delete(l);
      },
    },
    listeners,
    dispatch: (message: unknown): Promise<unknown> => {
      // The content listener answers asynchronously (returns `true`, calls
      // sendResponse later). Resolve on the first sendResponse; only fall back to
      // undefined if NO listener kept the channel open (returned falsy).
      return new Promise((resolve) => {
        let settled = false;
        let keptOpen = false;
        const sendResponse = (response?: unknown): void => {
          if (!settled) {
            settled = true;
            resolve(response);
          }
        };
        for (const l of listeners) {
          const r = l(message, { id: "background" }, sendResponse);
          if (r === true) keptOpen = true;
        }
        if (!keptOpen && !settled) {
          settled = true;
          resolve(undefined);
        }
      });
    },
  };

  (globalThis as unknown as { chrome: { runtime: unknown } }).chrome = {
    runtime: {
      sendMessage: fake.sendMessage,
      onMessage: fake.onMessage,
    },
  };

  return fake;
}

/** Collect the `scan-result` envelopes captured by the sendMessage spy. */
function scanResultMessages(fake: RuntimeFake): ExtensionMessage[] {
  return fake.sendMessage.mock.calls
    .map((c) => c[0] as ExtensionMessage)
    .filter((m) => m && m.type === "scan-result");
}

describe("content/index — init scans via real orchestrator and reports to background", () => {
  let fake: RuntimeFake;

  beforeEach(() => {
    document.body.innerHTML = "";
    fake = installRuntimeFake();
  });

  afterEach(() => {
    delete (globalThis as unknown as { chrome?: unknown }).chrome;
  });

  it("scans the page and SENDS the detected torrents to the background", async () => {
    document.body.innerHTML = `
      <a id="m-a" href="${MAGNET_A}">Ubuntu</a>
      <p>And another one as text: ${MAGNET_B} cheers</p>
      <a href="https://example.org/normal.html">a normal non-torrent link here</a>
    `;

    const controller = await initContentScript({ autoScan: true });

    // The real orchestrator found BOTH magnets (link + text scanners).
    const detected = controller.orchestrator.getDetectedTorrents();
    const infohashes = detected.map((t) => t.magnet?.infohash).filter(Boolean);
    expect(infohashes).toContain(INFOHASH_A);
    expect(infohashes).toContain(INFOHASH_B);

    // USER-OBSERVABLE: a scan-result message was sent up to the background, and
    // it carries the detected items (not an empty set, not "just a status code").
    const sent = scanResultMessages(fake);
    expect(sent.length).toBeGreaterThanOrEqual(1);

    const lastResult = sent[sent.length - 1]?.payload?.result as
      | { items?: ReadonlyArray<{ magnet?: { infohash?: string } | null }> }
      | undefined;
    expect(lastResult).toBeTruthy();
    const sentInfohashes = (lastResult?.items ?? [])
      .map((it) => it.magnet?.infohash)
      .filter(Boolean);
    expect(sentInfohashes).toContain(INFOHASH_A);
    expect(sentInfohashes).toContain(INFOHASH_B);

    controller.cleanup();
  });

  it("a `scan-now` (rescan) message from background re-scans and re-reports the grown set", async () => {
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;

    const controller = await initContentScript({ autoScan: true });

    // First scan saw only MAGNET_A.
    expect(
      controller.orchestrator
        .getDetectedTorrents()
        .map((t) => t.magnet?.infohash),
    ).toContain(INFOHASH_A);
    const sendsBefore = fake.sendMessage.mock.calls.length;

    // A new magnet appears on the page (e.g. SPA navigation) AFTER the first scan.
    const anchor = document.createElement("a");
    anchor.setAttribute("href", MAGNET_B);
    anchor.textContent = "Debian";
    document.body.appendChild(anchor);

    // Background asks the content script to rescan.
    const response = await fake.dispatch({ type: "scan-now" });
    expect(response).toEqual({ success: true });

    // The rescan picked up the NEW magnet too.
    const after = controller.orchestrator
      .getDetectedTorrents()
      .map((t) => t.magnet?.infohash);
    expect(after).toContain(INFOHASH_A);
    expect(after).toContain(INFOHASH_B);

    // And it reported again (the grown set was sent up).
    expect(fake.sendMessage.mock.calls.length).toBeGreaterThan(sendsBefore);
    const sent = scanResultMessages(fake);
    const lastResult = sent[sent.length - 1]?.payload?.result as
      | { items?: ReadonlyArray<{ magnet?: { infohash?: string } | null }> }
      | undefined;
    const sentInfohashes = (lastResult?.items ?? [])
      .map((it) => it.magnet?.infohash)
      .filter(Boolean);
    expect(sentInfohashes).toContain(INFOHASH_B);

    controller.cleanup();
  });

  it("answers `get-detected` from the live orchestrator set", async () => {
    document.body.innerHTML = `<a href="${MAGNET_A}">Ubuntu</a>`;
    const controller = await initContentScript({ autoScan: true });

    const response = (await fake.dispatch({ type: "get-detected" })) as {
      success: boolean;
      torrents: Array<{ id: string }>;
    };
    expect(response.success).toBe(true);
    expect(response.torrents.length).toBe(1);

    controller.cleanup();
  });

  it("unknown message types are rejected (not silently swallowed)", async () => {
    const controller = await initContentScript({ autoScan: true });
    const response = (await fake.dispatch({ type: "not-a-real-type" })) as {
      success: boolean;
      error?: string;
    };
    expect(response.success).toBe(false);
    expect(response.error).toContain("not-a-real-type");
    controller.cleanup();
  });
});

describe("content/highlight — HighlightManager adds and removes a DOM marker", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("adds a badge marker into the detected magnet anchor and removes it on toggle-off", () => {
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const anchor = document.getElementById("m-a") as HTMLAnchorElement;
    expect(anchor.querySelector(".bobalink-badge")).toBeNull();

    const events = new TypedEventEmitter();
    const manager = new HighlightManager(events);

    // Simulate the orchestrator announcing a detection for this magnet.
    events.emit("torrent-detected", {
      id: "id-a",
      type: "magnet",
      displayName: "Ubuntu 24.04 LTS",
      url: MAGNET_A,
    });

    // USER-OBSERVABLE: a marker element now lives inside the anchor.
    const badge = anchor.querySelector(".bobalink-badge");
    expect(badge).not.toBeNull();
    expect(badge?.textContent ?? "").toContain("MAGNET");
    expect(document.querySelectorAll(".bobalink-badge").length).toBe(1);

    // Toggle highlighting OFF — the marker must be cleaned up.
    manager.setEnabled(false);
    expect(anchor.querySelector(".bobalink-badge")).toBeNull();
    expect(document.querySelectorAll(".bobalink-badge").length).toBe(0);

    manager.destroy();
  });

  it("does not add a marker when highlighting is disabled from the start", () => {
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const events = new TypedEventEmitter();
    const manager = new HighlightManager(events, { enabled: false });

    events.emit("torrent-detected", {
      id: "id-a",
      type: "magnet",
      displayName: "Ubuntu 24.04 LTS",
      url: MAGNET_A,
    });

    expect(document.querySelectorAll(".bobalink-badge").length).toBe(0);
    manager.destroy();
  });

  it("clearAllHighlights removes every marker and destroy() unsubscribes", () => {
    document.body.innerHTML = `
      <a id="m-a" href="${MAGNET_A}">Ubuntu</a>
      <a id="m-b" href="${MAGNET_B}">Debian</a>
    `;
    const events = new TypedEventEmitter();
    const manager = new HighlightManager(events);

    events.emit("torrent-detected", {
      id: "id-a",
      type: "magnet",
      displayName: "Ubuntu",
      url: MAGNET_A,
    });
    events.emit("torrent-detected", {
      id: "id-b",
      type: "magnet",
      displayName: "Debian",
      url: MAGNET_B,
    });
    expect(document.querySelectorAll(".bobalink-badge").length).toBe(2);

    manager.clearAllHighlights();
    expect(document.querySelectorAll(".bobalink-badge").length).toBe(0);

    // After destroy, further events do nothing (listeners removed).
    manager.destroy();
    events.emit("torrent-detected", {
      id: "id-a",
      type: "magnet",
      displayName: "Ubuntu",
      url: MAGNET_A,
    });
    expect(document.querySelectorAll(".bobalink-badge").length).toBe(0);
  });
});
