/**
 * @fileoverview Core torrent-related type definitions for BobaLink.
 *
 * Defines all data structures used to represent magnet links, torrent files,
 * parsed torrent metadata, and detection results throughout the extension.
 *
 * @module types/torrent
 */

/**
 * Parsed information from a magnet URI.
 * Magnet URIs follow the de facto BitTorrent magnet link format:
 * magnet:?xt=urn:btih:<hash>&dn=<name>&tr=<tracker>&tr=<tracker>...
 */
export interface MagnetInfo {
  /** The full magnet URI as found on the page */
  readonly uri: string;

  /** BitTorrent infohash (40-char hex SHA-1 digest) */
  readonly infohash: string;

  /** Display name from dn parameter, if present */
  readonly displayName: string | null;

  /** List of tracker URLs from tr parameters */
  readonly trackers: readonly string[];

  /** Web seed URLs from ws parameters */
  readonly webSeeds: readonly string[];

  /** Exact length in bytes from xl parameter, if present */
  readonly exactLength: number | null;

  /** Exact source from xs parameter, if present (e.g., .torrent file URL) */
  readonly exactSource: string | null;

  /** Keywords from kt parameter, if present */
  readonly keywords: readonly string[];

  /** Acceptable source from as parameter, if present */
  readonly acceptableSource: string | null;

  /** Manifest URL from mt parameter, if present */
  readonly manifest: string | null;

  /** When this magnet was detected */
  readonly detectedAt: number;

  /** DOM element that contained this magnet, if known */
  readonly sourceElement: Element | null;
}

/**
 * Information about a .torrent file found on a page.
 */
export interface TorrentFile {
  /** URL where the .torrent file can be downloaded */
  readonly url: string;

  /** Filename from the URL or content-disposition header */
  readonly filename: string;

  /** File size in bytes, if known from headers or context */
  readonly size: number | null;

  /** Whether this torrent file URL points to the same origin as the page */
  readonly sameOrigin: boolean;

  /** When this torrent file was detected */
  readonly detectedAt: number;

  /** DOM element that contained this torrent file link, if known */
  readonly sourceElement: Element | null;
}

/**
 * Parsed metadata from a decoded .torrent file.
 */
export interface ParsedTorrent {
  /** BitTorrent infohash (40-char hex SHA-1 digest) */
  readonly infohash: string;

  /** Display name from torrent info dictionary */
  readonly name: string;

  /** Creation date as Unix timestamp, if present */
  readonly creationDate: number | null;

  /** Comment from torrent, if present */
  readonly comment: string | null;

  /** Created by string, if present */
  readonly createdBy: string | null;

  /** Piece length in bytes */
  readonly pieceLength: number;

  /** Whether this is a private torrent */
  readonly isPrivate: boolean;

  /** List of tracker URLs from announce and announce-list */
  readonly trackers: readonly string[];

  /** Source tag, if present (used by some private trackers) */
  readonly source: string | null;

  /** File information */
  readonly files: readonly TorrentFileInfo[];

  /** Total size in bytes */
  readonly totalSize: number;

  /** Number of pieces */
  readonly numPieces: number;
}

/**
 * Information about a single file within a torrent.
 */
export interface TorrentFileInfo {
  /** File path components */
  readonly path: readonly string[];

  /** File size in bytes */
  readonly length: number;

  /** Full path as string */
  readonly fullPath: string;
}

/**
 * The type of torrent content detected.
 */
export type TorrentContentType = "magnet" | "torrent-file";

/**
 * A detected torrent item, either magnet link or .torrent file.
 * This is the unified type used throughout the extension for detected content.
 */
export interface DetectedTorrent {
  /** Unique identifier derived from infohash or URL hash */
  readonly id: string;

  /** The type of torrent content */
  readonly type: TorrentContentType;

  /** The magnet info, if type is 'magnet' */
  readonly magnet: MagnetInfo | null;

  /** The torrent file info, if type is 'torrent-file' */
  readonly torrentFile: TorrentFile | null;

  /** Combined display name for UI presentation */
  readonly displayName: string;

  /** Whether this item has been selected for batch operations */
  selected: boolean;

  /** Whether this item has already been sent to Boba */
  sent: boolean;

  /** Status of the last send attempt */
  sendStatus: SendStatus | null;

  /** When this item was first detected */
  readonly detectedAt: number;
}

/**
 * Status of sending a torrent to Boba/qBitTorrent.
 */
export type SendStatus =
  | "pending"
  | "sending"
  | "success"
  | "error"
  | "queued";

/**
 * Result of a send operation to qBitTorrent.
 */
export interface SendResult {
  /** Whether the operation succeeded */
  readonly success: boolean;

  /** The detected torrent that was sent */
  readonly torrent: DetectedTorrent;

  /** Error message if success is false */
  readonly error: string | null;

  /** qBitTorrent response data if available */
  readonly response: Record<string, unknown> | null;

  /** Timestamp when the operation completed */
  readonly completedAt: number;
}

/**
 * Aggregated scan result from a page.
 */
export interface PageScanResult {
  /** URL of the scanned page */
  readonly pageUrl: string;

  /** Title of the scanned page */
  readonly pageTitle: string;

  /** All detected torrent items */
  readonly items: readonly DetectedTorrent[];

  /** Number of magnet links found */
  readonly magnetCount: number;

  /** Number of .torrent files found */
  readonly torrentFileCount: number;

  /** When the scan was performed */
  readonly scannedAt: number;

  /** Duration of the scan in milliseconds */
  readonly scanDurationMs: number;
}
