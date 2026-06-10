/**
 * @fileoverview SECURITY — content-script XSS / DOM-injection sanitization.
 *
 * The content layer renders detected-torrent markers INTO the live page DOM
 * (HighlightManager.addBadge) and runs the full scan→detect→highlight pipeline
 * over arbitrary page content (initContentScript). Both paths process UNTRUSTED
 * input: the torrent NAME (the magnet `dn=` parameter) and the page anchor's own
 * href/text are attacker-controlled on a hostile page.
 *
 * The production code claims (highlight.ts:22-23) to build markers with SAFE DOM
 * APIs — `document.createElement` + `textContent`, never `innerHTML`. These tests
 * PROVE that claim end-to-end in jsdom: a malicious torrent name / anchor is fed
 * through the REAL highlight + render path, and we assert the document gained NO
 * `<script>` element and NO event-handler (`on*`) attribute — i.e. the untrusted
 * string was rendered as TEXT, never parsed as markup.
 *
 * ANTI-BLUFF (§11.4 / §11.4.10): every assertion inspects the REAL DOM state
 * (querySelectorAll('script'), attribute enumeration), not "no error". Each test
 * FAILS against an innerHTML-based implementation:
 *   - If addBadge built its content via `el.innerHTML = \`…${name}…\``, the
 *     `<img onerror>` / `<script>` payload in a name would be PARSED, creating a
 *     real <img>/<script> node + an onerror attribute — the assertions below
 *     would then see a script element / an on* attribute and FAIL. Because the
 *     code uses createElement+textContent, the payload stays inert text and the
 *     assertions pass. (The badge text is a fixed "MAGNET"/"TORRENT" label, so a
 *     hostile name CANNOT reach markup regardless — these tests lock that in.)
 *   - The full-pipeline test additionally asserts that running the scanner over a
 *     page whose anchor carries an XSS payload injects nothing executable.
 *
 * @module tests/security/content-xss.test
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { HighlightManager } from "../../src/content/highlight";
import { initContentScript } from "../../src/content/index";
import { TypedEventEmitter } from "../../src/shared/events";

// ─────────────────────────────────────────────────────────────────────────────
// Malicious payloads (classic reflected-XSS vectors)
// ─────────────────────────────────────────────────────────────────────────────

/** A real torrent infohash so the orchestrator accepts the magnet. */
const INFOHASH = "0123456789abcdef0123456789abcdef01234567";

/** Payloads that, if a string is parsed as HTML, create a script / event handler. */
const XSS_NAMES = [
  '<img src=x onerror=alert(1)>',
  '"><script>alert(document.cookie)</script>',
  '<svg/onload=alert(1)>',
  "<iframe src=javascript:alert(1)></iframe>",
  "</a><script>evil()</script><a>",
] as const;

