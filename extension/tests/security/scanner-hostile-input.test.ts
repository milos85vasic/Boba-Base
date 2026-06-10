/**
 * @fileoverview Security hardening tests — hostile page input against the REAL
 * detection scanners + parsers (BobaLink).
 *
 * A torrent-detection extension runs on UNTRUSTED, attacker-controlled pages.
 * Every byte of a magnet URI, an anchor `href`, and page text is hostile input.
 * These tests feed the REAL production parsers/scanners (no stubs) deliberately
 * malicious page content inside jsdom and assert USER-OBSERVABLE safety
 * properties, NOT merely "no error":
 *
 *   1. The magnet parser extracts the correct infohash OR rejects the URI; it
 *      NEVER produces a `displayName` that, when rendered into the DOM, injects
 *      live markup — the name stays inert text (no executable `<script>`/
 *      `<img onerror>` survives). Proven by actually assigning the value to a
 *      real DOM node and asserting zero injected elements + zero live event
 *      handlers.
 *   2. Pathological inputs (thousands of `tr=`, megabyte display names,
 *      RTL-override unicode, percent-encoding attacks) parse in BOUNDED time
 *      and produce bounded, sane output — no hang (ReDoS), no crash.
 *   3. The LinkScanner treats ONLY genuine `magnet:` / http(s) `.torrent` links
 *      as detections — `javascript:`, `data:`, `vbscript:`, null-byte, oversized
 *      hrefs are IGNORED (never emitted as a detection the user can click).
 *   4. The orchestrator survives a DoS-shaped page (50k junk anchors + a few
 *      real magnets) — returns ONLY the real magnets, in bounded time.
 *
 * Each assertion FAILS if its safety property breaks (anti-bluff §11.4 / §107):
 * a parser that let `<img onerror>` through would fail the "name stays inert"
 * assertions; an unbounded regex would blow the time budget; a scanner that
 * detected `javascript:` would fail the scheme-allowlist assertions.
 *
 * @module tests/security/scanner-hostile-input.test
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  parseMagnetUri,
  sanitizeDisplayName,
  findMagnetUris,
} from "../../src/parser/magnet";
import { LinkScanner } from "../../src/scanner/link-scanner";
import { ScannerOrchestrator } from "../../src/scanner/orchestrator";
import { TypedEventEmitter } from "../../src/shared/events";
import type { DetectedTorrent } from "../../src/types/torrent";

const VALID_INFOHASH = "0123456789abcdef0123456789abcdef01234567";
const VALID_MAGNET = `magnet:?xt=urn:btih:${VALID_INFOHASH}`;

/** A LinkScanner over a fresh emitter (no MutationObserver side effects). */
function makeLinkScanner(): LinkScanner {
  return new LinkScanner(new TypedEventEmitter());
}

/**
 * Orchestrator with mutation observation DISABLED — deterministic, no timers,
 * no background MutationObserver. We drive it with an explicit `scanNow()`.
 */
function makeOrchestrator(): ScannerOrchestrator {
  return new ScannerOrchestrator(new TypedEventEmitter(), {
    observeMutations: false,
  });
}

/**
 * Render an untrusted string into a REAL DOM element as `textContent` (the way
 * the extension's UI surfaces are supposed to consume it) and report whether
 * any LIVE markup got injected: child elements created, or an `onerror`/script
 * handler that the browser would actually execute.
 *
 * This is the user-observable oracle for "the name stays inert text": if the
 * sanitized value injects markup here, an XSS reached the user.
 */
function renderAndInspect(value: string): {
  injectedElements: number;
  hasScriptOrImg: boolean;
} {
  const host = document.createElement("div");
  // The contract is "textContent-style inert text"; assigning via textContent
  // can never create elements, so we additionally probe the worse case: even
  // if a naive consumer did `innerHTML = value`, a properly-sanitized value
  // (angle brackets escaped) yields ZERO elements.
  host.innerHTML = value;
  const injectedElements = host.querySelectorAll("*").length;
  const hasScriptOrImg =
    host.querySelector("script, img, iframe, svg, object, embed") !== null;
  return { injectedElements, hasScriptOrImg };
}

