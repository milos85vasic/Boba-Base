-- =============================================
-- BobaLink Extension Database Schema v1.0.0
-- =============================================
-- Description: Complete SQLite schema for the BobaLink browser extension.
-- This schema is used via chrome.storage.local with an sql.js wrapper
-- for persistent, structured storage of torrent discovery, queue,
-- configuration, and analytics data.
--
-- Tables: 9
-- Indexes: 7
-- Default site selectors: 20
-- Default config values: 16
--
-- Compatible with: SQLite 3.38+, sql.js
-- =============================================

-- =============================================
-- 1. Application Metadata
-- =============================================
-- Stores schema version, migration state, and app-level metadata.
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

INSERT OR IGNORE INTO app_metadata (key, value, updated_at) VALUES
    ('schema_version', '1.0.0', strftime('%s','now')),
    ('app_name', 'BobaLink', strftime('%s','now')),
    ('app_version', '1.0.0', strftime('%s','now')),
    ('installed_at', strftime('%s','now'), strftime('%s','now')),
    ('last_db_vacuum', strftime('%s','now'), strftime('%s','now'));

-- =============================================
-- 2. Extension Configuration
-- =============================================
-- Key-value store for user-configurable settings with type safety.
CREATE TABLE IF NOT EXISTS extension_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    data_type TEXT CHECK(data_type IN ('string', 'number', 'boolean', 'json', 'encrypted')) NOT NULL,
    description TEXT,
    updated_at INTEGER NOT NULL
);

INSERT OR IGNORE INTO extension_config (key, value, data_type, description, updated_at) VALUES
    ('server.base_url', 'http://localhost:8080', 'string', 'Boba/qBitTorrent server URL', strftime('%s','now')),
    ('server.auth_method', 'cookie', 'string', 'Authentication method', strftime('%s','now')),
    ('server.api_key', '', 'encrypted', 'API key for authentication', strftime('%s','now')),
    ('server.username', '', 'string', 'Username for cookie auth', strftime('%s','now')),
    ('server.password', '', 'encrypted', 'Password for cookie auth', strftime('%s','now')),
    ('download.default_category', '', 'string', 'Default torrent category', strftime('%s','now')),
    ('download.default_save_path', '', 'string', 'Default download save path', strftime('%s','now')),
    ('download.start_paused', 'false', 'boolean', 'Start torrents paused', strftime('%s','now')),
    ('download.auto_manage', 'true', 'boolean', 'Use automatic torrent management', strftime('%s','now')),
    ('behavior.auto_scan', 'true', 'boolean', 'Auto-scan pages on load', strftime('%s','now')),
    ('behavior.highlight_detected', 'true', 'boolean', 'Highlight detected torrents on page', strftime('%s','now')),
    ('behavior.show_notifications', 'true', 'boolean', 'Show download notifications', strftime('%s','now')),
    ('behavior.rate_limit_requests', '30', 'number', 'Max API requests per minute', strftime('%s','now')),
    ('behavior.max_storage_mb', '50', 'number', 'Max storage size in MB', strftime('%s','now')),
    ('security.require_https', 'true', 'boolean', 'Require HTTPS for server communication', strftime('%s','now')),
    ('security.encrypt_credentials', 'true', 'boolean', 'Encrypt stored credentials', strftime('%s','now')),
    ('security.session_timeout', '3600', 'number', 'Session timeout in seconds', strftime('%s','now')),
    ('ui.theme', 'auto', 'string', 'UI theme (auto/light/dark)', strftime('%s','now')),
    ('ui.popup_width', '400', 'number', 'Popup width in pixels', strftime('%s','now')),
    ('ui.popup_height', '600', 'number', 'Popup height in pixels', strftime('%s','now')),
    ('ui.show_tracker_list', 'true', 'boolean', 'Show tracker list in popup', strftime('%s','now')),
    ('ui.batch_select_default', 'true', 'boolean', 'Auto-select all discovered torrents', strftime('%s','now')),
    ('advanced.debug_mode', 'false', 'boolean', 'Enable debug logging', strftime('%s','now')),
    ('advanced.scan_interval_ms', '2000', 'number', 'DOM scan debounce interval ms', strftime('%s','now')),
    ('advanced.max_torrent_size_gb', '100', 'number', 'Max torrent size to display', strftime('%s','now'));

