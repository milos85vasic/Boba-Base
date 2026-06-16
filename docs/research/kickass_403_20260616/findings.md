# Kickass plugin `upstream_http_403` — deep multi-angle research + verdict

**Revision:** 1
**Last modified:** 2026-06-16T00:00:00Z
**Scope:** `plugins/kickass.py` (Kickasstorrents qBittorrent search plugin)
**Anchors:** §11.4.150 (deep multi-angle research), §11.4.112 (structural-impossibility won't-fix), §11.4.6 (no-guessing), §11.4.123 (rock-solid proof)

---

## Verdict

**STRUCTURALLY-BLOCKED (upstream anti-bot) — NO source fix applied.**

Every reachable KickassTorrents (KAT) domain in 2026 is either Cloudflare/WAF-403 or
returns HTTP 200 with a **JavaScript bot-challenge / redirect body that contains ZERO
of the markup the plugin parses**. A qBittorrent search plugin issues a plain `urllib`
GET with a browser User-Agent and **cannot execute JavaScript**, so it can never clear
these gates. There is no mirror that serves the legacy `<tr class="odd|even">` listing
HTML to a non-JS client. Changing `kickass.py`'s `url` to any live mirror would NOT fix
the 403/empty result — it would move the failure from `403` to `0 results from a
JS-challenge page`. Therefore no `url`/mirror-fallback change is made (that would be a
bluff fix per §11.4.6/§11.4.123). The plugin already degrades gracefully (`break` on
non-200 / empty body), so live behaviour is an honest empty result, not a crash.

This matches the **upstream plugin maintainer's own documented status** (LightDestory —
the author named in `plugins/kickass.py` header).

---

## Evidence (captured live from this host, 2026-06-16)

Plugin User-Agent under test (computed from `plugins/helpers.py:_getBrowserUserAgent`,
date 2026-06-16):
`Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0`

### 1. Homepage HTTP codes (`curl -A "<plugin UA>" -L`)

| Domain | Homepage HTTP | Notes |
|---|---|---|
| kickasstorrents.to (plugin's current url) | **403** | Cloudflare/WAF block — the live `upstream_http_403` |
| kickasstorrents.cr | 403 | |
| kickass.sx | 403 | |
| kickasss.to | 403 | |
| katcr.to | 403 | |
| kickasstorrent.cr | 403 | |
| katcr.co | **200** | JS-challenge (see below) — NOT real content |
| kat.am | **200** | JS anti-adblock/redirect wrapper — NOT real content |
| newkatcr.co | 200 | JS-challenge |
| kat.rip | 200 | JS-challenge |
| thekat.cr / kickass.onl / kickasstorrents.ws / kickasstor.net | 000 | DNS/connection fail (dead) |

### 2. The HTTP-200 mirrors are JS bot-gates, not torrent listings

Probing the plugin's EXACT URL shape `<base>/search/the%20matrix/0/`:

- `katcr.co/search/the%20matrix/0/` -> HTTP 200, body **492 bytes**, plugin markers
  (`tr class="odd|even"`, `torrentname`, `cellMainLink`, `magnet:`) = **0**. Body:
  `<html><head><title>Loading...</title></head><body><script ...>window.location.replace('https://katcr.co/search/the%20matrix/0/?ch=1&js=<JWT>...`
  A JS `window.location.replace` challenge keyed on a `?ch=1&js=<JWT>` token.

- **Following** that `?ch=1&js=<JWT>` URL -> a SECOND gate, then a
  `<META http-equiv="refresh" ... URL='http://sarai-tid.com/zokredirect?...'>` — i.e. it
  redirects a non-JS client into a **malicious/ad redirect chain**, never to listings. A
  cookie-jar two-pass (`-c`/`-b`) sets **no** unlocking cookie; the second pass returns
  the same 492-byte challenge.

- `kat.am/search/the%20matrix/0/` -> HTTP 200, body 4595 bytes, plugin markers = 0; body
  is a JS anti-adblock/redirect wrapper (`Redirecting...`).

Conclusion: **no non-JS client can reach KAT listing HTML on any live domain.**

### 3. Upstream maintainer confirms (independent angle)

LightDestory official README
(`https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/README.md`,
accessed 2026-06-16) — Kickasstorrents plugin **v1.2 (22/02/2026)**, status "Unreliable",
verbatim note:

> "KATCR uses Cloudflare; the plugin will not work when CF protection is active. It is
> unstable and only works when CF is set to low threats."

Same plugin version (`# VERSION: 1.2`) shipped in `plugins/kickass.py`.

---

## Sources (cited, accessed 2026-06-16)

- Live `curl` probes from this host (commands + outputs captured in this session).
- LightDestory qBittorrent-Search-Plugins README (upstream maintainer, authoritative):
  https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/README.md
- HackRead — "KickassTorrents is back as katcr.co domain": https://hackread.com/kickasstorrents-is-back-as-katcr-co-domain/
- TechPP KAT proxy list (May 2026): https://techpp.com/2025/04/12/kickass-torrents-proxy-list/

No external solution exists that lets a JS-less `urllib` client clear the KAT
JS-challenge — the limitation is upstream anti-bot by design (cf. §11.4.112). A
browser-engine fetch (headless Chromium / FlareSolverr-class JS solver) would be required;
that is a separate architectural capability, out of scope for a stock nova3 plugin, and
would still land in malicious ad-redirect chains for these mirrors.

---

## Recommendation (for conductor; NOT applied here)

1. Leave `plugins/kickass.py`'s `url` unchanged (no mirror responds usefully). The plugin
   already degrades to an honest empty result — no crash.
2. Track as a §11.4.112 won't-fix `structurally-impossible` (upstream-Cloudflare / JS
   challenge) item; reopen only on NEW evidence a KAT mirror serves listing HTML to a
   non-JS client (per §11.4.34 / §11.4.7).
3. Optionally consider DROPPING kickass from the merge service PUBLIC_TRACKERS set so it
   stops contributing a permanent `upstream_http_403` to every query (operator decision
   per §11.4.122 — NOT done autonomously).
