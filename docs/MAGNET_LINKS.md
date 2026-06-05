# Magnet Link Implementation Guide

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

## Status: ✅ ALL PLUGINS RETURN MAGNET LINKS

All plugins have been updated to return magnet links in search results, enabling direct WebUI downloads.

## What Was Fixed

### Version 1.2.1 (Current)
- **LimeTorrents**: Improved magnet link fetching with:
  - Retry logic for failed requests
  - Better error handling
  - Skip results without magnet links (no HTTP fallback)
  - Multiple extraction patterns

### Version 1.2.0
All plugins updated to return magnet links:
- ✅ PirateBay - Native magnet support
- ✅ EZTV - Native magnet support  
- ✅ Rutor - Native magnet support
- ✅ RuTracker - Fetches magnet from topic pages
- ✅ Kinozal - Fetches magnet from topic pages (default: magnet=True)
- ✅ NNMClub - Fetches magnet from topic pages
- ✅ LimeTorrents - Fetches magnet from info pages (v4.16 with retry)
- ✅ SolidTorrents - Native magnet support
- ✅ TorrentProject - Fetches magnet from info pages
- ✅ TorLock - Fetches magnet from info pages
- ✅ TorrentsCSV - Native magnet support
- ✅ Jackett - Prefers MagnetUri over Link

## How It Works

### Search Flow
1. User searches in qBittorrent WebUI
2. Plugin returns results with `link` field containing magnet URI
3. User clicks "Download" 
4. qBittorrent receives magnet link directly
5. Download starts automatically

### Magnet Link Format
```
magnet:?xt=urn:btih:[40-char-hash]&dn=[encoded-name]&tr=[tracker1]&tr=[tracker2]...
```

## Testing Magnet Links

### Manual Test
```bash
cd /run/media/milosvasic/DATA4TB/Projects/qBitTorrent/plugins
python3 << 'EOF'
import sys
sys.path.insert(0, '.')

# Mock prettyPrinter
results = []
def mock_printer(data):
    results.append(data.copy())

import novaprinter
novaprinter.prettyPrinter = mock_printer

# Test any plugin
from piratebay import piratebay
engine = piratebay()
engine.search('ubuntu', 'all')

# Check results
if results:
    link = results[0].get('link', '')
    print(f"First result link: {link[:80]}...")
    print(f"Is magnet: {link.startswith('magnet:')}")
else:
    print("No results")
EOF
```

### Test All Plugins
```bash
./tests/test_all_magnet_links.py
```

## Common Issues

### Issue: HTTP link instead of magnet
**Cause**: Magnet fetching failed, plugin fell back to HTTP URL
**Fix**: Check site accessibility, verify HTML structure hasn't changed

### Issue: No results returned  
**Causes**:
- Site is down or blocking requests
- HTML structure changed
- Network connectivity issues

**Debug**: Enable logging in plugin:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Plugin-Specific Notes

### LimeTorrents (v4.16)
- Fetches magnets from individual info pages
- Retries failed requests up to 3 times
- Skips results if magnet fetch fails (no HTTP fallback)
- May be slow due to extra HTTP requests

### Private Trackers (RuTracker, Kinozal, NNMClub)
- Require authentication
- Fetch magnets from authenticated session
- Magnet links extracted from topic pages

### Public Trackers (PirateBay, EZTV, Rutor, etc.)
- Magnet links available directly in search results
- No extra HTTP requests needed
- Fast performance

## Verification Checklist

Before considering a plugin complete, verify:
- [ ] Search returns results
- [ ] Results have `link` field
- [ ] `link` field starts with `magnet:`
- [ ] Magnet link has valid hash (40 hex characters)
- [ ] Download starts when clicking result in WebUI

## Performance Tips

1. **Public trackers** are faster (magnets in search results)
2. **Private trackers** require extra requests (slower but necessary)
3. **LimeTorrents** makes extra requests (slower but ensures magnets)

## Future Improvements

- [ ] Cache magnet links to avoid re-fetching
- [ ] Parallel magnet fetching for multiple results
- [ ] Better error messages when sites are down
- [ ] Automatic fallback to alternative sites

## Support

If a plugin returns HTTP links:
1. Check site is accessible
2. Enable debug logging
3. Report issue with full error message
4. Include sample search query that failed
