# qBitTorrent Search Plugins Documentation

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

This document provides comprehensive documentation for all included search plugins.

## Table of Contents

1. [Overview](#overview)
2. [Plugin List](#plugin-list)
3. [Credential Requirements](#credential-requirements)
4. [Configuration](#configuration)
5. [Installation](#installation)
6. [Testing](#testing)
7. [Troubleshooting](#troubleshooting)

---

## Overview

This project includes multiple search engine plugins for qBittorrent, specifically designed for Russian torrent trackers. All plugins support environment variable configuration for credentials and settings.

### Features

- ✅ Environment variable support for all credentials
- ✅ Automatic .env file loading from multiple locations
- ✅ Docker/Podman container support
- ✅ Comprehensive test coverage
- ✅ Proxy support (HTTP/HTTPS/SOCKS5)

---

## Plugin List

### 1. RuTracker.org 🔐

**Status:** ✅ Fully Implemented and Tested

**Description:** Biggest Russian torrent tracker with vast content library.

**Credentials Required:**
- `RUTRACKER_USERNAME` - Your RuTracker username
- `RUTRACKER_PASSWORD` - Your RuTracker password

**Optional Settings:**
- `RUTRACKER_MIRRORS` - Comma-separated list of mirrors (default: https://rutracker.org,https://rutracker.net,https://rutracker.nl)

**Categories:** All, Movies, TV, Music, Games, Anime, Software

**Registration:** Required - [https://rutracker.org/forum/profile.php?mode=register](https://rutracker.org/forum/profile.php?mode=register)

---

### 2. Rutor.info ✅

**Status:** ✅ Implemented (Public Tracker - NO LOGIN REQUIRED)

**Description:** Popular free Russian torrent tracker, works without registration.

**Credentials Required:** **NONE** 🎉

**Optional Settings:**
- `RUTOR_USE_MAGNET` - Use magnet links instead of .torrent files (true/false, default: false)
- `RUTOR_PROXY_ENABLED` - Enable proxy (true/false, default: false)
- `RUTOR_HTTP_PROXY` - HTTP proxy URL
- `RUTOR_HTTPS_PROXY` - HTTPS proxy URL
- `RUTOR_USER_AGENT` - Custom User-Agent string

**Categories:** All, Movies, TV, Music, Games, Anime, Software, Pictures, Books

**Registration:** Not required

**Mirrors:**
- https://rutor.info
- https://rutor.is

---

### 3. Kinozal.tv 🔐

**Status:** 🚧 Coming Soon

**Description:** Russian torrent tracker focused on movies and TV shows.

**Credentials Required:**
- `KINOZAL_USERNAME` - Your Kinozal username
- `KINOZAL_PASSWORD` - Your Kinozal password

**Optional Settings:**
- `KINOZAL_USE_MAGNET` - Use magnet links (true/false, default: false)
- `KINOZAL_PROXY_ENABLED` - Enable proxy (true/false)
- `KINOZAL_HTTP_PROXY` - HTTP proxy URL
- `KINOZAL_HTTPS_PROXY` - HTTPS proxy URL

**Categories:** All, Movies, TV, Music, Games, Anime, Software

**Registration:** Required - [https://kinozal.tv/signup.php](https://kinozal.tv/signup.php)

**Note:** Has download limits (10 torrents by default), use magnet mode to bypass.

---

### 4. NNM-Club.me 🍪

**Status:** 🚧 Coming Soon

**Description:** One of the biggest Russian torrent trackers.

**Credentials Required:**
- `NNMCLUB_USERNAME` - Your NNM-Club username
- `NNMCLUB_COOKIES` - Browser cookies (NOT password!)

**How to Get Cookies:**
1. Login to https://nnmclub.to
2. Open Browser Dev Tools (F12)
3. Go to Network tab
4. Refresh page or navigate
5. Find any request and copy the `Cookie` header value
6. Example: `phpbb2mysql_4_sid=abc123; phpbb2mysql_4_data=xyz789`

**Optional Settings:**
- `NNMCLUB_PROXY_ENABLED` - Enable proxy (true/false)
- `NNMCLUB_HTTP_PROXY` - HTTP proxy URL
- `NNMCLUB_HTTPS_PROXY` - HTTPS proxy URL

**Categories:** All, Movies, TV, Music, Games, Anime, Software

**Registration:** Required - [https://nnmclub.to/forum/profile.php?mode=register](https://nnmclub.to/forum/profile.php?mode=register)

**⚠️ Important:** Very sensitive to proxies, may trigger DDoS protection (403 error)

---

## Credential Requirements Summary

| Plugin | Username | Password | Cookies | Registration |
|--------|----------|----------|---------|--------------|
| **RuTracker** | ✅ Required | ✅ Required | ❌ No | Required |
| **Rutor** | ❌ No | ❌ No | ❌ No | **Not Required** |
| **Kinozal** | ✅ Required | ✅ Required | ❌ No | Required |
| **NNM-Club** | ✅ Required | ❌ No | ✅ Required | Required |

---

## Configuration

### Environment Variables

All plugins support configuration via environment variables. You can set them in multiple ways:

#### 1. .env File (Recommended)

Create a `.env` file in the project root:

```bash
# RuTracker Configuration
RUTRACKER_USERNAME=your_username
RUTRACKER_PASSWORD=your_password
RUTRACKER_MIRRORS=https://rutracker.org,https://rutracker.net

# Rutor Configuration (optional - works without credentials)
RUTOR_USE_MAGNET=false
RUTOR_PROXY_ENABLED=false

# Kinozal Configuration
KINOZAL_USERNAME=your_username
KINOZAL_PASSWORD=your_password
KINOZAL_USE_MAGNET=false

# NNM-Club Configuration
NNMCLUB_USERNAME=your_username
NNMCLUB_COOKIES=phpbb2mysql_4_sid=abc123; phpbb2mysql_4_data=xyz789
```

#### 2. Docker Compose Environment

Add to `docker-compose.yml`:

```yaml
environment:
  - RUTRACKER_USERNAME=${RUTRACKER_USERNAME}
  - RUTRACKER_PASSWORD=${RUTRACKER_PASSWORD}
  - RUTOR_USE_MAGNET=${RUTOR_USE_MAGNET:-false}
  # ... etc
```

#### 3. System Environment Variables

```bash
export RUTRACKER_USERNAME="your_username"
export RUTRACKER_PASSWORD="your_password"
```

### .env File Locations (Priority Order)

Plugins search for `.env` files in this order:

1. Plugin directory (`plugins/.env`)
2. Project root (`.env`)
3. Parent directory (`../.env`)
4. Container config (`/config/.env`)
5. Home directory (`~/.qbit.env`)
6. Config directory (`~/.config/qbittorrent/.env`)

---

## Installation

### Quick Install

```bash
# Install all plugins
./install-plugin.sh --all

# Install specific plugin
./install-plugin.sh rutracker
./install-plugin.sh rutor
./install-plugin.sh kinozal
./install-plugin.sh nnmclub

# Install for local qBittorrent
./install-plugin.sh --local rutracker
```

### Manual Installation

#### For Container

```bash
# Copy plugin files
podman cp plugins/rutracker.py qbittorrent:/config/qBittorrent/nova3/engines/
podman cp plugins/rutracker.png qbittorrent:/config/qBittorrent/nova3/engines/

# Restart container
podman restart qbittorrent
```

#### For Local Installation

**Linux:**
```bash
cp plugins/rutracker.py ~/.local/share/qBittorrent/nova3/engines/
cp plugins/rutracker.png ~/.local/share/qBittorrent/nova3/engines/
```

**macOS:**
```bash
cp plugins/rutracker.py ~/Library/Application\ Support/qBittorrent/nova3/engines/
cp plugins/rutracker.png ~/Library/Application\ Support/qBittorrent/nova3/engines/
```

**Windows:**
```powershell
copy plugins\rutracker.py %LOCALAPPDATA%\qBittorrent\nova3\engines\
copy plugins\rutracker.png %LOCALAPPDATA%\qBittorrent\nova3\engines\
```

---

## Testing

### Comprehensive Plugin Tests

```bash
# Test all plugins
./run-all-tests.sh --suite plugins

# Test specific plugin
python3 tests/test_plugin_download_fix.py --run

# Test download functionality
python3 tests/test_download_comprehensive.py --run

# Quick validation
./test.sh --plugin
```

### Manual Plugin Testing

```bash
# Test search functionality
podman exec qbittorrent python3 /config/qBittorrent/nova3/nova2.py rutracker all ubuntu

# Test download functionality
podman exec qbittorrent python3 /config/qBittorrent/nova3/nova2dl.py rutor "https://rutor.info/download/123456"
```

---

## Troubleshooting

### Common Issues

#### 1. "Credentials not configured" Error

**Problem:** Plugin shows warning about missing credentials.

**Solution:**
- Check `.env` file exists and contains required variables
- Verify environment variables are set: `podman exec qbittorrent env | grep RUTRACKER`
- For container: ensure variables are passed in `docker-compose.yml`

#### 2. Login Failed / Authentication Error

**Problem:** Plugin cannot authenticate with tracker.

**Solutions:**

**RuTracker:**
- Verify username/password are correct
- Check for CAPTCHA (login via browser first)
- Try different mirror

**NNM-Club:**
- Cookies may have expired - get fresh cookies from browser
- Ensure cookie string is complete (includes both `sid` and `data`)
- Check proxy settings (NNM-Club is proxy-sensitive)

**Kinozal:**
- Verify credentials
- Check if account is in good standing
- Try magnet mode if download limit reached

#### 3. No Search Results

**Problem:** Search returns zero results.

**Solutions:**
- Try different search terms
- Check if tracker is accessible (visit website in browser)
- Verify proxy settings if using proxy
- Check plugin logs for errors

**View Logs:**
```bash
# Container logs
podman logs qbittorrent | grep -i error

# Plugin logs (if available)
podman exec qbittorrent cat /config/qBittorrent/nova3/engines/*.log
```

#### 4. Download Not Starting

**Problem:** Torrent added but doesn't start downloading.

**Solutions:**
- Check torrent state in qBittorrent UI
- Verify download path is accessible
- Check if torrent file was created:
  ```bash
  podman exec qbittorrent ls -la /tmp/*.torrent
  ```
- Ensure proper file permissions (644)

#### 5. 403 Forbidden Error

**Problem:** Tracker returns 403 error.

**Solutions:**

**NNM-Club:**
- Very sensitive to proxies - try without proxy first
- Use `proxychecker.py` to validate proxy compatibility
- Get fresh cookies

**All Trackers:**
- May be CloudFlare protection
- Try different mirror
- Wait and retry later

#### 6. Proxy Issues

**Problem:** Proxy not working.

**Solutions:**
- Verify proxy URL format: `http://proxy.example.com:8080` or `socks5://127.0.0.1:9050`
- Check proxy supports HTTPS
- For SOCKS5: ensure `socks` library is installed
- Test proxy: `curl -x http://proxy:8080 https://rutracker.org`

---

## Proxy Configuration

### HTTP/HTTPS Proxy

```bash
# Environment variables
export RUTOR_HTTP_PROXY="http://proxy.example.com:8080"
export RUTOR_HTTPS_PROXY="http://proxy.example.com:8080"
export RUTOR_PROXY_ENABLED="true"
```

### SOCKS5 Proxy

```bash
export RUTOR_HTTP_PROXY="socks5://127.0.0.1:9050"
export RUTOR_HTTPS_PROXY="socks5://127.0.0.1:9050"
export RUTOR_PROXY_ENABLED="true"
```

### Docker Compose with Proxy

```yaml
environment:
  - RUTOR_PROXY_ENABLED=true
  - RUTOR_HTTP_PROXY=http://proxy.example.com:8080
  - RUTOR_HTTPS_PROXY=http://proxy.example.com:8080
```

---

## Advanced Configuration

### Custom Mirrors

```bash
# RuTracker custom mirrors
RUTRACKER_MIRRORS=https://custom.mirror1.com,https://custom.mirror2.com

# Rutor mirrors (hardcoded in plugin)
# https://rutor.info
# https://rutor.is
```

### User-Agent Customization

```bash
export RUTOR_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
```

### Magnet vs Torrent Files

Some plugins support both magnet links and torrent files:

```bash
# Use magnet links (no download limits, but may not work in WebUI)
RUTOR_USE_MAGNET=true
KINOZAL_USE_MAGNET=true
```

**Note:** Magnet links may not work in qBittorrent WebUI, only in desktop application.

---

## Category Support

All plugins support the following categories:

| Category | RuTracker | Rutor | Kinozal | NNM-Club |
|----------|-----------|-------|---------|----------|
| All | ✅ | ✅ | ✅ | ✅ |
| Movies | ✅ | ✅ | ✅ | ✅ |
| TV | ✅ | ✅ | ✅ | ✅ |
| Music | ✅ | ✅ | ✅ | ✅ |
| Games | ✅ | ✅ | ✅ | ✅ |
| Anime | ✅ | ✅ | ✅ | ✅ |
| Software | ✅ | ✅ | ✅ | ✅ |
| Pictures | ✅ | ✅ | ❌ | ❌ |
| Books | ✅ | ✅ | ❌ | ❌ |

---

## Security Considerations

### Credentials Storage

- ✅ Store credentials in `.env` files (gitignored)
- ✅ Use environment variables in Docker/Podman
- ❌ Never commit credentials to git
- ❌ Never hardcode credentials in plugin files

### File Permissions

```bash
# .env files should be readable only by owner
chmod 600 .env

# Plugin files should be readable
chmod 644 plugins/*.py
```

### Container Security

```yaml
# docker-compose.yml
environment:
  - RUTRACKER_USERNAME=${RUTRACKER_USERNAME}  # Pass from .env, don't hardcode
```

---

## Performance Tips

### Search Optimization

1. **Use specific categories** - Faster than searching "all"
2. **Limit search terms** - More specific = faster
3. **Enable caching** - qBittorrent caches results

### Proxy Performance

1. **Use HTTP proxy** - Generally faster than SOCKS5
2. **Choose nearby proxy** - Lower latency
3. **Check proxy health** - Use `proxychecker.py`

---

## Additional Resources

- **RuTracker Forum:** https://rutracker.org/forum/
- **Rutor Mirror Status:** https://rutor.info, https://rutor.is
- **qBittorrent Plugin Wiki:** https://github.com/qbittorrent/search-plugins/wiki
- **Original Plugins Source:** https://github.com/imDMG/qBt_SE

---

## Contributing

To contribute improvements or report issues:

1. Test plugins thoroughly
2. Check existing issues
3. Create detailed bug reports with logs
4. Submit pull requests with tests

---

## License

All plugins maintain their original licenses from their respective authors. See individual plugin files for license information.
