/**
 * @fileoverview Magnet link parser for BobaLink (Phase 2 port).
 *
 * Provides fast detection and full parsing of magnet URI scheme links.
 * Supports BTIH (BitTorrent Info Hash) in hex and base32 formats,
 * multiple trackers, display names, and all standard magnet parameters
 * (xt / dn / tr / ws / xl / xs / kt / as / mt).
 *
 * Ported from the reference parser (ADOPT per F-adopt-vs-rewrite) with two
 * Boba hardening additions mandated by _analysis/05-src-features.md:
 *   1. The `dn` (display name) is XSS-sanitized to inert plain text
 *      (textContent-style — HTML markup and `<script>` payloads are
 *      neutralized, never live HTML). The sanitizer is DOM-independent so
 *      it is safe to run inside a background / service-worker context that
 *      has no `document`.
 *   2. A display-name fallback to `"Unknown"` is available via
 *      {@link getMagnetDisplayNameOrUnknown} when no `dn` is present.
 *
 * Performance optimized for scanning large DOM trees.
 *
 * @module parser/magnet
 */

import {
  MAGNET_REGEX,
  MAGNET_VALIDATION_REGEX,
  INFOHASH_REGEX,
  INFOHASH_HEX_REGEX,
  INFOHASH_BASE32_REGEX,
} from "../shared/constants";
import { ParseError } from "../shared/errors";
import { createLogger } from "../shared/logger";
import type { MagnetInfo } from "../types/torrent";

const log = createLogger("MagnetParser");

/** Fallback display name when a magnet has no usable `dn` parameter. */
export const MAGNET_DISPLAY_NAME_FALLBACK = "Unknown";

/**
 * Sanitize an untrusted magnet `dn` (display name) into inert plain text.
 *
 * The `dn` parameter is attacker-controlled (it travels in the URI verbatim),
 * so it must never reach the DOM as live HTML. This produces a
 * "textContent-style" string: HTML tags are stripped, any residual angle
 * brackets and ampersands are neutralized so nothing can be re-interpreted as
 * markup, and control characters are removed. Implemented WITHOUT touching
 * `document`, so it works in a service-worker / background context too.
 *
 * @param raw - The raw, decoded `dn` value
 * @returns A safe, markup-free display name (may be empty)
 */
export function sanitizeDisplayName(raw: string): string {
  // 1. Strip any HTML/XML tags outright (e.g. `<script>...</script>`,
  //    `<img onerror=...>`). The tag body excludes `<` (not just `>`): a real
  //    tag never contains a `<`, and excluding it makes a hostile run of `<`
  //    with no closing `>` (e.g. `"<".repeat(100000)`) strip in LINEAR time
  //    instead of the O(n^2) backtracking `<[^>]*>` exhibits on that input —
  //    a content-script DoS / ReDoS-class hang on attacker-controlled page text.
  let out = raw.replace(/<[^<>]*>/g, "");

  // 2. Neutralize any leftover markup-significant characters so a partial /
  //    malformed tag (e.g. a lone `<script` with no closing `>`) cannot be
  //    re-interpreted as live HTML by a downstream consumer.
  out = out
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

  // 3. Drop control characters (NUL, etc.) that have no place in a name.
  // eslint-disable-next-line no-control-regex
  out = out.replace(/[\x00-\x1f\x7f]/g, "");

  return out.trim();
}

/**
 * Check if a string contains a potential magnet link.
 * Fast check before full parsing - just looks for the prefix.
 *
 * @param text - Text to check
 * @returns True if text contains what looks like a magnet link
 */
export function containsMagnetLink(text: string): boolean {
  return text.includes("magnet:?");
}

/**
 * Find all magnet URIs in a text string.
 *
 * @param text - Text to search for magnet links
 * @returns Array of full magnet URI strings found (deduplicated, validated)
 */
export function findMagnetUris(text: string): string[] {
  if (!containsMagnetLink(text)) return [];

  const matches = text.match(MAGNET_REGEX);
  if (!matches) return [];

  // Deduplicate case-insensitively and keep only valid full magnet URIs.
  const seen = new Set<string>();
  const results: string[] = [];

  for (const match of matches) {
    const normalized = match.toLowerCase();
    if (!seen.has(normalized)) {
      seen.add(normalized);
      if (MAGNET_VALIDATION_REGEX.test(match)) {
        results.push(match);
      }
    }
  }

  return results;
}

/**
 * Extract the infohash from a magnet URI.
 *
 * @param magnetUri - The magnet URI to parse
 * @returns The 40-character hex infohash (lowercased), or null if invalid
 */
export function extractInfohash(magnetUri: string): string | null {
  const match = magnetUri.match(INFOHASH_REGEX);
  if (match?.[1]) {
    const hash = match[1].toLowerCase();
    if (INFOHASH_HEX_REGEX.test(hash)) {
      return hash;
    }
  }
  return null;
}

/**
 * Validate a 40-character hex infohash.
 *
 * @param infohash - The infohash to validate
 * @returns True if valid hex infohash
 */
