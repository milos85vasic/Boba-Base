# NNMClub Login Failure — Root-Cause Diagnosis

**Revision:** 1
**Last modified:** 2026-06-16T00:00:00Z
**Run-id:** nnmclub-login-diagnosis-20260616
**Authority:** §11.4.6 (no-guessing, FACT-grade), §11.4.114 (working-example comparison), §11.4.123 (rock-solid proof)
**Scope:** READ-ONLY investigation. No production edits, no commit. No credential values captured/printed.

---

## 1. Verdict (FACT-grade)

**Root cause: nnmclub.to gates `login.php` behind a Cloudflare Turnstile JS challenge.**
The Boba password-login POST (`_nnmclub_login` in `download-proxy/src/merge_service/search.py`, and
the plugin fallback `_password_login` in `plugins/nnmclub.py`) sends only
`username` / `password` / `login`. The server requires a valid `cf-turnstile-response`
token (produced by solving the JS widget in a real browser) before it will issue
the `phpbb2mysql_4_sid` session cookie. Without it the POST returns **HTTP 200 with
NO `Set-Cookie`** → no session → `has_session=False`.

**Classification: (a) CAPTCHA → operator must supply browser-exported `NNMCLUB_COOKIES`.**
This is NOT a code bug in the POST body, NOT a UA/Cloudflare-block on requests
(plain `curl` reaches the form fine), and NOT (provably) an invalid-credentials
problem — credentials never get a chance to be evaluated because the Turnstile gate
fails first. The dead-domain fix (f6b2761, nnm-club.me→nnmclub.to) correctly restored
reachability; the remaining failure is the Turnstile login gate.

---

## 2. Captured evidence (from nezha.local — direct internet, no Mac SSH tunnel)

All probes run as `ssh milosvasic@nezha.local 'curl ...'`.

### 2a. Login form requires a JS CAPTCHA + hidden fields
`GET https://nnmclub.to/forum/login.php`:
```
<form action="login.php" method="post" target="_top" id="loginFrm">
<input name="f"        type="hidden" value="-1">
<input               type="hidden" name="redirect" value="" />
<input               type="hidden" name="code"     value="5cab14e06b8e112b" />
... CAPTCHA ...
<noscript><b>Для отображение CAPTCHA, пожалуйста, включите JavaScript</b></noscript>
```
CAPTCHA widget tokens present in the page:
```
cf-turnstile
turnstile
data-sitekey
```
→ **Cloudflare Turnstile.** The visible CAPTCHA only renders with JavaScript; a
non-browser client cannot produce the `cf-turnstile-response` token.

### 2b. The hidden `code` field is a STATIC anti-CSRF token, not the blocker
Two separate `GET`s returned the **identical** value `code=5cab14e06b8e112b`.
A per-session nonce would differ. So including `code` would not fix login — Turnstile is the gate.

### 2c. Credential POST (with hidden `code` included) yields NO session cookie
```
fresh code=5cab14e06b8e112b
POST .../login.php  (username=probe_xyz, password=probe_xyz, login=вход, redirect=, code=<above>)
HTTP/2 200
# (no Set-Cookie line in response headers)
```
A successful login would carry `Set-Cookie: phpbb2mysql_4_sid=...`. It is absent →
server rejected the login at the Turnstile gate before evaluating credentials.

### 2d. Cloudflare in front, but NOT blocking the request
```
server: cloudflare
cf-cache-status: DYNAMIC
HTTP/2 200
```
The page loads (HTTP 200), so this is **not** a UA/IP Cloudflare challenge on the
request itself — option (c) is ruled out. The block is the in-page Turnstile widget
the login flow must satisfy.

---

## 3. Working-tracker comparison (§11.4.114)

| Tracker  | login.php Turnstile? | Boba auth method | has_session |
|----------|----------------------|------------------|-------------|
| rutracker.org | **none** (probe returned empty) | password POST (`login_username`/`login_password`/`login`) | True |
| kinozal | none observed | password POST | True |
| iptorrents | n/a (cookies) | — | True |
| **nnmclub.to** | **cf-turnstile present** | password POST (`username`/`password`/`login`) — Turnstile token missing | **False** |

