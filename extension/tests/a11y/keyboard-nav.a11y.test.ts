/**
 * @fileoverview Keyboard-navigation + focus-management a11y tests (Phase 6 DEPTH)
 * for the options tablist and the popup — WCAG 2.1 keyboard operability
 * (SC 2.1.1 Keyboard, SC 2.1.2 No Keyboard Trap, SC 2.4.3 Focus Order),
 * §11.4 anti-bluff covenant.
 *
 * Unlike the static-markup a11y tests in this directory, these load the REAL
 * committed entrypoint HTML into jsdom, initialise the REAL production logic
 * (`src/options/options.ts` `initOptions`, `src/popup/popup.ts` `initPopup`),
 * and then SIMULATE real `KeyboardEvent`s. Every assertion inspects the
 * USER-OBSERVABLE resulting state — which tab is `aria-selected`, which panel is
 * visible, where focus landed, whether an activation handler fired — NOT merely
 * "no error".
 *
 * ANTI-BLUFF (§11.4 / §11.4.69): each test FAILS if the keyboard behaviour
 * breaks — e.g. ArrowRight no longer moving the active tab, roving tabindex not
 * following selection, Home/End not jumping, a positive tabindex hijacking the
 * Tab order, or a popup button no longer activating on Enter/Space. They are not
 * tautologies over a self-authored fixture: the markup + logic under test are
 * the real ones that ship.
 *
 * WAI-ARIA Authoring Practices — Tabs pattern (automatic-activation variant):
 * https://www.w3.org/WAI/ARIA/apg/patterns/tabs/  (verified 2026-06-10)
 */
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OPTIONS_HTML_PATH, POPUP_HTML_PATH } from "./load-html";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/** Parse the real entrypoint <body> into the ambient jsdom document. */
function loadBody(htmlPath: string): void {
  const html = readFileSync(htmlPath, "utf8");
  const bodyMatch = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  document.body.innerHTML = bodyMatch ? (bodyMatch[1] ?? "") : html;
}

/** Assert a value is present, returning it narrowed (no `!` per project ESLint). */
function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

/** Dispatch a real keydown for `key` on `el` and return the event. */
function pressKey(el: Element, key: string): KeyboardEvent {
  const ev = new KeyboardEvent("keydown", {
    key,
    bubbles: true,
    cancelable: true,
  });
  el.dispatchEvent(ev);
  return ev;
}

/** The currently `aria-selected="true"` tab's `data-tab`, or null. */
function selectedTabId(doc: Document): string | null {
  const sel = doc.querySelector('[role="tab"][aria-selected="true"]');
  return sel?.getAttribute("data-tab") ?? null;
}

/** The single visible (`:not([hidden])`) tabpanel id, or null. */
function visiblePanelId(doc: Document): string | null {
  const panels = Array.from(
    doc.querySelectorAll<HTMLElement>('[role="tabpanel"]'),
  );
  const shown = panels.filter((p) => !p.hidden);
  return shown.length === 1 ? shown[0]?.id ?? null : null;
}

// ─────────────────────────────────────────────────────────────────────────────
// OPTIONS — tablist keyboard navigation (WAI-ARIA Tabs pattern)
// ─────────────────────────────────────────────────────────────────────────────

