# Tracker Credentials — Env Vars vs Cookies Files

**Revision:** 2
**Last modified:** 2026-08-18T00:00:00Z
**Audience:** Operators configuring tracker access on a fresh boba host or
refreshing an expired session.
**Authority:** Operator mandate 2026-08-15 (canonical file naming +
`~/Downloads` default + env-vars-AND-cookies-files support).

---

## The two mechanisms

Boba consumes tracker credentials via **exactly two** channels — and both are
respected together:

| # | Mechanism | Kind | Precedence | Refreshed by |
|---|---|---|---|---|
| 1 | `.env` env vars | `<TRACKER>_USERNAME` / `<TRACKER>_PASSWORD` / `<TRACKER>_COOKIES` | Whatever is present at container-start time. | Manual edit (or the loader for `_COOKIES`). |
| 2 | `~/Downloads/cookies_<tracker>.txt` | Browser Netscape TSV | The loader auto-writes into `.env`, so cookies-file **wins** for `_COOKIES` — every restart re-parses the file. | Re-export from browser + restart / `boba-svc up`. |

The **loader** `scripts/load-tracker-cookies.sh` is the bridge: it turns the
file into the env var, atomically, with `§11.4.10.A` leak-audit + `§11.4.10`
value-never-logged discipline. See its
[dedicated guide](../scripts/load-tracker-cookies.md).

---

## Per-tracker matrix

| Tracker | Auth style | Env vars | Cookies file (recommended) | Load-bearing session cookie | Notes |
|---|---|---|---|---|---|
| **RuTracker** | Login form → session cookie | `RUTRACKER_USERNAME` `RUTRACKER_PASSWORD` `RUTRACKER_COOKIES` | `~/Downloads/cookies_rutracker.txt` | `bb_session=` | User/pass CAN log in but the session cookie is the durable path; also carries `cf_clearance` for Cloudflare. |
| **NNM-Club** | Cookie-only (form auth flaky) | `NNMCLUB_USERNAME` `NNMCLUB_PASSWORD` `NNMCLUB_COOKIES` | `~/Downloads/cookies_nnmclub.txt` | `phpbb2mysql_4_sid=` | Cookie is the **only** reliable auth. Plugin refuses if cookie lacks `phpbb2mysql_4_sid=`. |
| **RuTor** | Public (no login) | `RUTOR_USERNAME` `RUTOR_PASSWORD` (present for parity, unused) | `~/Downloads/cookies_rutor.txt` (optional) | *n/a* | Cookie jar helps ONLY with `cf_clearance` (Cloudflare challenges). Empty is fine. |
| **Kinozal** | Login form → session cookie | `KINOZAL_USERNAME` `KINOZAL_PASSWORD` | `~/Downloads/cookies_kinozal.txt` (optional) | `uid=` + `pass=` | Form auth works; cookies-file is a fallback when the form flow rate-limits. |
| **IPTorrents** | Login form → session cookie | `IPTORRENTS_USERNAME` `IPTORRENTS_PASSWORD` `IPTORRENTS_COOKIES` | `~/Downloads/cookies_iptorrents.txt` | `pass=` (required canary; `uid=` is a low-entropy identifier, present alongside it) | Freeleech-only per `CLAUDE.md`. Cookies-file autoload added 2026-08-18 — routed through `extract-tracker-cookies.sh` (same login-required validation as RuTracker/NNM-Club). |
| **Jackett-fronted trackers** | API-key | `JACKETT_API_KEY` (extracted by autoconfig) | *n/a* | *n/a* | Managed by `boba-jackett` — see `docs/JACKETT_INTEGRATION.md`. |

**Rule of thumb:** if a tracker needs a session token AND your browser can log
into it fine, use the cookies file — refreshing is one browser re-export away.
If you have programmatic credentials and no CAPTCHA / MFA, env-vars are
simpler.

---

## Step-by-step — export cookies from your browser

### Firefox (recommended — most reliable Netscape export)

1. Install the **Cookie Quick Manager** add-on:
   <https://addons.mozilla.org/en-US/firefox/addon/cookie-quick-manager/>
2. Log into the tracker's website in a normal browser window (solve any
   CAPTCHA, tick *Remember me*, verify you land on your profile).
3. Click the add-on icon → **Manage all cookies** → search the tracker's
   domain (`rutracker.org`, `nnmclub.to`, `rutor.is`, `kinozal.guru`,
   `iptorrents.com`) → **Export → Netscape HTTP Cookie File**.
4. Save as **exactly** `cookies_<tracker>.txt` in your host's `~/Downloads/`
   folder — the loader's convention is:

   ```
   ${TRACKER_COOKIE_DIR:-$HOME/Downloads}/cookies_<tracker>.txt
   ```

   with `<tracker>` **lowercase** (`rutracker`, `nnmclub`, `rutor`,
   `kinozal`, `iptorrents`).
5. Trigger a reload:

   ```bash
   bash scripts/load-tracker-cookies.sh          # writes into .env
   bash scripts/boba-svc.sh restart              # containers pick it up
   ```

### Chrome / Chromium / Brave / Edge

1. Install **Get cookies.txt LOCALLY** extension:
   <https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc>
