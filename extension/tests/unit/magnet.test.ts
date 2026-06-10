/**
 * @fileoverview Unit tests for the magnet URI parser (Phase 2 port).
 *
 * These tests exercise the REAL parser module (no mocks of the unit under
 * test) and assert user-observable outcomes — the parsed field values a
 * caller would actually consume — per the anti-bluff covenant (§11.4):
 * each assertion would FAIL against a no-op / stub implementation.
 *
 * @module tests/unit/magnet
 */

import { describe, it, expect } from "vitest";

import {
  containsMagnetLink,
  findMagnetUris,
  extractInfohash,
  isValidHexInfohash,
  isValidBase32Infohash,
  base32ToHex,
  parseMagnetUri,
  buildMagnetUri,
  getMagnetDisplayName,
  getMagnetDisplayNameOrUnknown,
  dedupeMagnets,
  sanitizeDisplayName,
  MAGNET_DISPLAY_NAME_FALLBACK,
} from "../../src/parser/magnet";
import { ParseError } from "../../src/shared/errors";
import type { MagnetInfo } from "../../src/types/torrent";

// A canonical 40-char hex infohash used across the suite.
const HEX = "1234567890abcdef1234567890abcdef12345678";

// Verified base32 ⇄ hex test vector (computed independently of the module):
//   base32 "YEX6DQDLXISUVHOJ6UM3GNNKPQJWPKEK"  →  hex below.
const BASE32 = "YEX6DQDLXISUVHOJ6UM3GNNKPQJWPKEK";
const BASE32_AS_HEX = "c12fe1c06bba254a9dc9f519b335aa7c1367a88a";

describe("containsMagnetLink", () => {
  it("detects the magnet prefix in surrounding text", () => {
    expect(containsMagnetLink(`see magnet:?xt=urn:btih:${HEX} now`)).toBe(true);
  });

  it("returns false for non-magnet text", () => {
    expect(containsMagnetLink("https://example.com/file.torrent")).toBe(false);
  });
});

describe("findMagnetUris", () => {
  it("extracts every valid magnet URI embedded in a block of text", () => {
    const a = `magnet:?xt=urn:btih:${HEX}&dn=Alpha`;
    const b = `magnet:?xt=urn:btih:abcdefabcdefabcdefabcdefabcdefabcdefabcd&dn=Beta`;
    const text = `prefix ${a} middle <a href="${b}">link</a> suffix`;

    const found = findMagnetUris(text);

    expect(found).toContain(a);
    expect(found).toContain(b);
    expect(found).toHaveLength(2);
  });

  it("deduplicates the same magnet seen twice (case-insensitive)", () => {
    const lower = `magnet:?xt=urn:btih:${HEX}`;
    const upper = `magnet:?xt=urn:btih:${HEX.toUpperCase()}`;
    const found = findMagnetUris(`${lower} and again ${upper}`);
    expect(found).toHaveLength(1);
  });

  it("returns an empty array when no magnet is present", () => {
    expect(findMagnetUris("nothing here")).toEqual([]);
  });
});

describe("infohash validation", () => {
  it("validates a 40-char hex infohash and rejects malformed ones", () => {
    expect(isValidHexInfohash(HEX)).toBe(true);
    expect(isValidHexInfohash("xyz")).toBe(false);
    expect(isValidHexInfohash(HEX.slice(0, 39))).toBe(false);
  });

  it("validates a 32-char base32 infohash and rejects malformed ones", () => {
    expect(isValidBase32Infohash(BASE32)).toBe(true);
    expect(isValidBase32Infohash("0189")).toBe(false); // 0/1/8/9 not in base32
    expect(isValidBase32Infohash(BASE32.slice(0, 31))).toBe(false);
  });

  it("extracts and lowercases the hex infohash from a magnet URI", () => {
    expect(extractInfohash(`magnet:?xt=urn:btih:${HEX.toUpperCase()}`)).toBe(
      HEX,
    );
    expect(extractInfohash("magnet:?xt=urn:btih:notahash")).toBeNull();
  });
});

describe("base32ToHex conversion", () => {
  it("converts a known base32 infohash to the exact expected hex", () => {
    // The load-bearing assertion: a specific input → a specific output.
    expect(base32ToHex(BASE32)).toBe(BASE32_AS_HEX);
  });

  it("throws ParseError on an invalid base32 string", () => {
    expect(() => base32ToHex("not-valid-base32!")).toThrow(ParseError);
  });
});

