/**
 * @fileoverview Site-specific scanner database for BobaLink.
 *
 * Maintains CSS selectors and custom detection logic for popular torrent sites.
 * When visiting a known site, the orchestrator uses these optimized selectors
 * instead of generic scanning, improving accuracy and performance.
 *
 * @module scanner/site-db
 */

import { SITE_SELECTORS } from "../shared/constants";
import { getDomain } from "../shared/utils";

/**
 * Information about a known torrent site.
 */
export interface SiteConfig {
  /** Domain name */
  readonly domain: string;

  /** Human-readable site name */
  readonly name: string;

  /** CSS selectors for torrent links on this site */
  readonly selectors: readonly string[];

  /** Whether this site requires authentication */
  readonly private: boolean;

  /** Known URL patterns for this site */
  readonly urlPatterns: readonly RegExp[];

  /** Whether the site uses JavaScript to load torrent links dynamically */
  readonly dynamicContent: boolean;

  /** Recommended debounce delay for mutation observer on this site */
  readonly mutationDebounceMs: number;
}

/**
 * Database of known torrent sites with optimized selectors.
 */
const SITES: Readonly<Record<string, SiteConfig>> = {
  "1337x.to": {
    domain: "1337x.to",
    name: "1337x",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
      'a[href*="/torrent/"]',
    ],
    private: false,
    urlPatterns: [/^https?:\/\/(www\.)?1337x\.to/i],
    dynamicContent: false,
    mutationDebounceMs: 500,
  },
  "thepiratebay.org": {
    domain: "thepiratebay.org",
    name: "The Pirate Bay",
    selectors: ['a[href^="magnet:"]'],
    private: false,
    urlPatterns: [
      /^https?:\/\/(www\.)?thepiratebay\.org/i,
      /^https?:\/\/(www\.)?thepiratebay10\.org/i,
    ],
    dynamicContent: true,
    mutationDebounceMs: 800,
  },
  "rarbg.to": {
    domain: "rarbg.to",
    name: "RARBG",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
      'a[href*="/download.php"]',
    ],
    private: false,
    urlPatterns: [/^https?:\/\/(www\.)?rarbg\.(to|accessed|proxy)/i],
    dynamicContent: false,
    mutationDebounceMs: 500,
  },
  "yts.mx": {
    domain: "yts.mx",
    name: "YTS",
    selectors: ['a[href^="magnet:"]'],
    private: false,
    urlPatterns: [
      /^https?:\/\/(www\.)?yts\.(mx|lt|ag)/i,
    ],
    dynamicContent: false,
    mutationDebounceMs: 500,
  },
  "eztv.re": {
    domain: "eztv.re",
    name: "EZTV",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
    ],
    private: false,
    urlPatterns: [/^https?:\/\/(www\.)?eztv\.(re|io|ag)/i],
    dynamicContent: true,
    mutationDebounceMs: 600,
  },
  "nyaa.si": {
    domain: "nyaa.si",
    name: "Nyaa",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
      'a[href*="/download/"]',
    ],
    private: false,
    urlPatterns: [/^https?:\/\/(www\.)?nyaa\.(si|net)/i],
    dynamicContent: false,
    mutationDebounceMs: 400,
  },
  "limetorrents.lol": {
    domain: "limetorrents.lol",
    name: "LimeTorrents",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
    ],
    private: false,
    urlPatterns: [/^https?:\/\/(www\.)?limetorrents\./i],
    dynamicContent: false,
    mutationDebounceMs: 500,
  },
  "torrentgalaxy.to": {
    domain: "torrentgalaxy.to",
    name: "TorrentGalaxy",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
      'a[href*="/download.php"]',
    ],
    private: false,
    urlPatterns: [/^https?:\/\/(www\.)?torrentgalaxy\./i],
    dynamicContent: true,
    mutationDebounceMs: 700,
  },
  "fitgirl-repacks.site": {
    domain: "fitgirl-repacks.site",
    name: "FitGirl Repacks",
    selectors: ['a[href^="magnet:"]'],
    private: false,
    urlPatterns: [/^https?:\/\/(www\.)?fitgirl-repacks\.site/i],
    dynamicContent: false,
    mutationDebounceMs: 500,
  },
  "rutracker.org": {
    domain: "rutracker.org",
    name: "RuTracker",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
      'a.dl-stub',
    ],
    private: true,
    urlPatterns: [/^https?:\/\/(www\.)?rutracker\./i],
    dynamicContent: false,
    mutationDebounceMs: 500,
  },
  "animetosho.org": {
    domain: "animetosho.org",
    name: "AnimeTosho",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
      'a[href*="/download/"]',
    ],
    private: false,
    urlPatterns: [/^https?:\/\/(www\.)?animetosho\.org/i],
    dynamicContent: true,
    mutationDebounceMs: 600,
  },
  "demonoid.is": {
    domain: "demonoid.is",
    name: "Demonoid",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
    ],
    private: false,
    urlPatterns: [/^https?:\/\/(www\.)?demonoid\./i],
    dynamicContent: false,
    mutationDebounceMs: 500,
  },
  "iptorrents.com": {
    domain: "iptorrents.com",
    name: "IPTorrents",
    selectors: [
      'a[href$=".torrent"]',
      'a[href*="download.php"]',
    ],
    private: true,
    urlPatterns: [/^https?:\/\/(www\.)?iptorrents\./i],
    dynamicContent: false,
    mutationDebounceMs: 400,
  },
  "torrentleech.org": {
    domain: "torrentleech.org",
    name: "TorrentLeech",
    selectors: [
      'a[href$=".torrent"]',
      'a[href*="/download/"]',
    ],
    private: true,
    urlPatterns: [/^https?:\/\/(www\.)?torrentleech\./i],
    dynamicContent: false,
    mutationDebounceMs: 400,
  },
  "beyond-hd.me": {
    domain: "beyond-hd.me",
    name: "BeyondHD",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
    ],
    private: true,
    urlPatterns: [/^https?:\/\/(www\.)?beyond-hd\./i],
    dynamicContent: false,
    mutationDebounceMs: 500,
  },
  "passthepopcorn.me": {
    domain: "passthepopcorn.me",
    name: "PassThePopcorn",
    selectors: [
      'a[href^="magnet:"]',
      'a[href$=".torrent"]',
    ],
    private: true,
    urlPatterns: [/^https?:\/\/(www\.)?passthepopcorn\./i],
    dynamicContent: true,
    mutationDebounceMs: 800,
  },
};