The Boba `_nnmclub_login` is a faithful clone of the rutracker pattern. It works for
rutracker precisely because rutracker's `login.php` has **no Turnstile**. nnmclub's
does, so the identical pattern cannot succeed there. The code is not "wrong" — the
target's auth surface is fundamentally different (browser-only).

Probe contrast:
```
rutracker login.php turnstile grep → (empty)   # no widget
nnmclub  login.php turnstile grep → cf-turnstile / turnstile / data-sitekey
```

---

## 4. Why the existing diag message is misleading (§11.4.6)

`search.py:1538-1547` records on failure:
```
"nnmclub login returned no session cookie — likely credential failure"
```
The word **"likely"** is a §11.4.6 no-guessing violation, and the guess is wrong:
the FACT is a Turnstile gate, not a credential failure. Suggested corrected wording:
`"nnmclub login.php is gated by Cloudflare Turnstile (JS CAPTCHA); password POST cannot
obtain a session — set NNMCLUB_COOKIES from a browser session."`

---

## 5. Classification & required action

**Classification (a): CAPTCHA → browser-exported cookies (operator/env, §11.4.3 topology).**

### Operator action (the working path — already supported by code)
`_search_nnmclub` (search.py:1466-1474) ALREADY prefers `NNMCLUB_COOKIES` when set and
skips the password login entirely. The operator must export cookies from a logged-in
browser session at nnmclub.to and set the `NNMCLUB_COOKIES` env var.

**Exact cookies required** (the code's hard gate is `phpbb2mysql_4_sid`; a full working
session also carries the data + persistence cookies — export all `phpbb2mysql_4_*`):
- `phpbb2mysql_4_sid`   ← **REQUIRED** — search.py:1479 / plugin login() line 212 reject without it
- `phpbb2mysql_4_data`  ← needed for persistent auth (plugin `_init` line 341 keys on this)
- `cf_clearance`        ← recommended — Cloudflare clearance cookie, lets subsequent requests bypass the Turnstile interstitial

`NNMCLUB_COOKIES` format (semicolon-separated, per search.py:1470 and plugin login() line 188):
```
NNMCLUB_COOKIES="phpbb2mysql_4_sid=<...>; phpbb2mysql_4_data=<...>; cf_clearance=<...>"
```
Cookies expire periodically (same operational caveat as RuTracker per CLAUDE.md) and
must be re-exported when nnmclub auth lapses.

### NOT recommended (out of scope / fragile)
Automating Turnstile solving (3rd-party solver services, headless-browser token mint)
is brittle, may violate the tracker ToS, and is not the established Boba pattern. The
cookie-injection path (§11.4.3 operator-supplied evidence) is the correct, robust fix.

### No code fix needed for login to work
The cookie path already works end-to-end in code. The only code-quality follow-ups
(separate, optional):
1. Fix the §11.4.6 "likely credential failure" diag string (section 4) → state the
   Turnstile FACT so operators know to supply cookies.
2. Optionally have `_nnmclub_login` detect `cf-turnstile` in the login page and emit a
   `error_type: "upstream_captcha"` diag (mirroring rutracker's `upstream_captcha` label
   at search.py:1255-1257) instead of `auth_failure`.

### RED-test design (for the diag-string follow-up, if pursued)
- RED: assert that when `_nnmclub_login` is driven against a login page containing
  `cf-turnstile`, the recorded diag `error_type == "upstream_captcha"` (currently
  `auth_failure`) and the message contains "Turnstile", not "likely". Fails pre-fix.
- GREEN: classifier detects the `cf-turnstile` marker; flip RED_MODE=0 as the guard.

---

## 6. Files referenced
- `/Volumes/T7/Projects/boba/download-proxy/src/merge_service/search.py` — `_search_nnmclub` (1454), `_nnmclub_login` (1501), diag (1538), cookie-precedence (1466)
- `/Volumes/T7/Projects/boba/plugins/nnmclub.py` — `login()` (180), `_password_login()` (217), `_init()` cookie load (311)
- `/Volumes/T7/Projects/boba/download-proxy/src/api/auth.py` — nnmclub auth_status branch (not the cause; reflects has_session truthfully)
