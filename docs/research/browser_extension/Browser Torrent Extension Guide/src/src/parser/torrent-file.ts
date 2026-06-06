/**
 * @fileoverview .torrent file parser for BobaLink.
 *
 * Parses BitTorrent .torrent files (bencoded) to extract metadata including
 * infohash, files, trackers, and other torrent properties.
 *
 * Uses the bencode decoder for parsing and Web Crypto API for SHA-1 hashing.
 *
 * @module parser/torrent-file
 */

import { createLogger } from "../shared/logger";
import { ParseError } from "../shared/errors";
import type { ParsedTorrent, TorrentFileInfo } from "../types/torrent";
import { decode, encode, sha1, type BencodeDict, type BencodeValue } from "./bencode";

const log = createLogger("TorrentFileParser");

/**
 * Parse a .torrent file from bytes (Uint8Array).
 *
 * @param data - Raw .torrent file contents
 * @returns Parsed torrent metadata including computed infohash
 * @throws ParseError if the file is not a valid torrent
 */
export async function parseTorrentFile(data: Uint8Array): Promise<ParsedTorrent> {
  const endTimer = log.timed("parseTorrentFile");

  try {
    // Decode the bencoded data
    const decoded = decode(data);

    if (typeof decoded !== "object" || decoded === null || Array.isArray(decoded)) {
      throw new ParseError("Torrent file must be a bencode dictionary");
    }

    const rootDict = decoded as BencodeDict;

    // Extract the info dictionary (required)
    const info = rootDict["info"];
    if (!info || typeof info !== "object" || Array.isArray(info)) {
      throw new ParseError("Torrent missing required 'info' dictionary");
    }
    const infoDict = info as BencodeDict;

    // Compute infohash: SHA-1 of the bencoded info dictionary
    const infoBencoded = encode(infoDict);
    const infohash = await sha1(infoBencoded);

    log.debug(`Parsed torrent: infohash=${infohash.slice(0, 16)}...`);

    // Extract name (required)
    const name = getString(infoDict, "name");
    if (!name) {
      throw new ParseError("Torrent missing required 'name' field");
    }

    // Extract optional metadata
    const creationDate = getNumberOrNull(rootDict, "creation date");
    const comment = getStringOrNull(rootDict, "comment");
    const createdBy = getStringOrNull(rootDict, "created by");
    const source = getStringOrNull(infoDict, "source");

    // Piece length (required)
    const pieceLength = getNumber(infoDict, "piece length");

    // Private flag
    const privateFlag = getNumberOrNull(infoDict, "private");
    const isPrivate = privateFlag === 1;

    // Pieces (concatenated SHA-1 hashes of pieces)
    const pieces = infoDict["pieces"];
    const numPieces =
      pieces instanceof Uint8Array
        ? Math.floor(pieces.length / 20)
        : typeof pieces === "string"
          ? Math.floor(pieces.length / 20)
          : 0;

    // Extract trackers
    const trackers = extractTrackers(rootDict);

    // Extract file information
    const files = extractFiles(infoDict, name);

    // Calculate total size
    const totalSize = files.reduce((sum, f) => sum + f.length, 0);

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
    throw new ParseError(`Failed to parse torrent file: ${String(err)}`, {
      cause: err instanceof Error ? err : undefined,
    });
  }
}

/**
 * Parse a .torrent file downloaded from a URL.
 * Downloads the file and then parses it.
 *
 * @param url - URL of the .torrent file
 * @returns Parsed torrent metadata
 * @throws ParseError if download or parsing fails
 */
export async function parseTorrentFromUrl(url: string): Promise<ParsedTorrent> {
  log.debug(`Downloading torrent from ${url}`);

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
    if (contentType && !contentType.includes("application/x-bittorrent") && !contentType.includes("application/octet-stream")) {
      log.warn(`Unexpected content type for torrent: ${contentType}`);
    }

    const data = new Uint8Array(await response.arrayBuffer());
    return await parseTorrentFile(data);
  } catch (err) {
    if (err instanceof ParseError) throw err;
    throw new ParseError(`Failed to download torrent from ${url}: ${String(err)}`, {
      cause: err instanceof Error ? err : undefined,
    });
  }
}