/** Build a magnet whose display-name (`dn=`) is the attacker-controlled payload. */
function maliciousMagnet(name: string): string {
  return `magnet:?xt=urn:btih:${INFOHASH}&dn=${encodeURIComponent(name)}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// DOM XSS oracles — inspect the REAL document state, not "no error"
// ─────────────────────────────────────────────────────────────────────────────

/** Every <script> element currently in the document (any injection → non-empty). */
function scriptElements(): HTMLScriptElement[] {
  return Array.from(document.querySelectorAll("script"));
}

/** Every element carrying an inline event-handler (on*) attribute. */
function elementsWithEventHandler(): Element[] {
  const hits: Element[] = [];
  for (const el of document.querySelectorAll("*")) {
    for (const attr of Array.from(el.attributes)) {
      if (attr.name.toLowerCase().startsWith("on")) {
        hits.push(el);
        break;
      }
    }
  }
  return hits;
}

/** Elements an HTML-parsed payload would create: <img>, <svg>, <iframe>. */
function injectedMarkupElements(): Element[] {
  return Array.from(document.querySelectorAll("img, svg, iframe"));
}

describe("content/highlight — XSS: malicious torrent name renders as TEXT, not markup", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it.each(XSS_NAMES)(
    "addBadge does not inject a <script>/on*-handler for name %j",
    (name) => {
      const magnet = maliciousMagnet(name);
      // The page anchor's VISIBLE TEXT is also the hostile name — set via
      // textContent so the *fixture* itself does not pre-inject markup; the
      // anchor's href is the magnet the manager will look up + badge.
      const anchor = document.createElement("a");
      anchor.setAttribute("href", magnet);
      anchor.textContent = name;
      document.body.appendChild(anchor);

      // Baseline: a clean page has none of these.
      expect(scriptElements().length).toBe(0);
      expect(elementsWithEventHandler().length).toBe(0);
      expect(injectedMarkupElements().length).toBe(0);

      const events = new TypedEventEmitter();
      const manager = new HighlightManager(events, {
        style: "badge",
        enabled: true,
      });

      // Drive the REAL detection→highlight path with the hostile name.
      events.emit("torrent-detected", {
        id: "id-xss",
        type: "magnet",
        displayName: name,
        url: magnet,
      });

      // USER-OBSERVABLE: a badge WAS added (proves the path actually ran — this
      // is not a vacuous pass on a no-op manager).
      const badge = anchor.querySelector(".bobalink-badge");
      expect(badge).not.toBeNull();
      // The badge label is the fixed, safe token — never the hostile name.
      expect(badge?.textContent ?? "").toContain("MAGNET");
      expect(badge?.textContent ?? "").not.toContain("onerror");
      expect(badge?.textContent ?? "").not.toContain("<script>");

      // CORE XSS ASSERTIONS — the document gained NOTHING executable. An
      // innerHTML-based addBadge would have parsed the payload and created a
      // <script>/<img onerror>; createElement+textContent keeps it inert.
      expect(scriptElements().length).toBe(0);
      expect(elementsWithEventHandler().length).toBe(0);
      // No <img>/<svg>/<iframe> sprang into existence from the badge render.
      // (The anchor text was set via textContent, so the fixture added none.)
      expect(injectedMarkupElements().length).toBe(0);

      // Defence in depth: the badge subtree contains only safe inert nodes.
      for (const node of badge?.querySelectorAll("*") ?? []) {
        expect(["SPAN"]).toContain(node.tagName);
        for (const attr of Array.from(node.attributes)) {
          expect(attr.name.toLowerCase().startsWith("on")).toBe(false);
        }
      }

      manager.destroy();
    },
  );

  it("a hostile name supplied as the badge title is escaped, not parsed", () => {
    // The badge `title` is built from the torrent TYPE (a fixed enum), never the
    // name — but assert no attribute injection regardless: a payload-bearing name
    // must not bleed into ANY attribute as live markup.
    const name = '" onload="alert(1)';
    const magnet = maliciousMagnet(name);
    const anchor = document.createElement("a");
    anchor.setAttribute("href", magnet);
    anchor.textContent = "safe-anchor-text";
    document.body.appendChild(anchor);

    const events = new TypedEventEmitter();
    const manager = new HighlightManager(events, { style: "badge", enabled: true });
    events.emit("torrent-detected", {
      id: "id-attr",
      type: "magnet",
      displayName: name,
      url: magnet,
    });

    const badge = anchor.querySelector(".bobalink-badge");
    expect(badge).not.toBeNull();
    // No on* handler anywhere, and the badge title is the fixed safe string.
    expect(elementsWithEventHandler().length).toBe(0);
    expect(badge?.getAttribute("title") ?? "").toContain("Magnet Link");
    expect(badge?.getAttribute("title") ?? "").not.toContain("onload");

    manager.destroy();
  });
});

describe("content/index — XSS: full scan→detect→highlight pipeline injects nothing executable", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    // No chrome.* in jsdom → getRuntime() returns null; the entry skips the
    // background send and never registers an onMessage listener. The scan +
    // highlight path (the XSS-relevant DOM render) still runs in full.
    delete (globalThis as unknown as { chrome?: unknown }).chrome;
  });

  afterEach(() => {
    delete (globalThis as unknown as { chrome?: unknown }).chrome;
  });

  it("running the real content entry over a page with an XSS-named magnet adds no <script>/on*", async () => {
    const name = '<img src=x onerror=alert(1)>';
    const magnet = maliciousMagnet(name);

    // Hostile anchor — text set via textContent so the fixture itself injects no
    // markup; the magnet href is what the scanner detects + the manager badges.
    const anchor = document.createElement("a");
    anchor.setAttribute("href", magnet);
    anchor.textContent = name;
    anchor.id = "m-xss";
    document.body.appendChild(anchor);

    expect(scriptElements().length).toBe(0);
    expect(elementsWithEventHandler().length).toBe(0);

    // No explicit config → loadConfig() falls back to DEFAULT_CONFIG, which has
    // highlightTorrents: true + highlightStyle: "badge", so the render path runs.
    const controller = await initContentScript({ autoScan: true });

    // The real orchestrator detected the magnet (pipeline ran end-to-end).
    const detected = controller.orchestrator.getDetectedTorrents();
    expect(detected.some((t) => t.magnet?.infohash === INFOHASH)).toBe(true);

    // A badge was rendered into the hostile anchor (highlight path executed).
    const badge = document.querySelector("#m-xss .bobalink-badge");
    expect(badge).not.toBeNull();

    // CORE: despite the <img onerror> payload in the name AND the anchor text,
    // the document contains NO injected script / event handler / markup node.
    expect(scriptElements().length).toBe(0);
    expect(elementsWithEventHandler().length).toBe(0);
    expect(injectedMarkupElements().length).toBe(0);

    controller.cleanup();
  });
});
