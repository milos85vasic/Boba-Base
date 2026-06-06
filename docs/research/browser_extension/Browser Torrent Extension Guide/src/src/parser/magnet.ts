/**
 * @fileoverview Magnet link parser for BobaLink.
 *
 * Provides fast detection and full parsing of magnet URI scheme links.
 * Supports BTIH (BitTorrent Info Hash) in hex and base32 formats,
 * multiple trackers, display names, and all standard magnet parameters.
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
 * @returns Array of full magnet URI strings found
 */
export function findMagnetUris(text: string): string[] {
  if (!containsMagnetLink(text)) return [];

  const matches = text.match(MAGNET_REGEX);
  if (!matches) return [];

  // Deduplicate and filter valid
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
 * @returns The 40-character hex infohash, or null if invalid
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
 * - xt (exact topic): The infohash
 * - dn (display name): Human-readable name
 * - tr (tracker): Tracker URL (can be multiple)
 * - ws (web seed): Web seed URL
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

    // Extract infohash
    const infohash = extractInfohash(magnetUri);
    if (!infohash) {
      // Try base32 format
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

    // Use URLSearchParams for robust parameter parsing
    // Replace magnet:? with ? to make it parseable
    const queryString = magnetUri.substring("magnet:?".length);

    // Manually parse parameters since URLSearchParams handles multiple same keys
    const params = new Map<string, string[]>();
    const pairs = queryString.split(/&|;/);

    for (const pair of pairs) {
      const eqIndex = pair.indexOf("=");
      if (eqIndex === -1) continue;

      const key = pair.substring(0, eqIndex);
      const value = decodeURIComponent(pair.substring(eqIndex + 1));

      const existing = params.get(key);
      if (existing) {
        existing.push(value);
      } else {
        params.set(key, [value]);
      }
    }

    // Handle multiple xt params (DHT backup hashes)
    const xtParams = params.get("xt") ?? [];
    const primaryXt = xtParams[0] ?? "";

    // Extract infohash from primary xt (should match what we found earlier)
    const primaryMatch = primaryXt.match(/urn:btih:([a-fA-F0-9]{40})/i);
    const finalInfohash = (primaryMatch?.[1] ?? infohash).toLowerCase();

    // Parse trackers (multiple tr params)
    const trackers = params.get("tr") ?? [];

    // Parse web seeds (multiple ws params)
    const webSeeds = params.get("ws") ?? [];

    // Parse display name
    const dnParams = params.get("dn");
    const displayName = dnParams?.[0] ?? null;

    // Parse exact length
    const xlParams = params.get("xl");
    const exactLength = xlParams?.[0] ? parseInt(xlParams[0], 10) : null;

    // Parse exact source (.torrent URL)
    const xsParams = params.get("xs");
    const exactSource = xsParams?.[0] ?? null;

    // Parse keywords
    const ktParams = params.get("kt");
    const keywords = ktParams?.[0] ? ktParams[0].split(/[+\s]+/) : [];

    // Parse acceptable source
    const asParams = params.get("as");
    const acceptableSource = asParams?.[0] ?? null;

    // Parse manifest
    const mtParams = params.get("mt");
    const manifest = mtParams?.[0] ?? null;

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
    throw new ParseError(`Failed to parse magnet URI: ${String(err)}`, {
      cause: err instanceof Error ? err : undefined,
      context: { uri: magnetUri },
    });
  }
}

/**
 * Generate a magnet URI from components.
 * Useful for reconstructing magnet links with modifications.
 *
 * @param infohash - 40-character hex infohash (required)
 * @param displayName - Optional display name
 * @param trackers - Optional tracker URLs
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
 * Falls back to truncated infohash if no display name is available.
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
 * Truncate a magnet URI for logging (to avoid log spam).
 *
 * @param uri - Magnet URI to truncate
 * @returns Truncated string
 */
function truncateForLog(uri: string): string {
  if (uri.length <= 80) return uri;
  return uri.slice(0, 80) + "...";
}
