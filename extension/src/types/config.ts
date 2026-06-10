/**
 * @fileoverview Configuration type definitions for BobaLink.
 *
 * Defines the shape of all user-configurable settings, server configurations,
 * authentication methods, and download preferences.
 *
 * De-dup (F types REFACTOR): `AuthMethod` is declared HERE as the single
 * canonical source; `types/api.ts` re-exports it rather than re-declaring it.
 *
 * @module types/config
 */

/**
 * Authentication method for connecting to qBitTorrent/Boba servers.
 *
 * Canonical declaration — re-exported by `types/api.ts`.
 */
export type AuthMethod = "none" | "cookie" | "api_key" | "basic";

/**
 * Server configuration for a single Boba/qBitTorrent backend.
 */
export interface ServerConfig {
  /** Unique identifier for this server configuration */
  readonly id: string;

  /** User-defined display name for this server */
  readonly name: string;

  /** Base URL of the Boba merge service / qBitTorrent WebUI (e.g., http://localhost:7187) */
  readonly url: string;

  /** Whether this server is currently active/selected */
  readonly active: boolean;

  /** Authentication method to use */
  readonly authMethod: AuthMethod;

  /** Username for cookie or basic auth */
  readonly username: string | null;

  /** Password for cookie or basic auth (stored encrypted) */
  readonly encryptedPassword: string | null;

  /** API key for api_key auth (stored encrypted) */
  readonly encryptedApiKey: string | null;

  /**
   * Optional shared-secret token for Boba's merge-service download-write endpoints
   * (`BOBA_API_TOKEN` on :7187). Stored encrypted. When set, the Phase-4 Boba client
   * sends it as `Authorization: Bearer <token>` (or `X-Boba-Token`). The backend gate
   * is OPEN by default — only enforced when the operator sets `BOBA_API_TOKEN`.
   */
  readonly encryptedBobaApiToken?: string | null;

  /** Timeout for API requests in milliseconds */
  readonly requestTimeout: number;

  /** Whether to verify HTTPS certificates */
  readonly verifySsl: boolean;

  /** Category to assign torrents in qBitTorrent */
  readonly defaultCategory: string | null;

  /** Default save path for torrents */
  readonly defaultSavePath: string | null;

  /** Whether to start torrents immediately or paused */
  readonly startPaused: boolean;

  /** Whether to skip hash checking when adding torrents */
  readonly skipHashCheck: boolean;

  /** Content layout preference */
  readonly contentLayout: "original" | "subfolder" | "no_subfolder";

  /** Whether to use automatic torrent management */
  readonly autoTMM: boolean;

  /** Limit upload speed in KiB/s (0 = unlimited) */
  readonly uploadLimit: number;

  /** Limit download speed in KiB/s (0 = unlimited) */
  readonly downloadLimit: number;
}

/**
 * Extension-wide configuration settings.
 */
export interface ExtensionConfig {
  /** Schema version for config migration */
  readonly schemaVersion: number;

  /** Array of configured servers */
  readonly servers: readonly ServerConfig[];

  /** ID of the currently active server */
  readonly activeServerId: string | null;

  /** Whether to automatically scan pages on load */
  readonly autoScan: boolean;

  /** Delay in ms before auto-scan starts after page load */
  readonly autoScanDelay: number;

  /** Whether to highlight detected torrents on the page */
  readonly highlightTorrents: boolean;

  /** Highlight style: badge, border, or glow */
  readonly highlightStyle: "badge" | "border" | "glow";

  /** Whether to show notifications for scan/send results */
  readonly showNotifications: boolean;

  /** Whether to sound a notification beep on completion */
  readonly notificationSound: boolean;

  /** Whether to automatically send detected torrents without confirmation */
  readonly autoSend: boolean;

  /** Maximum number of items to keep in send history */
  readonly maxHistoryItems: number;

  /** Whether to enable debug logging */
  readonly debugMode: boolean;

  /** How often to check server health (in minutes) */
  readonly healthCheckInterval: number;

  /** Whether to enable offline queue for failed sends */
  readonly offlineQueue: boolean;

  /** Maximum number of items in the offline queue */
  readonly maxOfflineQueueSize: number;

  /** Whether to show the context menu items */
  readonly showContextMenu: boolean;

  /** Keyboard shortcut enabled state */
  readonly keyboardShortcuts: boolean;

  /** When the config was last updated */
  readonly lastUpdated: number;

  /** Encryption key version for credential storage */
  readonly encryptionKeyVersion: number;
}

/**
 * Default extension configuration values.
 * Used when initializing storage for the first time.
 */
export const DEFAULT_CONFIG: Readonly<ExtensionConfig> = {
  schemaVersion: 1,
  servers: [],
  activeServerId: null,
  autoScan: true,
  autoScanDelay: 2000,
  highlightTorrents: true,
  highlightStyle: "badge",
  showNotifications: true,
  notificationSound: false,
  autoSend: false,
  maxHistoryItems: 100,
  debugMode: false,
  healthCheckInterval: 5,
  offlineQueue: true,
  maxOfflineQueueSize: 50,
  showContextMenu: true,
  keyboardShortcuts: true,
  lastUpdated: 0,
  encryptionKeyVersion: 1,
} as const;

/**
 * Configuration for the auto-discovery feature.
 * Scans common Boba Project ports to find running servers.
 */
export interface AutoDiscoveryConfig {
  /** Ports to scan for Boba servers */
  readonly ports: readonly number[];

  /** Timeout per port scan in milliseconds */
  readonly scanTimeout: number;

  /** Whether to scan for qBitTorrent (via the Boba merge service, :7187) */
  readonly scanQbittorrent: boolean;

  /** Whether to scan for Boba FastAPI / merge service (port 7187) */
  readonly scanFastApi: boolean;

  /** Whether to scan for Boba Go (port 7189) */
  readonly scanGo: boolean;
}

/**
 * Default auto-discovery configuration.
 *
 * Ports retargeted (Phase 1): the reference probed [7187, 7189, 8080]; the
 * :8080 qBittorrent direct port is replaced by the :7187 merge service, so
 * the distinct probe set is [7187, 7189].
 */
export const DEFAULT_AUTO_DISCOVERY: Readonly<AutoDiscoveryConfig> = {
  ports: [7187, 7189],
  scanTimeout: 3000,
  scanQbittorrent: true,
  scanFastApi: true,
  scanGo: true,
} as const;

/**
 * Result of a server connection test.
 */
export interface ConnectionTestResult {
  /** Whether the connection was successful */
  readonly success: boolean;

  /** Server URL that was tested */
  readonly url: string;

  /** Server version if connected */
  readonly version: string | null;

  /** Error message if connection failed */
  readonly error: string | null;

  /** Response time in milliseconds */
  readonly responseTimeMs: number;

  /** Timestamp when the test was performed */
  readonly testedAt: number;
}

/**
 * Configuration change event detail.
 */
export interface ConfigChangeEvent {
  /** The key that changed */
  readonly key: string;

  /** The new value */
  readonly newValue: unknown;

  /** The previous value */
  readonly oldValue: unknown;

  /** When the change occurred */
  readonly changedAt: number;
}
