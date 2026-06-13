/**
 * @fileoverview Partial Send-All failure state-rendering tests for the REAL
 * popup module (§11.4 anti-bluff).
 *
 * Sibling to `popup.test.ts` (basic render / all-success dispatch / Connected /
 * Disconnected) and `popup-ux.test.ts` (XSS-safe render, in-flight disable,
 * all-success sent flip, all-sent Send-All disable, long-name containment).
 *
 * GENUINE GAP this file closes: neither sibling exercises a PARTIAL Send-All
 * failure — a single dispatch where the background reports SOME ids succeeded
 * and SOME failed. The `popup-ux.test.ts` harness even declares a per-id
 * `sendOk` predicate but NO test ever passes one, so every existing send path
 * resolves all-success. The mixed outcome drives distinct production code in
 * `sendTorrents()` (popup.ts) that nothing asserts:
 *
 *   - only the SUCCEEDED ids flip to the visual sent state; the FAILED ids stay
 *     unsent (no `torrent-sent` class, no "✓ Sent" badge, Send button still
 *     enabled + labelled "Send") so the user can retry exactly the failed rows;
 *   - the `failed = ids.length - ok.size` branch announces the failure count
 *     into the `#action-status` live region ("N torrent(s) failed to send"),
 *     NOT the success message;
 *   - after a partial failure Send-All is RE-ENABLED (because at least one row
 *     is still unsent) so the user can retry, whereas a full success disables it;
 *   - a TOTAL failure (zero ids succeed) flips no row and announces the failure.
 *
 * Every assertion inspects user-observable DOM (classes / textContent /
 * disabled-state / live-region text) and is anti-bluff: it fails against a
 * no-op or all-success stub of the partial-failure path. The real
 * `src/entrypoints/popup/index.html` body + the real exported `initPopup()` are
 * driven — no popup logic is re-implemented in the test.
 *
 * @module tests/unit/popup-states.test
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

interface SendMessageSpy {
  (msg: { type: string; payload?: Record<string, unknown> }): Promise<unknown>;
  calls: Array<{ type: string; payload?: Record<string, unknown> }>;
}

/**
 * Install a chrome stub whose send-torrent reply marks each id per `sendOk`,
 * so a test can model a PARTIAL failure (some ids `success:true`, some
 * `success:false`) using the REAL background SendOutcome shape
 * (`{ id, success, displayName, error }` — flat, NOT nested under `torrent`).
 */
