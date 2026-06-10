/**
 * @fileoverview Shared constants for BobaLink extension.
 *
 * Centralizes all regex patterns, default ports, URL templates, and
 * magic strings used throughout the extension.
 *
 * Port retarget (Phase 1, _analysis/04 §8 + Plan E §2): the reference
 * hardcoded qBittorrent on :8080. Boba reaches qBittorrent through the
 * download-proxy / merge service; the single foundation endpoint is the
 * Boba merge service on :7187. Every former :8080 value is now :7187.
 *
 * @module shared/constants
 */

// ─────────────────────────────────────────────────────────────────────────────
// Regex Patterns
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Regex for detecting magnet links in text.
 * Matches the standard magnet URI format with btih (BitTorrent infohash).
 *
 * Pattern: magnet:?xt=urn:btih:[40-char hex hash]
 *
 * @example
 * ```
 * magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678
 * magnet:?xt=urn:btih:1234567890ABCDEF1234567890ABCDEF12345678&dn=My+File
 * ```
 */
export const MAGNET_REGEX = /magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^\s"'<>]*/gi;

/**
 * Strict regex for validating a magnet URI format.
 * Requires the full prefix and a valid 40-char hex hash.
 */
export const MAGNET_VALIDATION_REGEX =
  /^magnet:\?xt=urn:btih:[a-fA-F0-9]{40}(?:[&;][^\s"'<>]*)?$/i;

/**
 * Regex for extracting the infohash from a magnet URI.
 * Captures the 40-character hex string after btih:
 */
export const INFOHASH_REGEX = /xt=urn:btih:([a-fA-F0-9]{40})/i;

/**
 * Regex for detecting .torrent file links.
 * Matches URLs ending in .torrent with common query parameters.
 */
export const TORRENT_FILE_REGEX =
  /https?:\/\/[^\s"'<>]+\.torrent(?:\?[^\s"'<>]*)?/gi;

/**
 * Regex for validating a .torrent file URL.
 */
export const TORRENT_FILE_VALIDATION_REGEX = /^https?:\/\/.+\.torrent(\?.*)?$/i;

/**
 * Regex for validating a 40-character hex infohash.
 */
export const INFOHASH_HEX_REGEX = /^[a-fA-F0-9]{40}$/;

/**
 * Regex for validating a 32-character base32 infohash.
 */
export const INFOHASH_BASE32_REGEX = /^[A-Z2-7]{32}$/;

/**
 * Regex for extracting the display name (dn) from a magnet URI.
 */
export const MAGNET_DN_REGEX = /[?&]dn=([^&;]*)/;

/**
 * Regex for extracting tracker URLs (tr) from a magnet URI.
 */
export const MAGNET_TR_REGEX = /[?&]tr=([^&;]*)/g;

// ─────────────────────────────────────────────────────────────────────────────
// Default Ports and URLs
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Default ports used by Boba Project services.
 */
export const DEFAULT_PORTS = {
  /** Boba Project FastAPI backend / merge service */
  FAST_API: 7187,

  /** Boba Project Go backend */
  GO: 7189,

  /**
   * qBitTorrent WebUI, reached via the Boba merge service on :7187
   * (retargeted from the reference :8080, _analysis/04 §8 + Plan E §2).
   */
  QBITTORRENT: 7187,
} as const;

/**
 * Default base URLs for Boba services.
 */
export const DEFAULT_URLS = {
  /** Boba FastAPI / merge service */
  FAST_API: "http://localhost:7187",

  /** Boba Go server */
  GO: "http://localhost:7189",

  /** qBitTorrent WebUI (via Boba merge service, retargeted from :8080) */
  QBITTORRENT: "http://localhost:7187",
} as const;

/**
 * Headers the Phase-4 Boba client uses to present the optional shared-secret
 * token (`BOBA_API_TOKEN`) to the merge-service download-write endpoints on :7187.
 * Either header is accepted by the backend gate (constant-time compared); the
 * gate is OPEN by default and only enforced when the operator sets the env var.
 */
export const BOBA_TOKEN_HEADERS = {
  /** `Authorization: Bearer <token>` */
  AUTHORIZATION: "Authorization",
  /** `X-Boba-Token: <token>` (alternative for clients that can't set Authorization) */
  X_BOBA_TOKEN: "X-Boba-Token",
} as const;

/**
 * qBitTorrent API endpoint paths.
 */
export const QBITTORRENT_ENDPOINTS = {
  /** Authentication */
  AUTH_LOGIN: "/api/v2/auth/login",
  AUTH_LOGOUT: "/api/v2/auth/logout",

  /** Application */
  APP_VERSION: "/api/v2/app/version",
  APP_PREFERENCES: "/api/v2/app/preferences",
  APP_SET_PREFERENCES: "/api/v2/app/setPreferences",

  /** Torrents */
  TORRENTS_ADD: "/api/v2/torrents/add",
  TORRENTS_INFO: "/api/v2/torrents/info",
  TORRENTS_DELETE: "/api/v2/torrents/delete",
  TORRENTS_PAUSE: "/api/v2/torrents/pause",
  TORRENTS_RESUME: "/api/v2/torrents/resume",

  /** Transfer */
  TRANSFER_INFO: "/api/v2/transfer/info",
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Timing and Performance
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Debounce delays for various operations in milliseconds.
 */
export const DEBOUNCE_DELAYS = {
  /** DOM mutation observer debounce */
  MUTATION: 500,

  /** Storage write debounce */
  STORAGE_WRITE: 250,

  /** Auto-scan after page changes */
  AUTO_SCAN: 1000,

  /** Badge update debounce */
  BADGE_UPDATE: 300,

  /** Notification debounce to prevent spam */
  NOTIFICATION: 2000,
} as const;

/**
 * Request timeouts in milliseconds.
 */
export const REQUEST_TIMEOUTS = {
  /** Default API request timeout */
  DEFAULT: 15000,

  /** Health check timeout */
  HEALTH_CHECK: 5000,

  /** Authentication timeout */
  AUTH: 10000,

  /** Torrent add timeout */
  ADD_TORRENT: 30000,

  /** Auto-discovery timeout per server */
  AUTO_DISCOVERY: 3000,
} as const;

/**
 * Retry configuration.
 */
export const RETRY_CONFIG = {
  /** Maximum number of retries */
  MAX_RETRIES: 3,

  /** Base delay in milliseconds (exponential backoff) */
  BASE_DELAY_MS: 1000,

  /** Maximum delay between retries */
  MAX_DELAY_MS: 30000,

  /** Jitter factor (0-1) to add randomness to delays */
  JITTER_FACTOR: 0.3,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Rate Limiting
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Rate limiting configuration.
 */
export const RATE_LIMIT = {
  /** Maximum requests per window */
  MAX_REQUESTS: 10,

  /** Window size in milliseconds */
  WINDOW_MS: 1000,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Storage Keys
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Keys used with chrome.storage.local.
 */
export const STORAGE_KEYS = {
  /** Extension configuration */
  CONFIG: "bobalink_config",

  /** Authentication state */
  AUTH_STATE: "bobalink_auth_state",

  /** Encrypted credentials */
  CREDENTIALS: "bobalink_credentials",

  /** Detected torrents per tab */
  DETECTED: "bobalink_detected",

  /** Send history */
  HISTORY: "bobalink_history",

  /** Offline queue */
  QUEUE: "bobalink_queue",

  /** Server health status */
  HEALTH: "bobalink_health",

  /** Encryption key material */
  KEY_MATERIAL: "bobalink_key_material",
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Encryption
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Encryption algorithm configuration.
 */
export const ENCRYPTION = {
  /** Algorithm name */
  ALGORITHM: "AES-GCM",

  /** Key length in bits */
  KEY_LENGTH_BITS: 256,

  /** IV length in bytes */
  IV_LENGTH_BYTES: 12,

  /** Salt length in bytes for key derivation */
  SALT_LENGTH_BYTES: 16,

  /** Key derivation algorithm */
  KDF_ALGORITHM: "PBKDF2",

  /** PBKDF2 iteration count */
  KDF_ITERATIONS: 100000,

  /** Key derivation hash function */
  KDF_HASH: "SHA-256",

  /** Current key version for migration support */
  CURRENT_KEY_VERSION: 1,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// UI Constants
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Badge colors for different states.
 */
export const BADGE_COLORS = {
  /** Connected and healthy */
  HEALTHY: "#4CAF50",

  /** Connection degraded */
  DEGRADED: "#FF9800",

  /** Not connected or error */
  ERROR: "#F44336",

  /** Scanning in progress */
  SCANNING: "#2196F3",

  /** Torrents detected */
  DETECTED: "#9C27B0",

  /** Default/neutral */
  DEFAULT: "#757575",
} as const;

/**
 * Extension icon sizes required by Chrome.
 */
export const ICON_SIZES = [16, 32, 48, 128] as const;

// ─────────────────────────────────────────────────────────────────────────────
// Site-Specific Selectors
// ─────────────────────────────────────────────────────────────────────────────

/**
 * CSS selectors for torrent links on popular torrent sites.
 *
 * Single source of truth for code-level selectors (the reference split these
 * across constants.SITE_SELECTORS + scanner/site-db.SITES; collapsed here per
 * F site-db REFACTOR). Supplements the generic magnet: and .torrent detection.
 * Boba's real private trackers (rutracker/kinozal/nnmclub/iptorrents) are
 * present alongside the public-tracker entries.
 */
export const SITE_SELECTORS: Readonly<Record<string, readonly string[]>> = {
  // General patterns
  generic: [
    'a[href^="magnet:"]',
    'a[href$=".torrent"]',
    'a[href*=".torrent?"]',
    'a[href*="download.php?id="]',
  ],

  // 1337x
  "1337x.to": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // The Pirate Bay
  "thepiratebay.org": ['a[href^="magnet:"]'],
  "thepiratebay10.org": ['a[href^="magnet:"]'],

  // RARBG (and mirrors)
  "rarbg.to": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],
  "rarbgtorrents.org": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // YTS
  "yts.mx": ['a[href^="magnet:"]'],
  "yts.lt": ['a[href^="magnet:"]'],

  // EZTV
  "eztv.re": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // LimeTorrents
  "limetorrents.lol": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // TorrentGalaxy
  "torrentgalaxy.to": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // Nyaa (anime)
  "nyaa.si": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // AnimeTosho
  "animetosho.org": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // Torrentz2
  "torrentz2.eu": ['a[href^="magnet:"]'],

  // FitGirl Repacks
  "fitgirl-repacks.site": ['a[href^="magnet:"]'],

  // RuTracker (Boba private tracker)
  "rutracker.org": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // Kinozal (Boba private tracker)
  "kinozal.tv": ['a[href^="magnet:"]', 'a[href*="/download.php?id="]'],

  // NNM-Club (Boba private tracker)
  "nnmclub.to": ['a[href^="magnet:"]', 'a[href*="download.php?id="]'],

  // RuTor (Boba public tracker)
  "rutor.info": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // KAT (Kickass Torrents)
  "katcr.co": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // Demonoid
  "demonoid.is": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // IPTorrents (Boba private tracker)
  "iptorrents.com": ['a[href$=".torrent"]', 'a[href*="download.php/"]'],

  // TorrentLeech (private)
  "torrentleech.org": ['a[href$=".torrent"]', 'a[href*="/download/"]'],

  // BeyondHD (private)
  "beyond-hd.me": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],

  // PassThePopcorn (private)
  "passthepopcorn.me": ['a[href^="magnet:"]', 'a[href$=".torrent"]'],
};

// ─────────────────────────────────────────────────────────────────────────────
// Misc
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Extension internal constants.
 */
export const EXT = {
  /** Extension ID (used for internal messaging) */
  ID: "bobalink",

  /** Display name */
  NAME: "BobaLink",

  /** Default category for torrents */
  DEFAULT_CATEGORY: "BobaLink",

  /** Maximum items to show in popup */
  MAX_POPUP_ITEMS: 50,

  /** Maximum length for display names in UI */
  MAX_DISPLAY_NAME_LENGTH: 80,
} as const;