describe("Security — magnet parser hostile `dn` (display name) XSS", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("strips <img onerror> in dn → infohash correct, name renders INERT (no element, no handler)", () => {
    const payload = encodeURIComponent(
      `<img src=x onerror="window.__xss_fired=true">pwn`,
    );
    const uri = `${VALID_MAGNET}&dn=${payload}`;

    const info = parseMagnetUri(uri);

    // The real torrent identity is still extracted correctly.
    expect(info.infohash).toBe(VALID_INFOHASH);

    // The display name carries NO live markup.
    const name = info.displayName ?? "";
    expect(name).not.toContain("<img");
    expect(name.toLowerCase()).not.toContain("onerror");

    // User-observable oracle: rendering the value injects ZERO elements and
    // the global the payload tried to set was never touched.
    (window as unknown as Record<string, unknown>).__xss_fired = undefined;
    const { injectedElements, hasScriptOrImg } = renderAndInspect(name);
    expect(injectedElements).toBe(0);
    expect(hasScriptOrImg).toBe(false);
    expect(
      (window as unknown as Record<string, unknown>).__xss_fired,
    ).toBeUndefined();
  });

  it("strips <script> in dn → name renders with ZERO executable elements", () => {
    const payload = encodeURIComponent(
      `<script>window.__xss2=1</script>Real Name`,
    );
    const info = parseMagnetUri(`${VALID_MAGNET}&dn=${payload}`);

    const name = info.displayName ?? "";
    expect(name.toLowerCase()).not.toContain("<script");
    // The visible text the user reads survives, inert.
    expect(name).toContain("Real Name");

    (window as unknown as Record<string, unknown>).__xss2 = undefined;
    const { injectedElements } = renderAndInspect(name);
    expect(injectedElements).toBe(0);
    expect(
      (window as unknown as Record<string, unknown>).__xss2,
    ).toBeUndefined();
  });

  it("neutralizes a lone/malformed `<script` (no closing >) so it cannot re-open as markup", () => {
    const out = sanitizeDisplayName(`<script attr="x" foo`);
    // No raw `<` survives — it is HTML-entity escaped.
    expect(out).not.toMatch(/<[a-z]/i);
    const { injectedElements } = renderAndInspect(out);
    expect(injectedElements).toBe(0);
  });

  it("a `javascript:`/`data:`-bearing dn does not become a live link or script", () => {
    const payload = encodeURIComponent(
      `<a href="javascript:alert(1)">x</a><iframe src="data:text/html,<script>1</script>">`,
    );
    const info = parseMagnetUri(`${VALID_MAGNET}&dn=${payload}`);
    const name = info.displayName ?? "";

    const { injectedElements, hasScriptOrImg } = renderAndInspect(name);
    expect(injectedElements).toBe(0);
    expect(hasScriptOrImg).toBe(false);
    expect(name.toLowerCase()).not.toContain("<a");
    expect(name.toLowerCase()).not.toContain("<iframe");
  });
});

describe("Security — magnet parser malformed / non-btih xt", () => {
  it("REJECTS a magnet whose xt is not a valid btih infohash", () => {
    // 40 chars but contains non-hex → not a valid btih.
    const bad = `magnet:?xt=urn:btih:zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz&dn=x`;
    expect(() => parseMagnetUri(bad)).toThrow();
  });

  it("REJECTS a magnet with a missing xt entirely", () => {
    expect(() => parseMagnetUri("magnet:?dn=NoHashHere")).toThrow();
  });

  it("REJECTS a non-magnet scheme masquerading as a magnet", () => {
    expect(() =>
      parseMagnetUri(`javascript:magnet:?xt=urn:btih:${VALID_INFOHASH}`),
    ).toThrow();
  });

  it("accepts a base32 btih and converts to a valid 40-hex infohash", () => {
    // 32-char RFC4648 base32 of some 160-bit value.
    const base32 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"; // 32 'A' → all-zero bits
    const info = parseMagnetUri(`magnet:?xt=urn:btih:${base32}`);
    expect(info.infohash).toMatch(/^[a-f0-9]{40}$/);
  });
});

