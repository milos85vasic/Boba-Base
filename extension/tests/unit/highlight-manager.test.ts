/**
 * @fileoverview Anti-bluff unit tests for the content-script HIGHLIGHT MANAGER
 * (`src/content/highlight.ts`) — its OWN behaviour + edge cases.
 *
 * These tests import the PRODUCTION {@link HighlightManager} and drive it against
 * a REAL jsdom DOM via a REAL {@link TypedEventEmitter}, exactly as the
 * orchestrator drives it in production: the manager subscribes to
 * `torrent-detected` events and marks the matching anchors. Every assertion is on
 * USER-OBSERVABLE DOM state (badge wrapper nodes, marker classes, anchor child
 * structure, anchor `href`) — never "no error".
 *
 * SCOPE — this file deliberately covers the gaps NOT exercised by the existing
 * suites, to avoid duplication:
 *   - `tests/integration/content-background.test.ts` only flips the manager's
 *     `isEnabled()` flag through the content controller handle — it asserts NO
 *     DOM marker state.
 *   - `tests/unit/content.test.ts` covers ONLY the BADGE style: basic
 *     add-on-detect + remove-on-toggle-off, no-marker-when-disabled, and
 *     `clearAllHighlights`/`destroy`.
 * The NEW behaviour proven here: leak-free structural restore on disable;
 * idempotency (double-detect / enable-twice / disable-when-off); re-enable
 * re-marks the detected set; re-highlight marks links added AFTER first scan;
 * the marker never alters the anchor `href`; and the `border` + `glow`
 * class-based styles mark and unmark correctly.
 *
 * Each test FAILS against a no-op stub of the behaviour it pins — the inline
 * "Regression:" note on every test states the exact defect it catches.
 *
 * §11.4.50: no absolute wall-clock thresholds — every assertion is a
 * deterministic DOM-state equality, identical on every run.
 *
 * @module tests/unit/highlight-manager
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { HighlightManager } from "../../src/content/highlight";
import { TypedEventEmitter } from "../../src/shared/events";

// ─────────────────────────────────────────────────────────────────────────────
// jsdom shim: `CSS.escape`.
//
// The production `.torrent`-file highlight path (`findElementsByUrl`) calls
// `CSS.escape(url)` to build a `a[href="…"]` selector — a STANDARD browser API
// present in every Chrome/MV3 content-script context the extension runs in. The
// Vitest jsdom environment does NOT provide `globalThis.CSS`, so without this
// shim `CSS.escape` throws `ReferenceError`, which the manager's own try/catch
// swallows — masking the real code path and making the .torrent anchor silently
// un-highlighted in the test ONLY. This is a jsdom gap, not a product defect:
// real Chrome has `CSS.escape`. We install the spec algorithm
// (https://drafts.csswg.org/cssom/#serialize-an-identifier) so the test
// exercises the SAME code path that runs in production. The magnet path does not
// use CSS.escape, so the already-shipped magnet tests are unaffected by this.
// ─────────────────────────────────────────────────────────────────────────────
if (typeof (globalThis as { CSS?: unknown }).CSS === "undefined") {
  (globalThis as { CSS: { escape(value: string): string } }).CSS = {
    escape(value: string): string {
      // Minimal CSS.escape per the CSSOM spec, sufficient for URL identifiers.
      const str = String(value);
      let result = "";
      for (let i = 0; i < str.length; i++) {
        const ch = str.charAt(i);
        const code = str.charCodeAt(i);
        if (code === 0x0000) {
          result += "�";
        } else if (
          (code >= 0x0001 && code <= 0x001f) ||
          code === 0x007f ||
          (i === 0 && code >= 0x0030 && code <= 0x0039)
        ) {
          result += "\\" + code.toString(16) + " ";
        } else if (
          code >= 0x0080 ||
          ch === "-" ||
          ch === "_" ||
          (code >= 0x0030 && code <= 0x0039) ||
          (code >= 0x0041 && code <= 0x005a) ||
          (code >= 0x0061 && code <= 0x007a)
        ) {
          result += ch;
        } else {
          result += "\\" + ch;
        }
      }
      return result;
    },
  };
}

// Real-shaped fixtures (40-hex infohash magnets + a `.torrent` file URL).
const INFOHASH_A = "0123456789abcdef0123456789abcdef01234567";
const INFOHASH_B = "fedcba9876543210fedcba9876543210fedcba98";
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu%2024.04%20LTS`;
const MAGNET_B = `magnet:?xt=urn:btih:${INFOHASH_B}&dn=Debian%2012`;
const TORRENT_URL = "https://files.example.org/releases/cool-release.torrent";

const BADGE = ".bobalink-badge";
const BORDER = "bobalink-border";
const GLOW = "bobalink-glow";

/** Emit the orchestrator's detection event for a magnet/.torrent URL. */
function detect(
  events: TypedEventEmitter,
  url: string,
  type: "magnet" | "torrent-file" = "magnet",
): void {
  events.emit("torrent-detected", {
    id: `id-${url}`,
    type,
    displayName: "Fixture",
    url,
  });
}

