/**
 * @fileoverview .torrent file parser for BobaLink (Phase 2 wave-2 port).
 *
 * Parses BitTorrent `.torrent` files (bencoded) and extracts metadata: the
 * infohash, files (single- and multi-file), trackers, piece count, the
 * `private` flag, and other torrent properties. Also generates a magnet URI
 * from the parsed torrent and sanitizes private-tracker passkeys out of any
 * announce URL it exposes or logs.
 *
 * WIRED to the committed bencode module (`./bencode`) per
 * `docs/browser_extension/_plan/F-adopt-vs-rewrite.md` (the reference parser
 * was dead code — never invoked — and is here wired in properly). The
 * infohash is computed as the SHA-1 of the RAW bencoded `info` dictionary:
 *
 *     infohash = await sha1(encode(infoDict))
 *
 * The bencode module's `sha1` is async (Web Crypto / WebCrypto `subtle`), so
 * every entry point that produces an infohash is `async`.
 *
 * Boba hardening additions mandated by `_analysis/05-src-features.md` +
 * `_analysis/02-research-dimensions.md` Dim07, on top of the reference's
 * public API:
 *   1. Passkey sanitization — a private-tracker passkey embedded in an
 *      announce URL (path segment or `passkey=` / `pid=` query parameter)
 *      never survives into the exposed `ParsedTorrent.trackers` nor into any
 *      log line.
 *   2. Magnet-URI generation — a magnet link can be reconstructed from a
 *      parsed torrent (`buildMagnetFromTorrent`). Trackers folded into the
 *      generated magnet are also passkey-sanitized.
 *
 * Compiles under the extension's strict tsconfig (`strict`,
 * `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`,
 * `noUnusedLocals`/`noUnusedParameters`).
 *
 * @see https://wiki.theory.org/BitTorrentSpecification
 * @module parser/torrent-file
 */

import { createLogger } from "../shared/logger";
import { ParseError } from "../shared/errors";
import type { ParsedTorrent, TorrentFileInfo } from "../types/torrent";
import {
  decode,
  extractInfoDictBytes,
  sha1,
  type BencodeDict,
  type BencodeValue,
} from "./bencode";

const log = createLogger("TorrentFileParser");

/** A 40-char lowercase hex infohash matcher (SHA-1 digest). */
const HEX_INFOHASH_REGEX = /^[a-f0-9]{40}$/;

/**
 * Parse a `.torrent` file from bytes (Uint8Array).
 *
 * The returned `trackers` are passkey-sanitized (the exposed form) so a
 * private-tracker passkey never leaks downstream.
 *
 * @param data - Raw `.torrent` file contents
 * @returns Parsed torrent metadata including the computed infohash
 * @throws ParseError if the file is not a valid torrent
 */