describe("parseMagnetUri — every parameter", () => {
  it("parses xt, dn, multiple tr, ws, xl, xs, kt, as, mt", () => {
    const uri =
      `magnet:?xt=urn:btih:${HEX}` +
      "&dn=Ubuntu%2024.04%20ISO" +
      "&tr=" +
      encodeURIComponent("udp://tracker.one:1337/announce") +
      "&tr=" +
      encodeURIComponent("https://tracker.two/announce") +
      "&ws=" +
      encodeURIComponent("https://seed.example.com/file.iso") +
      "&xl=4294967296" +
      "&xs=" +
      encodeURIComponent("https://example.com/file.torrent") +
      "&kt=ubuntu+linux+iso" +
      "&as=" +
      encodeURIComponent("https://mirror.example.com/file") +
      "&mt=" +
      encodeURIComponent("https://example.com/manifest");

    const info = parseMagnetUri(uri);

    expect(info.infohash).toBe(HEX);
    expect(info.displayName).toBe("Ubuntu 24.04 ISO");
    expect(info.trackers).toEqual([
      "udp://tracker.one:1337/announce",
      "https://tracker.two/announce",
    ]);
    expect(info.webSeeds).toEqual(["https://seed.example.com/file.iso"]);
    expect(info.exactLength).toBe(4294967296);
    expect(info.exactSource).toBe("https://example.com/file.torrent");
    expect(info.keywords).toEqual(["ubuntu", "linux", "iso"]);
    expect(info.acceptableSource).toBe("https://mirror.example.com/file");
    expect(info.manifest).toBe("https://example.com/manifest");
  });

  it("lowercases an uppercase hex xt", () => {
    const info = parseMagnetUri(`magnet:?xt=urn:btih:${HEX.toUpperCase()}`);
    expect(info.infohash).toBe(HEX);
  });

  it("converts a base32 xt to the exact hex infohash", () => {
    const info = parseMagnetUri(`magnet:?xt=urn:btih:${BASE32}&dn=B32`);
    // User-observable proof of the base32 → hex path end-to-end.
    expect(info.infohash).toBe(BASE32_AS_HEX);
    expect(info.displayName).toBe("B32");
  });

  it("throws ParseError when the string is not a magnet URI", () => {
    expect(() => parseMagnetUri("https://example.com/x")).toThrow(ParseError);
  });

  it("throws ParseError when no valid btih infohash is present", () => {
    expect(() => parseMagnetUri("magnet:?dn=NoHash")).toThrow(ParseError);
  });
});

describe("display name handling", () => {
  it("leaves displayName null when dn is absent, falling back to 'Unknown'", () => {
    const info = parseMagnetUri(`magnet:?xt=urn:btih:${HEX}`);
    expect(info.displayName).toBeNull();
    expect(getMagnetDisplayNameOrUnknown(info)).toBe("Unknown");
    expect(MAGNET_DISPLAY_NAME_FALLBACK).toBe("Unknown");
  });

  it("getMagnetDisplayName falls back to a truncated infohash echo", () => {
    const info = parseMagnetUri(`magnet:?xt=urn:btih:${HEX}`);
    expect(getMagnetDisplayName(info)).toBe(`Torrent ${HEX.slice(0, 12)}...`);
  });

  it("XSS-sanitizes a dn containing a <script> payload (no live HTML)", () => {
    const evil = "<script>alert('xss')</script>Movie";
    const uri = `magnet:?xt=urn:btih:${HEX}&dn=${encodeURIComponent(evil)}`;

    const info = parseMagnetUri(uri);
    const name = info.displayName ?? "";

    // The script tag must be gone, and no angle-bracket markup may survive
    // in a form a DOM could re-interpret as an element.
    expect(name).not.toContain("<script>");
    expect(name).not.toContain("</script>");
    expect(name).not.toMatch(/<[a-z/]/i);
    // The human-readable remainder is preserved (alert text + "Movie").
    expect(name).toContain("Movie");
  });

  it("sanitizeDisplayName strips tags and neutralizes stray brackets", () => {
    expect(sanitizeDisplayName("<b>Hello</b>")).toBe("Hello");
    // A lone unterminated '<' must not survive as raw markup.
    expect(sanitizeDisplayName("a < b")).not.toContain("<");
  });
});

describe("buildMagnetUri — round trip", () => {
  it("builds a url-encoded magnet that re-parses to the same fields", () => {
    const dn = "My Movie (2024) [1080p]";
    const trackers = ["udp://t.example:80/announce", "https://t2.example/x"];

    const uri = buildMagnetUri(HEX, dn, trackers);

    // url-encoding is applied (no raw spaces/parens leak into the URI).
    expect(uri).toContain(`xt=urn:btih:${HEX}`);
    expect(uri).toContain(`dn=${encodeURIComponent(dn)}`);
    expect(uri).not.toContain(" ");

    const reparsed = parseMagnetUri(uri);
    expect(reparsed.infohash).toBe(HEX);
    expect(reparsed.displayName).toBe(dn);
    expect(reparsed.trackers).toEqual(trackers);
  });

  it("throws ParseError when the infohash is invalid", () => {
    expect(() => buildMagnetUri("nope")).toThrow(ParseError);
  });
});

describe("dedupeMagnets", () => {
  it("collapses magnets with the same infohash (case-insensitive)", () => {
    const a = parseMagnetUri(`magnet:?xt=urn:btih:${HEX}&dn=First`);
    const bUpper: MagnetInfo = {
      ...a,
      uri: `magnet:?xt=urn:btih:${HEX.toUpperCase()}`,
      infohash: HEX.toUpperCase(),
      displayName: "Second",
    };
    const c = parseMagnetUri(
      "magnet:?xt=urn:btih:abcdefabcdefabcdefabcdefabcdefabcdefabcd",
    );

    const deduped = dedupeMagnets([a, bUpper, c]);

    expect(deduped).toHaveLength(2);
    // First-seen entry is preserved.
    expect(deduped[0]?.displayName).toBe("First");
    expect(deduped.map((m) => m.infohash.toLowerCase())).toEqual([
      HEX,
      "abcdefabcdefabcdefabcdefabcdefabcdefabcd",
    ]);
  });
});
