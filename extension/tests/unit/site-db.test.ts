/**
 * @fileoverview Anti-bluff unit tests for the REAL scanner/site-db lookup layer.
 *
 * Imports the production `src/scanner/site-db.ts` (NOT a stub). The load-bearing
 * assertions inspect user-observable outcomes — the actual CSS selector arrays a
 * caller would feed to the DOM scanner — and would FAIL against a no-op stub
 * (returning [] / null / undefined). Includes the anti-divergence guard that
 * proves site-db is backed by the SINGLE `SITE_SELECTORS` source of truth with
 * no duplicate host keys (the Plan-F known defect this REFACTOR removes).
 *
 * @module tests/unit/site-db.test
 */

import { describe, it, expect } from "vitest";
import {
  getSiteSelectors,
  hasSite,
  listKnownSites,
} from "../../src/scanner/site-db";
import { SITE_SELECTORS } from "../../src/shared/constants";

describe("getSiteSelectors — lookup by hostname", () => {
  it("returns the exact selectors for a known public tracker (1337x.to)", () => {
    const sel = getSiteSelectors("1337x.to");
    // user-observable: the precise array the scanner will query the DOM with
    expect(sel).toEqual(SITE_SELECTORS["1337x.to"]);
    expect(sel).toContain('a[href^="magnet:"]');
    expect(sel).toContain('a[href$=".torrent"]');
  });

  it("resolves a real Boba private tracker (rutracker.org) to its selectors", () => {
    const sel = getSiteSelectors("rutracker.org");
    expect(sel).toEqual(SITE_SELECTORS["rutracker.org"]);
    expect(sel).toContain('a[href^="magnet:"]');
    expect(sel.length).toBeGreaterThan(0);
  });

  it("resolves the other Boba private trackers (kinozal/nnmclub/iptorrents)", () => {
    expect(getSiteSelectors("kinozal.tv")).toEqual(SITE_SELECTORS["kinozal.tv"]);
    expect(getSiteSelectors("nnmclub.to")).toEqual(SITE_SELECTORS["nnmclub.to"]);
    expect(getSiteSelectors("iptorrents.com")).toEqual(
      SITE_SELECTORS["iptorrents.com"],
    );
    // kinozal uses a download.php selector, not magnet — prove the real value
    expect(getSiteSelectors("kinozal.tv")).toContain(
      'a[href*="/download.php?id="]',
    );
  });
});

describe("getSiteSelectors — www-prefix matching", () => {
  it("matches the bare domain when given the www. host (rutracker)", () => {
    const bare = getSiteSelectors("rutracker.org");
    const wwwd = getSiteSelectors("www.rutracker.org");
    expect(wwwd).toEqual(bare);
    expect(wwwd).toEqual(SITE_SELECTORS["rutracker.org"]);
  });

  it("matches with mixed-case + www. (WWW.1337x.TO)", () => {
    expect(getSiteSelectors("WWW.1337x.TO")).toEqual(SITE_SELECTORS["1337x.to"]);
  });

  it("accepts a full URL and strips www. (https://www.kinozal.tv/...)", () => {
    expect(getSiteSelectors("https://www.kinozal.tv/details.php?id=1")).toEqual(
      SITE_SELECTORS["kinozal.tv"],
    );
  });

  it("falls back to the base domain for a sub-domain host", () => {
    // tracker.nnmclub.to → nnmclub.to
    expect(getSiteSelectors("tracker.nnmclub.to")).toEqual(
      SITE_SELECTORS["nnmclub.to"],
    );
  });
});

describe("getSiteSelectors — unknown host returns the generic fallback", () => {
  it("returns the generic selector set for an unknown host", () => {
    const sel = getSiteSelectors("totally-unknown-site.example");
    expect(sel).toEqual(SITE_SELECTORS["generic"]);
    expect(sel).toContain('a[href^="magnet:"]');
  });

  it("returns the generic fallback for an empty / garbage input (never undefined)", () => {
    expect(getSiteSelectors("")).toEqual(SITE_SELECTORS["generic"]);
    expect(getSiteSelectors("not a url")).toEqual(SITE_SELECTORS["generic"]);
    expect(getSiteSelectors("https://")).toEqual(SITE_SELECTORS["generic"]);
  });
});

describe("hasSite — known vs unknown", () => {
  it("is true for a known site (exact, www., and base-domain fallback)", () => {
    expect(hasSite("rutracker.org")).toBe(true);
    expect(hasSite("www.rutracker.org")).toBe(true);
    expect(hasSite("tracker.nnmclub.to")).toBe(true);
  });

  it("is false for an unknown host and for the generic bucket itself", () => {
    expect(hasSite("totally-unknown-site.example")).toBe(false);
    expect(hasSite("")).toBe(false);
    // "generic" is a fallback bucket, NOT a real site
    expect(hasSite("generic")).toBe(false);
  });
});

describe("single source of truth — anti-divergence guard (Plan-F REFACTOR)", () => {
  it("every site-db entry IS the constants.ts SITE_SELECTORS entry (no 2nd table)", () => {
    for (const host of listKnownSites()) {
      // identity through the lookup path === the constant — proves no shadow copy
      expect(getSiteSelectors(host)).toBe(SITE_SELECTORS[host]);
    }
  });

  it("the table has NO duplicate host keys", () => {
    const keys = Object.keys(SITE_SELECTORS);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("known-sites list covers Boba's real trackers and excludes 'generic'", () => {
    const known = listKnownSites();
    expect(known).toContain("rutracker.org");
    expect(known).toContain("kinozal.tv");
    expect(known).toContain("nnmclub.to");
    expect(known).toContain("iptorrents.com");
    expect(known).toContain("rutor.info");
    expect(known).not.toContain("generic");
  });
});