function installChrome(opts: {
  detected: DetectedTorrent[];
  health?: string;
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
        case "send-torrent":
          return Promise.resolve({
            success: true,
            data: {
              results: (msg.payload?.ids as string[]).map((id) => ({
                id,
                success: ok(id),
                displayName: id,
                error: ok(id) ? null : "boom",
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

/** Find the rendered row whose dataset.id matches. */
function rowFor(id: string): HTMLElement {
  return mustExist(
    document.querySelector<HTMLElement>(`.torrent-item[data-id="${id}"]`),
    `.torrent-item[data-id="${id}"]`,
  );
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
// Partial Send-All failure — mixed Sent / Failed rows
// ─────────────────────────────────────────────────────────────────────────────

describe("popup states — partial Send-All failure", () => {
  it("flips only the succeeded row to sent and leaves the failed row retryable", async () => {
    // Regression: a Send-All where id-a succeeds and id-b fails MUST flip ONLY
    // id-a into the visual sent state; id-b must stay unsent and retryable. A
    // stub that swept BOTH ids sent (the only path the existing tests exercise)
    // would wrongly pass — this asserts the per-id divergence.
    installChrome({
      detected: [
        makeMagnetTorrent("id-a", "Ubuntu", INFOHASH_A),
        makeMagnetTorrent("id-b", "Debian", INFOHASH_B),
      ],
      sendOk: (id) => id === "id-a",
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const sendAll = mustExist(
      document.getElementById("btn-send-all"),
      "#btn-send-all",
    ) as HTMLButtonElement;
    sendAll.click();
    await flush();

    // Succeeded row id-a: sent visual state, disabled "Sent" button, badge.
    const aRow = rowFor("id-a");
    expect(aRow.classList.contains("torrent-sent")).toBe(true);
    expect(aRow.querySelector(".torrent-status")?.textContent).toContain("Sent");
    const aBtn = mustExist(
      aRow.querySelector<HTMLButtonElement>(".btn-send-one"),
      "id-a .btn-send-one",
    );
    expect(aBtn.disabled).toBe(true);
    expect(aBtn.textContent).toBe("Sent");

    // Failed row id-b: still unsent, NO sent badge, Send button enabled to retry.
    const bRow = rowFor("id-b");
    expect(bRow.classList.contains("torrent-sent")).toBe(false);
    expect(bRow.querySelector(".torrent-status")).toBeNull();
    const bBtn = mustExist(
      bRow.querySelector<HTMLButtonElement>(".btn-send-one"),
      "id-b .btn-send-one",
    );
    expect(bBtn.disabled).toBe(false);
    expect(bBtn.textContent).toBe("Send");
  });

  it("announces the failure count to the action-status live region on a partial failure", async () => {
    // Regression: the `failed = ids.length - ok.size` branch must announce
    // "1 torrent failed to send", NOT the "Sent N" success message. A stub that
    // always reported all-success (existing tests) never reaches this branch.
    installChrome({
      detected: [
        makeMagnetTorrent("id-a", "Ubuntu", INFOHASH_A),
        makeMagnetTorrent("id-b", "Debian", INFOHASH_B),
      ],
      sendOk: (id) => id === "id-a",
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    (
      mustExist(document.getElementById("btn-send-all"), "#btn-send-all") as
        HTMLButtonElement
    ).click();
    await flush();

    const status = mustExist(
      document.getElementById("action-status"),
      "#action-status",
    );
    const text = (status.textContent ?? "").toLowerCase();
    expect(text).toContain("fail");
    expect(text).toContain("1");
    // It must NOT be the success message.
    expect(text).not.toContain("sent 1");
  });

  it("re-enables Send-All after a partial failure so the failed row can be retried", async () => {
    // Regression: render() sets sendAll.disabled = current.every(t => t.sent).
    // After a partial failure at least one row is unsent, so Send-All MUST be
    // re-enabled (an all-success path would disable it). Guards against a stub
    // that left the button stuck-disabled after dispatch.
    installChrome({
      detected: [
        makeMagnetTorrent("id-a", "Ubuntu", INFOHASH_A),
        makeMagnetTorrent("id-b", "Debian", INFOHASH_B),
      ],
      sendOk: (id) => id === "id-a",
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const sendAll = mustExist(
      document.getElementById("btn-send-all"),
      "#btn-send-all",
    ) as HTMLButtonElement;
    expect(sendAll.disabled).toBe(false);
    sendAll.click();
    await flush();

    expect(sendAll.disabled).toBe(false);
  });

  it("flips no row and announces failure when every id in Send-All fails", async () => {
    // Regression: a TOTAL failure (ok.size === 0) must flip NO row sent and must
    // announce the failure, not silently succeed. The success-path stub the
    // existing tests use cannot reach this state.
    installChrome({
      detected: [
        makeMagnetTorrent("id-a", "Ubuntu", INFOHASH_A),
        makeMagnetTorrent("id-b", "Debian", INFOHASH_B),
      ],
      sendOk: () => false,
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    (
      mustExist(document.getElementById("btn-send-all"), "#btn-send-all") as
        HTMLButtonElement
    ).click();
    await flush();

    // No row flipped to sent.
    expect(document.querySelectorAll(".torrent-item.torrent-sent").length).toBe(0);
    expect(rowFor("id-a").classList.contains("torrent-sent")).toBe(false);
    expect(rowFor("id-b").classList.contains("torrent-sent")).toBe(false);

    // Both Send buttons remain enabled to retry.
    for (const id of ["id-a", "id-b"]) {
      const btn = mustExist(
        rowFor(id).querySelector<HTMLButtonElement>(".btn-send-one"),
        `${id} .btn-send-one`,
      );
      expect(btn.disabled).toBe(false);
    }

    // The live region reports the failure (2 failed), not a success.
    const status = mustExist(
      document.getElementById("action-status"),
      "#action-status",
    );
    const text = (status.textContent ?? "").toLowerCase();
    expect(text).toContain("fail");
    expect(text).toContain("2");
  });

  it("a single-row Send that fails leaves the row retryable and announces failure", async () => {
    // Regression: the per-row Send path (sendTorrents([id], btn)) on failure must
    // re-enable the row button (catch/else keeps it usable) and announce the
    // failure — distinct from the all-success per-row flip the siblings cover.
    installChrome({
      detected: [makeMagnetTorrent("id-a", "Ubuntu", INFOHASH_A)],
      sendOk: () => false,
    });
    const { initPopup } = await loadPopupModule();
    await initPopup(document);

    const row = rowFor("id-a");
    const btn = mustExist(
      row.querySelector<HTMLButtonElement>(".btn-send-one"),
      "id-a .btn-send-one",
    );
    btn.click();
    await flush();

    // Row not flipped sent; still labelled "Send" (not "Sent").
    expect(rowFor("id-a").classList.contains("torrent-sent")).toBe(false);
    const postBtn = mustExist(
      rowFor("id-a").querySelector<HTMLButtonElement>(".btn-send-one"),
      "id-a .btn-send-one (post)",
    );
    expect(postBtn.textContent).toBe("Send");

    const status = mustExist(
      document.getElementById("action-status"),
      "#action-status",
    );
    expect((status.textContent ?? "").toLowerCase()).toContain("fail");
  });
});
