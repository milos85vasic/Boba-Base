# nnmclub-cookie-harvest.mjs

**Revision:** 1
**Last modified:** 2026-06-16T00:00:00Z

## Overview

Playwright headless-Chromium harvester that logs into nnmclub and emits the
`NNMCLUB_COOKIES` header string (`phpbb2mysql_4_sid` + `phpbb2mysql_4_data` +
`cf_clearance`). Reuses the repo's installed Chromium (from `extension/` /
`frontend/` node_modules).

## Prerequisites

- Node + Playwright + a Chromium install (present via the extension/frontend dev deps).
- `NNMCLUB_USERNAME` / `NNMCLUB_PASSWORD` in the environment (never printed, §11.4.10).

## Usage

```bash
node scripts/nnmclub-cookie-harvest.mjs                 # headless attempt
NNMCLUB_HARVEST_HEADFUL=1 node scripts/nnmclub-cookie-harvest.mjs   # visible browser, one-time manual Turnstile solve
```

Normally invoked via `scripts/nnmclub-cookie-refresh.sh`, which captures stdout
into `.env` and restarts the proxy.

## The Turnstile reality (verified, §11.4.6)

nnmclub `login.php` is gated by a **Cloudflare Turnstile** JS CAPTCHA (sitekey
`0x4AAAAAAAhS8bNcgfb-0Kni`). A real-browser probe confirmed the username /
password / login fields are present and fillable — it is **not** a
selector/timing bug — but Turnstile renders an *interactive*, bot-detected
challenge that does **not** auto-resolve in managed mode. Therefore:

- **Headless (unattended) login fails by design** — the script exits non-zero
  with an honest diagnostic; it never fabricates a session and writes no cookie.
- **Working paths:** a one-time headful solve (`NNMCLUB_HARVEST_HEADFUL=1`), or
  supply browser cookies via `scripts/extract-tracker-cookies.sh ~/Downloads/nnmclub.txt nnmclub`.

## Outputs / exit codes

- **stdout:** `NNMCLUB_COOKIES` header string on success (consumed by the refresh script; never logged).
- **Exit 0:** session obtained (`phpbb2mysql_4_sid` present).
- **Exit non-zero:** Turnstile block / timeout / bad creds — honest diagnostic, no secret leaked.

## Related

- `scripts/nnmclub-cookie-refresh.sh` — wiring (writes `.env`, restarts proxy).
- `scripts/extract-tracker-cookies.sh` — browser-jar → tracker-cookie extractor (the reliable path).
- `download-proxy/src/merge_service/search.py` — consumes `NNMCLUB_COOKIES`.

_Last verified: 2026-06-16 (headless Turnstile-block finding captured with the real sitekey)._