/**
 * Get site configuration for the current page.
 *
 * @param url - URL to match against known sites
 * @returns SiteConfig if matched, null otherwise
 */
export function getSiteConfig(url: string): SiteConfig | null {
  const domain = getDomain(url);

  // Try exact domain match
  if (domain in SITES) {
    return SITES[domain];
  }

  // Try pattern matching
  for (const site of Object.values(SITES)) {
    for (const pattern of site.urlPatterns) {
      if (pattern.test(url)) {
        return site;
      }
    }
  }

  // Try base domain match (strip subdomains)
  const parts = domain.split(".");
  if (parts.length > 2) {
    const baseDomain = parts.slice(-2).join(".");
    if (baseDomain in SITES) {
      return SITES[baseDomain];
    }
  }

  return null;
}

/**
 * Get CSS selectors for a URL.
 * Returns site-specific selectors if known, otherwise generic ones.
 *
 * @param url - URL to get selectors for
 * @returns Array of CSS selectors
 */
export function getSelectorsForUrl(url: string): readonly string[] {
  const site = getSiteConfig(url);
  return site?.selectors ?? SITE_SELECTORS["generic"];
}

/**
 * Get the recommended mutation observer debounce delay for a URL.
 *
 * @param url - URL to get debounce for
 * @returns Debounce delay in milliseconds
 */
export function getMutationDebounceForUrl(url: string): number {
  const site = getSiteConfig(url);
  return site?.mutationDebounceMs ?? 500;
}

/**
 * Check if a URL is a known torrent site.
 *
 * @param url - URL to check
 * @returns True if the site is in our database
 */
export function isKnownTorrentSite(url: string): boolean {
  return getSiteConfig(url) !== null;
}

/**
 * Get the display name for a torrent site.
 *
 * @param url - URL of the site
 * @returns Human-readable site name, or the domain as fallback
 */
export function getSiteName(url: string): string {
  const site = getSiteConfig(url);
  return site?.name ?? getDomain(url);
}

/**
 * List all known torrent sites.
 *
 * @returns Array of site configurations
 */
export function listKnownSites(): readonly SiteConfig[] {
  return Object.freeze(Object.values(SITES));
}