/**
 * Compute the infohash from a raw .torrent file without full parsing.
 * More efficient than full parse when only the infohash is needed.
 *
 * @param data - Raw .torrent file contents
 * @returns 40-character hex infohash
 * @throws ParseError if the file is invalid
 */
export async function computeInfohash(data: Uint8Array): Promise<string> {
  try {
    const decoded = decode(data);

    if (typeof decoded !== "object" || decoded === null || Array.isArray(decoded)) {
      throw new ParseError("Not a valid torrent file");
    }

    const rootDict = decoded as BencodeDict;
    const info = rootDict["info"];

    if (!info || typeof info !== "object" || Array.isArray(info)) {
      throw new ParseError("Torrent missing 'info' dictionary");
    }

    const infoBencoded = encode(info as BencodeDict);
    return await sha1(infoBencoded);
  } catch (err) {
    if (err instanceof ParseError) throw err;
    throw new ParseError(`Failed to compute infohash: ${String(err)}`, {
      cause: err instanceof Error ? err : undefined,
    });
  }
}

/**
 * Extract tracker URLs from the root dictionary.
 * Handles both 'announce' (single) and 'announce-list' (tiered list).
 *
 * @param rootDict - Root torrent dictionary
 * @returns Flat array of tracker URLs
 */
function extractTrackers(rootDict: BencodeDict): readonly string[] {
  const trackers: string[] = [];
  const seen = new Set<string>();

  // Primary announce URL
  const announce = getStringOrNull(rootDict, "announce");
  if (announce) {
    trackers.push(announce);
    seen.add(announce);
  }

  // Tiered announce list
  const announceList = rootDict["announce-list"];
  if (Array.isArray(announceList)) {
    for (const tier of announceList) {
      if (Array.isArray(tier)) {
        for (const tracker of tier) {
          const trackerUrl =
            typeof tracker === "string"
              ? tracker
              : tracker instanceof Uint8Array
                ? new TextDecoder().decode(tracker)
                : null;

          if (trackerUrl && !seen.has(trackerUrl)) {
            trackers.push(trackerUrl);
            seen.add(trackerUrl);
          }
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

  // Single-file torrent
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

  // Multi-file torrent
  if (!Array.isArray(files)) {
    throw new ParseError("Invalid 'files' field in torrent info");
  }

  const result: TorrentFileInfo[] = [];

  for (const fileEntry of files) {
    if (typeof fileEntry !== "object" || fileEntry === null || Array.isArray(fileEntry)) {
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

  return path
    .map((p: BencodeValue) => {
      if (typeof p === "string") return p;
      if (p instanceof Uint8Array) return new TextDecoder().decode(p);
      return String(p);
    })
    .filter((p) => p.length > 0);
}

// ─────────────────────────────────────────────────────────────────────────────
// Type-safe value extractors
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Get a required string value from a dictionary.
 *
 * @param dict - Bencode dictionary
 * @param key - Key to look up
 * @returns String value, or empty string if not found/wrong type
 */
function getString(dict: BencodeDict, key: string): string {
  const value = dict[key];
  if (typeof value === "string") return value;
  if (value instanceof Uint8Array) return new TextDecoder().decode(value);
  return "";
}

/**
 * Get an optional string value from a dictionary.
 *
 * @param dict - Bencode dictionary
 * @param key - Key to look up
 * @returns String value, or null if not found
 */
function getStringOrNull(dict: BencodeDict, key: string): string | null {
  const value = dict[key];
  if (value === undefined) return null;
  if (typeof value === "string") return value;
  if (value instanceof Uint8Array) return new TextDecoder().decode(value);
  return null;
}

/**
 * Get a required number value from a dictionary.
 *
 * @param dict - Bencode dictionary
 * @param key - Key to look up
 * @returns Number value, or 0 if not found/wrong type
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
 * @returns Number value, or null if not found
 */
function getNumberOrNull(dict: BencodeDict, key: string): number | null {
  const value = dict[key];
  if (typeof value === "number") return value;
  return null;
}
