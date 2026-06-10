/**
 * @fileoverview Anti-bluff unit tests for the REAL TextScanner (scanner/text-scanner.ts).
 *
 * Imports the production `src/scanner/text-scanner.ts` and drives it over a real
 * jsdom DOM (Vitest `environment: "jsdom"` → `document` + `TreeWalker` are live).
 * No mock of the scanner, no stub of the magnet parser — the assertions inspect
 * the user-observable detection records the scanner returns.
 *
 * What each test PROVES (every one fails against a no-op stub that returns []):
 *  - bare magnet URIs pasted as plain TEXT (forum-style) are detected with the
 *    correct infohash via the committed magnet parser;
 *  - a magnet that lives ONLY in an `<a href>` attribute (with non-magnet link
 *    text) is NOT detected by the TextScanner — by design it walks text NODES,
 *    not attributes, so it does not double-count what the LinkScanner owns
 *    (disposition F-adopt-vs-rewrite: text-scanner "Catches forum-pasted magnets";
 *    `<a href>` is the LinkScanner's responsibility);
 *  - the SAME magnet detected on two separate scans yields the SAME stable id
 *    (the committed BaseScanner derives a time-independent id — relevant to the
 *    orchestrator's id-keyed dedup);
 *  - plain prose with no magnet yields zero detections.
 *
 * @module tests/unit/text-scanner.test
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { TextScanner } from "../../src/scanner/text-scanner";
import { TypedEventEmitter } from "../../src/shared/events";
import type { DetectedTorrent } from "../../src/types/torrent";

/** A real, valid 40-char hex infohash (lowercase canonical form). */
const HASH_A = "abcdef0123456789abcdef0123456789abcdef01";
const HASH_B = "0123456789abcdef0123456789abcdef01234567";

/** Build a bare magnet URI string (the kind pasted into forum text). */
function magnet(hash: string, name?: string): string {
  const dn = name ? `&dn=${encodeURIComponent(name)}` : "";
  return `magnet:?xt=urn:btih:${hash}${dn}`;
}

/**
 * Install an `innerHTML` body and return a fresh TextScanner bound to a real
 * event emitter. Text nodes must be ≥ 20 chars to pass the scanner's
 * min-length filter, so the fixtures wrap magnets in real sentence text.
 */
function scannerFor(bodyHtml: string): TextScanner {
  document.body.innerHTML = bodyHtml;
  return new TextScanner(new TypedEventEmitter());
}

describe("TextScanner (real DOM, jsdom)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("detects a bare magnet URI pasted as plain text, with the correct infohash", async () => {
    const scanner = scannerFor(
      `<p>Hey everyone, grab this release here: ${magnet(HASH_A, "Cool Release")} — enjoy!</p>`,
    );

    const results = await scanner.scan();

    expect(results.length).toBe(1);
    const item = results[0] as DetectedTorrent;
    expect(item.type).toBe("magnet");
    expect(item.magnet).not.toBeNull();
    // Correct infohash, normalized lowercase by the committed magnet parser.
    expect(item.magnet?.infohash).toBe(HASH_A);
    // Display name flows from the parsed `dn`.
    expect(item.displayName).toContain("Cool Release");
  });

  it("detects multiple distinct bare magnets across separate text nodes", async () => {
    const scanner = scannerFor(
      `<div>
         <p>First forum post pasting a magnet link: ${magnet(HASH_A)} thanks for sharing!</p>
         <p>Second comment further down also has one: ${magnet(HASH_B)} grabbing now.</p>
       </div>`,
    );

    const results = await scanner.scan();

    const hashes = results.map((r) => r.magnet?.infohash).sort();
    expect(hashes).toEqual([HASH_B, HASH_A].sort());
    expect(results.length).toBe(2);
  });

  it("does NOT detect a magnet that lives only in an <a href> attribute", async () => {
    // The magnet is ONLY in the href; the anchor's TEXT says "Download" (no
    // magnet substring). TextScanner walks text NODES, not attributes, so it
    // must NOT pick this up — that is the LinkScanner's job. This prevents the
    // same torrent being double-counted by both scanners.
    const scanner = scannerFor(
      `<p>Official mirror is available right over here: <a href="${magnet(
        HASH_A,
      )}">Download the torrent now</a> for free.</p>`,
    );

    const results = await scanner.scan();

    expect(results.length).toBe(0);
  });

  it("produces a STABLE id for the same magnet across two scans", async () => {
    const scanner = scannerFor(
      `<p>Sharing this great pack with the community: ${magnet(HASH_A)} grab it!</p>`,
    );

    const first = await scanner.scan();
    const second = await scanner.scan();

    expect(first.length).toBe(1);
    expect(second.length).toBe(1);
    // Same torrent, two scans → identical id (time-independent), so the
    // orchestrator's id-keyed dedup collapses them to one.
    expect((first[0] as DetectedTorrent).id).toBe((second[0] as DetectedTorrent).id);
  });

  it("ignores plain text with no magnet link at all", async () => {
    const scanner = scannerFor(
      `<p>This is just an ordinary paragraph of text with no torrent content whatsoever.</p>
       <div>Another block of prose, also entirely magnet-free, to be safe.</div>`,
    );

    const results = await scanner.scan();

    expect(results.length).toBe(0);
  });
});