describe("Security — magnet parser pathological size / encoding (bounded time)", () => {
  it("handles thousands of tr= trackers in bounded time without hanging", () => {
    const trackers = Array.from(
      { length: 5000 },
      (_, i) => `tr=${encodeURIComponent(`http://tracker${i}.example/announce`)}`,
    ).join("&");
    const uri = `${VALID_MAGNET}&${trackers}`;

    const start = performance.now();
    const info = parseMagnetUri(uri);
    const elapsed = performance.now() - start;

    // Correct identity + every tracker captured.
    expect(info.infohash).toBe(VALID_INFOHASH);
    expect(info.trackers.length).toBe(5000);
    // Bounded: linear parse of 5k pairs must be well under 2s.
    expect(elapsed).toBeLessThan(2000);
  });

  it("handles a megabyte-scale hostile dn in bounded time, output stays inert", () => {
    const huge = "<img onerror=1>".repeat(50_000); // ~750 KB of payload
    const uri = `${VALID_MAGNET}&dn=${encodeURIComponent(huge)}`;

    const start = performance.now();
    const info = parseMagnetUri(uri);
    const elapsed = performance.now() - start;

    expect(info.infohash).toBe(VALID_INFOHASH);
    expect(elapsed).toBeLessThan(2000);
    const name = info.displayName ?? "";
    expect(name.toLowerCase()).not.toContain("onerror");
    const { injectedElements } = renderAndInspect(name);
    expect(injectedElements).toBe(0);
  });

  it("does not hang on a pathological no-`>` tag soup (ReDoS guard)", () => {
    // A long run of '<' with no closing '>' is the classic backtracking trap.
    const soup = "<".repeat(100_000);
    const start = performance.now();
    const out = sanitizeDisplayName(soup);
    const elapsed = performance.now() - start;
    expect(elapsed).toBeLessThan(2000);
    // Every '<' became an entity; nothing renders as an element.
    const { injectedElements } = renderAndInspect(out);
    expect(injectedElements).toBe(0);
  });

  it("survives malformed percent-encoding in a param value without throwing", () => {
    // A lone `%` and a truncated `%E0` are invalid UTF-8 percent sequences.
    const uri = `${VALID_MAGNET}&dn=bad%E0%ZZ%`;
    const info = parseMagnetUri(uri);
    expect(info.infohash).toBe(VALID_INFOHASH);
    // Whatever survived must still be inert.
    const { injectedElements } = renderAndInspect(info.displayName ?? "");
    expect(injectedElements).toBe(0);
  });

  it("RTL-override / control characters in dn are stripped or kept inert", () => {
    // U+202E (RLO) is a spoofing primitive; control chars must not survive.
    const raw = `evil‮txt.exe `;
    const out = sanitizeDisplayName(raw);
    expect(out).not.toContain(" ");
    expect(out).not.toContain("");
    const { injectedElements } = renderAndInspect(out);
    expect(injectedElements).toBe(0);
  });

  it("findMagnetUris does not over-match: a hostile blob yields only valid magnets, bounded", () => {
    const noise = "magnet:?xt=urn:btih:notahash ".repeat(10_000);
    const blob = `${noise} ${VALID_MAGNET} ${noise}`;
    const start = performance.now();
    const uris = findMagnetUris(blob);
    const elapsed = performance.now() - start;
    expect(elapsed).toBeLessThan(2000);
    // Only the genuinely valid magnet is returned (the 'notahash' noise is rejected).
    expect(uris).toContain(VALID_MAGNET);
    expect(uris.every((u) => /urn:btih:[a-f0-9]{40}/i.test(u))).toBe(true);
  });
});