-- =============================================
-- 3. Discovered Torrents
-- =============================================
-- Tracks all torrents discovered on web pages per session.
CREATE TABLE IF NOT EXISTS discovered_torrents (
    id TEXT PRIMARY KEY,              -- infoHash (40-character hex)
    page_url TEXT NOT NULL,           -- URL where torrent was found
    page_title TEXT,                  -- Page title at time of discovery
    magnet_uri TEXT,                  -- Full magnet URI
    torrent_url TEXT,                 -- Direct .torrent file URL
    torrent_data_b64 TEXT,            -- Base64 encoded .torrent file content
    name TEXT,                        -- Torrent name (from metadata or magnet dn)
    display_name TEXT,                -- URL-decoded display name for UI
    trackers TEXT,                    -- JSON array of tracker URLs
    size_bytes INTEGER,               -- Total size in bytes (null if unknown)
    source_type TEXT CHECK(source_type IN ('magnet-link', 'torrent-file', 'torrent-url', 'infohash')) NOT NULL,
    discovery_method TEXT CHECK(discovery_method IN ('link-scan', 'text-scan', 'site-specific', 'manual')) DEFAULT 'link-scan',
    is_private INTEGER DEFAULT 0,     -- 1 if private torrent
    detected_at INTEGER NOT NULL,     -- Unix timestamp
    sent_to_boba INTEGER DEFAULT 0,   -- 1 if sent to Boba/qBitTorrent
    sent_at INTEGER,                  -- Unix timestamp of send
    boba_status TEXT CHECK(boba_status IN ('pending', 'queued', 'sending', 'added', 'duplicate', 'error', 'retrying')) DEFAULT 'pending',
    boba_error TEXT,                  -- Error message if failed
    tab_id INTEGER,                   -- Chrome tab ID
    tab_group_id INTEGER,             -- Chrome tab group ID
    selected INTEGER DEFAULT 1,       -- For batch operations (1=selected)
    metadata_json TEXT                -- Additional metadata as JSON
);

-- =============================================
-- 4. Download Queue (Offline Support)
-- =============================================
-- Stores torrents queued for download when server is unreachable.
CREATE TABLE IF NOT EXISTS download_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    info_hash TEXT NOT NULL,          -- 40-char hex infohash
    magnet_uri TEXT,                  -- Full magnet URI
    torrent_data_b64 TEXT,            -- Base64 encoded .torrent file
    name TEXT,                        -- Torrent name
    category TEXT,                    -- qBitTorrent category
    save_path TEXT,                   -- Download save path
    tags TEXT,                        -- JSON array of tags
    add_paused INTEGER DEFAULT 0,     -- 1 = add paused
    skip_checking INTEGER DEFAULT 0,  -- 1 = skip hash check
    sequential_download INTEGER DEFAULT 0,  -- 1 = sequential
    first_last_piece_prio INTEGER DEFAULT 0, -- 1 = prioritize first/last pieces
    added_at INTEGER NOT NULL,        -- Unix timestamp
    retry_count INTEGER DEFAULT 0,    -- Number of retry attempts
    last_retry_at INTEGER,            -- Last retry timestamp
    next_retry_at INTEGER,            -- Next scheduled retry (exponential backoff)
    last_error TEXT,                  -- Last error message
    error_code TEXT,                  -- Categorized error code
    status TEXT CHECK(status IN ('pending', 'retrying', 'failed_permanent', 'completed', 'cancelled')) DEFAULT 'pending',
    server_url TEXT NOT NULL,         -- Target server URL
    server_id INTEGER                 -- References server_config.id
);

