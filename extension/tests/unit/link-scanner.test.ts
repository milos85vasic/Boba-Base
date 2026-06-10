/**
 * @fileoverview Anti-bluff unit tests for the REAL LinkScanner (scanner/link-scanner.ts).
 *
 * Imports the production `src/scanner/link-scanner.ts` and exercises it against a
 * REAL jsdom DOM (`document.body.innerHTML = ...`). These are USER-OBSERVABLE
 * assertions: given a page containing magnet `<a>` links, absolute `.torrent`
 * links, and non-torrent links, the scanner MUST detect the torrent links (with
 * the correct infohash / display name), IGNORE the non-torrent links, dedup
 * identical magnets, and produce STABLE ids (scanning the same DOM twice yields
 * the same ids).
 *
 * The stable-id and detection assertions FAIL against a no-op stub that returns
 * [] — that is the §11.4 anti-bluff RED proof driven in the agent session.
 *
 * Runs under vitest + jsdom (window.location defaults to http://localhost/, so
 * getSiteSelectors() resolves to the generic selector set — magnet + .torrent).
 *
 * @module tests/unit/link-scanner.test
 */

import { describe, it, expect, beforeEach } from "vitest";
import { LinkScanner } from "../../src/scanner/link-scanner";
import { TypedEventEmitter } from "../../src/shared/events";
import type { DetectedTorrent } from "../../src/types/torrent";

const INFOHASH_A = "0123456789abcdef0123456789abcdef01234567";
const INFOHASH_B = "fedcba9876543210fedcba9876543210fedcba98";

// dn uses %20-encoded spaces: the committed parser decodes via
// decodeURIComponent (NOT form-urlencoded), so `+` stays a literal `+`.
const MAGNET_A = `magnet:?xt=urn:btih:${INFOHASH_A}&dn=Ubuntu%2024.04%20LTS`;
const MAGNET_B = `magnet:?xt=urn:btih:${INFOHASH_B}&dn=Debian%2012`;
const TORRENT_URL = "https://example.org/files/cool-release.torrent";

/** Build a fresh scanner against a new event emitter. */
function makeScanner(): LinkScanner {
  return new LinkScanner(new TypedEventEmitter());
}

/** Find the detected item whose magnet infohash matches. */
function byInfohash(
  items: readonly DetectedTorrent[],
  infohash: string,
): DetectedTorrent | undefined {
  return items.find((it) => it.magnet?.infohash === infohash);
}

describe("LinkScanner — DOM detection (anti-bluff, real jsdom)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("detects magnet links with correct infohash + display name", async () => {
    document.body.innerHTML = `
      <a id="m" href="${MAGNET_A}">Ubuntu download</a>
      <p>some prose</p>
    `;

    const items = await makeScanner().scan();

    const magnet = byInfohash(items, INFOHASH_A);
    expect(magnet).toBeDefined();
    expect(magnet?.type).toBe("magnet");
    // dn from the magnet URI wins over the anchor text.
    expect(magnet?.displayName).toBe("Ubuntu 24.04 LTS");
    expect(magnet?.magnet?.uri).toBe(MAGNET_A);
  });

  it("detects .torrent file links (correct type + url + filename)", async () => {
    document.body.innerHTML = `<a id="t" href="${TORRENT_URL}">Get the .torrent</a>`;

    const items = await makeScanner().scan();

    const file = items.find((it) => it.type === "torrent-file");
    expect(file).toBeDefined();
    expect(file?.torrentFile?.url).toBe(TORRENT_URL);
    expect(file?.torrentFile?.filename).toBe("cool-release.torrent");
    // anchor text becomes the display name when present.
    expect(file?.displayName).toBe("Get the .torrent");
  });

  it("IGNORES non-torrent links (http pages, mailto, anchors, plain .html)", async () => {
    document.body.innerHTML = `
      <a href="https://example.org/page.html">A normal page</a>
      <a href="https://news.example.com/article">News</a>
      <a href="mailto:someone@example.com">Email</a>
      <a href="#section">Jump</a>
      <a href="${MAGNET_A}">The one real torrent</a>
    `;

    const items = await makeScanner().scan();

    // Exactly one detection — only the magnet, none of the four decoys.
    expect(items.length).toBe(1);
    expect(items[0]?.magnet?.infohash).toBe(INFOHASH_A);
  });

  it("detects a mix of magnets and .torrent files together", async () => {
    document.body.innerHTML = `
      <a href="${MAGNET_A}">A</a>
      <a href="${MAGNET_B}">B</a>
      <a href="${TORRENT_URL}">File</a>
      <a href="https://example.org/not-a-torrent">Decoy</a>
    `;

    const items = await makeScanner().scan();

    expect(items.length).toBe(3);
    expect(byInfohash(items, INFOHASH_A)).toBeDefined();
    expect(byInfohash(items, INFOHASH_B)).toBeDefined();
    expect(items.some((it) => it.type === "torrent-file")).toBe(true);
  });

  it("dedups identical magnet links (same href twice → one detection)", async () => {
    document.body.innerHTML = `
      <a href="${MAGNET_A}">first copy</a>
      <a href="${MAGNET_A}">second copy</a>
      <a href="${MAGNET_A.toUpperCase()}">third (case variant)</a>
    `;

    const items = await makeScanner().scan();

    const magnets = items.filter((it) => it.type === "magnet");
    expect(magnets.length).toBe(1);
    expect(magnets[0]?.magnet?.infohash).toBe(INFOHASH_A);
  });

  it("produces STABLE ids: scanning the SAME DOM twice yields the SAME ids", async () => {
    document.body.innerHTML = `
      <a href="${MAGNET_A}">A</a>
      <a href="${MAGNET_B}">B</a>
      <a href="${TORRENT_URL}">File</a>
    `;

    const firstIds = (await makeScanner().scan())
      .map((it) => it.id)
      .sort();
    const secondIds = (await makeScanner().scan())
      .map((it) => it.id)
      .sort();

    expect(firstIds.length).toBe(3);
    expect(secondIds).toEqual(firstIds);
    // and the ids discriminate distinct torrents.
    expect(new Set(firstIds).size).toBe(3);
  });

  it("returns [] for a DOM with no torrent links at all", async () => {
    document.body.innerHTML = `<a href="https://example.org/">home</a><p>nothing here</p>`;
    const items = await makeScanner().scan();
    expect(items).toEqual([]);
  });
});
