"""
Environment variable loader for merge service.

Loads and validates environment variables for:
- qBittorrent connection
- Metadata API keys (OMDb, TMDB, etc.)
- Service configuration
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EnvConfig:
    """Environment configuration for merge service."""

    # qBittorrent
    qbittorrent_host: str
    qbittorrent_port: int
    qbittorrent_username: str
    qbittorrent_password: str

    # Service
    proxy_port: int
    log_level: str

    # Metadata APIs
    omdb_api_key: str | None = None
    tmdb_api_key: str | None = None
    anilist_client_id: str | None = None

    # Private trackers
    rutracker_username: str | None = None
    rutracker_password: str | None = None
    kinozal_username: str | None = None
    kinozal_password: str | None = None
    nnmclub_cookies: str | None = None
    iptorrents_username: str | None = None
    iptorrents_password: str | None = None


def load_env() -> EnvConfig:
    """Load and validate environment variables."""

    # qBittorrent settings
    qbittorrent_host = os.environ.get("QBITTORRENT_HOST", "localhost")
    qbittorrent_port = int(os.environ.get("QBITTORRENT_PORT", "7185"))
    qbittorrent_username = os.environ.get("QBITTORRENT_USER", os.environ.get("QBITTORRENT_USERNAME", "admin"))
    qbittorrent_password = os.environ.get("QBITTORRENT_PASS", os.environ.get("QBITTORRENT_PASSWORD", "admin"))

    # Service settings
    proxy_port = int(os.environ.get("PROXY_PORT", "7186"))
    log_level = os.environ.get("LOG_LEVEL", "INFO")

    # Metadata API keys
    omdb_api_key = os.environ.get("OMDB_API_KEY")
    tmdb_api_key = os.environ.get("TMDB_API_KEY")
    anilist_client_id = os.environ.get("ANILIST_CLIENT_ID")

    # Private tracker credentials
    rutracker_username = os.environ.get("RUTRACKER_USERNAME")
    rutracker_password = os.environ.get("RUTRACKER_PASSWORD")
    iptorrents_username = os.environ.get("IPTORRENTS_USERNAME")
    iptorrents_password = os.environ.get("IPTORRENTS_PASSWORD")
    kinozal_username = os.environ.get("KINOZAL_USERNAME") or iptorrents_username
    kinozal_password = os.environ.get("KINOZAL_PASSWORD") or iptorrents_password
    nnmclub_cookies = os.environ.get("NNMCLUB_COOKIES")

    config = EnvConfig(
        qbittorrent_host=qbittorrent_host,
        qbittorrent_port=qbittorrent_port,
        qbittorrent_username=qbittorrent_username,
        qbittorrent_password=qbittorrent_password,
        proxy_port=proxy_port,
        log_level=log_level,
        omdb_api_key=omdb_api_key,
        tmdb_api_key=tmdb_api_key,
        anilist_client_id=anilist_client_id,
        rutracker_username=rutracker_username,
        rutracker_password=rutracker_password,
        kinozal_username=kinozal_username,
        kinozal_password=kinozal_password,
        nnmclub_cookies=nnmclub_cookies,
        iptorrents_username=iptorrents_username,
        iptorrents_password=iptorrents_password,
    )

    logger.info(f"Loaded configuration for qBittorrent at {qbittorrent_host}:{qbittorrent_port}")

    return config


# Global config instance
_config: EnvConfig | None = None


def get_config() -> EnvConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_env()
    return _config


def reload_config() -> None:
    """Reload configuration from environment."""
    global _config
    _config = load_env()