-- =============================================
-- 5. Server Configuration
-- =============================================
-- Multi-server support for Boba/qBitTorrent instances.
CREATE TABLE IF NOT EXISTS server_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,               -- Display name (e.g., "Home Boba")
    base_url TEXT NOT NULL UNIQUE,    -- Server base URL
    auth_method TEXT CHECK(auth_method IN ('none', 'cookie', 'api_key', 'basic')) NOT NULL DEFAULT 'none',
    api_key_encrypted TEXT,           -- Encrypted API key
    username TEXT,                    -- Username for cookie/basic auth
    password_encrypted TEXT,          -- Encrypted password
    is_default INTEGER DEFAULT 0,     -- 1 = default server
    is_reachable INTEGER DEFAULT 0,   -- 1 = last check succeeded
    last_check_at INTEGER,            -- Last connectivity check
    last_check_result TEXT CHECK(last_check_result IN ('success', 'auth_required', 'unreachable', 'error')),
    qbittorrent_version TEXT,         -- Detected qBitTorrent version
    boba_version TEXT,                -- Detected Boba version
    boba_fastapi_port INTEGER DEFAULT 7187,  -- Boba FastAPI port
    boba_go_port INTEGER DEFAULT 7189,       -- Boba Go port
    qbittorrent_port INTEGER DEFAULT 8080,   -- qBitTorrent WebUI port
    created_at INTEGER NOT NULL,      -- Unix timestamp
    updated_at INTEGER NOT NULL,      -- Unix timestamp
    notes TEXT                        -- User notes about this server
);

-- =============================================
-- 6. Send History
-- =============================================
-- Immutable log of all torrent send attempts.
CREATE TABLE IF NOT EXISTS send_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    info_hash TEXT NOT NULL,          -- Source infohash
    name TEXT,                        -- Torrent name
    magnet_uri TEXT,                  -- Magnet URI sent
    source_type TEXT NOT NULL,        -- Type of source
    sent_at INTEGER NOT NULL,         -- Unix timestamp
    server_id INTEGER REFERENCES server_config(id),
    server_url TEXT NOT NULL,         -- Target server URL
    success INTEGER NOT NULL,         -- 1 = success, 0 = failure
    response_code INTEGER,            -- HTTP response code
    error_message TEXT,               -- Error message on failure
    torrent_added_hash TEXT           -- Hash returned by qBitTorrent
);

-- =============================================
-- 7. Site-Specific Selectors
-- =============================================
-- CSS selectors for extracting torrent data from specific sites.
CREATE TABLE IF NOT EXISTS site_selectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_pattern TEXT NOT NULL,     -- e.g., "thepiratebay.*"
    selector_type TEXT CHECK(selector_type IN ('magnet-link', 'torrent-link', 'name', 'size', 'seeders', 'leechers', 'date', 'uploader')) NOT NULL,
    css_selector TEXT NOT NULL,       -- CSS selector string
    attribute TEXT,                   -- e.g., 'href', null for text content
    regex_filter TEXT,                -- Optional regex to extract value
    priority INTEGER DEFAULT 100,     -- Lower = higher priority
    is_enabled INTEGER DEFAULT 1,     -- 1 = active
    notes TEXT                        -- Human-readable description
);