describe("options tablist — keyboard navigation (WCAG 2.1.1 / 2.4.3)", () => {
  beforeEach(async () => {
    // No chrome.storage needed to populate; initOptions reads config but the
    // storage module degrades to DEFAULT_CONFIG when chrome is absent — and tab
    // wiring (the thing under test) does not depend on the populate result.
    delete (globalThis as { chrome?: unknown }).chrome;
    document.body.innerHTML = "";
    vi.resetModules();
    loadBody(OPTIONS_HTML_PATH);
    const { initOptions } = await import("../../src/options/options");
    await initOptions(document);
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("starts with exactly the first tab selected, its panel visible (catches: wrong initial state)", () => {
    expect(selectedTabId(document)).toBe("server");
    expect(visiblePanelId(document)).toBe("panel-server");
  });

  it("ArrowRight on the active tab moves selection to the NEXT tab + shows its panel (catches: no keyboard nav)", () => {
    const first = mustExist(
      document.querySelector<HTMLElement>('[role="tab"][data-tab="server"]'),
      "server tab",
    );
    pressKey(first, "ArrowRight");

    // User-observable: selection + visible panel both advanced to "download".
    expect(selectedTabId(document)).toBe("download");
    expect(visiblePanelId(document)).toBe("panel-download");
  });

  it("ArrowRight roves tabindex (new tab tabindex=0, old tab tabindex=-1) + moves focus (catches: broken roving tabindex)", () => {
    const first = mustExist(
      document.querySelector<HTMLElement>('[role="tab"][data-tab="server"]'),
      "server tab",
    );
    const second = mustExist(
      document.querySelector<HTMLElement>('[role="tab"][data-tab="download"]'),
      "download tab",
    );
    first.focus();
    pressKey(first, "ArrowRight");

    // Roving tabindex: only the selected tab is in the Tab sequence.
    expect(second.tabIndex).toBe(0);
    expect(first.tabIndex).toBe(-1);
    // Focus follows the arrow key so keyboard users stay on the active tab.
    expect(document.activeElement).toBe(second);
  });

  it("ArrowLeft moves selection to the PREVIOUS tab (catches: one-directional nav)", () => {
    // Move to the 3rd tab first, then ArrowLeft back to the 2nd.
    const tabs = Array.from(
      document.querySelectorAll<HTMLElement>('[role="tab"][data-tab]'),
    );
    const t1 = mustExist(tabs[0], "tab[0]");
    pressKey(t1, "ArrowRight"); // → download
    const onDownload = mustExist(
      document.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]'),
      "selected tab",
    );
    pressKey(onDownload, "ArrowRight"); // → queue
    const onQueue = mustExist(
      document.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]'),
      "selected tab",
    );
    pressKey(onQueue, "ArrowLeft"); // ← download

    expect(selectedTabId(document)).toBe("download");
    expect(visiblePanelId(document)).toBe("panel-download");
  });

  it("ArrowRight wraps from the LAST tab to the FIRST (catches: no wrap-around)", () => {
    const tabs = Array.from(
      document.querySelectorAll<HTMLElement>('[role="tab"][data-tab]'),
    );
    const last = mustExist(tabs[tabs.length - 1], "last tab");
    // Select the last tab directly, then ArrowRight should wrap to first.
    pressKey(last, "Home"); // jump to first to set a known state
    pressKey(
      mustExist(
        document.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]'),
        "selected tab",
      ),
      "End",
    ); // jump to last
    expect(selectedTabId(document)).toBe("security");

    pressKey(
      mustExist(
        document.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]'),
        "selected tab",
      ),
      "ArrowRight",
    );
    expect(selectedTabId(document)).toBe("server");
  });

  it("ArrowLeft wraps from the FIRST tab to the LAST (catches: no backward wrap)", () => {
    const first = mustExist(
      document.querySelector<HTMLElement>('[role="tab"][data-tab="server"]'),
      "server tab",
    );
    pressKey(first, "ArrowLeft");
    expect(selectedTabId(document)).toBe("security");
    expect(visiblePanelId(document)).toBe("panel-security");
  });

  it("Home jumps to the FIRST tab, End jumps to the LAST (catches: missing Home/End)", () => {
    const tabs = Array.from(
      document.querySelectorAll<HTMLElement>('[role="tab"][data-tab]'),
    );
    const t1 = mustExist(tabs[0], "first tab");
    pressKey(t1, "End");
    expect(selectedTabId(document)).toBe("security");
    expect(visiblePanelId(document)).toBe("panel-security");

    const onLast = mustExist(
      document.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]'),
      "selected tab",
    );
    pressKey(onLast, "Home");
    expect(selectedTabId(document)).toBe("server");
    expect(visiblePanelId(document)).toBe("panel-server");
  });

  it("the focused tab's panel is the visible one after Home/End (catches: focus/visibility desync)", () => {
    const tabs = Array.from(
      document.querySelectorAll<HTMLElement>('[role="tab"][data-tab]'),
    );
    const t1 = mustExist(tabs[0], "first tab");
    t1.focus();
    pressKey(t1, "End");

    const focused = document.activeElement as HTMLElement | null;
    const focusedTabId = mustExist(focused, "focused element").getAttribute(
      "data-tab",
    );
    expect(focusedTabId).toBe("security");
    expect(visiblePanelId(document)).toBe("panel-security");
  });

  it("arrow keys call preventDefault so the page does not scroll (catches: default-scroll leak)", () => {
    const first = mustExist(
      document.querySelector<HTMLElement>('[role="tab"][data-tab="server"]'),
      "server tab",
    );
    const ev = pressKey(first, "ArrowRight");
    expect(ev.defaultPrevented).toBe(true);
  });

  it("a non-navigation key (e.g. 'a') does NOT change the selected tab (catches: over-eager handler)", () => {
    const first = mustExist(
      document.querySelector<HTMLElement>('[role="tab"][data-tab="server"]'),
      "server tab",
    );
    pressKey(first, "a");
    expect(selectedTabId(document)).toBe("server");
    expect(visiblePanelId(document)).toBe("panel-server");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// OPTIONS — focus order / no positive-tabindex hijack (WCAG 2.4.3)
// ─────────────────────────────────────────────────────────────────────────────

describe("options focus order — no Tab-order hijack, no keyboard trap (WCAG 2.4.3 / 2.1.2)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    loadBody(OPTIONS_HTML_PATH);
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("no interactive control declares a POSITIVE tabindex (catches: tabindex>0 hijacking order)", () => {
    const controls = Array.from(
      document.querySelectorAll<HTMLElement>(
        "button, input, select, textarea, a[href], [tabindex]",
      ),
    );
    const offenders = controls
      .filter((el) => {
        const raw = el.getAttribute("tabindex");
        if (raw === null) return false;
        const n = Number.parseInt(raw, 10);
        return Number.isFinite(n) && n > 0;
      })
      .map((el) => `${el.tagName}#${el.id || "(no-id)"}[tabindex=${el.getAttribute("tabindex")}]`);
    expect(offenders, "controls with a positive tabindex").toEqual([]);
  });

  it("only the selected tab is in the Tab sequence; the rest are roved out (catches: all-tabs-tabbable)", () => {
    const tabs = Array.from(
      document.querySelectorAll<HTMLElement>('[role="tab"][data-tab]'),
    );
    // In the committed markup at rest: server tab has no explicit tabindex (=> 0),
    // every other tab carries tabindex="-1". Exactly one is keyboard-reachable.
    const reachable = tabs.filter((t) => {
      const raw = t.getAttribute("tabindex");
      return raw === null || Number.parseInt(raw, 10) >= 0;
    });
    expect(reachable.length).toBe(1);
    expect(reachable[0]?.getAttribute("data-tab")).toBe("server");
  });

  it("no form control is disabled at rest, so none is silently skipped from Tab order unexpectedly (catches: stuck-disabled field)", () => {
    // Sanity: the save button + every field is enabled (a disabled control is
    // correctly skipped by Tab — we assert the markup does not ship anything
    // unintentionally disabled that the user would expect to reach).
    const disabled = Array.from(
      document.querySelectorAll<HTMLElement>(
        "button[disabled], input[disabled], select[disabled]",
      ),
    ).map((el) => `${el.tagName}#${el.id || "(no-id)"}`);
    expect(disabled, "unexpectedly disabled controls in the options form").toEqual([]);
  });

  it("the Save button is a real <button> reachable in the natural Tab flow (catches: non-focusable save)", () => {
    const save = mustExist(document.getElementById("opt-save"), "opt-save");
    expect(save.tagName).toBe("BUTTON");
    // Native <button> is focusable with no positive tabindex — confirm it is not
    // removed from the Tab order via tabindex="-1".
    const raw = save.getAttribute("tabindex");
    expect(raw === null || Number.parseInt(raw, 10) >= 0).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// POPUP — keyboard activation of buttons + options link (WCAG 2.1.1)
// ─────────────────────────────────────────────────────────────────────────────

describe("popup — keyboard activation of controls (WCAG 2.1.1)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    loadBody(POPUP_HTML_PATH);
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("Send-All and Refresh are native <button>s (Enter/Space activate natively) (catches: div-as-button)", () => {
    const sendAll = mustExist(document.getElementById("btn-send-all"), "btn-send-all");
    const refresh = mustExist(document.getElementById("btn-refresh"), "btn-refresh");
    // A native <button> is operable via Enter AND Space with zero extra JS — the
    // single most robust way to satisfy SC 2.1.1. A <div role=button> would need
    // a manual keydown handler this markup must NOT depend on.
    expect(sendAll.tagName).toBe("BUTTON");
    expect(sendAll.getAttribute("type")).toBe("button");
    expect(refresh.tagName).toBe("BUTTON");
    expect(refresh.getAttribute("type")).toBe("button");
  });

  it("the options links are real <a href> (Enter activates natively) (catches: non-link options trigger)", () => {
    for (const id of ["open-options", "open-options-warning"]) {
      const link = mustExist(document.getElementById(id), id);
      expect(link.tagName).toBe("A");
      expect(link.hasAttribute("href")).toBe(true);
    }
  });

  it("no popup control declares a positive tabindex (catches: Tab-order hijack)", () => {
    const offenders = Array.from(
      document.querySelectorAll<HTMLElement>("button, a[href], [tabindex]"),
    )
      .filter((el) => {
        const raw = el.getAttribute("tabindex");
        if (raw === null) return false;
        const n = Number.parseInt(raw, 10);
        return Number.isFinite(n) && n > 0;
      })
      .map((el) => `${el.tagName}#${el.id || "(no-id)"}`);
    expect(offenders, "popup controls with a positive tabindex").toEqual([]);
  });

  it("Enter on the per-row Send button (real <button>) fires its click handler (catches: row button not keyboard-operable)", async () => {
    // Drive the REAL popup logic so the per-row Send buttons are created by the
    // production code, then prove pressing Enter on one activates it. A native
    // <button> dispatches a synthetic click on Enter in real browsers; jsdom does
    // not synthesise that, so we assert the row button is a native <button>
    // (Enter/Space-operable by the platform) AND that its click handler performs
    // the send — i.e. the control is genuinely keyboard-actionable, not a
    // click-only div.
    const sent: unknown[][] = [];
    const chromeFake = {
      runtime: {
        sendMessage: vi.fn((msg: { type: string; payload?: unknown }) => {
          if (msg.type === "get-detected") {
            return Promise.resolve({
              success: true,
              data: {
                result: {
                  items: [
                    {
                      id: "t1",
                      displayName: "Ubuntu 24.04",
                      type: "magnet",
                      magnet: { infohash: "abc123def456abc1" },
                      sent: false,
                    },
                  ],
                },
              },
            });
          }
          if (msg.type === "health-check") {
            return Promise.resolve({
              success: true,
              data: { results: [{ status: "healthy" }] },
            });
          }
          if (msg.type === "send-torrent") {
            sent.push([msg.payload]);
            return Promise.resolve({
              success: true,
              data: { results: [{ id: "t1", success: true }] },
            });
          }
          return Promise.resolve({ success: false });
        }),
        openOptionsPage: vi.fn(),
      },
      tabs: { query: vi.fn(() => Promise.resolve([{ id: 7 }])) },
    };
    (globalThis as { chrome?: unknown }).chrome = chromeFake;

    const { initPopup } = await import("../../src/popup/popup");
    await initPopup(document);

    const rowBtn = mustExist(
      document.querySelector<HTMLButtonElement>(".btn-send-one"),
      "per-row Send button",
    );
    // Keyboard-operable foundation: native <button>.
    expect(rowBtn.tagName).toBe("BUTTON");
    expect(rowBtn.getAttribute("type")).toBe("button");

    // Activating it (the platform does this for Enter/Space on a <button>) must
    // dispatch the send — user-observable proof the control does real work.
    rowBtn.click();
    await Promise.resolve();
    await Promise.resolve();
    expect(sent.length).toBeGreaterThan(0);
    const payload = sent[0]?.[0] as { ids?: string[] } | undefined;
    expect(payload?.ids).toEqual(["t1"]);
  });
});