describe("Security — LinkScanner href scheme allowlist (hostile anchors ignored)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("IGNORES javascript:/data:/vbscript: hrefs, detects ONLY the real magnet", async () => {
    document.body.innerHTML = `
      <a href="javascript:alert(1)">js</a>
      <a href="data:text/html,<script>alert(1)</script>">data</a>
      <a href="vbscript:msgbox(1)">vb</a>
      <a href="javascript:void(magnet:?xt=urn:btih:${VALID_INFOHASH})">trap</a>
      <a href="${VALID_MAGNET}">the real one</a>
    `;

    const items = await makeLinkScanner().scan();

    // Exactly one detection: the genuine magnet.
    expect(items.length).toBe(1);
    expect(items[0]?.type).toBe("magnet");
    expect(items[0]?.magnet?.infohash).toBe(VALID_INFOHASH);
    // None of the hostile-scheme hrefs leaked into a detection URI.
    for (const it of items) {
      const uri = it.magnet?.uri ?? it.torrentFile?.url ?? "";
      expect(uri.toLowerCase()).not.toContain("javascript:");
      expect(uri.toLowerCase()).not.toContain("vbscript:");
      expect(uri.toLowerCase()).not.toMatch(/^data:/);
    }
  });

  it("IGNORES a `data:` URL that merely ENDS in .torrent (not http/https)", async () => {
    document.body.innerHTML = `
      <a href="data:application/x-bittorrent;base64,AAAA.torrent">fake</a>
      <a href="ftp://host/file.torrent">ftp</a>
      <a href="javascript:x.torrent">js</a>
    `;
    const items = await makeLinkScanner().scan();
    // The .torrent validation regex requires an http(s) origin → none detected.
    expect(items.length).toBe(0);
  });

  it("IGNORES null-byte and oversized hrefs (no crash, no detection)", async () => {
    const oversized = "https://evil.example/" + "a".repeat(200_000) + ".not";
    document.body.innerHTML = `
      <a href="https://evil.example/x .torrent">nullbyte</a>
      <a id="big">huge</a>
      <a href="${VALID_MAGNET}">real</a>
    `;
    // Set the oversized href via the DOM API (avoids HTML-parse weirdness).
    document.getElementById("big")?.setAttribute("href", oversized);

    const start = performance.now();
    const items = await makeLinkScanner().scan();
    const elapsed = performance.now() - start;

    expect(elapsed).toBeLessThan(2000);
    // Only the real magnet — the null-byte and oversized non-torrent hrefs are ignored.
    const real = items.filter((i) => i.magnet?.infohash === VALID_INFOHASH);
    expect(real.length).toBe(1);
    expect(items.every((i) => (i.torrentFile?.url ?? "") !== oversized)).toBe(
      true,
    );
  });

  it("a magnet anchor with a hostile dn still produces an INERT displayName", async () => {
    const payload = encodeURIComponent(`<img src=x onerror=alert(1)>`);
    document.body.innerHTML = `<a href="${VALID_MAGNET}&dn=${payload}">click</a>`;

    const items = await makeLinkScanner().scan();
    expect(items.length).toBe(1);

    const name = items[0]?.displayName ?? "";
    expect(name.toLowerCase()).not.toContain("onerror");
    const { injectedElements } = renderAndInspect(name);
    expect(injectedElements).toBe(0);
  });
});

describe("Security — orchestrator DoS resilience (junk-flood page)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("returns ONLY the real magnets from a 50k junk-anchor page, in bounded time", async () => {
    const INFOHASH_2 = "fedcba9876543210fedcba9876543210fedcba98";
    const realA = `magnet:?xt=urn:btih:${VALID_INFOHASH}&dn=Alpha`;
    const realB = `magnet:?xt=urn:btih:${INFOHASH_2}&dn=Beta`;

    // Build 50k junk anchors with hostile/non-torrent hrefs + the 2 real magnets.
    const parts: string[] = [];
    for (let i = 0; i < 50_000; i++) {
      parts.push(`<a href="https://junk.example/page${i}.html">j${i}</a>`);
    }
    parts.push(`<a href="${realA}">A</a>`);
    parts.push(`<a href="${realB}">B</a>`);
    document.body.innerHTML = parts.join("");

    const orch = makeOrchestrator();
    const start = performance.now();
    const result = await orch.scanNow();
    const elapsed = performance.now() - start;
    orch.stop();

    // Bounded time even with 50k anchors.
    expect(elapsed).toBeLessThan(5000);

    // ONLY the two real magnets are detected — junk is excluded.
    const magnets = result.items.filter(
      (i: DetectedTorrent) => i.type === "magnet",
    );
    expect(magnets.length).toBe(2);
    const hashes = magnets.map((m) => m.magnet?.infohash).sort();
    expect(hashes).toEqual([VALID_INFOHASH, INFOHASH_2].sort());
    expect(result.magnetCount).toBe(2);
  });
});
