-- =============================================
-- BobaLink Extension Database Migration 001
-- Initial Schema (v1.0.0)
-- =============================================
-- Migration: 001_initial
-- Description: Creates all core tables, indexes, and seed data
-- for the BobaLink browser extension.
-- Author: BobaLink Team
-- Date: 2024-01-01
-- =============================================

BEGIN TRANSACTION;

-- =============================================
-- Application Metadata
-- =============================================
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

INSERT OR IGNORE INTO app_metadata (key, value, updated_at) VALUES
    ('schema_version', '1.0.0', strftime('%s','now')),
    ('migration_id', '001_initial', strftime('%s','now')),
    ('app_name', 'BobaLink', strftime('%s','now')),
    ('app_version', '1.0.0', strftime('%s','now')),
    ('installed_at', strftime('%s','now'), strftime('%s','now')),
    ('last_db_vacuum', strftime('%s','now'), strftime('%s','now'));

-- =============================================
-- Extension Configuration
-- =============================================
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
-- Discovered Torrents
-- =============================================
CREATE TABLE IF NOT EXISTS discovered_torrents (
    id TEXT PRIMARY KEY,
    page_url TEXT NOT NULL,
    page_title TEXT,
    magnet_uri TEXT,
    torrent_url TEXT,
    torrent_data_b64 TEXT,
    name TEXT,
    display_name TEXT,
    trackers TEXT,
    size_bytes INTEGER,
    source_type TEXT CHECK(source_type IN ('magnet-link', 'torrent-file', 'torrent-url', 'infohash')) NOT NULL,
    discovery_method TEXT CHECK(discovery_method IN ('link-scan', 'text-scan', 'site-specific', 'manual')) DEFAULT 'link-scan',
    is_private INTEGER DEFAULT 0,
    detected_at INTEGER NOT NULL,
    sent_to_boba INTEGER DEFAULT 0,
    sent_at INTEGER,
    boba_status TEXT CHECK(boba_status IN ('pending', 'queued', 'sending', 'added', 'duplicate', 'error', 'retrying')) DEFAULT 'pending',
    boba_error TEXT,
    tab_id INTEGER,
    tab_group_id INTEGER,
    selected INTEGER DEFAULT 1,
    metadata_json TEXT
);

-- =============================================
-- Download Queue (Offline Support)
-- =============================================
CREATE TABLE IF NOT EXISTS download_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    info_hash TEXT NOT NULL,
    magnet_uri TEXT,
    torrent_data_b64 TEXT,
    name TEXT,
    category TEXT,
    save_path TEXT,
    tags TEXT,
    add_paused INTEGER DEFAULT 0,
    skip_checking INTEGER DEFAULT 0,
    sequential_download INTEGER DEFAULT 0,
    first_last_piece_prio INTEGER DEFAULT 0,
    added_at INTEGER NOT NULL,
    retry_count INTEGER DEFAULT 0,
    last_retry_at INTEGER,
    next_retry_at INTEGER,
    last_error TEXT,
    error_code TEXT,
    status TEXT CHECK(status IN ('pending', 'retrying', 'failed_permanent', 'completed', 'cancelled')) DEFAULT 'pending',
    server_url TEXT NOT NULL,
    server_id INTEGER
);

-- =============================================
-- Server Configuration
-- =============================================
CREATE TABLE IF NOT EXISTS server_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL UNIQUE,
    auth_method TEXT CHECK(auth_method IN ('none', 'cookie', 'api_key', 'basic')) NOT NULL DEFAULT 'none',
    api_key_encrypted TEXT,
    username TEXT,
    password_encrypted TEXT,
    is_default INTEGER DEFAULT 0,
    is_reachable INTEGER DEFAULT 0,
    last_check_at INTEGER,
    last_check_result TEXT CHECK(last_check_result IN ('success', 'auth_required', 'unreachable', 'error')),
    qbittorrent_version TEXT,
    boba_version TEXT,
    boba_fastapi_port INTEGER DEFAULT 7187,
    boba_go_port INTEGER DEFAULT 7189,
    qbittorrent_port INTEGER DEFAULT 8080,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    notes TEXT
);

-- =============================================
-- Send History
-- =============================================
CREATE TABLE IF NOT EXISTS send_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    info_hash TEXT NOT NULL,
    name TEXT,
    magnet_uri TEXT,
    source_type TEXT NOT NULL,
    sent_at INTEGER NOT NULL,
    server_id INTEGER REFERENCES server_config(id),
    server_url TEXT NOT NULL,
    success INTEGER NOT NULL,
    response_code INTEGER,
    error_message TEXT,
    torrent_added_hash TEXT
);

-- =============================================
-- Site-Specific Selectors
-- =============================================
CREATE TABLE IF NOT EXISTS site_selectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_pattern TEXT NOT NULL,
    selector_type TEXT CHECK(selector_type IN ('magnet-link', 'torrent-link', 'name', 'size', 'seeders', 'leechers', 'date', 'uploader')) NOT NULL,
    css_selector TEXT NOT NULL,
    attribute TEXT,
    regex_filter TEXT,
    priority INTEGER DEFAULT 100,
    is_enabled INTEGER DEFAULT 1,
    notes TEXT
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
-- Queue Processing Log
-- =============================================
CREATE TABLE IF NOT EXISTS queue_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_item_id INTEGER REFERENCES download_queue(id),
    action TEXT NOT NULL CHECK(action IN ('enqueue', 'retry', 'success', 'fail', 'cancel', 'skip')),
    timestamp INTEGER NOT NULL,
    details TEXT,
    error TEXT
);

-- =============================================
-- Statistics
-- =============================================
CREATE TABLE IF NOT EXISTS statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_type TEXT NOT NULL CHECK(stat_type IN ('torrents_detected', 'torrents_sent', 'torrents_failed', 'api_calls', 'api_errors', 'queue_items', 'queue_retries', 'scans_performed', 'page_visits')),
    stat_value INTEGER NOT NULL DEFAULT 0,
    stat_date TEXT NOT NULL,
    created_at INTEGER NOT NULL,
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

COMMIT;