export function isValidHexInfohash(infohash: string): boolean {
  return INFOHASH_HEX_REGEX.test(infohash);
}

/**
 * Validate a 32-character base32 infohash.
 *
 * @param infohash - The infohash to validate
 * @returns True if valid base32 infohash
 */
export function isValidBase32Infohash(infohash: string): boolean {
  return INFOHASH_BASE32_REGEX.test(infohash);
}

/**
 * Convert a base32 infohash to hex format.
 *
 * RFC 4648 base32: each char → 5 bits, grouped into 4-bit nibbles → hex.
 * A 32-char base32 string yields 160 bits = 40 hex characters.
 *
 * @param base32Hash - 32-character base32 string
 * @returns 40-character hex string
 * @throws ParseError if the base32 string is invalid
 */
export function base32ToHex(base32Hash: string): string {
  if (!isValidBase32Infohash(base32Hash)) {
    throw new ParseError(`Invalid base32 infohash: ${base32Hash}`);
  }

  // Base32 alphabet (RFC 4648)
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";

  // Convert each base32 char to 5 bits
  for (const char of base32Hash.toUpperCase()) {
    const val = alphabet.indexOf(char);
    if (val === -1) {
      throw new ParseError(`Invalid base32 character: ${char}`);
    }
    bits += val.toString(2).padStart(5, "0");
  }

  // Group into 4-bit nibbles and convert to hex
  let hex = "";
  for (let i = 0; i < bits.length; i += 4) {
    const nibble = bits.slice(i, i + 4);
    if (nibble.length === 4) {
      hex += parseInt(nibble, 2).toString(16);
    }
  }

  return hex;
}

/**
 * Parse a magnet URI into a structured MagnetInfo object.
 *
 * Handles all standard BitTorrent magnet parameters:
 * - xt (exact topic): The infohash (hex or base32 btih)
 * - dn (display name): Human-readable name — XSS-sanitized to inert text
 * - tr (tracker): Tracker URL (can be multiple)
 * - ws (web seed): Web seed URL (can be multiple)
 * - xl (exact length): File size in bytes
 * - xs (exact source): Direct .torrent file URL
 * - as (acceptable source): Fallback source URL
 * - kt (keyword topic): Search keywords
 * - mt (manifest topic): Link to a manifest
 *
 * @param magnetUri - The full magnet URI to parse
 * @param sourceElement - Optional DOM element that contained this link
 * @returns Parsed MagnetInfo object
 * @throws ParseError if the URI is not a valid magnet link
 */
export function parseMagnetUri(
  magnetUri: string,
  sourceElement: Element | null = null,
): MagnetInfo {
  const endTimer = log.timed(`parseMagnetUri: ${truncateForLog(magnetUri)}`);

  try {
    // Validate basic format
    if (!magnetUri.toLowerCase().startsWith("magnet:?")) {
      throw new ParseError(`Not a magnet URI: ${truncateForLog(magnetUri)}`, {
        context: { uri: magnetUri },
      });
    }

    // Extract infohash (hex form)
    const infohash = extractInfohash(magnetUri);
    if (!infohash) {
      // Try base32 format: convert to hex and re-parse the rewritten URI.
      const base32Match = magnetUri.match(/xt=urn:btih:([A-Z2-7]{32})/i);
      if (base32Match?.[1]) {
        const hexHash = base32ToHex(base32Match[1]);
        return parseMagnetUri(
          magnetUri.replace(
            /xt=urn:btih:[A-Z2-7]{32}/i,
            `xt=urn:btih:${hexHash}`,
          ),
          sourceElement,
        );
      }

      throw new ParseError(
        `No valid BTIH infohash found in magnet URI: ${truncateForLog(magnetUri)}`,
        { context: { uri: magnetUri } },
      );
    }

    // Manually parse parameters so repeated keys (multiple tr, xt) are kept.
    const queryString = magnetUri.substring("magnet:?".length);
    const params = new Map<string, string[]>();
    const pairs = queryString.split(/&|;/);

    for (const pair of pairs) {
      const eqIndex = pair.indexOf("=");
      if (eqIndex === -1) continue;

      const key = pair.substring(0, eqIndex);
      let value: string;
      try {
        value = decodeURIComponent(pair.substring(eqIndex + 1));
      } catch {
        // Malformed percent-encoding: keep the raw value rather than throwing.
        value = pair.substring(eqIndex + 1);
      }

      const existing = params.get(key);
      if (existing) {
        existing.push(value);
      } else {
        params.set(key, [value]);
      }
    }

    // Handle multiple xt params (DHT backup hashes); primary is first.
    const xtParams = params.get("xt") ?? [];
    const primaryXt = xtParams[0] ?? "";
    const primaryMatch = primaryXt.match(/urn:btih:([a-fA-F0-9]{40})/i);
    const finalInfohash = (primaryMatch?.[1] ?? infohash).toLowerCase();

    // Trackers (multiple tr params)
    const trackers = params.get("tr") ?? [];

    // Web seeds (multiple ws params)
    const webSeeds = params.get("ws") ?? [];

    // Display name — XSS-sanitized. Absent / empty-after-sanitize → null
    // (the MagnetInfo contract keeps `displayName: string | null`; the
    // "Unknown" fallback is applied by getMagnetDisplayNameOrUnknown).
    const rawDn = params.get("dn")?.[0];
    const sanitizedDn =
      rawDn !== undefined ? sanitizeDisplayName(rawDn) : "";
    const displayName = sanitizedDn.length > 0 ? sanitizedDn : null;

    // Exact length
    const xlRaw = params.get("xl")?.[0];
    const parsedXl = xlRaw !== undefined ? parseInt(xlRaw, 10) : NaN;
    const exactLength = Number.isFinite(parsedXl) ? parsedXl : null;

    // Exact source (.torrent URL)
    const exactSource = params.get("xs")?.[0] ?? null;

    // Keywords
    const ktRaw = params.get("kt")?.[0];
    const keywords =
      ktRaw !== undefined && ktRaw.length > 0 ? ktRaw.split(/[+\s]+/) : [];

    // Acceptable source
    const acceptableSource = params.get("as")?.[0] ?? null;

    // Manifest
    const manifest = params.get("mt")?.[0] ?? null;

    endTimer();

    return {
      uri: magnetUri,
      infohash: finalInfohash,
      displayName,
      trackers,
      webSeeds,
      exactLength,
      exactSource,
      keywords,
      acceptableSource,
      manifest,
      detectedAt: Date.now(),
      sourceElement,
    };
  } catch (err) {
    if (err instanceof ParseError) throw err;
    // Build options conditionally: under `exactOptionalPropertyTypes` the
    // optional `cause?: Error` must be OMITTED (not set to undefined) when no
    // Error cause is available.
    const options: { cause?: Error; context: { uri: string } } = {
      context: { uri: magnetUri },
    };
    if (err instanceof Error) {
      options.cause = err;
    }
    throw new ParseError(`Failed to parse magnet URI: ${String(err)}`, options);
  }
}