let managers: HighlightManager[] = [];

/** Track managers so afterEach can destroy them (removes listeners + markers). */
function makeManager(
  events: TypedEventEmitter,
  options?: { style?: "badge" | "border" | "glow"; enabled?: boolean },
): HighlightManager {
  const m = new HighlightManager(events, options ?? {});
  managers.push(m);
  return m;
}

beforeEach(() => {
  document.body.innerHTML = "";
  managers = [];
});

afterEach(() => {
  for (const m of managers) m.destroy();
  managers = [];
  document.body.innerHTML = "";
});

// ─────────────────────────────────────────────────────────────────────────────
// 1) Enabling marks EXACTLY the detected links (badge wrapper on those anchors)
// ─────────────────────────────────────────────────────────────────────────────

describe("HighlightManager — enabling marks exactly the detected links", () => {
  it("adds the badge wrapper ONLY to the detected anchor, leaving undetected anchors untouched", () => {
    // Regression: a manager that marked ALL anchors (or the wrong one) instead of
    // the detected-URL match would put a badge on the plain link too. We assert
    // the badge is inside the magnet anchor and the plain anchor has none.
    document.body.innerHTML = `
      <a id="m-a" href="${MAGNET_A}">Ubuntu</a>
      <a id="plain" href="https://example.org/page.html">Not a torrent</a>
    `;
    const events = new TypedEventEmitter();
    makeManager(events);

    detect(events, MAGNET_A);

    const detectedAnchor = document.getElementById("m-a") as HTMLAnchorElement;
    const plainAnchor = document.getElementById("plain") as HTMLAnchorElement;

    expect(detectedAnchor.querySelector(BADGE)).not.toBeNull();
    expect(plainAnchor.querySelector(BADGE)).toBeNull();
    // Exactly one marker on the whole page → the detected set, nothing extra.
    expect(document.querySelectorAll(BADGE).length).toBe(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2) Disabling REMOVES every marker and restores the anchor's prior structure
// ─────────────────────────────────────────────────────────────────────────────

describe("HighlightManager — disabling leaves no orphan marker (structural restore)", () => {
  it("setEnabled(false) removes the badge so the detected anchor's children return to their pre-highlight state", () => {
    // Regression: a clear() that detached the badge from the manager's bookkeeping
    // but left the wrapper element in the DOM (a leak) would keep an orphan
    // `.bobalink-badge` child on the anchor. We snapshot the anchor's child node
    // count BEFORE highlighting and assert it is restored EXACTLY after disable —
    // no leftover wrapper, and no spurious extra nodes either.
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const anchor = document.getElementById("m-a") as HTMLAnchorElement;
    const childCountBefore = anchor.childNodes.length;

    const events = new TypedEventEmitter();
    const manager = makeManager(events);

    detect(events, MAGNET_A);
    // Highlighting added exactly one wrapper child.
    expect(anchor.childNodes.length).toBe(childCountBefore + 1);
    expect(anchor.querySelector(BADGE)).not.toBeNull();

    manager.setEnabled(false);

    // USER-OBSERVABLE: the anchor's children are back to the original count and
    // no badge wrapper survives anywhere on the page.
    expect(anchor.childNodes.length).toBe(childCountBefore);
    expect(anchor.querySelector(BADGE)).toBeNull();
    expect(document.querySelectorAll(BADGE).length).toBe(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3) Idempotency — double-detect / enable-twice / disable-when-off
// ─────────────────────────────────────────────────────────────────────────────

describe("HighlightManager — idempotent marking and toggling", () => {
  it("two detections of the SAME url do not double-wrap the anchor", () => {
    // Regression: missing the `highlighted.has(element)` guard would append a
    // SECOND badge wrapper on the re-detection, so the user would see two chips on
    // one link. We fire the same detection twice and assert exactly one wrapper.
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const anchor = document.getElementById("m-a") as HTMLAnchorElement;
    const events = new TypedEventEmitter();
    makeManager(events);

    detect(events, MAGNET_A);
    detect(events, MAGNET_A);

    expect(anchor.querySelectorAll(BADGE).length).toBe(1);
    expect(document.querySelectorAll(BADGE).length).toBe(1);
  });

  it("setEnabled(true) when already enabled does NOT re-run marking (no duplicate wrapper)", () => {
    // Regression: a setEnabled that ignored the `this.enabled === enabled` no-op
    // guard would, on a redundant enable, re-mark the detected set and append a
    // duplicate badge. We mark once, then call setEnabled(true) again and assert
    // the wrapper count is unchanged.
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const anchor = document.getElementById("m-a") as HTMLAnchorElement;
    const events = new TypedEventEmitter();
    const manager = makeManager(events);

    detect(events, MAGNET_A);
    expect(anchor.querySelectorAll(BADGE).length).toBe(1);

    manager.setEnabled(true); // redundant — manager already enabled
    expect(manager.isEnabled()).toBe(true);
    expect(anchor.querySelectorAll(BADGE).length).toBe(1);
  });

  it("setEnabled(false) when already disabled is a no-op (stays clear, no throw)", () => {
    // Regression: a disable path that re-ran clearAllHighlights unconditionally
    // could, in a buggy variant, perturb DOM/bookkeeping on a second disable. We
    // start disabled, detect (no marker), disable again, and assert still zero.
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const events = new TypedEventEmitter();
    const manager = makeManager(events, { enabled: false });

    detect(events, MAGNET_A);
    expect(document.querySelectorAll(BADGE).length).toBe(0);

    manager.setEnabled(false); // already off
    expect(manager.isEnabled()).toBe(false);
    expect(document.querySelectorAll(BADGE).length).toBe(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4) Re-enable re-marks the already-detected set; re-scan marks NEW links
// ─────────────────────────────────────────────────────────────────────────────

describe("HighlightManager — re-enable re-marks, and new links get marked", () => {
  it("setEnabled(false) then setEnabled(true) restores the badge on the previously-detected anchor", () => {
    // Regression: a re-enable that forgot to replay `detectedUrls` would leave the
    // page un-marked after a toggle-off→on cycle, so the user toggling highlight
    // back on would see nothing. We detect, toggle off (gone), toggle on (back).
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const anchor = document.getElementById("m-a") as HTMLAnchorElement;
    const events = new TypedEventEmitter();
    const manager = makeManager(events);

    detect(events, MAGNET_A);
    expect(anchor.querySelector(BADGE)).not.toBeNull();

    manager.setEnabled(false);
    expect(anchor.querySelector(BADGE)).toBeNull();

    manager.setEnabled(true);
    // The previously-detected magnet is re-marked from the remembered set.
    expect(anchor.querySelector(BADGE)).not.toBeNull();
    expect(document.querySelectorAll(BADGE).length).toBe(1);
  });

  it("a NEW link added to the DOM after first detection gets marked when its detection fires", () => {
    // Regression: a manager that snapshotted the anchor set once at construction
    // (rather than querying the live DOM per detection) would never mark links
    // appended later. We detect MAGNET_A, then append a SECOND anchor + detect it,
    // and assert BOTH anchors carry a badge (the new one is not missed).
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const events = new TypedEventEmitter();
    makeManager(events);

    detect(events, MAGNET_A);
    expect(document.querySelectorAll(BADGE).length).toBe(1);

    const fresh = document.createElement("a");
    fresh.id = "m-b";
    fresh.href = MAGNET_B;
    fresh.textContent = "Debian";
    document.body.appendChild(fresh);

    detect(events, MAGNET_B);

    expect(
      (document.getElementById("m-a") as HTMLAnchorElement).querySelector(BADGE),
    ).not.toBeNull();
    expect(fresh.querySelector(BADGE)).not.toBeNull();
    expect(document.querySelectorAll(BADGE).length).toBe(2);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5) The marker does NOT alter the link's href / break the anchor
// ─────────────────────────────────────────────────────────────────────────────

describe("HighlightManager — the marker preserves the anchor's href", () => {
  it("highlighting a magnet anchor leaves its href byte-for-byte unchanged (link still works)", () => {
    // Regression: a marker that rewrote/wrapped the anchor's href (or replaced the
    // anchor) would break the user's click target. We capture the href attribute
    // before and after highlighting and assert exact equality, AND that the same
    // <a> element instance still carries it.
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const anchor = document.getElementById("m-a") as HTMLAnchorElement;
    const hrefBefore = anchor.getAttribute("href");

    const events = new TypedEventEmitter();
    makeManager(events);

    detect(events, MAGNET_A);

    // The badge was added (so we are genuinely testing the post-mark state)…
    expect(anchor.querySelector(BADGE)).not.toBeNull();
    // …and the href is identical, on the same element, with the anchor intact.
    expect(anchor.getAttribute("href")).toBe(hrefBefore);
    expect(anchor.getAttribute("href")).toBe(MAGNET_A);
    expect(document.getElementById("m-a")).toBe(anchor);
  });

  it("highlighting a .torrent-file anchor preserves its href too", () => {
    // Regression: same href-integrity guarantee for the file-link path (a distinct
    // findElementsByUrl branch from the magnet path). We assert the .torrent href
    // is untouched after the badge is applied.
    document.body.innerHTML = `<a id="f" href="${TORRENT_URL}">Download</a>`;
    const anchor = document.getElementById("f") as HTMLAnchorElement;

    const events = new TypedEventEmitter();
    makeManager(events);

    detect(events, TORRENT_URL, "torrent-file");

    expect(anchor.querySelector(BADGE)).not.toBeNull();
    expect(anchor.getAttribute("href")).toBe(TORRENT_URL);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 6) The class-based styles (border / glow) mark and unmark correctly
// ─────────────────────────────────────────────────────────────────────────────

describe("HighlightManager — border/glow class styles add and remove the marker class", () => {
  it("the `border` style toggles the bobalink-border CLASS on the detected anchor (no badge wrapper)", () => {
    // Regression: the class-based styles are a separate code path from the badge
    // wrapper; a manager that only implemented `badge` would leave the class off.
    // We assert the class is added on detect and removed on disable, with NO badge
    // wrapper ever created for this style.
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const anchor = document.getElementById("m-a") as HTMLAnchorElement;
    const events = new TypedEventEmitter();
    const manager = makeManager(events, { style: "border" });

    detect(events, MAGNET_A);
    expect(anchor.classList.contains(BORDER)).toBe(true);
    expect(document.querySelectorAll(BADGE).length).toBe(0);

    manager.setEnabled(false);
    expect(anchor.classList.contains(BORDER)).toBe(false);
  });

  it("the `glow` style toggles the bobalink-glow CLASS and clearAllHighlights removes it", () => {
    // Regression: clearAllHighlights must strip the glow class, not just badge
    // nodes — otherwise the glow style would leak a permanent class on the anchor.
    // We mark with glow, assert the class, clear, and assert it is gone.
    document.body.innerHTML = `<a id="m-a" href="${MAGNET_A}">Ubuntu</a>`;
    const anchor = document.getElementById("m-a") as HTMLAnchorElement;
    const events = new TypedEventEmitter();
    const manager = makeManager(events, { style: "glow" });

    detect(events, MAGNET_A);
    expect(anchor.classList.contains(GLOW)).toBe(true);

    manager.clearAllHighlights();
    expect(anchor.classList.contains(GLOW)).toBe(false);
    // href untouched by the class style too.
    expect(anchor.getAttribute("href")).toBe(MAGNET_A);
  });
});
