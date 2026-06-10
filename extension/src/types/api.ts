/**
 * @fileoverview API response and authentication type definitions.
 *
 * Defines all data structures used for communication with qBitTorrent/Boba APIs,
 * including auth responses, torrent add parameters, and health check responses.
 *
 * De-dup (F types REFACTOR): `AuthMethod` is the canonical declaration in
 * `types/config.ts`; this module imports and re-exports it instead of
 * re-declaring the identical union.
 *
 * @module types/api
 */

import type { AuthMethod } from "./config";

/** Re-export the canonical AuthMethod so existing `types/api` consumers resolve it. */
export type { AuthMethod } from "./config";

// ─────────────────────────────────────────────────────────────────────────────
// qBitTorrent API Types
// ─────────────────────────────────────────────────────────────────────────────

/**
 * qBitTorrent API version response.
 */
export interface QBittorrentVersion {
  /** qBitTorrent version string (e.g., "v4.6.0") */
  readonly version: string;
}

/**
 * qBitTorrent application preferences (subset relevant to BobaLink).
 */
export interface QBittorrentAppPreferences {
  /** WebUI locale */
  readonly locale: string;

  /** Save path */
  readonly save_path: string;

  /** Temp path */
  readonly temp_path: string;

  /** Whether to preallocate files */
  readonly preallocate_all: boolean;

  /** Incoming port */
  readonly listen_port: number;

  /** Max active downloads */
  readonly max_active_downloads: number;

  /** Max active uploads */
  readonly max_active_uploads: number;

  /** Max active torrents */
  readonly max_active_torrents: number;

  /** Download speed limit (bytes/s) */
  readonly dl_limit: number;

  /** Upload speed limit (bytes/s) */
  readonly up_limit: number;

  /** WebUI username */
  readonly web_ui_username: string;
}

/**
 * Parameters for adding a torrent to qBitTorrent.
 * Matches the qBitTorrent WebUI API /api/v2/torrents/add endpoint.
 */
export interface QBittorrentAddTorrentParams {
  /** Magnet URI(s) to add, separated by newlines */
  readonly urls?: string;

  /** .torrent file content as multipart form data */
  readonly torrents?: File;

  /** Save path for the torrent */
  readonly savepath?: string;

  /** Cookie to use for download */
  readonly cookie?: string;

  /** Category to assign */
  readonly category?: string;

  /** Tags to assign, comma-separated */
  readonly tags?: string;

  /** Skip hash checking */
  readonly skip_checking?: string; // "true" | "false"

  /** Add torrent paused */
  readonly paused?: string; // "true" | "false"

  /** Root folder mode */
  readonly root_folder?: string; // "true" | "false"

  /** Rename torrent */
  readonly rename?: string;

  /** Upload speed limit (bytes/s) */
  readonly upLimit?: number;

  /** Download speed limit (bytes/s) */
  readonly dlLimit?: number;

  /** Whether to use automatic torrent management */
  readonly autoTMM?: string; // "true" | "false"

  /** Sequential download */
  readonly sequentialDownload?: string; // "true" | "false"

  /** First/last piece priority */
  readonly firstLastPiecePrio?: string; // "true" | "false"

  /** Content layout */
  readonly contentLayout?: "Original" | "Subfolder" | "NoSubfolder";

  /** Stop condition */
  readonly stopCondition?: string;
}

/**
 * Response from qBitTorrent torrents/add endpoint.
 */
export interface QBittorrentAddResponse {
  /** Whether the add operation succeeded */
  readonly success: boolean;

  /** Error message if the operation failed */
  readonly error?: string;
}

/**
 * qBitTorrent torrent info (subset for our needs).
 */
export interface QBittorrentTorrentInfo {
  /** Torrent hash */
  readonly hash: string;

  /** Torrent name */
  readonly name: string;

  /** Magnet URI */
  readonly magnet_uri: string;

  /** Size in bytes */
  readonly size: number;

  /** Progress (0.0 - 1.0) */
  readonly progress: number;

  /** Download speed (bytes/s) */
  readonly dlspeed: number;

  /** Upload speed (bytes/s) */
  readonly upspeed: number;

  /** Priority */
  readonly priority: number;

  /** Number of seeds */
  readonly num_seeds: number;

  /** Number of leechers */
  readonly num_leechs: number;

  /** Ratio */
  readonly ratio: number;

  /** ETA in seconds */
  readonly eta: number;

  /** State */
  readonly state: string;

  /** Category */
  readonly category: string;

  /** Tags */
  readonly tags: string;

  /** Added on (Unix timestamp) */
  readonly added_on: number;

  /** Completion on (Unix timestamp) */
  readonly completion_on: number;

  /** Save path */
  readonly save_path: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth Types
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Cookie-based authentication credentials.
 */
export interface CookieAuthCredentials {
  readonly method: "cookie";
  readonly username: string;
  readonly password: string;
}

/**
 * API key authentication credentials.
 */
export interface ApiKeyAuthCredentials {
  readonly method: "api_key";
  readonly apiKey: string;
}

/**
 * Basic HTTP authentication credentials.
 */
export interface BasicAuthCredentials {
  readonly method: "basic";
  readonly username: string;
  readonly password: string;
}

/**
 * No authentication required.
 */
export interface NoAuthCredentials {
  readonly method: "none";
}

/**
 * Union type of all authentication credential types.
 */
export type AuthCredentials =
  | CookieAuthCredentials
  | ApiKeyAuthCredentials
  | BasicAuthCredentials
  | NoAuthCredentials;

/**
 * Authentication state maintained by the extension.
 */
export interface AuthState {
  /** Current authentication method */
  readonly method: AuthMethod;