INSERT OR IGNORE INTO site_selectors (domain_pattern, selector_type, css_selector, attribute, priority, notes) VALUES
    ('thepiratebay.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'The Pirate Bay'),
    ('1337x.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, '1337x magnet'),
    ('1337x.*', 'torrent-link', 'a[href$=".torrent"]', 'href', 20, '1337x direct torrent'),
    ('nyaa.si', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'Nyaa magnet'),
    ('nyaa.si', 'torrent-link', 'a[href$=".torrent"]', 'href', 20, 'Nyaa direct torrent'),
    ('rutracker.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'RuTracker magnet'),
    ('rutracker.*', 'torrent-link', 'a[href$=".torrent"]', 'href', 20, 'RuTracker direct torrent'),
    ('kinozal.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'Kinozal magnet'),
    ('nnm-club.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'NNM-Club magnet'),
    ('iptorrents.*', 'torrent-link', 'a[href$=".torrent"]', 'href', 10, 'IPTorrents direct'),
    ('limetorrents.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'LimeTorrents magnet'),
    ('torrentgalaxy.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'TorrentGalaxy magnet'),
    ('glodls.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'GloDLS magnet'),
    ('torlock.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'Torlock magnet'),
    ('eztv.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'EZTV magnet'),
    ('yts.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'YTS magnet'),
    ('rarbg.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'RARBG mirrors'),
    ('demonoid.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'Demonoid magnet'),
    ('torrentfunk.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'TorrentFunk magnet'),
    ('yourbittorrent.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'YourBittorrent magnet'),
    ('bitsearch.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'BitSearch magnet'),
    ('bt4g.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'BT4G magnet'),
    ('solidtorrents.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'SolidTorrents magnet'),
    ('knaben.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'Knaben magnet'),
    ('snowfl.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'Snowfl magnet'),
    ('bittorrent.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'BitTorrent search'),
    ('megapeer.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'MegaPeer magnet'),
    ('badasstorrents.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'BadassTorrents magnet'),
    ('extratorrent.*', 'magnet-link', 'a[href^="magnet:"]', 'href', 10, 'ExtraTorrent mirrors');

-- =============================================
-- 8. Queue Processing Log
-- =============================================
-- Detailed log of queue processing events.
CREATE TABLE IF NOT EXISTS queue_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_item_id INTEGER REFERENCES download_queue(id),
    action TEXT NOT NULL CHECK(action IN ('enqueue', 'retry', 'success', 'fail', 'cancel', 'skip')),
    timestamp INTEGER NOT NULL,       -- Unix timestamp
    details TEXT,                     -- JSON with additional details
    error TEXT                        -- Error message if applicable
);

-- =============================================
-- 9. Statistics
-- =============================================
-- Aggregated daily statistics for analytics.
CREATE TABLE IF NOT EXISTS statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_type TEXT NOT NULL CHECK(stat_type IN ('torrents_detected', 'torrents_sent', 'torrents_failed', 'api_calls', 'api_errors', 'queue_items', 'queue_retries', 'scans_performed', 'page_visits')),
    stat_value INTEGER NOT NULL DEFAULT 0,
    stat_date TEXT NOT NULL,          -- YYYY-MM-DD
    created_at INTEGER NOT NULL,      -- Unix timestamp
    UNIQUE(stat_type, stat_date)
);

-- =============================================
-- Performance Indexes
-- =============================================
CREATE INDEX IF NOT EXISTS idx_discovered_page_url ON discovered_torrents(page_url);
CREATE INDEX IF NOT EXISTS idx_discovered_status ON discovered_torrents(boba_status);
CREATE INDEX IF NOT EXISTS idx_discovered_tab ON discovered_torrents(tab_id);
CREATE INDEX IF NOT EXISTS idx_discovered_detected ON discovered_torrents(detected_at);
CREATE INDEX IF NOT EXISTS idx_discovered_selected ON discovered_torrents(selected) WHERE selected = 1;

CREATE INDEX IF NOT EXISTS idx_queue_status ON download_queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_next_retry ON download_queue(next_retry_at);
CREATE INDEX IF NOT EXISTS idx_queue_hash ON download_queue(info_hash);
CREATE INDEX IF NOT EXISTS idx_queue_server ON download_queue(server_url);

CREATE INDEX IF NOT EXISTS idx_history_hash ON send_history(info_hash);
CREATE INDEX IF NOT EXISTS idx_history_date ON send_history(sent_at);
CREATE INDEX IF NOT EXISTS idx_history_server ON send_history(server_id);

CREATE INDEX IF NOT EXISTS idx_config_key ON extension_config(key);
CREATE INDEX IF NOT EXISTS idx_server_default ON server_config(is_default) WHERE is_default = 1;
CREATE INDEX IF NOT EXISTS idx_server_url ON server_config(base_url);

CREATE INDEX IF NOT EXISTS idx_selectors_domain ON site_selectors(domain_pattern);
CREATE INDEX IF NOT EXISTS idx_selectors_enabled ON site_selectors(is_enabled) WHERE is_enabled = 1;

CREATE INDEX IF NOT EXISTS idx_queue_log_item ON queue_log(queue_item_id);
CREATE INDEX IF NOT EXISTS idx_queue_log_timestamp ON queue_log(timestamp);

CREATE INDEX IF NOT EXISTS idx_stats_type_date ON statistics(stat_type, stat_date);
