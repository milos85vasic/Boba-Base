# nnmclub-cookie-refresh.sh

**Revision:** 1
**Last modified:** 2026-06-16T00:00:00Z

## Overview

Wiring script that obtains a fresh nnmclub session, writes `NNMCLUB_COOKIES`
into `.env` (chmod 600, value never echoed), clears the proxy `__pycache__`,
and restarts `qbittorrent-proxy` so the new cookies take effect. The
out-of-the-box / cron entry point for keeping nnmclub authenticated.

## Prerequisites

- `NNMCLUB_USERNAME` / `NNMCLUB_PASSWORD` in the environment (for the harvester path), OR a browser `cookies.txt` (for the extractor path).
- Node + Playwright (used by `nnmclub-cookie-harvest.mjs`) when harvesting.
- `podman` (or `docker`) to restart the proxy.

## Usage

```bash
scripts/nnmclub-cookie-refresh.sh            # harvest → write .env → restart
NNMCLUB_HARVEST_HEADFUL=1 scripts/nnmclub-cookie-refresh.sh   # one-time manual Turnstile solve
```

## Internal behaviour + the Turnstile reality

The harvester (`nnmclub-cookie-harvest.mjs`) drives a real headless Chromium
through `login.php`. **Cloudflare Turnstile defeats unattended headless login**
(verified — sitekey `0x4AAAAAAAhS8bNcgfb-0Kni` is an interactive, bot-detected
challenge that does not auto-resolve), so the headless path exits non-zero with
an honest diagnostic. Working paths: a one-time headful solve
(`NNMCLUB_HARVEST_HEADFUL=1`), or supplying browser cookies via
`scripts/extract-tracker-cookies.sh ~/Downloads/nnmclub.txt nnmclub`.

No-bluff guard: the script REJECTS any harvested/extracted value lacking
`phpbb2mysql_4_sid` (the session cookie) — it will not write a non-authenticating
value into `.env`.

## Edge cases

- Turnstile block / timeout / bad creds → non-zero exit, `.env` untouched, no secret leaked.
- `.env` write is atomic + `chmod 600`; the cookie value is never printed.

## Related

- `scripts/nnmclub-cookie-harvest.mjs` — the Playwright harvester it runs.
- `scripts/extract-tracker-cookies.sh` — browser-jar → tracker-cookie extractor.
- `download-proxy/src/merge_service/search.py` — consumes `NNMCLUB_COOKIES`.

_Last verified: 2026-06-16 (Turnstile-block finding captured; manual + extractor paths work)._
