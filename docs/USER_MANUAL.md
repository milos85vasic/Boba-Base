# qBitTorrent-Fixed User Manual

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

## Complete Guide to Using All 12 Search Plugins

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Plugin Overview](#plugin-overview)
3. [Configuration](#configuration)
4. [Using the WebUI](#using-the-webui)
5. [Using Private Trackers](#using-private-trackers)
6. [Merge Search Service](#merge-search-service)
7. [Troubleshooting](#troubleshooting)
8. [Testing](#testing)
9. [FAQ](#faq)

---

## Quick Start

### 1. Installation

```bash
# Clone and setup
git clone https://github.com/yourusername/qBitTorrent-Fixed.git
cd qBitTorrent-Fixed

# Run automated setup
./setup.sh

# Configure credentials (optional, for private trackers)
vim .env
```

### 2. Start Everything

```bash
# Terminal 1: Start qBittorrent
./start.sh

# Terminal 2: Start WebUI Bridge (for private trackers)
python3 webui-bridge.py

# Access WebUI
http://localhost:7186
# Login: admin / admin
```

#### Go Backend (Optional)

The Go/Gin backend replaces the Python FastAPI merge service and webui-bridge:

```bash
# Start with Go backend instead of Python
podman compose --profile go up -d

# Or build and run locally
cd qBitTorrent-go && ./scripts/build.sh
./qbittorrent-proxy   # Starts merge service on port 7187
./webui-bridge        # Starts bridge on port 7188
```

### 3. Verify Installation

```bash
# Run all tests
./run-all-tests.sh

# Check plugin status
python3 tests/final_verification.py
```

---

## Plugin Overview

### Public Trackers (9 plugins)

These work immediately without configuration:

| Plugin | Content Type | WebUI | Magnet Links | Notes |
|--------|--------------|-------|--------------|-------|
| **The Pirate Bay** | General | ✅ | ✅ | Most popular |
| **EZTV** | TV Shows | ✅ | ✅ | Best for TV |
| **Rutor** | Russian | ✅ | ✅ | Russian content |
| **LimeTorrents** | General | ✅ | ❌ | Verified torrents |
| **Solid Torrents** | General | ✅ | ✅ | Fast search |
| **TorrentProject** | General | ✅ | ❌ | Comprehensive |
| **torrents-csv** | General | ✅ | ✅ | Open database |
| **TorLock** | General | ✅ | ✅ | No fake torrents |
| **Jackett** | Meta | ✅ | ❌ | Aggregates multiple |

### Private Trackers (3 plugins)

These require credentials:

| Plugin | Content Type | Credentials Required | Best For |
|--------|--------------|---------------------|----------|
| **RuTracker** | Russian | Username/Password | Russian content |
| **Kinozal** | Movies/TV | Username/Password | Movies and TV |
| **NNMClub** | General | Cookies | General content |

---

## Configuration

### Setting Up Credentials

Edit `.env` file:

```bash
# Public trackers (no configuration needed)

# Private trackers (optional, for WebUI support)
RUTRACKER_USERNAME=your_rutracker_username
RUTRACKER_PASSWORD=your_rutracker_password

KINOZAL_USERNAME=your_kinozal_username
KINOZAL_PASSWORD=your_kinozal_password

# For NNMClub, get cookies from browser:
# 1. Login to nnmclub.to in browser
# 2. Open developer tools (F12)
# 3. Go to Application/Storage > Cookies
# 4. Copy uid and pass cookies
NNMCLUB_COOKIES="uid=123456; pass=abcdef1234567890abcdef1234567890"
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QBITTORRENT_DATA_DIR` | `/mnt/DATA` | Download directory |
| `QBITTORRENT_HOST` | `localhost` | qBittorrent host |
| `QBITTORRENT_PORT` | `7185` | qBittorrent WebUI port |
| `MERGE_SERVICE_PORT` | `7187` | Merge Search Service port |
| `MERGE_SERVICE_HOST` | `0.0.0.0` | Merge service bind address |
| `PROXY_PORT` | `7186` | Download proxy port |
| `BRIDGE_PORT` | `7188` | WebUI Bridge port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALLOWED_ORIGINS` | — | CORS origins (comma-separated, no wildcards in prod) |
| `MAX_CONCURRENT_SEARCHES` | `5` | Concurrent tracker search cap |
| `DISABLE_THEME_INJECTION` | — | Set to `1` to disable cross-app theme |
| `OMDB_API_KEY` | — | OMDb metadata API key |
| `TMDB_API_KEY` | — | TMDB metadata API key |
| `ANILIST_CLIENT_ID` | — | AniList API client ID |

### Install Paths

| Path | Purpose |
|------|---------|
| `config/qBittorrent/` | qBittorrent configuration (auto-created by container) |
| `config/qBittorrent/nova3/engines/` | Search plugin engine files |
| `config/download-proxy/` | Download proxy config + hooks |
| `config/merge-service/` | Scheduler persistence (`scheduling.json`) |
| `plugins/` | Plugin source of truth (canonical) |
| `plugins/community/` | Non-canonical/community plugins |
| `frontend/` | Angular 21 dashboard source |

### CLI Flags

```bash
./start.sh -p       # Pull images before starting
./start.sh -s       # Show container status after starting
./start.sh -v       # Verbose output

./stop.sh -r        # Remove containers after stopping
./stop.sh --purge   # Remove containers AND images

./ci.sh             # Full CI pipeline
./ci.sh --quick     # Syntax + unit tests only
./ci.sh --tests-only # Skip syntax checks

scripts/run-tests.sh hermetic  # Fast tests (no services)
scripts/run-tests.sh live      # Tests requiring running containers
scripts/run-tests.sh all       # Everything

scripts/scan.sh --all          # Run all security scanners
scripts/scan.sh pip-audit ruff # Run specific scanners
```

### Plugin Installation

```bash
./install-plugin.sh --all              # Install all plugins
./install-plugin.sh rutracker rutor    # Install specific plugins
./install-plugin.sh --verify           # Verify all plugins installed
./install-plugin.sh --local --all      # Install for desktop app
```

Plugins are copied from `plugins/X.py` → `config/qBittorrent/nova3/engines/X.py`. Always edit the source in `plugins/` — the engines directory is clobbered on reinstall.

---

## Using the WebUI

### Basic Search

1. Open `http://localhost:7186`
2. Login with admin/admin
3. Click "Search" tab
4. Enter search term (e.g., "ubuntu")
5. Select plugin from dropdown
6. Click "Search"

### Downloading Torrents

#### Public Trackers (PirateBay, EZTV, etc.)

1. Search for content
2. Click download icon (⬇️)
3. Torrent appears in Transfer list
4. Download starts automatically

#### Private Trackers (RuTracker, Kinozal, NNMClub)

**Option A: Using WebUI Bridge (Recommended)**

1. Start WebUI Bridge: `python3 webui-bridge.py`
2. Search for content
3. Click download icon
4. Bridge handles authentication automatically

**Option B: Using Desktop App**

1. Install plugins locally: `./install-plugin.sh --local --all`
2. Open qBittorrent Desktop App
3. Go to View → Search Engine
4. Downloads work without bridge

**Option C: Manual Download**

1. Search in WebUI
2. Note the torrent name
3. Go to tracker website directly
4. Download .torrent file
5. Upload to qBittorrent WebUI

---

## Using Private Trackers

### RuTracker

**Requirements:**
- Active account on rutracker.org
- Valid username and password

**Setup:**
```bash
# Add to .env
RUTRACKER_USERNAME=your_username
RUTRACKER_PASSWORD=your_password

# Restart container
./restart.sh
```

**Usage:**
1. Enable RuTracker in Search Plugins
2. Search for Russian content
3. Click download (works with WebUI Bridge)

**Tips:**
- RuTracker has the best Russian content
- Very reliable for software and movies
- Works best with WebUI Bridge

### Kinozal

**Requirements:**
- Active account on kinozal.tv
- Valid username and password

**Setup:**
```bash
# Add to .env
KINOZAL_USERNAME=your_username
KINOZAL_PASSWORD=your_password
```

**Usage:**
1. Enable Kinozal in Search Plugins
2. Search for movies/TV shows
3. Works with WebUI Bridge

### NNMClub

**Requirements:**
- Active account on nnmclub.to
- Cookie-based authentication

**Setup:**
```bash
# Get cookies from browser
# Add to .env
NNMCLUB_COOKIES="uid=your_uid; pass=your_pass_hash"
```

**Getting Cookies:**
1. Login to nnmclub.to in browser
2. Press F12 (Developer Tools)
3. Go to Application/Storage → Cookies
4. Find `uid` and `pass` cookies
5. Copy values to .env

---

## Merge Search Service

The Merge Search Service is a unified search interface that queries multiple private trackers simultaneously, deduplicates results, and presents them in a single dashboard.

### What It Does

- Searches **RuTracker**, **Kinozal**, and **NNMClub** in parallel
- Deduplicates results that appear on multiple trackers
- Detects quality tags (e.g., 1080p, 4K, WEB-DL, Blu-ray) automatically
- Proxied downloads handle authentication cookies transparently

### Accessing the Dashboard

Open your browser to:

```
http://localhost:7187/
```

The dashboard runs inside the `qbittorrent-proxy` container and is available whenever containers are running. With the Go backend (`--profile go`), the same dashboard is served by the Go binary.

### Dashboard Usage

1. **Search** — Enter a query and press Search. Results from all configured trackers appear in a single list.
2. **Download** — Click the download button on any result. The proxy intercepts the tracker URL and fetches the .torrent file using stored credentials.
3. **Active Torrents** — The dashboard shows currently active downloads from the qBittorrent instance.

### API Endpoints (Power Users)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/search?q=<query>` | GET | Search all configured trackers |
| `/api/search?q=<query>&tracker=rutracker` | GET | Search a specific tracker |
| `/api/download` | POST | Download a torrent by URL |
| `/api/torrents/active` | GET | List active downloads |
| `/api/health` | GET | Service health check |

Example:
```bash
curl "http://localhost:7187/api/search?q=ubuntu&tracker=rutracker"
```

### Configuration

The merge service uses the same environment variables as the plugins. Set these in `.env`:

```bash
RUTRACKER_USERNAME=your_username
RUTRACKER_PASSWORD=your_password

KINOZAL_USERNAME=your_username
KINOZAL_PASSWORD=your_password

NNMCLUB_COOKIES="uid=123456; pass=abcdef1234567890"
```

Restart containers after changing credentials: `./stop.sh -r && ./start.sh`

### Quality Detection

The service automatically detects quality tags from torrent names:

- **Resolution**: 4K, 2160p, 1080p, 720p, 480p
- **Source**: Blu-ray, WEB-DL, WEBRip, HDTV, CAM, TS
- **Codec**: HEVC, H.265, H.264, x265, x264
- **Audio**: Atmos, DTS-HD, DTS, AAC, FLAC

Results are tagged and can be filtered by quality in the dashboard.

### Known Limitations

- **Credentials required** — RuTracker and Kinozal need valid username/password. NNMClub needs browser cookies. Trackers without configured credentials are skipped.
- **RuTracker CAPTCHA** — If RuTracker presents a CAPTCHA, login will fail. Solve it in a browser first, then retry.
- **Rate limiting** — Tracker websites may rate-limit frequent requests. The service includes basic throttling.
- **No public trackers** — The merge service only covers private trackers. Use the qBittorrent search tab for public tracker plugins.

---

## Troubleshooting

### Issue: Plugin Not Showing in WebUI

**Solution:**
```bash
./install-plugin.sh --all
podman restart qbittorrent
# Hard refresh browser (Ctrl+Shift+R)
```

### Issue: Download Doesn't Start (Private Trackers)

**Cause:** WebUI bypasses authentication

**Solutions:**

1. **Use WebUI Bridge (Recommended)**
   ```bash
   python3 webui-bridge.py
   ```

2. **Use Desktop App**
   ```bash
   ./install-plugin.sh --local --all
   # Then use Desktop App
   ```

3. **Check Credentials**
   ```bash
   cat .env
   # Verify username/password are correct
   ```

### Issue: Search Returns No Results

**Check:**
1. Internet connection
2. Plugin is enabled in Search tab
3. Try different search terms
4. Check container logs: `podman logs qbittorrent`
5. Check proxy logs: `podman logs qbittorrent-proxy`
6. Verify tracker credentials: `curl http://localhost:7187/health`

### Issue: Merge Service Returns 503

**Cause:** Service shutting down or not started

**Check:**
```bash
podman logs qbittorrent-proxy | tail -20
curl http://localhost:7187/health
```

### Issue: CORS Errors in Browser Console

**Fix:** Set `ALLOWED_ORIGINS` in `.env`:
```bash
ALLOWED_ORIGINS=http://localhost:4200,http://localhost:7187
```

### Issue: Column Data Shows Zeros

**Status:** Fixed in this version. All plugins return real data for seeds, leech, and size.

### Issue: Container Won't Start

**Solution:**
```bash
# Full reset
./stop.sh -r
podman system prune -f
./start.sh
```

### Issue: RuTracker Login Fails (CAPTCHA)

**Fix:** Solve the CAPTCHA in a browser first, then retry. Cookies expire periodically.

### Issue: Security Scan Failures

**Fix:** Run scanners individually to identify the issue:
```bash
scripts/scan.sh pip-audit ruff
# Check artifacts/scans/ for SARIF reports
```

---

## Testing

### Run All Tests

```bash
# Comprehensive test suite
./run-all-tests.sh

# Individual tests
python3 -m pytest tests/unit/ tests/e2e/ --import-mode=importlib
python3 tests/final_verification.py
python3 -m pytest tests/unit/ --import-mode=importlib
```

### Test Results

Tests cover:
- ✅ Plugin structure validation
- ✅ Search functionality
- ✅ Download functionality
- ✅ Column data validation (seeds, leech, size)
- ✅ Authentication handling

Expected result: **100% success rate**

---

## FAQ

### Q: Why create a fork instead of fixing upstream?

**A:** The WebUI limitation is in qBittorrent's core design. This fork provides a working solution while maintaining compatibility.

### Q: Do I need to run WebUI Bridge?

**A:** Only if you want to use private trackers (RuTracker, Kinozal, NNMClub) in WebUI. Public trackers work without it.

### Q: Is this legal?

**A:** The software itself is legal (Apache 2.0 license). Usage depends on your local laws and the content you download.

### Q: Will this break with qBittorrent updates?

**A:** The plugin API is stable. Updates to qBittorrent should not break functionality.

### Q: Can I add more plugins?

**A:** Yes! See `docs/PLUGINS.md` for adding custom plugins.

### Q: Why does RuTracker work in Desktop App but not WebUI?

**A:** Desktop App uses nova2dl.py with authentication. WebUI sends URLs directly without auth. The WebUI Bridge fixes this.

### Q: How do I update plugins?

**A:**
```bash
./install-plugin.sh --all
./restart.sh
```

### Q: Where are downloads saved?

**A:** Default: `/mnt/DATA` (configurable in `.env`)

Structure:
```
/mnt/DATA/
├── Incomplete/          # Partial downloads
├── Torrents/
│   ├── All/            # All .torrent files
│   └── Completed/      # Completed .torrent files
└── [completed files]   # Finished downloads
```

---

## Advanced Topics

### Custom Plugin Development

See `docs/PLUGIN_DEVELOPMENT.md` for creating custom search plugins.

### WebUI Bridge Configuration

Edit `webui-bridge.py`:
```python
QBITTORRENT_HOST = 'localhost'  # Change if remote
QBITTORRENT_PORT = 7186         # WebUI port
BRIDGE_PORT = 7188              # Bridge port
```

### Backup and Restore

**Backup:**
```bash
# Config
tar czf qbittorrent-backup-$(date +%Y%m%d).tar.gz config/

# Plugins
tar czf plugins-backup-$(date +%Y%m%d).tar.gz plugins/
```

**Restore:**
```bash
tar xzf qbittorrent-backup-YYYYMMDD.tar.gz
tar xzf plugins-backup-YYYYMMDD.tar.gz
./restart.sh
```

---

## Support

### Getting Help

1. **Documentation:** Read all docs in `docs/` folder
2. **Tests:** Run `./run-all-tests.sh` to diagnose issues
3. **Logs:** Check `podman logs qbittorrent`
4. **Issues:** Report on GitHub

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Run tests: `./run-all-tests.sh`
5. Submit pull request

---

## Version History

### v2.0.0 (Current)
- ✅ All 12 plugins working
- ✅ WebUI Bridge for private trackers
- ✅ Comprehensive test suite
- ✅ Full documentation

### v1.0.0
- Initial release
- 4 Russian trackers

---

**Last Updated:** March 2025  
**Version:** 2.0.0  
**License:** Apache 2.0
