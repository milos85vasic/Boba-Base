# qBittorrent Search Plugin Troubleshooting Guide

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

This guide covers common issues with search plugins and their solutions.

## Table of Contents

1. [Known Issues](#known-issues)
2. [Quick Fixes](#quick-fixes)
3. [WebUI vs Desktop App](#webui-vs-desktop-app)
4. [Plugin Installation](#plugin-installation)
5. [Download Issues](#download-issues)
6. [Debugging Steps](#debugging-steps)

## Known Issues

### Issue 1: Downloads Don't Start from Search (WebUI Only)

**Symptom:** You search for torrents using RuTracker or other private trackers, find results, click download, but the torrent never appears in the download list.

**Root Cause:** qBittorrent WebUI has a fundamental limitation where it does NOT use `nova2dl.py` for downloading torrents from search results. Instead, it tries to download the torrent URL directly, which fails for private trackers that require authentication.

**Affected Plugins:**
- RuTracker (requires login)
- Kinozal (requires login)
- NNMClub (requires login)
- Rutor (works with magnet links)

**Solutions:**

#### Option A: Use qBittorrent Desktop Application (Recommended)
The desktop app properly uses `nova2dl.py` which handles authentication:
```bash
# Install plugins for desktop app
./install-plugin.sh --local rutracker
```

#### Option B: Use Magnet Links Instead
Configure Rutor plugin to return magnet links instead of .torrent files:
```bash
# Edit .env file
RUTOR_USE_MAGNET=true
```

#### Option C: Manual Download
1. Search for torrents in WebUI
2. Note the torrent name/size
3. Go to the tracker website directly
4. Download the .torrent file manually
5. Add it to qBittorrent via "Upload local torrent" button

#### Option D: Use Alternative Trackers
Rutor works best with WebUI because it provides magnet links that don't require authentication.

### Issue 2: Only RuTracker Plugin Visible

**Symptom:** In the Search > Search Plugins section, only RuTracker appears even though all 4 plugins should be installed.

**Root Causes:**
1. Plugins not properly copied to the container
2. File permissions incorrect
3. Container not restarted after plugin installation
4. Plugin syntax errors

**Solutions:**

#### Step 1: Verify Plugin Installation
```bash
./install-plugin.sh --verify
```

This will check:
- All plugin files exist
- Files have correct permissions
- Python syntax is valid

#### Step 2: Reinstall All Plugins
```bash
# Reinstall all plugins
./install-plugin.sh --all

# Verify installation
./install-plugin.sh --verify
```

#### Step 3: Check Container Plugins
```bash
# For Podman
podman exec qbittorrent ls -la /config/qBittorrent/nova3/engines/

# For Docker
docker exec qbittorrent ls -la /config/qBittorrent/nova3/engines/
```

You should see all 4 plugin files:
- `rutracker.py`
- `rutor.py`
- `kinozal.py`
- `nnmclub.py`

#### Step 4: Restart Container
```bash
# For Podman
podman restart qbittorrent

# For Docker
docker restart qbittorrent
```

#### Step 5: Refresh WebUI
After restarting, hard-refresh the WebUI page (Ctrl+Shift+R or Cmd+Shift+R).

## Quick Fixes

### Fix All Issues at Once
```bash
# 1. Stop container
./stop.sh

# 2. Reinstall all plugins
./install-plugin.sh --all

# 3. Verify installation
./install-plugin.sh --verify

# 4. Start container
./start.sh

# 5. Wait for container to be ready, then refresh WebUI
sleep 5
```

### Run All Tests
```bash
# Test plugin installation and structure
python3 -m pytest tests/unit/ --import-mode=importlib

# Test download functionality
python3 tests/test_download_comprehensive.py
```

## WebUI vs Desktop App

### WebUI Limitations

The qBittorrent WebUI has a fundamental limitation with search plugin downloads:

```
WebUI Search Flow:
1. User searches → WebUI calls plugin's search() method ✓ Works
2. User clicks download → WebUI sends URL to /api/v2/torrents/add ✗ Problem!
3. Backend tries to download URL directly ✗ No authentication!
4. Download fails for private trackers ✗

Desktop App Flow:
1. User searches → App calls plugin's search() method ✓ Works
2. User clicks download → App calls nova2dl.py ✓ Correct!
3. nova2dl.py uses plugin's download_torrent() method ✓ Authenticated!
4. Download succeeds ✓
```

### Recommendations

| Use Case | Recommended Approach |
|----------|---------------------|
| Private trackers (RuTracker, Kinozal, NNMClub) | Use Desktop App or manual download |
| Public trackers with magnets (Rutor) | Works with both WebUI and Desktop |
| Automation/Remote access | Use magnet links where possible |

## Plugin Installation

### Install All Plugins
```bash
./install-plugin.sh --all
```

### Install Specific Plugin
```bash
./install-plugin.sh rutracker
```

### Install Locally (Desktop App)
```bash
./install-plugin.sh --local rutracker
```

### Verify Installation
```bash
./install-plugin.sh --verify
```

### Test Plugins
```bash
./install-plugin.sh --test
```

## Download Issues

### Testing Download Functionality

#### Test via nova2dl.py (Command Line)
```bash
# Test RuTracker download (works with authentication)
podman exec -u abc qbittorrent \
  python3 /config/qBittorrent/nova3/nova2dl.py \
  rutracker 'https://rutracker.org/forum/dl.php?t=6782121'

# Expected output:
# /tmp/rutracker_xxx.torrent https://rutracker.org/forum/dl.php?t=6782121
```

#### Test Plugin Directly
```bash
# Test RuTracker plugin
python3 plugins/rutracker.py
```

### Common Download Errors

#### "Unable to connect using given credentials"
- Check your RuTracker username/password in `.env` file
- Verify credentials work on rutracker.org website
- Check if RuTracker is accessible (try different mirrors)

#### "No data received from URL"
- The torrent might have been removed
- Try a different torrent
- Check if you have permission to access the torrent

#### "Received HTML page instead of torrent file"
- Authentication failed
- Your session might have expired
- Try restarting the container

## Debugging Steps

### Enable Debug Logging

#### For RuTracker Plugin
Edit `plugins/rutracker.py` and change:
```python
logging.basicConfig(level=logging.WARNING)
```
to:
```python
logging.basicConfig(level=logging.DEBUG)
```

#### For Container
```bash
# View container logs
podman logs -f qbittorrent

# Or
docker logs -f qbittorrent
```

### Check Plugin Status via API

```bash
# Get list of installed plugins
curl -X POST \
  http://localhost:7186/api/v2/auth/login \
  -d "username=admin&password=admin"

curl -X GET \
  http://localhost:7186/api/v2/search/plugins \
  -b "SID=your_session_id"
```

### Manual Plugin Testing

```python
# Test plugin directly
import sys
sys.path.insert(0, 'plugins')
from rutracker import RuTracker

# Create instance
engine = RuTracker()

# Test search
engine.search("ubuntu")
print(f"Found {len(engine.results)} results")

# Test download (if results found)
if engine.results:
    first = list(engine.results.values())[0]
    engine.download_torrent(first['link'])
```

### Check File Permissions

```bash
# Check plugin files in container
podman exec qbittorrent ls -la /config/qBittorrent/nova3/engines/

# Should show:
# -rw-r--r-- 1 abc abc rutracker.py
# -rw-r--r-- 1 abc abc rutor.py
# -rw-r--r-- 1 abc abc kinozal.py
# -rw-r--r-- 1 abc abc nnmclub.py
```

### Reset Everything

If nothing else works, reset the entire setup:

```bash
# 1. Stop and remove container
./stop.sh -r

# 2. Remove config (WARNING: This removes all settings!)
rm -rf config/qBittorrent

# 3. Reinstall plugins
./install-plugin.sh --all

# 4. Start fresh
./start.sh
```

## FAQ

### Q: Why do magnet links work but .torrent files don't?
**A:** Magnet links don't require authentication to the tracker. They're just a URL that qBittorrent can handle directly. .torrent files from private trackers require you to be logged in to download them.

### Q: Can I fix the WebUI to use nova2dl.py?
**A:** This would require modifying qBittorrent's core code. The WebUI is designed to work with magnet links and public trackers. For private trackers, use the desktop app.

### Q: Do I need credentials for all plugins?
**A:** 
- **RuTracker**: Yes, requires username/password
- **Rutor**: No, works without authentication
- **Kinozal**: Yes, requires username/password
- **NNMClub**: Yes, requires cookies

### Q: How do I get NNMClub cookies?
**A:**
1. Login to nnmclub.to in your browser
2. Open browser developer tools (F12)
3. Go to Application/Storage > Cookies
4. Copy the cookie string
5. Add to `.env`: `NNMCLUB_COOKIES="name1=value1; name2=value2"`

### Q: Can I use a proxy?
**A:** Yes, some plugins support proxies:
```bash
# For Rutor
RUTOR_PROXY_ENABLED=true
RUTOR_PROXY_HTTP=http://proxy:8080
RUTOR_PROXY_HTTPS=https://proxy:8080
```

## Getting Help

If you're still having issues:

1. Run the test suite: `python3 -m pytest tests/unit/ --import-mode=importlib`
2. Check container logs: `podman logs qbittorrent`
3. Enable debug logging in plugins
4. Check qBittorrent's official documentation: https://wiki.qbittorrent.org/

## Summary

| Issue | Quick Fix |
|-------|-----------|
| Downloads don't start | Use desktop app or magnet links |
| Only RuTracker visible | Run `./install-plugin.sh --all` and restart container |
| Plugin errors | Run `./install-plugin.sh --verify` |
| Authentication failed | Check credentials in `.env` file |
| Slow downloads | Try different mirrors or use proxy |

Remember: The fundamental limitation is that WebUI cannot download from private trackers directly. Use the desktop app or magnet links as workarounds.