2. Log into the tracker.
3. Open extension → *Export As* → **Netscape** → save to
   `~/Downloads/cookies_<tracker>.txt`.
4. Same reload commands as above.

### Command-line (curl-style) — advanced

If you already have a `cookies.txt` from a `curl -c` login flow you scripted
yourself, simply rename it to match the convention and drop it in
`~/Downloads/`. The format is standard Netscape TSV — the loader is
oblivious to how the file was produced, only to its schema and the
tracker-name it's addressed to.

---

## Verifying it worked

The definitive test:

```bash
bash challenges/scripts/credentials_wired_challenge.sh
```

Expected shape (verified 2026-08-18):

```
PASS: .env mode = 0600
PASS: .env matched by .gitignore
PASS: .env is not tracked in git
PASS: all 11 required credential var NAMES present in .env
PASS: NNMCLUB_COOKIES contains phpbb2mysql_4_sid= (session cookie present)
PASS: RUTRACKER_COOKIES contains bb_session= (RuTracker session cookie present)
PASS: RUTOR_COOKIES shape OK (public tracker; cf_clearance helps Cloudflare)
PASS: KINOZAL_COOKIES contains uid= or pass= (Kinozal session cookie present)
PASS: IPTORRENTS_COOKIES contains uid= or pass= (IPTorrents session cookie present)
PASS: all 11 credential vars propagated to qbittorrent-proxy container env (non-empty)
PASS: scripts/load-tracker-cookies.sh exists + executable + bash -n clean
PASS: scripts/load-tracker-cookies.sh --dry-run exit 0
PASS: scripts/load-tracker-cookies.sh --dry-run emits the standard summary line
PASS: cookies_rutracker.txt  present in /home/milosvasic/Downloads AND recognised by loader
PASS: cookies_nnmclub.txt    present in /home/milosvasic/Downloads AND recognised by loader
PASS: cookies_rutor.txt      present in /home/milosvasic/Downloads AND recognised by loader
PASS: cookies_kinozal.txt    present in /home/milosvasic/Downloads AND recognised by loader
PASS: cookies_iptorrents.txt present in /home/milosvasic/Downloads AND recognised by loader
Total: PASS=18 FAIL=0
```

Any FAIL names the offending file / var / substring.

---

## Precedence & lifecycle

1. **`~/Downloads/cookies_<tracker>.txt` exists and matches `.env`'s value.**
   Loader marks `UNCHANGED (idempotent)`, no I/O.
2. **File exists and DIFFERS from `.env`.** Loader `§11.4.10.A`-audits the new
   values (aborts if leaked), then atomically overwrites the `<TRACKER>_COOKIES`
   line in `.env`. Containers pick it up on the next `up` / `restart`.
3. **File exists but the session cookie is missing.** Loader reports `PARSE —
   was not exported from a logged-in session` and skips that tracker; the
   existing `.env` value is kept.
4. **File absent.** Loader reports `SKIP`. If `.env` still holds a working
   `<TRACKER>_COOKIES=` from an earlier run, containers continue to use it —
   the env var is the durable state, the file is just the on-ramp.
5. **`.env` has env-vars but no cookies file.** Nothing to load; containers use
   whatever `.env` provides. This is the fresh-install baseline.

**Precedence at container-start time is always: `.env` wins**, because the
container never reads `~/Downloads` directly. The loader's whole job is to keep
`.env` in sync with whatever cookies-file exists.

---

## Security — what boba does NOT do

- **Cookie values NEVER appear in logs.** Every status line prints tracker
  name, cookie NAMES, counts, mtime — never a value.
- **`.env` is mode `0600` and gitignored.** The atomic writer enforces both.
- **`~/Downloads/cookies_*.txt` are NEVER committed.** They live on the
  operator's host filesystem, outside the repo. The loader NEVER `git add`s
  them.
- **§11.4.10.A pre-store leak audit** runs on every non-empty cookie value ≥ 8
  chars before writing — if the value already appears in the working tree or
  the last 1000 commits, the store is BLOCKED and the operator is instructed
  to rotate the cookie in the browser (invalidate the session server-side,
  re-login, re-export).
- **RuTor is a public tracker.** Its cookie file, if present, is loaded solely
  for `cf_clearance` (Cloudflare) usefulness — no session token is ever needed.

---

## Related documentation

- **[`docs/scripts/load-tracker-cookies.md`](../scripts/load-tracker-cookies.md)**
  — the loader's full script-level reference.
- **[`docs/scripts/extract-tracker-cookies.md`](../scripts/extract-tracker-cookies.md)**
  — the single-tracker extraction primitive the loader delegates to.
- **[`docs/TOKENS_AND_KEYS.md`](../TOKENS_AND_KEYS.md)** — the master env-vars
  reference for every credential category (trackers, metadata, scanners,
  observability).
- **[`docs/FAQ.md`](../FAQ.md)** — cookie-refresh FAQs.
- **[`CLAUDE.md`](../../CLAUDE.md)** — project-wide env-var + credentials
  policy (§11.4.10 handling, freeleech-only, WebUI defaults).
- **`challenges/scripts/credentials_wired_challenge.sh`** — the standing
  RED/GREEN guard.