/**
 * Generate a magnet URI from components.
 * Useful for reconstructing magnet links with modifications.
 *
 * @param infohash - 40-character hex infohash (required)
 * @param displayName - Optional display name (url-encoded into `dn`)
 * @param trackers - Optional tracker URLs (url-encoded into `tr`)
 * @returns Constructed magnet URI
 * @throws ParseError if infohash is invalid
 */
export function buildMagnetUri(
  infohash: string,
  displayName?: string,
  trackers?: readonly string[],
): string {
  if (!isValidHexInfohash(infohash)) {
    throw new ParseError(`Invalid infohash: ${infohash}`);
  }

  const parts: string[] = [`magnet:?xt=urn:btih:${infohash.toLowerCase()}`];

  if (displayName) {
    parts.push(`dn=${encodeURIComponent(displayName)}`);
  }

  if (trackers) {
    for (const tracker of trackers) {
      parts.push(`tr=${encodeURIComponent(tracker)}`);
    }
  }

  return parts.join("&");
}

/**
 * Get a display-friendly name from a MagnetInfo.
 * Falls back to a truncated infohash if no display name is available.
 *
 * @param magnet - The magnet info to get a name from
 * @returns Human-readable name
 */
export function getMagnetDisplayName(magnet: MagnetInfo): string {
  if (magnet.displayName) {
    return magnet.displayName;
  }
  return `Torrent ${magnet.infohash.slice(0, 12)}...`;
}

/**
 * Get a display name, falling back to {@link MAGNET_DISPLAY_NAME_FALLBACK}
 * (`"Unknown"`) when the magnet carries no usable `dn`.
 *
 * This is the Boba-mandated fallback (`_analysis/05-src-features.md`) used by
 * UI surfaces that prefer a stable literal over an infohash echo.
 *
 * @param magnet - The magnet info to get a name from
 * @returns Sanitized display name, or `"Unknown"`
 */
export function getMagnetDisplayNameOrUnknown(magnet: MagnetInfo): string {
  return magnet.displayName ?? MAGNET_DISPLAY_NAME_FALLBACK;
}

/**
 * Deduplicate magnets by their (lowercased) infohash, preserving first-seen
 * order. The infohash is the canonical identity of a torrent, so two magnets
 * with the same hash but different display names / trackers collapse to one.
 *
 * @param magnets - Magnets to deduplicate
 * @returns A new array with one entry per unique infohash
 */
export function dedupeMagnets(
  magnets: readonly MagnetInfo[],
): MagnetInfo[] {
  const seen = new Set<string>();
  const result: MagnetInfo[] = [];
  for (const magnet of magnets) {
    const key = magnet.infohash.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      result.push(magnet);
    }
  }
  return result;
}

/**
 * Truncate a magnet URI for logging (to avoid log spam).
 *
 * @param uri - Magnet URI to truncate
 * @returns Truncated string
 */
function truncateForLog(uri: string): string {
  if (uri.length <= 80) return uri;
  return uri.slice(0, 80) + "...";
}