  /** Whether currently authenticated */
  readonly isAuthenticated: boolean;

  /** SID cookie value for cookie auth */
  readonly sidCookie: string | null;

  /** When the SID cookie expires */
  readonly sidExpiresAt: number | null;

  /** Basic auth header value */
  readonly basicAuthHeader: string | null;

  /** API key header value */
  readonly apiKeyHeader: string | null;

  /** When auth was last refreshed */
  readonly lastRefreshedAt: number | null;

  /** Number of consecutive auth failures */
  readonly consecutiveFailures: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Health Check Types
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Server health status.
 */
export type HealthStatus = "healthy" | "degraded" | "unhealthy" | "unknown";

/**
 * Health check result for a single server.
 */
export interface HealthCheckResult {
  /** Server ID that was checked */
  readonly serverId: string;

  /** Server URL that was checked */
  readonly url: string;

  /** Current health status */
  readonly status: HealthStatus;

  /** qBitTorrent version if available */
  readonly version: string | null;

  /** Response time in milliseconds */
  readonly responseTimeMs: number;

  /** Whether authentication is currently valid */
  readonly authValid: boolean;

  /** Error message if check failed */
  readonly error: string | null;

  /** Timestamp when the check was performed */
  readonly checkedAt: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Boba API Types
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Boba API server info response.
 */
export interface BobaServerInfo {
  /** Server name */
  readonly name: string;

  /** Server version */
  readonly version: string;

  /** Available features */
  readonly features: readonly string[];

  /** qBitTorrent connection status */
  readonly qbittorrent_connected: boolean;

  /** qBitTorrent version */
  readonly qbittorrent_version: string | null;
}

/**
 * Boba API search result (subset).
 */
export interface BobaSearchResult {
  /** Result ID */
  readonly id: string;

  /** Torrent name */
  readonly name: string;

  /** Infohash */
  readonly infohash: string;

  /** Magnet URI */
  readonly magnet_uri: string;

  /** Size in bytes */
  readonly size: number;

  /** Seed count */
  readonly seeders: number;

  /** Leecher count */
  readonly leechers: number;

  /** Source tracker/site */
  readonly source: string;

  /** Upload date */
  readonly upload_date: string;

  /** Category */
  readonly category: string;
}

/**
 * Boba API search response.
 */
export interface BobaSearchResponse {
  /** Search results */
  readonly results: readonly BobaSearchResult[];

  /** Total result count */
  readonly total: number;

  /** Current page */
  readonly page: number;

  /** Results per page */
  readonly per_page: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Queue Types
// ─────────────────────────────────────────────────────────────────────────────

/**
 * An item in the offline queue waiting to be sent.
 */
export interface QueueItem {
  /** Unique ID for this queue item */
  readonly id: string;

  /** The torrent that should be sent */
  readonly torrent: {
    readonly infohash: string;
    readonly magnetUri: string | null;
    readonly torrentUrl: string | null;
    readonly displayName: string;
  };

  /** Server ID this should be sent to */
  readonly serverId: string;

  /** When this item was added to the queue */
  readonly addedAt: number;

  /** Number of send attempts */
  readonly attempts: number;

  /** Last error message */
  readonly lastError: string | null;

  /** When the last attempt was made */
  readonly lastAttemptAt: number | null;

  /** Priority level */
  readonly priority: "high" | "normal" | "low";
}

/**
 * Queue processing result.
 */
export interface QueueProcessResult {
  /** Number of items processed */
  readonly processed: number;

  /** Number of items successfully sent */
  readonly succeeded: number;

  /** Number of items that failed */
  readonly failed: number;

  /** Number of items remaining in queue */
  readonly remaining: number;

  /** Detailed results for each item */
  readonly results: ReadonlyArray<{
    readonly itemId: string;
    readonly success: boolean;
    readonly error: string | null;
  }>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Message Types (for chrome.runtime messaging)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Message types sent between extension contexts.
 */
export type MessageType =
  | "scan-page"
  | "scan-result"
  | "send-torrent"
  | "send-result"
  | "get-detected"
  | "get-config"
  | "set-config"
  | "get-auth-state"
  | "authenticate"
  | "health-check"
  | "health-result"
  | "queue-process"
  | "queue-status"
  | "open-dashboard"
  | "show-notification"
  | "update-badge"
  | "torrent-detected"
  | "selection-change";

/**
 * Base message interface for chrome.runtime messaging.
 */
export interface ExtensionMessage {
  readonly type: MessageType;
  readonly payload?: Record<string, unknown>;
  readonly requestId?: string;
}

/**
 * Message response from background script.
 */
export interface ExtensionMessageResponse {
  readonly success: boolean;
  readonly data?: Record<string, unknown>;
  readonly error?: string;
}
