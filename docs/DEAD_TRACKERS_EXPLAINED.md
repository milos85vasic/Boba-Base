# Dead Public Tracker Status

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

As of 2026-04-24, the dead tracker list contains 14 entries.
We successfully revived 10 trackers from the original 22 dead entries.

## Revived Trackers (10)

| Tracker | Fix Applied | Results Verified |
|---------|------------|-----------------|
| torrentgalaxy | Replaced plugin → torrentgalaxy.one | ✅ 150+ results |
| kickass | URL → kickasstorrents.to | ✅ 8+ results |
| torlock | URL → torlock2.com | ✅ 400+ results |
| gamestorrents | URL → .app | ✅ (games tracker) |
| yts | URL → yts.lt | ✅ (movie tracker) |
| nyaa | Removed from dead list | ✅ 37+ results |
| bitsearch | Added as new tracker | ✅ 60+ results |
| torrentkitty | Fixed regex parser | ✅ 20+ results |
| megapeer | Rewrote URL + parser | ✅ (Russian tracker) |
| anilibra | Rewrote for new API | ✅ (anime tracker) |

## Remaining Dead (14) — Why Each Is Unfixable

### Cloudflare Search Block (5)
These return HTTP 200 for homepage but HTTP 403/Cloudflare challenge on search:
- **bitru** — `bitru.org` works but `/search?q=` hits Cloudflare challenge page
- **bt4g** — `bt4gprx.com` homepage works, search API returns 403
- **extratorrent** — All mirrors redirect to parked domains or 403
- **eztv** — `eztvx.to` homepage works, `/search/` returns 403
- **one337x** — `1337x.to` and all mirrors blocked by Cloudflare

*Fix would require:* VPN/proxy rotation infrastructure or CAPTCHA solving.

### Domain Completely Dead (5)
No working alternative domains found after testing 20+ TLDs each:
- **audiobookbay** — `.fi`, `.is`, `.se`, `.nl` all timeout
- **pctorrent** — `pctorrent.ru` does not resolve
- **yihua** — `yihua.biz` does not resolve
- **xfsub** — `xfsub.com` TLS handshake failure
- **torrentfunk** — `torrentfunk.com` returns HTTP 500

*Fix would require:* Site operators to restore service or new working mirror.

### Site No Longer Provides Torrents (3)
- **ali213** — Chinese gaming site reorganized; torrent download chain
  (`soft50.com` → `btfile.soft5566.com`) completely dead
- **therarbg** — SPA with client-side routing; all search endpoints redirect
  to `/`; no accessible backend search API found after reverse-engineering
- **btsow** — All domains use JWT-based anti-bot redirect loops

*Fix would require:* Full site reverse-engineering or JavaScript execution.

### Replaced (1)
- **solidtorrents** — `solidtorrents.to` redirects to `bitsearch.to`;
  replaced by dedicated `bitsearch` tracker

## Dashboard Behavior

With `ENABLE_DEAD_TRACKERS=0` (default): 24 public trackers active, 14 excluded.
With `ENABLE_DEAD_TRACKERS=1`: All 38 public trackers searched.
The 14 dead trackers will show error chips in the dashboard when enabled,
with specific error types (upstream_http_403, dns_failure, etc.).