export async function parseTorrentFile(data: Uint8Array): Promise<ParsedTorrent> {
  const endTimer = log.timed("parseTorrentFile");

  try {
    // Decode the bencoded data.
    const decoded = decode(data);

    if (typeof decoded !== "object" || decoded === null || Array.isArray(decoded)) {
      throw new ParseError("Torrent file must be a bencode dictionary");
    }

    const rootDict = decoded as BencodeDict;

    // Extract the info dictionary (required).
    const info = rootDict["info"];
    if (!info || typeof info !== "object" || Array.isArray(info)) {
      throw new ParseError("Torrent missing required 'info' dictionary");
    }
    const infoDict = info as BencodeDict;

    // Compute infohash: SHA-1 of the RAW bencoded info dictionary, taken as the
    // ORIGINAL byte slice from the input buffer — NOT a decode→re-encode. A
    // re-encode UTF-8-mangles the binary `info.pieces` field (20-byte SHA-1
    // hashes full of bytes 0x80–0xff) and yields the WRONG infohash for any real
    // torrent. `extractInfoDictBytes` returns the untouched on-disk info bytes.
    const infoBencoded = extractInfoDictBytes(data);
    const infohash = await sha1(infoBencoded);

    // Name (required).
    const name = getString(infoDict, "name");
    if (!name) {
      throw new ParseError("Torrent missing required 'name' field");
    }

    // Optional metadata.
    const creationDate = getNumberOrNull(rootDict, "creation date");
    const comment = getStringOrNull(rootDict, "comment");
    const createdBy = getStringOrNull(rootDict, "created by");
    const source = getStringOrNull(infoDict, "source");

    // Piece length (required).
    const pieceLength = getNumber(infoDict, "piece length");

    // Private flag — BEP-27: `private = 1` ⇒ private torrent.
    const privateFlag = getNumberOrNull(infoDict, "private");
    const isPrivate = privateFlag === 1;

    // Pieces: concatenated 20-byte SHA-1 piece hashes ⇒ count = len / 20.
    // Counted from a LOSSLESS (binary) decode of the raw info-dict bytes — the
    // UTF-8 decode that produced `infoDict` mangles the binary `pieces` field,
    // so its string length is NOT the true byte length and would mis-count.
    const numPieces = countPieces(infoBencoded);

    // Trackers — passkey-sanitized for the EXPOSED form.
    const trackers = extractTrackers(rootDict);

    // Files (single- or multi-file).
    const files = extractFiles(infoDict, name);

    // Total size = sum of file lengths.
    const totalSize = files.reduce((sum, f) => sum + f.length, 0);

    // Log the infohash prefix only — the sanitized trackers carry no passkey,
    // but we never log full announce URLs regardless.
    log.debug(`Parsed torrent: infohash=${infohash.slice(0, 16)}…`);

    endTimer();

    return {
      infohash,
      name,
      creationDate,
      comment,
      createdBy,
      pieceLength,
      isPrivate,
      trackers,
      source,
      files,
      totalSize,
      numPieces,
    };
  } catch (err) {
    if (err instanceof ParseError) throw err;
    const options: { cause?: Error } = {};
    if (err instanceof Error) options.cause = err;
    throw new ParseError(`Failed to parse torrent file: ${String(err)}`, options);
  }
}

/**
 * Parse a `.torrent` file downloaded from a URL.
 * Downloads the file and then parses it.
 *
 * @param url - URL of the `.torrent` file
 * @returns Parsed torrent metadata
 * @throws ParseError if download or parsing fails
 */
export async function parseTorrentFromUrl(url: string): Promise<ParsedTorrent> {
  log.debug(`Downloading torrent from ${sanitizePasskeyFromUrl(url)}`);

  try {
    const response = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
    });

    if (!response.ok) {
      throw new ParseError(
        `HTTP ${response.status} downloading torrent: ${response.statusText}`,
      );
    }

    const contentType = response.headers.get("content-type");
    if (
      contentType &&
      !contentType.includes("application/x-bittorrent") &&
      !contentType.includes("application/octet-stream")
    ) {
      log.warn(`Unexpected content type for torrent: ${contentType}`);
    }

    const data = new Uint8Array(await response.arrayBuffer());
    return await parseTorrentFile(data);
  } catch (err) {
    if (err instanceof ParseError) throw err;
    const options: { cause?: Error } = {};
    if (err instanceof Error) options.cause = err;
    throw new ParseError(
      `Failed to download torrent from ${sanitizePasskeyFromUrl(url)}: ${String(err)}`,
      options,
    );
  }
}

/**
 * Compute the infohash from a raw `.torrent` file without full parsing.
 * More efficient than a full parse when only the infohash is needed.
 *
 * @param data - Raw `.torrent` file contents
 * @returns 40-character hex infohash (SHA-1 of the bencoded info dict)
 * @throws ParseError if the file is invalid
 */
