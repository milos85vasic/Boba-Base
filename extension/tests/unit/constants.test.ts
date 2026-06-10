/**
 * @fileoverview Anti-bluff unit tests for the REAL constants module + the
 * port-retarget regression guard.
 *
 * Imports the production `src/shared/constants.ts` and `src/types/config.ts`.
 * The load-bearing assertions FAIL if any retargeted constant still says 8080
 * (the reference's wrong qBittorrent port). Also asserts the magnet/infohash
 * regexes actually match/reject real values (user-observable behaviour), and
 * that the site-selector registry covers Boba's real private trackers.
 *
 * @module tests/unit/constants.test
 */

import { describe, it, expect } from "vitest";
import {
  DEFAULT_PORTS,
  DEFAULT_URLS,
  MAGNET_REGEX,
  MAGNET_VALIDATION_REGEX,
  INFOHASH_REGEX,
  INFOHASH_HEX_REGEX,
  TORRENT_FILE_VALIDATION_REGEX,
  SITE_SELECTORS,
  ENCRYPTION,
} from "../../src/shared/constants";
import { DEFAULT_AUTO_DISCOVERY } from "../../src/types/config";

const VALID_HASH = "1234567890abcdef1234567890abcdef12345678";

describe("port retarget 8080 → 7187 (regression guard)", () => {
  it("DEFAULT_PORTS.QBITTORRENT is 7187, never 8080", () => {
    expect(DEFAULT_PORTS.QBITTORRENT).toBe(7187);
    expect(DEFAULT_PORTS.QBITTORRENT).not.toBe(8080);
  });

  it("DEFAULT_URLS contain no :8080 anywhere", () => {
    const all = Object.values(DEFAULT_URLS).join(" ");
    expect(all).not.toContain("8080");
    expect(DEFAULT_URLS.QBITTORRENT).toBe("http://localhost:7187");
  });

  it("no DEFAULT_PORTS value equals 8080", () => {
    expect(Object.values(DEFAULT_PORTS)).not.toContain(8080);
  });

  it("DEFAULT_AUTO_DISCOVERY.ports drop 8080 and keep the Boba ports", () => {
    expect(DEFAULT_AUTO_DISCOVERY.ports).not.toContain(8080);
    expect(DEFAULT_AUTO_DISCOVERY.ports).toContain(7187);
    expect(DEFAULT_AUTO_DISCOVERY.ports).toContain(7189);
  });
});

describe("magnet / infohash / torrent regexes match real values", () => {
  it("MAGNET_REGEX detects a magnet URI in surrounding text", () => {
    const text = `prefix magnet:?xt=urn:btih:${VALID_HASH}&dn=Demo suffix`;
    const matches = text.match(MAGNET_REGEX);
    expect(matches).not.toBeNull();
    expect(matches?.[0]).toContain(VALID_HASH);
  });

  it("MAGNET_VALIDATION_REGEX accepts valid and rejects malformed magnets", () => {
    expect(MAGNET_VALIDATION_REGEX.test(`magnet:?xt=urn:btih:${VALID_HASH}`)).toBe(
      true,
    );
    expect(MAGNET_VALIDATION_REGEX.test("magnet:?xt=urn:btih:tooshort")).toBe(
      false,
    );
  });

  it("INFOHASH_REGEX extracts the 40-char hash", () => {
    const m = `magnet:?xt=urn:btih:${VALID_HASH}`.match(INFOHASH_REGEX);
    expect(m?.[1]).toBe(VALID_HASH);
  });

  it("INFOHASH_HEX_REGEX validates a 40-char hex string", () => {
    expect(INFOHASH_HEX_REGEX.test(VALID_HASH)).toBe(true);
    expect(INFOHASH_HEX_REGEX.test("xyz")).toBe(false);
  });

  it("TORRENT_FILE_VALIDATION_REGEX accepts a .torrent url", () => {
    expect(
      TORRENT_FILE_VALIDATION_REGEX.test("https://site.tld/file.torrent"),
    ).toBe(true);
    expect(TORRENT_FILE_VALIDATION_REGEX.test("https://site.tld/file.zip")).toBe(
      false,
    );
  });
});

describe("site-selector registry (single source of truth)", () => {
  it("includes a generic fallback entry", () => {
    expect(SITE_SELECTORS.generic).toBeDefined();
    expect(SITE_SELECTORS.generic).toContain('a[href^="magnet:"]');
  });

  it("covers Boba's real private trackers", () => {
    expect(SITE_SELECTORS["rutracker.org"]).toBeDefined();
    expect(SITE_SELECTORS["kinozal.tv"]).toBeDefined();
    expect(SITE_SELECTORS["nnmclub.to"]).toBeDefined();
    expect(SITE_SELECTORS["iptorrents.com"]).toBeDefined();
  });
});

describe("encryption parameters are the sound AES-256-GCM + PBKDF2 set", () => {
  it("declares AES-256-GCM with PBKDF2 100k iterations", () => {
    expect(ENCRYPTION.ALGORITHM).toBe("AES-GCM");
    expect(ENCRYPTION.KEY_LENGTH_BITS).toBe(256);
    expect(ENCRYPTION.KDF_ALGORITHM).toBe("PBKDF2");
    expect(ENCRYPTION.KDF_ITERATIONS).toBe(100000);
    expect(ENCRYPTION.IV_LENGTH_BYTES).toBe(12);
    expect(ENCRYPTION.SALT_LENGTH_BYTES).toBe(16);
  });
});
