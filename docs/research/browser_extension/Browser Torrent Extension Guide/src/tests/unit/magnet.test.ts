/**
 * @fileoverview Unit tests for magnet link parser.
 *
 * Tests detection, parsing, validation, and building of magnet URIs.
 */

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
} from "../../src/parser/magnet";
import fixtures from "../fixtures/magnets.json";

describe("Magnet Parser", () => {
  describe("containsMagnetLink", () => {
    it("returns true for text containing magnet:?", () => {
      expect(containsMagnetLink("Here is a magnet:?xt=urn:btih:abc...")).toBe(true);
    });

    it("returns false for text without magnet:?", () => {
      expect(containsMagnetLink("Just some regular text")).toBe(false);
    });

    it("returns false for empty string", () => {
      expect(containsMagnetLink("")).toBe(false);
    });

    it("is case-insensitive", () => {
      expect(containsMagnetLink("MAGNET:?XT=URN:BTIH:ABC...")).toBe(true);
    });
  });

  describe("findMagnetUris", () => {
    it("finds all magnet URIs in text", () => {
      const text = fixtures.magnetsInText.text;
      const uris = findMagnetUris(text);
      expect(uris.length).toBe(fixtures.magnetsInText.expectedCount);
    });

    it("returns empty array for text without magnets", () => {
      expect(findMagnetUris("No magnets here")).toEqual([]);
    });

    it("deduplicates identical URIs", () => {
      const uri = fixtures.validMagnets[0].uri;
      const text = `${uri} and ${uri}`;
      expect(findMagnetUris(text).length).toBe(1);
    });

    it("returns empty array for empty string", () => {
      expect(findMagnetUris("")).toEqual([]);
    });
  });

  describe("extractInfohash", () => {
    it("extracts 40-char hex infohash from valid magnet", () => {
      const uri = fixtures.validMagnets[0].uri;
      const hash = extractInfohash(uri);
      expect(hash).toBe(fixtures.validMagnets[0].infohash);
    });

    it("returns null for non-magnet URI", () => {
      expect(extractInfohash("http://example.com")).toBeNull();
    });

    it("returns null for magnet without btih", () => {
      expect(extractInfohash("magnet:?dn=test")).toBeNull();
    });

    it("handles uppercase infohash", () => {
      const uri = "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12";
      const hash = extractInfohash(uri);
      expect(hash).toBe("abcdef1234567890abcdef1234567890abcdef12");
    });
  });

  describe("isValidHexInfohash", () => {
    it("returns true for 40-char hex string", () => {
      expect(isValidHexInfohash("1234567890abcdef1234567890abcdef12345678")).toBe(true);
    });

    it("returns true for 40-char uppercase hex", () => {
      expect(isValidHexInfohash("ABCDEF1234567890ABCDEF1234567890ABCDEF12")).toBe(true);
    });

    it("returns false for 39-char string", () => {
      expect(isValidHexInfohash("1234567890abcdef1234567890abcdef1234567")).toBe(false);
    });

    it("returns false for non-hex characters", () => {
      expect(isValidHexInfohash("gggggggggggggggggggggggggggggggggggggggg")).toBe(false);
    });

    it("returns false for empty string", () => {
      expect(isValidHexInfohash("")).toBe(false);
    });
  });

  describe("isValidBase32Infohash", () => {
    it("returns true for 32-char base32 string", () => {
      expect(isValidBase32Infohash("MFRGGZDFMZTWQ2LKMNZXC4ZTFMRXCXBO")).toBe(true);
    });

    it("returns false for 31-char string", () => {
      expect(isValidBase32Infohash("MFRGGZDFMZTWQ2LKMNZXC4ZTFMRXCXB")).toBe(false);
    });

    it("returns false for non-base32 characters", () => {
      expect(isValidBase32Infohash("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")).toBe(false);
    });
  });

  describe("base32ToHex", () => {
    it("converts valid base32 to 40-char hex", () => {
      const { base32, hex } = fixtures.base32Infohash;
      const result = base32ToHex(base32);
      expect(result).toBe(hex);
      expect(result.length).toBe(40);
    });

    it("throws for invalid base32", () => {
      expect(() => base32ToHex("invalid")).toThrow();
    });
  });

  describe("parseMagnetUri", () => {
    it("parses a complete magnet URI with all fields", () => {
      const fixture = fixtures.validMagnets[0];
      const result = parseMagnetUri(fixture.uri);

      expect(result.infohash).toBe(fixture.infohash);
      expect(result.displayName).toBe(fixture.displayName);
      expect(result.uri).toBe(fixture.uri);
      expect(result.sourceElement).toBeNull();
    });

    it("parses magnet with trackers", () => {
      const fixture = fixtures.validMagnets[1];
      const result = parseMagnetUri(fixture.uri);

      expect(result.trackers).toEqual(fixture.trackers);
    });

    it("parses magnet with multiple trackers", () => {
      const fixture = fixtures.validMagnets[2];
      const result = parseMagnetUri(fixture.uri);

      expect(result.trackers.length).toBe(2);
      expect(result.trackers).toEqual(fixture.trackers);
    });

    it("parses magnet with web seeds", () => {
      const fixture = fixtures.validMagnets[3];
      const result = parseMagnetUri(fixture.uri);

      expect(result.webSeeds.length).toBe(1);
      expect(result.webSeeds[0]).toBe(fixture.webSeeds[0]);
    });

    it("handles magnet without display name", () => {
      const fixture = fixtures.validMagnets[4];
      const result = parseMagnetUri(fixture.uri);

      expect(result.infohash).toBe(fixture.infohash);
      expect(result.displayName).toBeNull();
    });

    it("throws for non-magnet URI", () => {
      expect(() => parseMagnetUri("http://example.com")).toThrow();
    });

    it("throws for magnet without valid infohash", () => {
      expect(() => parseMagnetUri("magnet:?dn=test")).toThrow();
    });

    it("stores source element when provided", () => {
      const fixture = fixtures.validMagnets[0];
      const mockElement = document.createElement("a");
      const result = parseMagnetUri(fixture.uri, mockElement);

      expect(result.sourceElement).toBe(mockElement);
    });

    it("normalizes infohash to lowercase", () => {
      const uri = "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12";
      const result = parseMagnetUri(uri);
      expect(result.infohash).toBe("abcdef1234567890abcdef1234567890abcdef12");
    });
  });

  describe("buildMagnetUri", () => {
    it("builds minimal magnet URI with just infohash", () => {
      const hash = "1234567890abcdef1234567890abcdef12345678";
      const uri = buildMagnetUri(hash);

      expect(uri).toBe(`magnet:?xt=urn:btih:${hash}`);
    });

    it("builds magnet URI with display name", () => {
      const hash = "1234567890abcdef1234567890abcdef12345678";
      const uri = buildMagnetUri(hash, "My File");

      expect(uri).toBe(`magnet:?xt=urn:btih:${hash}&dn=My+File`);
    });

    it("builds magnet URI with trackers", () => {
      const hash = "1234567890abcdef1234567890abcdef12345678";
      const trackers = ["udp://tracker1.com:80", "udp://tracker2.com:80"];
      const uri = buildMagnetUri(hash, "My File", trackers);

      expect(uri).toContain("tr=udp%3A%2F%2Ftracker1.com%3A80");
      expect(uri).toContain("tr=udp%3A%2F%2Ftracker2.com%3A80");
    });

    it("throws for invalid infohash", () => {
      expect(() => buildMagnetUri("invalid")).toThrow();
    });
  });

  describe("getMagnetDisplayName", () => {
    it("returns display name when available", () => {
      const magnet = parseMagnetUri(fixtures.validMagnets[0].uri);
      expect(getMagnetDisplayName(magnet)).toBe("Ubuntu 22.04 LTS");
    });

    it("returns truncated infohash when no display name", () => {
      const magnet = parseMagnetUri(fixtures.validMagnets[4].uri);
      const name = getMagnetDisplayName(magnet);
      expect(name).toContain("Torrent ");
      expect(name).toContain("...");
    });
  });
});
