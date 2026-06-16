# download-proxy/src/config/

Environment variable loading and log filtering.

## Files

- **`__init__.py`** — `EnvConfig` dataclass and `load_env()` / `get_config()` / `reload_config()`.
- **`log_filter.py`** — `CredentialScrubber`: redacts passwords, cookies, and API keys from log output.

## EnvConfig Fields

| Field | Env Var | Default |
|-------|---------|---------|
| `qbittorrent_host` | `QBITTORRENT_HOST` | `localhost` |
| `qbittorrent_port` | `QBITTORRENT_PORT` | `7185` |
| `qbittorrent_username` | `QBITTORRENT_USER` | `admin` |
| `qbittorrent_password` | `QBITTORRENT_PASS` | `admin` |
| `proxy_port` | `PROXY_PORT` | `7186` |
| `log_level` | `LOG_LEVEL` | `INFO` |
| `omdb_api_key` | `OMDB_API_KEY` | `None` |
| `tmdb_api_key` | `TMDB_API_KEY` | `None` |
| `anilist_client_id` | `ANILIST_CLIENT_ID` | `None` |
| `rutracker_username` | `RUTRACKER_USERNAME` | `None` |
| `rutracker_password` | `RUTRACKER_PASSWORD` | `None` |
| `kinozal_username` | `KINOZAL_USERNAME` | falls back to `IPTORRENTS_USERNAME` |
| `kinozal_password` | `KINOZAL_PASSWORD` | falls back to `IPTORRENTS_PASSWORD` |
| `nnmclub_cookies` | `NNMCLUB_COOKIES` | `None` |
| `rutracker_cookies` | `RUTRACKER_COOKIES` | `None` (browser cookies bypass the CAPTCHA-walled login) |
| `iptorrents_username` | `IPTORRENTS_USERNAME` | `None` |
| `iptorrents_password` | `IPTORRENTS_PASSWORD` | `None` |

## How to Test

```bash
python3 -m pytest tests/unit/ -k "config" -v --import-mode=importlib
```
