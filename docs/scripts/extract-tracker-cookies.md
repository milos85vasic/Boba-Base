# extract-tracker-cookies.sh

**Revision:** 2
**Last modified:** 2026-08-18T00:00:00Z

## Overview

Extracts **only** a single tracker's own-domain cookies from a Netscape
`cookies.txt` browser export and emits the `name=value; name=value` header
string consumed by the merge proxy's `*_COOKIES` env vars
(`NNMCLUB_COOKIES`, `RUTRACKER_COOKIES`, and `IPTORRENTS_COOKIES` — added
2026-08-18, Task #39).

Built because nnmclub (Cloudflare Turnstile), rutracker (CAPTCHA-walled
login), and iptorrents (login-form-only, no unattended POST path) cannot be
authenticated by an unattended password POST — the reliable path is
operator-supplied browser cookies. Operators routinely have a *full* browser
`cookies.txt` (every site they're logged into); this tool pulls just the one
tracker's cookies so the rest of the jar never reaches `.env`.

## Prerequisites

- A Netscape `cookies.txt` export (tab-separated: `domain flag path secure expiry name value`).
- The export must be from a session that is **logged into the tracker** (else the required session cookie is absent → exit 2).

## §11.4.10 privacy guarantee

A full browser `cookies.txt` contains the operator's ENTIRE cookie jar
(banking, shopping, email, payments). This tool:

- emits cookies for the requested tracker's **canonical own domain only**
  (`nnmclub.to` / `rutracker.org` / `iptorrents.com`) — every other site's
  cookies are discarded;
- de-dups by cookie name (first occurrence wins) so a mirror domain's divergent
  session value never collides with the canonical host's;
- logs only cookie **names + counts** to stderr — **never values**;
- writes the header string to **stdout** for the caller to redirect into a
  `chmod 600` `.env` (the value is never echoed to a log or the terminal).

## Usage

```bash
# Capture into an env var (value never printed):
NNMCLUB_COOKIES="$(scripts/extract-tracker-cookies.sh ~/Downloads/nnmclub.txt nnmclub)"
RUTRACKER_COOKIES="$(scripts/extract-tracker-cookies.sh ~/Downloads/rutracker.txt rutracker)"
IPTORRENTS_COOKIES="$(scripts/extract-tracker-cookies.sh ~/Downloads/iptorrents.txt iptorrents)"
```

## Edge cases

- **Required session cookie absent** (`phpbb2mysql_4_sid` for nnmclub,
  `bb_session` for rutracker, `pass` for iptorrents) → exits **2** with an
  honest message; the export was not from a logged-in session.
- **Unknown tracker** → exit 1.
- Mirror-domain rows (`.rutracker.net`, `.nnmclub.me`) are intentionally
  ignored — only the canonical domain that matches the proxy `base_url`.
- IPTorrents authenticates via a two-cookie pair (`uid=<numeric id>` +
  `pass=<32-char hash>`); `pass` is the load-bearing secret and is the
  required canary — `uid` alone (low entropy, easily-guessable) proves
  nothing about login state.

## Related

- `scripts/load-tracker-cookies.sh` — the caller for `rutracker` / `nnmclub` /
  `iptorrents`; `rutor` / `kinozal` use an inlined copy of this same awk shape
  since they don't need session-cookie validation the same way.
- `scripts/nnmclub-cookie-refresh.sh` — applies the extracted/harvested
  `NNMCLUB_COOKIES` into `.env` and restarts the proxy.
- `download-proxy/src/merge_service/search.py` — consumes `NNMCLUB_COOKIES`,
  `RUTRACKER_COOKIES`, and `IPTORRENTS_COOKIES` as the preferred auth path.

_Last verified: 2026-08-18 against real nnmclub.txt / rutracker.txt /
iptorrents.txt exports (session cookie present, foreign-site cookies provably
excluded, no dup names)._
