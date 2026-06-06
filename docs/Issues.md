# Issues — Open Workable Items

**Revision:** 2
**Last modified:** 2026-06-06T18:00:00Z
**Ticket prefix:** `BOB` (operator-mandated, 2026-06-06)
**Scope:** Open/active items only. Closed items migrate to [`Fixed.md`](Fixed.md).

> Tracking interim: this is the Markdown tracker. The full constitution-grade
> SQLite single-source-of-truth + `docs_chain` engine + procedure docs are
> themselves tracked below as **BOB-010** (not yet built). Until then this
> file + [`Issues_Summary.md`](Issues_Summary.md) are authoritative for open work.

---

## §1. [BOB-015] Individual public-tracker plugins error/time-out after the systemic fix

**Status:** Queued
**Type:** Bug
**Severity:** Medium
**Created:** 2026-06-06

After BOB-005 (systemic import failure) was fixed, 14 public trackers now
return results, but a few still error with DISTINCT, per-plugin causes (no
longer the shared import failure):
- per-plugin runtime exceptions: `piratebay`, `jackett`, `tokyotoshokan`
- per-tracker 25s deadline timeouts: `kickass`, `nyaa`, `torlock`
- `snowfl`: "plugin parse failed (upstream HTML likely changed)"

**Evidence:** live search `/tmp/boba_search2.json` — 14 success / 10 error,
total 909 results (vs 49 before BOB-005 fix). Each needs its own
investigation (parse update / timeout tuning / per-plugin import).
RuTracker is tracked separately as BOB-008 (CAPTCHA).

## §2. [BOB-006] NNMClub username/password login not wired (cookie-only)

**Status:** Queued
**Type:** Feature
**Created:** 2026-06-06

The code consumes only `NNMCLUB_COOKIES`; the operator-provided
`NNMCLUB_USERNAME`/`NNMCLUB_PASSWORD` are stored in `.env` but never used, so
NNMClub is not enabled. Implement a username/password → session-cookie login
(POST `/forum/login.php`, capture `phpbb2mysql_4_sid`) as a fallback when
`NNMCLUB_COOKIES` is unset, storing into `_tracker_sessions["nnmclub"]`.
**Plan:** `plugins/nnmclub.py` login() fallback + `search.py` enable/auth
checks + `auth.py` `/nnmclub/login` + `/nnmclub/status` + tests + challenge.

## §3. [BOB-008] RuTracker automated login blocked by CAPTCHA

**Status:** Operator-blocked
**Type:** Bug
**Created:** 2026-06-06
**Operator-Block-Details:** WHAT — RuTracker login with stored creds returns
no session cookie (CAPTCHA wall). WHY — automated user/pass login is
CAPTCHA-gated; self-resolution exhausted (creds correct + wired, login
attempted, `auth=True`). UNBLOCK — operator completes the CAPTCHA flow at
`/api/v1/auth/rutracker/captcha` + `/login`, or pastes a fresh `bb_session`
cookie via `/auth/rutracker/cookie-login`. WHO — operator.

**Evidence:** live search per-tracker stat `rutracker status=error auth=True
error="login returned no session cookie — likely CAPTCHA"`.

## §4. [BOB-007] RuTor credentials are unusable (public tracker, no login)

**Status:** Queued
**Type:** Task
**Created:** 2026-06-06

RuTor is a public tracker with no authentication endpoint; the code consumes
only `RUTOR_PROXY_*`/`RUTOR_USE_MAGNET`/`RUTOR_USER_AGENT`. The
operator-provided RuTor username/password (stored in `.env`) cannot be used.
**Resolution direction:** document RuTor as public-only in CLAUDE.md/AGENTS.md;
confirm with operator whether to keep the unused creds. Likely closes as
`Obsolete` (reason `feature-removed`/not-applicable) per §11.4.90 — pending
operator confirmation (§11.4.122).

## §5. [BOB-009] Containers submodule (§11.4.76) not integrated

**Status:** Queued
**Type:** Task
**Created:** 2026-06-06

`.gitmodules` lists only `constitution`. The constitution mandates consuming
`vasic-digital/containers` for container orchestration; the project uses
`docker-compose.yml` + `start.sh` instead. **Resolution direction:** add the
submodule + boot via its `pkg/boot`/`pkg/compose`/`pkg/health`, or record a
justified deviation.

## §6. [BOB-010] Workable-items SQLite DB + docs_chain + procedure docs not set up

**Status:** Queued
**Type:** Task
**Created:** 2026-06-06

The constitution-grade tracking system (SQLite single-source-of-truth per
§11.4.93/§11.4.95, `docs_chain` engine per §11.4.106, 5 procedure docs per
§11.4.63, per-domain Status/Status_Summary docs per §11.4.45/§11.4.56) is not
present. This Markdown tracker (Issues/Fixed + summaries, BOB prefix) is the
interim. The Go `workable-items` tool is scaffolded in the constitution
submodule (`constitution/scripts/workable-items/`) but not integrated.

## §7. [BOB-011] DOCX export not supported

**Status:** Queued
**Type:** Feature
**Created:** 2026-06-06

`scripts/generate_markdown_exports.sh` produces HTML (pandoc) + PDF
(weasyprint) but no DOCX. The operator wants DOCX too. **Resolution
direction:** add a `pandoc -t docx` branch (pandoc is installed).

## §8. [BOB-012] Many docs lack HTML/PDF exports; no export-sync gate (§11.4.65)

**Status:** Queued
**Type:** Task
**Created:** 2026-06-06

`docs/` is ~65% export-covered; `docs/CONTINUATION.md` and ~24
`docs/research/**` files lack HTML/PDF siblings, and no pre-build gate/hook
enforces export sync. **Resolution direction:** regenerate all exports + add a
`CM-MARKDOWN-EXPORT-SYNC`-class gate.