export async function computeInfohash(data: Uint8Array): Promise<string> {
  try {
    // SHA-1 of the RAW on-disk info-dict bytes (NOT a decode→re-encode, which
    // would mangle the binary `pieces` field and produce the wrong infohash).
    const infoBencoded = extractInfoDictBytes(data);
    return await sha1(infoBencoded);
  } catch (err) {
    if (err instanceof ParseError) throw err;
    const options: { cause?: Error } = {};
    if (err instanceof Error) options.cause = err;
    throw new ParseError(`Failed to compute infohash: ${String(err)}`, options);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Magnet generation
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Generate a magnet URI from a parsed torrent.
 *
 * Form: `magnet:?xt=urn:btih:<infohash>&dn=<name>&tr=<tracker>...`. The
 * display name and each tracker are URL-encoded; trackers are
 * passkey-sanitized so a private-tracker passkey never travels in the
 * generated magnet.
 *
 * @param parsed - A torrent parsed by {@link parseTorrentFile}
 * @returns The constructed magnet URI
 * @throws ParseError if the parsed torrent's infohash is not a 40-char hex digest
 */
export function buildMagnetFromTorrent(parsed: ParsedTorrent): string {
  const infohash = parsed.infohash.toLowerCase();
  if (!HEX_INFOHASH_REGEX.test(infohash)) {
    throw new ParseError(`Invalid infohash for magnet generation: ${infohash}`);
  }

  const parts: string[] = [`magnet:?xt=urn:btih:${infohash}`];

  if (parsed.name) {
    parts.push(`dn=${encodeURIComponent(parsed.name)}`);
  }

  for (const tracker of parsed.trackers) {
    const safe = sanitizePasskeyFromUrl(tracker);
    parts.push(`tr=${encodeURIComponent(safe)}`);
  }

  return parts.join("&");
}

// ─────────────────────────────────────────────────────────────────────────────
// Passkey sanitization
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Strip a private-tracker passkey from an announce URL so it never leaks into
 * an exposed (UI / magnet) or logged form.
 *
 * Private trackers embed a per-user passkey in the announce URL in one of two
 * shapes, both handled here:
 *   1. **Path-segment** — a 32+ hex-character segment, e.g.
 *      `https://tr.example/<passkey>/announce` →
 *      `https://tr.example/<redacted>/announce`.
 *   2. **Query-parameter** — `passkey=`, `pid=`, `authkey=`, `torrent_pass=`,
 *      `secret=`, `apikey=` (case-insensitive) →
 *      `…?passkey=<redacted>`.
 *
 * The URL otherwise round-trips unchanged: host, port, the `announce`
 * endpoint, and every non-secret query parameter are preserved so the
 * sanitized tracker is still recognizable. The function is DOM-independent
 * (safe in a background / service-worker context).
 *
 * @param url - The raw announce URL (may contain a passkey)
 * @returns The same URL with any passkey replaced by the literal `<redacted>`
 */
export function sanitizePasskeyFromUrl(url: string): string {
  let out = url;

  // 1. Query-parameter passkeys (case-insensitive key match). Replaces the
  //    value up to the next `&` / `#` / end-of-string. Handles repeated keys.
  out = out.replace(
    /([?&](?:passkey|pid|authkey|torrent_pass|secret|apikey)=)[^&#]*/gi,
    "$1<redacted>",
  );

  // 2. Path-segment passkeys: a long hex run (>=32 chars) sitting as its own
  //    path segment between slashes (the conventional private-tracker layout
  //    `.../<32-or-40-hex-passkey>/announce`). Anchored to segment boundaries
  //    so an ordinary hex word inside a name is not clobbered.
  out = out.replace(/\/[a-f0-9]{32,}(?=\/)/gi, "/<redacted>");

  return out;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tracker / file extraction
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Extract tracker URLs from the root dictionary, passkey-sanitized.
 * Handles both `announce` (single) and `announce-list` (tiered list),
 * deduplicating by sanitized URL.
 *
 * @param rootDict - Root torrent dictionary
 * @returns Flat array of passkey-sanitized tracker URLs
 */
function extractTrackers(rootDict: BencodeDict): readonly string[] {
  const trackers: string[] = [];
  const seen = new Set<string>();

  const push = (raw: string): void => {
    const safe = sanitizePasskeyFromUrl(raw);
    if (safe && !seen.has(safe)) {
      trackers.push(safe);
      seen.add(safe);
    }
  };

  // Primary announce URL.
  const announce = getStringOrNull(rootDict, "announce");
  if (announce) push(announce);

  // Tiered announce list.
  const announceList = rootDict["announce-list"];
  if (Array.isArray(announceList)) {
    for (const tier of announceList) {
      if (Array.isArray(tier)) {
        for (const tracker of tier) {
          const trackerUrl = bencodeToString(tracker);
          if (trackerUrl) push(trackerUrl);
        }
      }
    }
  }

  return trackers;
}

/**
 * Extract file information from the info dictionary.
 * Handles both single-file and multi-file torrents.
 *
 * @param infoDict - The info dictionary
 * @param defaultName - Fallback name for single-file torrents
 * @returns Array of file information
 */
function extractFiles(
  infoDict: BencodeDict,
  defaultName: string,
): readonly TorrentFileInfo[] {
  const files = infoDict["files"];

  // Single-file torrent.
  if (!files) {
    const length = getNumber(infoDict, "length");
    return [
      {
        path: [defaultName],
        length,
        fullPath: defaultName,
      },
    ];
  }

  // Multi-file torrent.
  if (!Array.isArray(files)) {
    throw new ParseError("Invalid 'files' field in torrent info");
  }

  const result: TorrentFileInfo[] = [];

  for (const fileEntry of files) {
    if (
      typeof fileEntry !== "object" ||
      fileEntry === null ||
      Array.isArray(fileEntry)
    ) {
      continue;
    }

    const entry = fileEntry as BencodeDict;
    const length = getNumber(entry, "length");
    const pathParts = extractPath(entry);

    result.push({
      path: pathParts,
      length,
      fullPath: pathParts.join("/"),
    });
  }

  return result;
}

/**
 * Extract the path array from a file entry.
 *
 * @param fileEntry - File dictionary from the files list
 * @returns Array of path component strings
 */
function extractPath(fileEntry: BencodeDict): string[] {
  const path = fileEntry["path"];
  if (!Array.isArray(path)) {
    return ["unknown"];
  }

  // Path segments are bencoded byte-strings; drop any non-string/empty segment
  // rather than stringifying an object (which would yield "[object Object]").
  return path
    .map((p: BencodeValue) => bencodeToString(p))
    .filter((s): s is string => s !== null && s.length > 0);
}

/**
 * Count the pieces (20-byte SHA-1 hashes) in an info dictionary, reading the
 * `pieces` field LOSSLESSLY.
 *
 * The raw info-dict bytes are decoded in `binary` mode so the `pieces` field
 * stays a `Uint8Array` whose true byte length is preserved. A UTF-8 decode
 * would mangle the high bytes (0x80–0xff) of real piece hashes, corrupting the
 * length and therefore the count. (A string fallback is retained for the
 * synthetic all-ASCII case, but binary is the real-torrent path.)
 *
 * @param infoBytes - The raw bencoded info-dict bytes
 * @returns Number of 20-byte piece hashes (floor of pieces.length / 20)
 */
function countPieces(infoBytes: Uint8Array): number {
  const info = decode(infoBytes, { encoding: "binary" });
  if (typeof info !== "object" || info === null || Array.isArray(info)) {
    return 0;
  }
  const pieces = (info as BencodeDict)["pieces"];
  if (pieces instanceof Uint8Array) return Math.floor(pieces.length / 20);
  if (typeof pieces === "string") return Math.floor(pieces.length / 20);
  return 0;
}

// ─────────────────────────────────────────────────────────────────────────────
// Type-safe value extractors
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Coerce a bencode value to a string when it is a string or byte string.
 *
 * @param value - Bencode value
 * @returns The decoded string, or null if the value is neither a string nor bytes
 */
function bencodeToString(value: BencodeValue): string | null {
  if (typeof value === "string") return value;
  if (value instanceof Uint8Array) return new TextDecoder().decode(value);
  return null;
}

/**
 * Get a required string value from a dictionary.
 *
 * @param dict - Bencode dictionary
 * @param key - Key to look up
 * @returns String value, or empty string if not found / wrong type
 */
function getString(dict: BencodeDict, key: string): string {
  return bencodeToString(dict[key] as BencodeValue) ?? "";
}

/**
 * Get an optional string value from a dictionary.
 *
 * @param dict - Bencode dictionary
 * @param key - Key to look up
 * @returns String value, or null if not found / wrong type
 */
function getStringOrNull(dict: BencodeDict, key: string): string | null {
  const value = dict[key];
  if (value === undefined) return null;
  return bencodeToString(value);
}

/**
 * Get a required number value from a dictionary.
 *
 * @param dict - Bencode dictionary
 * @param key - Key to look up
 * @returns Number value, or 0 if not found / wrong type
 */
function getNumber(dict: BencodeDict, key: string): number {
  const value = dict[key];
  if (typeof value === "number") return value;
  return 0;
}

/**
 * Get an optional number value from a dictionary.
 *
 * @param dict - Bencode dictionary
 * @param key - Key to look up
 * @returns Number value, or null if not found / wrong type
 */
function getNumberOrNull(dict: BencodeDict, key: string): number | null {
  const value = dict[key];
  if (typeof value === "number") return value;
  return null;
}
