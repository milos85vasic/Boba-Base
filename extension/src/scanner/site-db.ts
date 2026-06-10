/**
 * @fileoverview Site-selector database lookup for the BobaLink scanner.
 *
 * REFACTOR note (Plan F, scanner/site-db = REFACTOR — known defect): the
 * reference shipped TWO divergent site-selector tables — `SITE_SELECTORS` in
 * `shared/constants.ts` AND a second, richer `SITES` map redefined inside this
 * file. They drifted apart (different domains, different selector lists). This
 * module is now a THIN LOOKUP LAYER over the SINGLE source of truth — the merged
 * `SITE_SELECTORS` constant in `shared/constants.ts` (which the Phase-1
 * foundation already collapsed + extended with Boba's real trackers). NO second
 * table is defined here; we import and wrap the one constant.
 *
 * Behaviour (per _analysis/05-src-features.md + _analysis/02 Dim08): look up a
 * site's CSS selectors by hostname, with `www.` prefix stripping and
 * sub-domain → base-domain fallback. Unknown hosts fall back to the generic
 * selector set.
 *
 * @module scanner/site-db
 */

import { SITE_SELECTORS } from "../shared/constants";
import { getDomain } from "../shared/utils";

/**
 * The generic fallback selector set, used when a host is not in the DB.
 * Sourced from the single `SITE_SELECTORS` table — never redefined here.
 */
const GENERIC_SELECTORS: readonly string[] = SITE_SELECTORS["generic"] ?? [];

/**
 * Normalize a hostname for lookup: lower-case + strip a single leading `www.`.
 *
 * @param hostname - Raw hostname (e.g. "WWW.RuTracker.org")
 * @returns Normalized hostname (e.g. "rutracker.org")
 */
function normalizeHostname(hostname: string): string {
  const lower = hostname.trim().toLowerCase();
  return lower.startsWith("www.") ? lower.slice(4) : lower;
}

/**
 * Resolve an input that may be a bare hostname OR a full URL into a hostname.
 * A bare hostname (no scheme) is returned as-is; a URL is parsed via getDomain.
 *
 * @param hostnameOrUrl - "rutracker.org" or "https://rutracker.org/forum/..."
 * @returns The hostname component, or the trimmed input if not a URL
 */
function toHostname(hostnameOrUrl: string): string {
  const trimmed = hostnameOrUrl.trim();
  if (trimmed.includes("://")) {
    return getDomain(trimmed);
  }
  return trimmed;
}

/**
 * Find the table key matching a hostname, applying:
 *   1. exact match on the normalized hostname,
 *   2. base-domain fallback (strip sub-domains down to the last two labels).
 *
 * @param hostnameOrUrl - Hostname or URL to match
 * @returns The matching `SITE_SELECTORS` key, or null when no entry matches
 */
function matchKey(hostnameOrUrl: string): string | null {
  const host = normalizeHostname(toHostname(hostnameOrUrl));
  if (host === "") {
    return null;
  }

  // 1. exact host match
  if (host !== "generic" && Object.prototype.hasOwnProperty.call(SITE_SELECTORS, host)) {
    return host;
  }

  // 2. base-domain fallback (e.g. "tracker.rutracker.org" → "rutracker.org")
  const parts = host.split(".");
  if (parts.length > 2) {
    const base = parts.slice(-2).join(".");
    if (base !== "generic" && Object.prototype.hasOwnProperty.call(SITE_SELECTORS, base)) {
      return base;
    }
  }

  return null;
}

/**
 * Get the CSS selectors for a hostname (or URL).
 *
 * Returns the site-specific selectors when the host is known (with `www.`
 * stripping + sub-domain fallback), otherwise the generic selector set. Always
 * returns a non-empty-or-generic array — never undefined.
 *
 * @param hostnameOrUrl - "rutracker.org" or "https://rutracker.org/..."
 * @returns The CSS selector list for the site, or the generic fallback
 */
export function getSiteSelectors(hostnameOrUrl: string): readonly string[] {
  const key = matchKey(hostnameOrUrl);
  if (key === null) {
    return GENERIC_SELECTORS;
  }
  return SITE_SELECTORS[key] ?? GENERIC_SELECTORS;
}

/**
 * Check whether a hostname (or URL) is a known site in the DB.
 *
 * The `generic` fallback bucket is NOT a "site" — `hasSite("generic")` is false.
 *
 * @param hostnameOrUrl - Hostname or URL to check
 * @returns True when the host resolves to a specific (non-generic) entry
 */
export function hasSite(hostnameOrUrl: string): boolean {
  return matchKey(hostnameOrUrl) !== null;
}

/**
 * List every known site key (the single source of truth, minus the generic
 * fallback bucket). Useful for diagnostics and the anti-divergence guard.
 *
 * @returns Sorted array of known host keys
 */
export function listKnownSites(): readonly string[] {
  return Object.freeze(
    Object.keys(SITE_SELECTORS)
      .filter((k) => k !== "generic")
      .sort(),
  );
}
