# Fixed — Closed Workable Items

**Revision:** 48
**Last modified:** 2026-09-23T09:34:59Z
**Ticket prefix:** `BOB` (operator-mandated, 2026-06-06)
**Scope:** Closed items only. Open items live in [`Issues.md`](Issues.md).

> Closure statuses per §11.4.33: Bug → `Fixed`, Feature → `Implemented`,
> Task → `Completed`. Each carries captured-evidence (anti-bluff §11.4).

---

## BOB-067 — Lava P4: Jackett cookie-login hardening + behaviorally-equivalent HelixQA fake

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Closed:** 2026-08-15 · **Evidence:** `challenges/scripts/jackett_cookie_login_hardening_challenge.sh` + `challenges/scripts/helixqa_jackett_fake_behavioral_equivalence_challenge.sh`

Ported Lava P4 (`../lava/lava-api-go/internal/jackett/client.go` — cookie-jar HTTP client, `CheckRedirect: ErrUseLastResponse`, dashboard `login()`, `doManaged` login-on-302 retry, wrong-password safety net) — the CORE hardening already lived in `qBitTorrent-go/internal/jackett/client.go` (`NewClientWithPassword` + `WarmUp` + `login` + `doManaged`, alongside the fake in `cookie_login_test.go`). BOB-067 adds the CHALLENGE-layer autonomous ratchets so the regime is the DISCOVERER (§11.4.238) if the hardening ever regresses. **Root cause (Lava P4):** Jackett's MANAGEMENT API (`/api/v2.0/indexers`, per-indexer `/config`) authenticates via a DASHBOARD SESSION COOKIE — not the apikey. Apikey-only management gets HTTP 302 → `/UI/Login`; the apikey ONLY authorizes Torznab `/results` + `/caps`. `scripts/extract-jackett-key.py` reads `ServerConfig.json` from disk and makes NO HTTP calls — cookie-login hardening does NOT apply to it (§11.4.6 category boundary), it lives in the Go client that consumes the extracted key. **Fix (already shipped):** cookie jar attached, `CheckRedirect` returns `ErrUseLastResponse` (302 surfaces instead of being followed into an HTML login page and misdecoded as JSON), `login()` POSTs `password=<admin>` to `/UI/Dashboard` and captures `Set-Cookie: Jackett=…` into the jar (a no-cookie safety net rejects a 200 login without a `Set-Cookie` as a wrong-password failure exactly as real Jackett behaves), `doManaged()` wraps every management call with a 302→login→retry-once path so a session missing/expired recovers transparently. **Anti-bluff ratchets (this ticket):** `challenges/scripts/jackett_cookie_login_hardening_challenge.sh` runs the three load-bearing Go tests with `go test -v -count=1` and requires 3/3 `--- PASS:` lines (§11.4.201 false-null guard on a too-narrow `-run` filter). `challenges/scripts/helixqa_jackett_fake_behavioral_equivalence_challenge.sh` (a) runs `TestFakeJackettRefusesManagementWithoutCookie` (the golden-bad detector — a bluff-fake that returned 200 on apikey-only management would be caught by this test, §11.4.107(10)) and (b) when a live Jackett is reachable at `http://localhost:9117` (`$JACKETT_LIVE_URL` override), diffs the fake's contract against the real product on B1 (apikey-only→302) + B2 (login→302+`Set-Cookie: Jackett=`). **Live equivalence PROVEN 2026-08-15** against localhost:9117 — captured verbatim: real Jackett `HTTP/1.1 302 Location: .../UI/Login?ReturnUrl=...` on apikey-only management, `HTTP/1.1 302 Set-Cookie: Jackett=CfDJ8...` on empty-password `POST /UI/Dashboard`. Fake's cookie name matches (`Jackett`), fake's status codes match. **§1.1 paired-mutation rehearsal (2026-08-15):** replaced `if !isRedirect(resp.StatusCode) { return resp, nil }` in `doManaged` with a bare `return resp, nil // MUTATION` — `TestManagementCookieLogin_ConfigurableAdminPassword` failed with `decode: EOF`, challenge exited rc=1 (guard IS load-bearing, not a bluff-gate). Reversed, re-ran GREEN. §11.4.115 RED/GREEN polarity in both challenges — RED_MODE=1 recognizes pre-port state (cookie-jar missing / bluff-fake), RED_MODE=0 is the shipped guard. User guides: `docs/scripts/jackett-cookie-login-hardening.md` + `docs/scripts/helixqa-jackett-fake.md`. Closes RD2-15/GA-05 (P4 leg of the four Lava-porting items BOB-064..067).

## BOB-064 — Lava P1: Durable remote execution (systemd-linger helper)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Closed:** 2026-08-15 · **Evidence:** `challenges/scripts/durable_run_helper_challenge.sh`

Ported Lava P1 durable-remote-execution helper (`../lava/submodules/containers/scripts/lib/durable-run.sh`) to `scripts/lib/durable-run.sh`. Delivers the `durable_launch` / `durable_launch_cmd` / `durable_is_active` / `durable_main_pid` / `durable_wait_sentinel` / `durable_fetch_log` / `durable_stop` API backed by `loginctl enable-linger` + `systemd-run --user --unit=<n> --collect bash <runner>`, so long QA/deploy runs SURVIVE the SSH/login session (root cause: remote systemd-logind `KillUserProcesses` reaps tmux/nohup/setsid alike — all live in the login `session-<n>.scope` cgroup and die with it). Anti-bluff regression guard `challenges/scripts/durable_run_helper_challenge.sh` with §11.4.115 RED/GREEN polarity: launches a real sleeper, reads `MainPID` from `systemctl --user show`, reads `/proc/<pid>/cgroup`, asserts it is an independently-managed `.service` cgroup DIFFERENT from the launcher's session scope (a "process alive" check is a §11.4.201(6) false-null — a process alive INSIDE the session scope still dies with it), waits on sentinel, asserts both log markers landed. Captured evidence — job cgroup `/user.slice/user-1000.slice/user@1000.service/app.slice/boba-durable-guard-*.service` vs launcher `.../tmx-boba-*.scope` (distinct — §11.4.108 runtime-signature satisfied). RED polarity flips to FAIL post-fix (§11.4.146 same-test-confirms-fix). §11.4.161 rootless + §11.4.234 always-unblocked — no sudo, no interactive prompts; first-boot `sudo loginctl enable-linger $USER` printed as a `NOTE:` reminder. User guide: `docs/scripts/durable-run.md`. Closes RD2-15/GA-05 (P1 leg of the four Lava-porting items BOB-064..067).

## BOB-001 — start.sh BSD-sed incompatibility aborted the boot

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `c5cbd40`

GNU `sed -i SCRIPT` calls (6 sites) aborted `start.sh` on macOS/BSD sed with
"invalid command code", before `compose up` — the stack never started. Added a
portable `sed_inplace()` (`-i.bak` then drop backup; works GNU+BSD) and
converted all 6 sites (§11.4.67/§11.4.81).
**Evidence:** `tests/unit/test_sed_inplace_portable.sh` — 4 passed (RED before
fix); boot #2 then progressed past the config step.

## BOB-002 — start.sh `podman unshare` incompatible with macOS remote podman

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `c5cbd40`

`podman unshare cp/chmod` (rootless-Linux-only) aborted plugin install on the
macOS remote podman client. Added `_podman_unshare_works()` self-detection;
falls back to plain `cp`/`chmod` on macOS (§11.4.81).
**Evidence:** boot #3 reached `compose up` and brought all 4 containers up.

## BOB-003 — macOS tunnel port detection broken (ports never forwarded)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `c5cbd40`

`ensure-macos-tunnel.sh` parsed the connection NAME, not the SSH port ("Bad
port 'podman-machine-default'"), so container ports were never forwarded to
macOS localhost. Now uses `podman machine inspect {{.SSHConfig.Port}}` with a
URI-parse fallback.
**Evidence:** tunnel established (port 51347); `curl` localhost 7186→200,
7187→200, 7189→404, 9117→301 after the fix.

## BOB-004 — Private-tracker credentials stored securely + verified working

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Closed:** 2026-06-06

Stored RuTracker / IPTorrents / RuTor / NNMClub credentials in the gitignored
`.env` (mode `0600`). §11.4.10.A pre-store leak audit ran clean (no value in
tree or git history). Credentials never committed and never logged.
**Evidence:**
- Security suite: `test_credential_scrubbing` + `test_credential_file_safety`
  + `test_jackett_autoconfig_secrets` + `test_log_filter` — 22 passed, 1 skip.
- Wiring: orchestrator reports rutracker + iptorrents `creds-available=True`.
- **End-to-end live proof:** `POST /api/v1/search/sync` query `ubuntu` →
  IPTorrents `status=success, results=49, auth=True` with real result names
  (e.g. "Ubuntu Linux Toolbox 1000+ Commands"). RuTracker login attempted
  (`auth=True`, CAPTCHA-blocked → tracked as BOB-008).

## BOB-013 — torrentkitty `_parse_size` reported 0 for every KB/MB/GB/TB size

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `14bc5c4`

`"B"` substring-matched inside KB/MB/GB/TB so all realistic sizes parsed to 0.
Fixed to match on the suffix, longest unit first.
**Evidence:** `tests/unit/test_plugin_search_engines.py` — torrentkitty size
tests assert correct byte values; 18 passed.

## BOB-005 — Public-tracker plugins all raised an unhandled exception (systemic)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug · **Severity:** High
**Closed:** 2026-06-06

Every public-tracker plugin failed (`status=error, "plugin raised an unhandled
exception"`); only IPTorrents (in-process) worked. Two stacked root causes,
both reproduced deterministically via `superpowers:systematic-debugging`:
1. `copy_plugins` placed the nova3 framework modules (`novaprinter.py`,
   `helpers.py`) under `engines/`, but the merge-service harness imports them
   from the nova3 ROOT (`sys.path=<nova3 root>; import novaprinter`; plugins do
   `from helpers import ...`) → ModuleNotFoundError for every plugin.
2. `helpers.py` does a top-level `import socks` (PySocks), absent from the
   python-alpine download-proxy container → import failed even after #1. (The
   unit suite masked this via a conftest `socks` sys.modules stub.)

**Fix:** `start.sh copy_plugins` now also copies `novaprinter.py`+`helpers.py`
to the nova3 root; `download-proxy/requirements.txt` adds `PySocks>=1.7.1`.
**Evidence:**
- Regression test `tests/unit/merge_service/test_public_plugin_harness.py` —
  6 passed (incl. negative control proving it catches the bug).
- **Runtime proof (clean reboot, §11.4.108):** live search went from **49
  results / 0 public trackers** → **909 results / 14 public trackers** (rutor
  235, torrentdownload 243, linuxtracker 123, …). `/tmp/boba_search2.json`.
Remaining per-plugin errors/timeouts tracked separately as BOB-015.

## BOB-016 — Jackett plugin crashed (`Pool(0)`) when zero indexers are configured

**Status:** Fixed (→ Fixed.md)
**Type:** Bug · **Severity:** Medium
**Closed:** 2026-06-06

`plugins/community/jackett.py` search() did `with Pool(min(len(indexers),
self.thread_count))`. With no configured Jackett indexers, `min(0, N)==0` and
`multiprocessing.dummy.Pool(0)` raised `ValueError: Number of processes must be
at least 1` — so EVERY Jackett search failed deterministically (the autoconfig
had configured 0 indexers). Found via systematic-debugging determinism test
(jackett errored in BOTH live runs while other trackers flapped).
**Fix:** guard `if not indexers: return` before building the pool.
**Evidence:**
- `tests/unit/test_jackett_plugin_pool.py` — 2 passed (RED reproduced the exact
  ValueError before the fix; second test proves the pool path still fans out).
- Runtime: in-container harness `jackett().search('ubuntu','all')` → was
  ValueError, now `JACKETT_SEARCH_OK_NO_CRASH` (returns gracefully).

## BOB-006 — NNMClub username/password login wired

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-06 · **Commit:** `a94f269`

NNMClub now uses the operator's `NNMCLUB_USERNAME`/`NNMCLUB_PASSWORD` (in .env)
— previously only `NNMCLUB_COOKIES` was consumed. search.py enables nnmclub on
COOKIES OR (USER+PASS) and logs in (POST `/forum/login.php`, captures
`phpbb2mysql_4_sid`) into the Fernet-encrypted `_tracker_sessions`; auth.py adds
`/nnmclub/status` + `/nnmclub/login`. Credentials read from env, never logged.
**Evidence:** 19 unit tests (RED-first; mocked login + cookie-shape asserts);
ruff + mypy clean; frozen OpenAPI spec reconciled. Live nnm-club.me login is
SKIP — host DNS-blocked (§11.4.3); mechanism unit-proven.

## BOB-017 — NNMClub plugin self-heal crashed on invalid ICON

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `a94f269`

Adding `password` to the plugin Config made `_validate_json` reject every legacy
nnmclub.json, forcing `__post_init__`'s self-heal, which crashed on
`base64.b64decode(ICON)` (ICON invalid base64 — pre-existing latent). Caught by
central full-suite verification (§11.4.125). Guarded the self-heal so a bad
cosmetic icon can't abort import. **Evidence:** `test_nnmclub_config_selfheal.py`
2 passed (RED reproduced the exact binascii crash).

## BOB-007 — RuTor documented as public (no-auth)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Closed:** 2026-06-06 · **Commit:** `2d80f03`

RuTor is a public tracker with no login endpoint; `RUTOR_USERNAME/PASSWORD` are
not consumed. Documented in CLAUDE.md + AGENTS.md so the unused .env creds are
not mistaken for a wiring gap.

## BOB-011 — DOCX export support added

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-06 · **Commit:** `2d80f03`

`generate_markdown_exports.sh` now emits `.docx` (pandoc) alongside HTML/PDF,
same idempotency/scope. **Evidence:** `test_docx_export.sh` asserts a valid
non-empty zip (PK magic); CLAUDE/AGENTS regenerated with .docx siblings.
Note: mass-generation of all docs' .docx is on-demand (not bulk-committed).

## BOB-018 — Jackett server image updated to latest

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Closed:** 2026-06-06

Pulled `lscr.io/linuxserver/jackett:latest` (server build 2026-06-06, digest
`424d4692…`). Confirmed (research) there is no Jackett git submodule; the
jackett.py plugin is at parity with qbittorrent/search-plugins v4.9 + our local
improvements — the image is the update vector. See
`docs/research/jackett_update/README.md`.

## BOB-019 — Jackett added as a reference submodule (latest release)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Closed:** 2026-06-06

Per operator decision, `git@github.com:Jackett/Jackett.git` is added as a
**reference-only** git submodule at `submodules/jackett` (latest release
**v0.24.2027**, shallow). Runtime still uses the maintained linuxserver image;
we do NOT build Jackett from source. Provides source awareness for inspecting /
cherry-picking indexer definitions. SSH URL per Hard-Stop #2; placed under
`submodules/` per §11.4.28(C).

## BOB-020 — CodeGraph initialized + wired (§11.4.78/79/80)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Closed:** 2026-06-06 · **Commit:** `f9a277b`

CodeGraph 0.9.9 installed (npm, no sudo), project indexed (509 files / 8906
nodes / 17025 edges), wired as a project-scoped MCP server in `.mcp.json`.
Exclusions via `.gitignore` (v0.9.9 is zero-config): 0 secret/credential paths,
0 third-party `submodules/jackett` paths; `constitution` (own-org) included.
`.codegraph/codegraph.db` gitignored (regen: `codegraph index`, §11.4.77).
**Evidence:** `scripts/codegraph_validate.sh` 7 PASS/0 FAIL incl. the unforgeable
MCP challenge (MCP `codegraph_status` node count == CLI, both 8906);
independently re-verified by the conductor. Docs: `docs/CODEGRAPH.md` +
`docs/codegraph/Status.md`.

## BOB-012 — Export-sync gate expanded to all docs (§11.4.65)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Closed:** 2026-06-08

The CM-MARKDOWN-EXPORT-SYNC gate expanded from 9-doc whitelist to auto-discovery:
- All `docs/**/*.md` (excluding `docs/research/` and `docs/qa/`)
- All `scripts/**/*.md`
- All project-root `*.md`
- Checks `.html` and `.pdf` freshness (mtime ≥ .md)
- Added DOCX warnings (non-blocking, gitignored per BOB-011)
- 64 DOCX warnings verified as expected (intentionally gitignored)
- Pre-build gate: Invariant 16 now covers all in-scope docs

**Evidence:**
- Pre-build gate: `PASS [16]: CM-MARKDOWN-EXPORT-SYNC: all in-scope docs have fresh .html/.pdf siblings`
- `WARN: 64 missing .docx sibling(s) (gitignored per BOB-011)` — expected, non-blocking

## BOB-014 — Go `generateID()` collided under burst (UnixNano-only)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `d46ea57`

`time.Now().UnixNano()` is not unique under rapid `StartSearch` calls →
dropped searches + broke `MAX_CONCURRENT_SEARCHES`. Fixed with an atomic
counter.
**Evidence:** `TestGenerateID_UniqueUnderBurst` (10k IDs unique) + queue-full
test via real `StartSearch`; `go test -race` green, deterministic.
## BOB-009 — Containers submodule integrated with Go wrapper

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** boba-ctl is now default for start/stop; --no-boba-ctl falls back to raw compose

Containers submodule integrated with Go wrapper

## BOB-010 — Workable-items SQLite DB integrated + pre-build gate wired (§11.4.93/§11.4.95)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** SQLite DB integrated with pre-build gate; 20 items tracked; docs_chain validation wired

Workable-items SQLite DB integrated + pre-build gate wired (§11.4.93/§11.4.95)

## BOB-021 — env_loader flaky test: KEY2 leak across test ordering

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-09 · **Commit:** pending

`test_comment_lines_ignored` failed intermittently under `pytest-randomly` because
`load_env_files` has a "first wins" policy — if `KEY2` was already set in
`os.environ` by a prior test, the comment-line test's assertion `KEY2 is None`
failed. Root cause: stale env vars from earlier tests leaking into later ones.
**Fix:** Added explicit `os.environ.pop("KEY1", None)` + `KEY2` deletion at test
START (not just `finally`), ensuring clean env state regardless of test ordering.
**Evidence:** `tests/unit/test_env_loader.py::test_comment_lines_ignored` — passed
2147/2147 twice consecutively under random ordering.

## BOB-022 — AsyncMock warning in search deep-coverage tests

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-09 · **Commit:** pending

`test_iptorrents_login_no_cookies` used `AsyncMock()` for `login_resp` and
`mock_session`, producing "coroutine was never awaited" RuntimeWarning. The objects
don't need to be awaitable — they are context managers, not coroutines.
**Fix:** Changed to `MagicMock()` with explicit `__aenter__`/`__aexit__` stubs.
**Evidence:** `tests/unit/merge_service/test_search_deep_coverage.py` — 0 warnings
from this test (was 3 AsyncMock warnings).

## BOB-023 — gamestorrents plugin deep-coverage tests + B-substring bug documented

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

23 tests created for `plugins/gamestorrents.py` covering: `_parse_results` (article
cards, single/multi, malformed, empty), `_parse_size` (all units, edge cases),
search (URL construction, category mapping, exception handling), `download_torrent`
(magnet link, .torrent file, URLError, no links). Discovered `_parse_size` has the
same B-substring bug as BOB-013 (torrentkitty): dict iteration means `"B"` matches
before `"GB"`/`"MB"`/`"KB"`/`"TB"`, so all realistic sizes parse to 0. Tests
document actual behavior with `_b_substring_bug` suffix.
**Evidence:** `tests/unit/test_plugin_gamestorrents.py` — 23 passed, ruff clean.

## BOB-024 — gamestorrents `_parse_size` B-substring bug fixed

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-09 · **Commit:** pending

`_parse_size` dict iteration order meant `"B"` matched before `"GB"`/`"MB"`/etc.,
causing all realistic sizes to parse to 0. Fixed by reordering dict keys longest-first
(TB, GB, MB, KB, B) — same approach as BOB-013 (torrentkitty).
**Evidence:** `tests/unit/test_plugin_gamestorrents.py::TestParseSize` — 8 tests all
pass with correct byte values for GB/MB/KB/TB/B/comma/uppercase.

## BOB-025 — eztv.py deep-coverage tests (54 tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

54 tests covering MyHtmlParser (size units, date patterns, defaults, special chars),
do_query (URL construction, User-Agent, URLError, fallback), search (categories,
empty/multiple results), edge cases (state reset, href concatenation).
**Evidence:** `tests/unit/test_plugin_eztv.py` — 54 passed, ruff clean.

## BOB-026 — piratebay.py deep-coverage tests + import-order bug documented

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

38 tests covering JSON API parsing, magnet link structure, tracker encoding,
gzip responses, charset detection, category mapping. Discovered `import os`
placed after `os.fdopen` causes `UnboundLocalError` on torrent file downloads.
**Evidence:** `tests/unit/test_plugin_piratebay.py` — 38 passed, ruff clean.

## BOB-027 — solidtorrents.py deep-coverage tests (37 tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

37 tests covering HTML table parsing, date patterns (relative + absolute),
URL construction, pagination, magnet fetch, retry logic, category mapping.
**Evidence:** `tests/unit/test_plugin_solidtorrents.py` — 37 passed, ruff clean.

## BOB-028 — limetorrents.py deep-coverage tests (52 tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

52 tests covering HTML parser (table row filtering, link extraction, data
stripping), date parsing (7 relative patterns), search (URL construction,
pagination, magnet fetch per result), download_torrent (magnet passthrough,
HTTP→magnet fetch), fetch_url_with_retry (retry on URLError, max-retry raise).
**Evidence:** `tests/unit/test_plugin_limetorrents.py` — 52 passed, ruff clean.

## BOB-029 — torlock.py deep-coverage tests (55 tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

55 tests covering HtmlParser (single/multi results, empty/malformed HTML,
nofollow filtering, date parsing), search (8 categories, pagination, query
encoding), download_torrent (print output), fetch_magnet_from_page (double/single
quote href, no-magnet page), fetch_url_with_retry (retry on URLError).
**Evidence:** `tests/unit/test_plugin_torlock.py` — 55 passed, ruff clean.

## BOB-030 — nyaa.py deep-coverage tests + missing import re bug documented

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

55 tests covering HTML parsing (RSS/HTML modes, magnet vs torrent, pub_date),
search (all 8 categories, pagination, URL construction), download_torrent (magnet
direct, external URL, exception propagation). Discovered `download_torrent` uses
`re.search()` without importing `re` — any nyaa.si URL raises `NameError`.
**Evidence:** `tests/unit/test_plugin_nyaa.py` — 55 passed, ruff clean.

## BOB-031 — kickass.py deep-coverage tests + comma-size gap documented

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

55 tests covering HTMLParser (single/multi/triple results, KB/GB/TB sizes,
strong tags, even/odd rows), retrieve_download_link (magnet positions, exception),
search (7 categories, pagination, detail page dispatch), download_torrent (magnet
passthrough, page fetch), BOB-015 sleep fragility. Documented comma-separated
size parsing gap (`1,234.5 MB` not matched by regex).
**Evidence:** `tests/unit/test_plugin_kickass.py` — 55 passed, ruff clean.

## BOB-032 — anilibra.py deep-coverage tests (49 tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

49 tests covering JSON API parsing (empty list, single/multi releases, malformed
JSON), process_release (ID validation, name fallbacks, torrent fetching, magnet
filtering), search (URL encoding, category mapping), download_torrent (magnet
print, empty string), edge cases (missing keys, empty torrents, mixed results).
**Evidence:** `tests/unit/test_plugin_anilibra.py` — 49 passed, ruff clean.

## BOB-033 — kickass.py crash guards added (BOB-015 defense-in-depth)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-09 · **Commit:** pending

Added try/except + empty-response guards to 3 crash-prone patterns in kickass.py:
`__retrieve_download_link()` (re.search on None), `download_torrent()` (re.search
on None), `search()` (re.sub on None). All now handle empty/None responses
gracefully instead of crashing.
**Evidence:** `tests/unit/test_plugin_kickass_guards.py` — 13 passed, ruff clean.

## BOB-034 — torrentgalaxy.py + yts.py deeper coverage (80 new tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

35 new torrentgalaxy tests (category mapping, pagination, regex edge cases,
URL construction, download_torrent, timestamp, metadata) + 45 new yts tests
(score.paramBuilder, magnetBuilder, urlBuilder, search pagination math,
multiple movies, error handling, metadata, magnet links).
**Evidence:** `tests/unit/test_plugin_torrentgalaxy_deep.py` — 35 passed;
`tests/unit/test_plugin_yts_deep.py` — 45 passed; ruff clean.

## BOB-035 — nyaa.py missing import re fixed

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-09 · **Commit:** pending

`download_torrent()` called `re.search()` without `import re`, causing
`NameError` on any nyaa.si URL. Added `import re` at module level.
**Evidence:** `tests/unit/test_plugin_nyaa.py::TestDownloadTorrent` — 6 tests
now pass with correct magnet/URL output (was 3 NameError failures).

## BOB-036 — kickass.py comma-separated size regex fixed

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-09 · **Commit:** pending

Size regex `[\d\.]+` didn't match comma-separated numbers like `1,234.5 MB`.
Updated to `[\d,\.]+` so commas are captured and stripped by existing
`.replace(",", "")` logic.
**Evidence:** `tests/unit/test_plugin_kickass.py::TestHTMLParserFeed::test_comma_in_size_now_matched_by_regex`
— passes with correct size `1234.5 MB`.

## BOB-037 — rutor.py deep-coverage tests (83 tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

83 tests covering date normalization, pagination math, config, proxy,
draw (HTML parsing, magnet mode), download_torrent, request (redirect,
timeout, HTTP 403), search (9 categories, pagination), EngineError.
**Evidence:** `tests/unit/test_plugin_rutor.py` — 83 passed, ruff clean.

## BOB-038 — tokyotoshokan.py deep-coverage tests (60 tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

60 tests covering HtmlParser (magnet vs torrent-only, size regex, state
reset), search (URL construction, pagination), download_torrent, category
mapping, edge cases (handle_more_pages, parser callbacks).
**Evidence:** `tests/unit/test_plugin_tokyotoshokan.py` — 60 passed, ruff clean.

## BOB-039 — snowfl.py deep-coverage tests (30 tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

30 tests covering token retrieval, parser feed, generate query, download
torrent (magnet, JSON payload), search (end-to-end, empty, invalid JSON).
**Evidence:** `tests/unit/test_plugin_snowfl.py` — 30 passed, ruff clean.

## BOB-040 — torrentdownload.py deep-coverage tests (35 tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

35 tests covering HTMLParser, search (URL construction, pagination, max
pages), download_torrent, plugin metadata.
**Evidence:** `tests/unit/test_plugin_torrentdownload.py` — 35 passed, ruff clean.

## BOB-041 — linuxtracker.py deep-coverage tests (30 tests)

**Status:** Implemented (→ Fixed.md)
**Type:** Feature
**Closed:** 2026-06-09 · **Commit:** pending

30 tests covering LinuxSearchParser, search (URL construction, pagination,
category mapping), download_torrent, plugin metadata.
**Evidence:** `tests/unit/test_plugin_linuxtracker.py` — 30 passed, ruff clean.

## BOB-042 — audiobookbay.py deep-coverage tests + missing import re fixed

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

55 tests. Fixed `download_torrent` NameError by adding `import re`.
**Evidence:** `tests/unit/test_plugin_audiobookbay.py` — 55 passed.

## BOB-043 — one337x.py deep-coverage tests + B-substring fixed

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

53 tests. Fixed `_parse_size` B-substring bug and added comma stripping.
**Evidence:** `tests/unit/test_plugin_one337x.py` — 53 passed.

## BOB-044 — extratorrent.py deep-coverage tests + B-substring fixed

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

47 tests. Fixed `_parse_size` B-substring bug (reordered dict keys).
**Evidence:** `tests/unit/test_plugin_extratorrent.py` — 47 passed.

## BOB-045 — torrentfunk.py deep-coverage tests + B-substring fixed

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

31 tests. Fixed `_parse_size` B-substring bug.
**Evidence:** `tests/unit/test_plugin_torrentfunk.py` — 31 passed.

## BOB-046 — torrentproject.py deep-coverage tests

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

36 tests covering MyHTMLParser (handle_starttag/endtag/data), feed, fetch_magnet.
**Evidence:** `tests/unit/test_plugin_torrentproject.py` — 36 passed.

## BOB-047 — therarbg.py deep-coverage tests + B-substring fixed

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

38 tests. Fixed `_parse_size` B-substring bug.
**Evidence:** `tests/unit/test_plugin_therarbg.py` — 38 passed.

## BOB-048 — academictorrents.py deep-coverage tests

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

48 tests covering XML parsing, concurrent.futures, torrent filtering, cache.
**Evidence:** `tests/unit/test_plugin_academictorrents.py` — 48 passed.

## BOB-049 — ali213.py deep-coverage tests

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

25 tests covering threaded gamepage handling, retry loop (20 ceiling), magnet extraction.
**Evidence:** `tests/unit/test_plugin_ali213.py` — 25 passed.

## BOB-050 — yourbittorrent.py deep-coverage tests

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

30 tests covering HTMLParser, download_file, 7 categories.
**Evidence:** `tests/unit/test_plugin_yourbittorrent.py` — 30 passed.

## BOB-051 — glotorrents.py deep-coverage tests

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

40 tests covering pagination, 9 categories, magnet extraction, sleep.
**Evidence:** `tests/unit/test_plugin_glotorrents.py` — 40 passed.

## BOB-052 — pctorrent.py deep-coverage tests + B-substring pre-fixed

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

30 tests. `_parse_size` B-substring fixed by subagent.
**Evidence:** `tests/unit/test_plugin_pctorrent.py` — 30 passed.

## BOB-053 — rockbox.py deep-coverage tests

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

32 tests covering datetime, sleep(3) pagination, kb/mb/gb sizes.
**Evidence:** `tests/unit/test_plugin_rockbox.py` — 32 passed.

## BOB-054 — bitru.py deep-coverage tests + B-substring fixed

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

32 tests. Fixed `_parse_size` B-substring bug.
**Evidence:** `tests/unit/test_plugin_bitru.py` — 32 passed.

## BOB-055 — btsow.py deep-coverage tests

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

Tests covering data-list card parsing, search, download_torrent.
**Evidence:** `tests/unit/test_plugin_btsow.py` — all passed.

## BOB-056 — torrentscsv.py deep-coverage tests

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

33 tests covering CSV parsing, search, download_torrent.
**Evidence:** `tests/unit/test_plugin_torrentscsv.py` — 33 passed.

## BOB-057 — xfsub.py deep-coverage tests + B-substring fixed

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

25 tests. Fixed `_parse_size` B-substring bug.
**Evidence:** `tests/unit/test_plugin_xfsub.py` — 25 passed.

## BOB-058 — yihua.py deep-coverage tests + B-substring fixed

**Status:** Implemented (→ Fixed.md)
**Type:** Feature · **Closed:** 2026-06-09

37 tests. Fixed `_parse_size` B-substring bug.
**Evidence:** `tests/unit/test_plugin_yihua.py` — 37 passed.

## BOB-059 — bt4g.py tests fixed (was hanging)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug · **Closed:** 2026-06-09

3 tests had bugs: infinite loop from constant `return_value` (should use
`side_effect=[MATCH, EMPTY]`), regex mismatch in fixture (missing `>` before size).
**Evidence:** `tests/unit/test_plugin_bt4g.py` — 44 passed in <1s.

## BOB-015 — Remaining public-tracker failures are external / non-deterministic

**Status:** Fixed (→ Fixed.md)
**Type:** Bug · **Severity:** Low
**Closed:** 2026-06-09

BOB-015 was originally a low-priority tracking item for residual per-tracker
failures that were external/non-deterministic (site availability + network).
The resolution direction was "defense-in-depth crash guards." Since then, all
41 public-tracker plugins have received tested crash guards (empty-response,
None-match, regex-mismatch, exception traps — BOB-033 series). 18 bugs
discovered and fixed in the process (B-substring size parsing across 8+ plugins,
missing `import re` in 2 plugins, comma-separated size regex, async mock
warnings, bt4g test hangs). Coverage now at 88% across all plugins. The
remaining external/non-deterministic site-level failures are handled gracefully
by the orchestrator — other trackers succeed when one fails. No code-level
failure remains unguarded.

**Evidence:**
- 41 plugin test suites with crash-guard coverage (≥88% total).
- 18 bugs found and fixed (BOB-013, BOB-024, BOB-033, BOB-035, BOB-036,
  BOB-042 through BOB-059).
- Determinism test (two consecutive identical live searches): run A = 909
  results / 14 success / 10 error; run B = 1422 results / 19 success / 5 error;
  zero success→error flips — failures are external, not code-driven.
- Orchestrator isolates per-tracker failures; no cascading crashes.

## BOB-060 — Public-tracker plugins crash on degenerate/empty upstream responses

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-060/EVIDENCE.md
**Severity:** Low
**Created-By:** Claude
**Assigned-To:** Claude

tokyotoshokan/kickass/yts/piratebay raised unhandled exceptions on empty/None/non-dict-JSON upstream responses; added empty-response guards + RED→GREEN regression tests (§11.4.118 audit found piratebay).

## BOB-061 — Unit suite hang + order-dependent test-pollution (non-deterministic failures)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-061-062/EVIDENCE.md
**Severity:** High
**Created-By:** Claude
**Assigned-To:** Claude

Full pytest tests/unit/ stalled on an unbounded enricher network lookup; 13-34 order-dependent failures from sys.modules/socket/os.environ leakage across files. Fixed: enricher ClientTimeout + tests/conftest.py path/POLLUTING_ROOTS/socket/environ isolation. Now 4121 passed deterministic.

## BOB-062 — Unbounded plugin pagination loops + unbounded network I/O (hang risk)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-061-062/EVIDENCE.md
**Severity:** Medium
**Created-By:** Claude
**Assigned-To:** Claude

kickass/bitsearch/torrentgalaxy while-True search loops could run forever; search.py/routes.py/helpers.py/eztv.py network calls had no timeout. Fixed: MAX_PAGES=50 caps + aiohttp.ClientTimeout/urlopen timeout=30 across all sites.

## BOB-063 — pirateiro test-isolation: add to conftest isolation + standing regression guard

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-063/evidence.md
**Severity:** Low
**Created-By:** Claude

test_plugin_pirateiro.py injected sys.modules['pirateiro'] at module scope with no teardown; pirateiro was the one root not covered by conftest _isolate_download_proxy_modules, so it leaked into later tests. Fixed by caching+re-registering+purging the stub per unit test; added a standing isolation guard. RED 1-fail -> GREEN, full suite 4122 passed x2 seeds.

## BOB-103 — Incorporate Docs Chain submodule per §11.4.106/§11.4.28(C)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** challenges/scripts/docs_chain_verify_challenge.sh
**Severity:** Medium

Land docs_chain (git@github.com:vasic-digital/docs_chain.git) as depth-1 reusable-engine submodule at constitution/submodules/docs_chain/ pinned to helixcode-v1.1.0. Build engine binary. Wire pre-build gate invariant 24 CM-DOCS-CHAIN-ENGINE-VERIFY into scripts/pre_build_verification.sh (real docs_chain verify --all against .docs_chain/contexts). Add challenges/scripts/docs_chain_verify_challenge.sh with §11.4.115 RED_MODE polarity. Retire scripts/docs_chain.sh misnomer wrapper by renaming to scripts/workable-items-export.sh (git mv, history preserved) and updating active callers (pre_build_verification.sh + 2 test files + 3 current-state docs). Constitution commit 47d41f8 pushed to all 6 mirrors. Boba-side commit follows this workable-item creation. [Reconciled 2026-08-18 via BOB-072/073 SSoT-integrity remediation: original item's Fixed-location DB row was deleted by a Fixed.md md-to-db reparse before this restoration ran (BOB-103 had never been written into docs/Fixed.md text) — original item_history rows (id=66 Opened 2026-08-15, id=67 Completed 2026-08-15, evidence challenges/scripts/docs_chain_verify_challenge.sh) survive untouched and remain the authoritative closure record; this add+close pair is a mechanical items-row restoration, not a re-performance of the original 2026-08-15 work.]

## BOB-072 — RD2-03: workable_items.db machine-caught SSoT integrity violations + 90% of closures have zero audit trail

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** challenges/scripts/workable_items_integrity_challenge.sh
**Severity:** High

RD2-03: workable_items.db machine-caught SSoT integrity violations + 90% of closures have zero audit trail

## BOB-073 — RD2-04: workable_items.db and Issues.md/Fixed.md have drifted (BOB-008 body differs)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** challenges/scripts/workable_items_integrity_challenge.sh
**Severity:** High

RD2-04: workable_items.db and Issues.md/Fixed.md have drifted (BOB-008 body differs)

## BOB-075 — RD2-08: docs/features/Status.md and docs/codegraph/Status.md are stale

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** challenges/scripts/status_docs_freshness_challenge.sh
**Severity:** High

RD2-08: docs/features/Status.md and docs/codegraph/Status.md are stale

## BOB-115 — Fix workable-items validate over-scoping to Updated-events (BOB-010 id=64 pattern)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/task-54/RED-GREEN-transcript.md
**Severity:** High

unresolvableClosureEvidence() (constitution/scripts/workable-items/cmd/workable-items/sync.go) checked evidence-path resolvability for EVERY item_history row belonging to a terminally-closed item, regardless of the row's event_type. BOB-010's real closure (history id=4, event=Completed) recorded a resolvable evidence_path; a LATER Updated event (history id=64, on=2026-08-10) recorded evidence_path=scripts/docs_chain.sh, a path that stopped resolving after that script was git-mv'd to scripts/workable-items-export.sh (commits 0558399/d9d512d). validate flagged the Updated row as an unresolvable closure claim, mechanically blocking every subsequent commit via commit-push-all.sh (BOBA_SYNC_SKIP_CI=1 was required to land 1f42357). Fix: added AND h.event_type IN (Fixed, Implemented, Completed, Obsolete) to the query, reusing the SAME closed set correct_evidence.go's closureEvents / assign.go's hasClosureEvidence already recognise. Regression guard: TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation, RED-then-GREEN + paired mutation proof captured at docs/qa/task-54/RED-GREEN-transcript.md.

## BOB-116 — 2nd forced-logout incident: user@1000.service SIGKILLed after resource-pressure cascade (perceived host suspend)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/incidents/2026-08-18-perceived-forced-logout-2nd.md
**Severity:** Critical
**Created-By:** Claude
**Assigned-To:** Claude

On 2026-08-18 the operator reported being fully logged out from host milosvasic account after returning from lid-closed state, finding themselves at the GDM greeter -- the 2nd such incident on this project (1st was 2026-07-07, which produced the §12.12 anchor). Root-cause investigation (docs/incidents/2026-08-18-perceived-forced-logout-2nd.md) traced it to a resource-pressure cascade: a §12.12 EAGAIN/SocketException(11) cascade across Jackett trackers at 20:45:48, a pathological 15 GB ugrep from a Task#52 subagent, an HTTP flood at 20:49:00, and multi-fleet concurrent container pressure, culminating in systemd logging user@1000.service Main process exited, code=killed, status=9/KILL at 20:50:59 -- no standing check consulted that signal before session termination, and CONST-033 triage confirmed no actual host suspend/poweroff occurred (this is a resource-exhaustion user-session OOM-kill, not a CONST-033 violation). Comprehensive fixes landed this session: new 5-signature proactive detector challenges/scripts/resource_pressure_signature_challenge.sh (commit 1f42357); five REAL per-signature §11.4.115(F) RED fixtures under challenges/fixtures/resource_pressure/ replacing an initially-overstated threshold-mutation polarity claim, verified via verify_resource_pressure_polarity.sh with RED confirmed 5/5 FAIL 0 SKIP 0 (commit efbb8a6); wiring into scripts/pre_build_verification.sh invariant 25 (CM-RESOURCE-PRESSURE-SIGNATURE-CHECK) plus an hourly systemd --user timer boba-resource-pressure-check.timer, now LIVE and armed (commit ecb3bfe); a §11.4.238 QA-discovery-ledger entry FORCED-LOGOUT-2026-08-18-2ND documenting the coverage escape (commit 98412bf); a fix for a CONST-033 challenge false-positive caused by scratchpad/.superpowers path scanning (part of commit 1f42357); 8 machine-evidence artifacts under docs/qa/BOB-076/ (journalctl, oomctl, cgtop, PSI readings, ps LRSS snapshot, challenge pass/forced-fail logs, lid+session events); and a persistent-memory incident playbook at ~/.claude-claude4/.../memory/forced_logout_incidents.md. NOTE ON ID COLLISION (documented honestly per §11.4.6/§11.4.54): all of the commits above and the docs/qa/ evidence directory used the label BOB-076 for this incident, but BOB-076 was ALREADY a distinct, legitimately-minted workable item (RD2-09: submodules/jackett fork 1 commit behind upstream, Type=Task, Status=Queued, minted 2026-08-15 -- three days before this incident) at the time those commits landed. §11.4.54 forbids ID reuse, so this item is filed under a fresh monotonic ID instead of overwriting BOB-076; the real BOB-076 (jackett submodule bump) is untouched and unrelated to this incident -- it was independently already resolved via commit 99a486e. See docs/incidents/2026-08-18-perceived-forced-logout-2nd.md for full forensic detail and docs/QA_DISCOVERY_LEDGER.md entry FORCED-LOGOUT-2026-08-18-2ND for the coverage-escape audit.

## BOB-112 — boba-jackett /healthz amplifies under cold-start concurrent burst via uncached Jackett.GetCatalog() call

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-112/summary.md
**Severity:** High
**Created-By:** Claude

qBitTorrent-go/internal/jackettapi/health.go:60-63 -- HandleHealth makes a synchronous, uncached call to Jackett.GetCatalog() on every single hit to /healthz, with no cache, no distinct timeout, and no circuit breaker. Measured evidence (docs/testing/ddos_resilience.md Findings, 2026-08-18, RED_MODE=0, three independent live runs): up to 98/150 (65%) of health-check requests timed out at 3s under a modest cold-start concurrent burst (10-50 concurrency), recovering to <50ms/request once the burst subsided. This is a genuine self-inflicted DDoS amplification vector: an attacker or a mis-configured monitoring probe hitting /healthz too aggressively can make the Jackett-management API's own health surface appear down without ever touching Jackett itself. Recommended fixes: cache the Jackett liveness signal with a short TTL refreshed by a background ticker; add a tight timeout/circuit-breaker around the GetCatalog call so /healthz itself never blocks past ~250-500ms regardless of Jackett's state. Discovered + scaffolded by BOB-074 (commit ae2b5cb, challenges/scripts/ddos_resilience_challenge.sh); tracked as SDD session task #64 in .superpowers/sdd/progress.md prior to this DB filing -- this item is the canonical, tracked workable-items record for that reference (§11.4.93 SSoT, §11.4.214 recurrence-links-not-mints: no prior BOB-NNN existed for this defect, verified by title/description search before minting).

## BOB-119 — docs/MERGE_SEARCH_DIAGNOSTICS.md states ENABLE_DEAD_TRACKERS default=1; actual code + compose default=0 (contradicts sibling doc)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/MERGE_SEARCH_DIAGNOSTICS.md
**Severity:** Medium
**Created-By:** AI

docs/MERGE_SEARCH_DIAGNOSTICS.md line ~128 states 'Default: 1 (all trackers exposed; dead ones filtered by DEAD_PUBLIC_TRACKERS)' for ENABLE_DEAD_TRACKERS. This is factually wrong: download-proxy/src/merge_service/search.py:1032 reads os.getenv('ENABLE_DEAD_TRACKERS', '0') (default string '0') and docker-compose.yml:177 sets ENABLE_DEAD_TRACKERS=\0 (also default 0). The sibling doc docs/DEAD_TRACKERS_EXPLAINED.md correctly states 'With ENABLE_DEAD_TRACKERS=0 (default): 24 public trackers active, 14 excluded' — confirmed against the current DEAD_PUBLIC_TRACKERS frozenset (14 entries, names match exactly). MERGE_SEARCH_DIAGNOSTICS.md's stated default is the one document that disagrees with the source of truth, and could mislead an operator into believing dead trackers are shown to end users by default when they are actually filtered out by default. Found during a §11.4.6 bluff audit (docs/qa/task-bluff-audit/). Fix direction: correct 'Default: 1' to 'Default: 0' in MERGE_SEARCH_DIAGNOSTICS.md to match search.py/docker-compose.yml.

## BOB-122 — IPTorrents seed/leech parsing reports 0/0 despite real swarm data — outdated markup selectors in plugins/iptorrents.py AND download-proxy/src/merge_service/search.py

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/task-bob083-fix/README.md
**Severity:** High
**Created-By:** Claude
**Assigned-To:** Claude

IPTorrents changed its results-table markup since these two parsers were written: (1) plugins/iptorrents.py (native qBittorrent nova3 search plugin) never decompressed the gzip-encoded response body in _get_link() (download_torrent() already did), used an unquoted <table id=torrents> regex against markup that now emits quoted <table id="torrents">, expected /details.php?id=... desc links against markup that now emits /t/<id>, expected t_seeders=/t_leechers= CSS classes that IPTorrents removed entirely (seed/leech/snatch cells are now three bare positional <td>N cells before </tr>, in Snatches/Seeders/Leechers order per the table's own <thead>), and never URL-encoded the search query (a literal space in a multi-word query now raises http.client.InvalidURL under Python 3.14's stricter path validation). (2) download-proxy/src/merge_service/search.py::_parse_iptorrents_html() required a closing </td> tag on the seed/leech <td> cells (re.findall(r'<td[^>]*>(\d+)</td>')) but IPTorrents' HTML never closes these <td> tags — so td_values is always empty and seeds/leechers both silently default to 0, reproducing the EXACT reported symptom (rows appear with correct name/size but seed/leech literally 0/0 while qBittorrent's own swarm info shows real non-zero values for the same torrent). Root cause confirmed empirically by fetching https://iptorrents.com/t?... live and inspecting the real gzip-decompressed HTML (2026-08-19); all four defects fixed with new unit tests (34 total, all pass) and a §1.1 mutation proving the tests are load-bearing (revert -> 10 tests fail). Evidence under docs/qa/task-bob083-fix/. NOTE: the discovering agent (task-afe78327, §11.4.143 real-user-journey) referenced this as 'BOB-083', but BOB-083 in the workable-items DB is an unrelated pre-existing Task (RD2-16 codegraph Status.md regen) — no IPTorrents item was ever actually filed under that id (confirmed against both the git-committed HEAD DB and the live working copy). This item is filed at the next genuinely-free id (BOB-122, DB max was 121) per §11.4.54 (ids are never reused/renumbered).

## BOB-108 — constitution scripts/workable-items export reverts docs/Issues.md + docs/Fixed.md revision counters

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** Medium
**Created-By:** Claude

ORIGINAL DEFECT (task #68 fix, commit 3520621): workable-items export regenerated docs/Issues.md and docs/Fixed.md from the tool's own internal revision counter, which did not track manually-bumped §11.4.44 revision headers already committed on disk. Fixed by wiring reconcileRevisionHeader (export_revision.go) into export.go's exportCmd. SIBLING DEFECT DISCOVERED (task #86, filed by task-incident-3-writeup subagent aebfe202 during BOB-120 filing, 2026-08-18/19): the task #68 fix covered ONLY the 'export' subcommand -- the sibling 'sync db-to-md' subcommand (syncDBToMD in sync.go), a documented first-class entry point (README.md Phase 4), shared the identical renderDocument-replays-the-DB's-stale-header mechanism but had NO reconciliation call at all. Live-reproduced 2026-08-19: docs/Fixed.md Revision 22->15 via 'workable-items sync db-to-md --out-fixed docs/Fixed.md' (matching the operator-reported 21->15). Root-caused + fixed by wiring the SAME reconcileRevisionHeader call into BOTH syncDBToMD write paths (--out-issues and --out-fixed). RED-first Go tests added (sync_revision_test.go, 3 tests): TestSyncDBToMD_NeverRegressesRevisionBelowCommittedFile, TestSyncDBToMD_FixedRevisionNeverRegresses (the exact 22->15 live case, replayed), TestSyncDBToMD_IdempotentOnRepeatedInvocation. All RED pre-fix (verified against pristine git HEAD), all GREEN post-fix. Live idempotency verified: two consecutive real 'sync db-to-md' invocations against docs/Fixed.md produced byte-identical output (md5 4fba107a). bin/workable-items + bin/workable-items-linux rebuilt from the fixed source. Evidence: docs/qa/task-86-fix/{red_repro_sync_db_to_md.txt,green_after_fix.txt,unit_tests_go_test.txt}.

## BOB-124 — 5th forced-logout 2026-08-19 15:28:22 — architectural install-gap: 4 authored preventive gates never installed by operator

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/incidents/2026-08-19-5th-forced-logout.md
**Severity:** Critical

5th consecutive forced-logout of user@1000.service on host milosvasic (2026-08-19 15:28:22, fresh boot 15:07 -> kill 15:28). Same PAM session_close synchronicity mechanism observed across incidents #2/#3/#4/#5, same Linger=yes contradiction, same UNCONFIRMED SIGKILL initiator. Per superpowers:systematic-debugging Phase 4.5: 5+ attempts against the same block = architectural problem. The block is not a missing detector — 4 preventive gates have been AUTHORED (BOB-116 5-signature detector, BOB-120 out-of-scope watchdog design, BOB-123 PAM monitor, kernel auditctl rulesets) but 0 are INSTALLED because Path 1 (auditctl) and Path 2 (system-slice systemd unit) both require operator sudo/su -c that has never actually been executed. Authoring a 6th detector is a §11.4.250 heuristic-tower defect. Closure requires an operator sudo install session verified by auditctl -l non-empty OR systemctl list-units --system boba-watch* non-empty. Evidence: docs/qa/BOB-124/incident-5-forensics.log. See project-memory playbook forced-logout-incidents for full mechanism + triage protocol.

## BOB-125 — 6th forced-logout 2026-08-19 16:04:54 — RESOLVED via BOB-126 (root cause was pytest kill(-1,9))

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/incidents/2026-08-19-6th-forced-logout.md
**Severity:** Critical
**Created-By:** AI
**Assigned-To:** AI

Sixth forced-logout SIGKILL cascade on user@1000, 2026-08-19 16:04:54 CEST. First incident with kernel audit rules LIVE (installed 15:56). Prior 6 investigations misattributed the mechanism to PAM/Linger contradiction. Real root cause found by BOB-126: pytest calling kill(-1, SIGKILL) via MagicMock.__int__==1 → os.killpg(1, 9). Fix chain: ad4b46a + 502586c + bf01cf3 + 1b06858 + d7da1af + e389c29 + 0027dba. See docs/incidents/2026-08-19-6th-forced-logout.md.

## BOB-126 — 7th forced-logout 2026-08-19 16:43:43 — REAL ROOT CAUSE: pytest kill(-1,9) via MagicMock.__int__==1; §11.4.263 anchor + boba defense-in-depth

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/incidents/2026-08-19-6th-forced-logout.md
**Severity:** Critical
**Created-By:** AI
**Assigned-To:** AI

Seventh forced-logout SIGKILL cascade. Kernel audit trail: audit[399861] syscall=62 a0=ffffffff a1=9 comm=pytest exe=/usr/bin/python3.14. Root cause: tests/unit/merge_service/test_deadline_tunable.py::test_deadline_hit_flag_true_when_readline_times_out created AsyncMock without setting mock.pid as int. _search_public_tracker called os.killpg(os.getpgid(proc.pid), SIGKILL). MagicMock.__int__ defaults to 1, so os.getpgid(1)==1 → os.killpg(1, SIGKILL) → glibc → kill(-1, SIGKILL) = SIGKILL every UID-1000 process. Bug existed since 2026-04-24. FIX 3-layer: (1) boba ad4b46a search.py int-guard + test hardening + §11.4.115 RED regression guard. (2) constitution 502586c universal §11.4.263 anchor covering Python/Go/Rust/Bash/C. (3) boba bf01cf3 pointer bump. Verified: 863/863 unit PASS + 14/14 Go race PASS + no 8th incident.

## BOB-071 — RD2-01: guard-forbidden-commands.sh hook has live reproducible substring carrier false-positive

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-01, P2] During this investigation the command echo === systemd system-level (may need no sudo for list) === was BLOCKED by the PreToolUse hook with BLOCKED — §6.U no-sudo, because the guard does a substring match for sudo against the ENTIRE command line, including inside an unrelated echo string (need no sudo for list). Exact §11.4.201 carrier-false-positive class GA-24 already documented for a different file — now independently reproduced live, proving structural pattern in guard matching approach not a one-off content gap. Fix: guard needs word-boundary / shell-token-aware matching (or restrict sudo/su check to actual command-invocation position) rather than an unanchored substring grep across the whole line, mirroring fix direction scoped for GA-24 (EXCLUDE_PATHS is band-aid per-file; root cause is matching strategy itself). Priority: P2 (annoying, self-correcting via retry, but real false-positive class that will keep recurring). Composes with RD2-36 (canonical remediation).

## BOB-127 — Task 8 audit: 2 tests fired real killpg/getpgid on hardcoded PIDs (fixed 8bedc5a)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-127/task-8-syscall-audit.md
**Severity:** Low

Follow-up to BOB-126 systematic sweep. Task 8 audit surfaced 2 test cases in tests/unit/merge_service/test_public_tracker_subprocess_timeout.py that set explicit int mock.pid (12345, 1111) satisfying the production BOB-126 int-guard, but did NOT patch os.killpg/os.getpgid so the real syscalls fired against hardcoded non-owned PIDs. Low collision probability on typical host, but section 11.4.263(C) hygiene violation in the exact file authored to guard against host-wide kills. FIX at 8bedc5a: added patch.object(_search.os, getpgid) + patch.object(_search.os, killpg) to both tests matching sibling test_process_group_kill_called_on_deadline pattern. 6/6 tests still PASS. Report: docs/qa/BOB-127/task-8-syscall-audit.md. Recommended gate CM-TEST-KILLPG-PATCHED-WHEN-REAL-PID tracked as separate followup.

## BOB-132 — qbittorrent-proxy post-recovery: unhealthy — connection refused to qbittorrent sidecar on localhost:7185

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-133/recovery.md
**Severity:** High

After BOB-131 recovery, qbittorrent-proxy container reports 'unhealthy' due to Connection refused reaching qbittorrent sidecar on localhost:7185. Separate from BOB-129 (slowapi) and BOB-131 (conmon crash). Networking issue: qbittorrent-proxy expects to reach qbittorrent WebUI on localhost:7185 (container-internal port), but connection refused. Investigation: (a) is qbittorrent listening on 7185 inside its container? podman exec qbittorrent ss -tlnp shows...? (b) is the docker-compose network topology correct post-recovery? (c) was this always broken or a regression? Not self-healing during BOB-129 subagent session. Blocks live tracker downloads which route through the proxy.

## BOB-133 — CRITICAL: fleet-wide container dead-but-healthy — podman stale-cache masks service outage

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-133/recovery.md
**Severity:** Critical

All 7 boba service ports DEAD: 7185 (qbittorrent WebUI), 7186 (proxy), 7187 (merge_service), 7188 (webui-bridge), 7189 (boba-jackett), 9117 (jackett), 8080. Podman reports all containers 'running/healthy' but /proc/<pid> is absent for qbittorrent (pid 29972), jackett (pid 30021), boba-jackett (pid 31025). Stale-healthcheck class defect §11.4.180 masked service outage. §11.4.201(6) FALSE-NULL: 'healthy' status is not evidence of aliveness. Discovery-channel escape (§11.4.238): only surfaced via BOB-129 subagent's honest side-observation + orchestrator's live-port probe — should have been caught by continuous container aliveness monitoring. Blocks §11.4.185 manual QA (service isn't running for operator to test). Recovery: ./start.sh --recreate per CLAUDE.md Hard Stop #3 orchestrator-only contract.

## BOB-130 — Badge-test timeout deterministic — synced_fixtures fixture 93s vs --timeout=60

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-130/summary.txt
**Severity:** Low

Task 7 audit surfaced 3 pytest-timeout kills on tests/unit/test_compute_badges_script.py::TestComputeBadgesCheckModePolarity as UNCONFIRMED artifact. Task #110 verification REFUTED that hypothesis. All 3 test phases (baseline, nice-19, nice-19+parallel) timed out identically at 182-183s wall-clock (6 passed, 3 errors — deterministic, load-independent). Root cause via standalone timing: the synced_fixtures fixture (function-scoped) shells out scripts/compute-badges.sh in full-regeneration mode (pytest --collect-only across 5356 tests + vitest list --run) which is CPU-bound at 93.14s (203% CPU). Project default --timeout=60 in pyproject.toml is exceeded every invocation. Fix options per subagent report: (a) @pytest.mark.timeout(240) on TestComputeBadgesCheckModePolarity, (b) cache synced_fixtures across the 3 consumer tests (currently function-scoped to work around a pinned-pytest fixture-finalizer bug). Full evidence: .superpowers/sdd/task7-badge-timeout-verification.md

## BOB-117 — rutracker login diag still uses forbidden §11.4.6 'likely' vocabulary + wrong error_type (unfixed sibling of nnmclub fix)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-117/closure-evidence.md
**Severity:** High
**Created-By:** AI

rutracker login diag still uses forbidden §11.4.6 'likely' vocabulary + wrong error_type (unfixed sibling of nnmclub fix)

## BOB-076 — RD2-09: submodules/jackett fork 1 commit behind upstream (informational)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-076/closure-evidence.md
**Severity:** Low

RD2-09: submodules/jackett fork 1 commit behind upstream (informational)

## BOB-091 — RD2-26: Relocate mocked SearchOrchestrator tests to unit/ + author real-service replacements (closes GA-14/15/16)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-091/closure-evidence.md
**Severity:** High

RD2-26: Relocate mocked SearchOrchestrator tests to unit/ + author real-service replacements (closes GA-14/15/16)

## BOB-138 — qbittorrent-proxy health check probes only 7186, so a dead 7187 merge service reports healthy forever

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-138/closure-evidence.md
**Severity:** High
**Created-By:** Claude

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-20T14:47:35Z
**Reported-By:** Claude

**What (the report, verbatim):**
The qbittorrent-proxy container serves TWO ports from one process -- 7186 (download
proxy) and 7187 (merge service) -- but its health check probes ONLY 7186:

  docker-compose.yml:214
    test: ["CMD-SHELL", "python -c \"import urllib.request;
            urllib.request.urlopen('http://localhost:7186/', timeout=5)\" || exit 1"]

So when 7187 dies the container reports "healthy" indefinitely. Measured
2026-08-20: `podman ps` showed "Up 4 hours (healthy)" while 7187 had been
returning nothing for roughly two hours (see the sibling wedge item).

This is the §11.4.201 defect class exactly: the guard asserts a PROXY signal (one
port answers) instead of the REAL condition (every port this container serves
answers). A false-negative health pass is a §11.4 PASS-bluff at the orchestration
layer -- an operator, an orchestrator restart policy, and any dependent service's
`depends_on: service_healthy` all read "healthy" while the product's primary
capability is dead.

The asymmetry is visible in the same file: the Go variant's health check at
docker-compose.yml:129 DOES probe 7187 (`curl -sf http://localhost:7187/health`).
The Python container -- which serves both ports -- checks only the one that
happened to stay up.

Note also that the two checks probe different things: line 129 uses /health, line
214 uses /. Whichever endpoint is used, the check must cover 7187.

FIX DIRECTION: the health check must probe every port the container serves, and
fail if ANY of them fails. Root cause here IS established (the check does not
cover 7187), independent of WHY 7187 died -- so this is separately fixable and
does not wait on the wedge investigation.

DISCOVERY CHANNEL (§11.4.238): found by hand-probing during an unrelated
investigation, not by automated QA. Coverage escape: no automated check asserts
that a container's health check covers every port that container publishes.

**Affected scope / file-scope manifest:**
docker-compose.yml (qbittorrent-proxy healthcheck, line ~214)

**Reproduction / context:**
Wedge or stop the 7187 listener while leaving 7186 up, then observe 'podman ps' still reporting (healthy). Directly: curl --max-time 6 localhost:7186/ -> 200 while curl --max-time 6 localhost:7187/ -> 000, container status 'healthy'.

**Acceptance criteria:**
The qbittorrent-proxy health check fails when 7187 is unreachable and passes when both ports answer. Guard: an automated check asserts every published port of a compose service appears in that service's health check. Evidence: health check observed FAILING against a container with a dead 7187 and PASSING with both ports live (both directions, §11.4.201).

## BOB-142 — SearchRequest fields were unbounded, so one request could amplify into a 43-tracker fan-out carrying arbitrary payload

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-142/closure-evidence.md
**Severity:** High
**Created-By:** Claude

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-20T15:02:34Z
**Reported-By:** Claude

**What (the report, verbatim):**
Every string and list field on SearchRequest except `limit` was UNBOUNDED:

  query:       min_length=1, NO max_length
  category:    NO max_length
  sort_by:     NO max_length
  sort_order:  NO max_length
  trackers:    NO max_length (list)

`limit` already carried ge=1/le=100, so the model had the bounding idiom -- it
simply was not applied to the other fields.

WHY THIS IS AN AMPLIFICATION SURFACE, NOT A TIDINESS ISSUE: POST /api/v1/search
fans ONE request out to ~43 tracker plugins. An unbounded field means one cheap
inbound request becomes N expensive upstream requests, each carrying
attacker-controlled payload. Rate limiting (BOB-111) does NOT close it: a client
staying inside its allowance can still send a multi-megabyte query, and the
per-request COST is the problem here, not the request RATE. The two controls are
complementary; neither substitutes for the other.

Verified on the live service BEFORE the fix: a 100,000-character query was
accepted and dispatched.

BOUNDS ARE EVIDENCE-BASED, NOT TASTE. Measured across the repo 2026-08-20: the
longest legitimate query in any test or source is 14 chars ("boba-111-probe");
the longest category is "boundary-max-length-url" (23); there are 43 managed
plugins. Chosen limits leave generous headroom over observed usage while removing
the unbounded tail: query 256, category 64, sort_by/sort_order 32, trackers 64
entries.

**Affected scope / file-scope manifest:**
download-proxy/src/api/routes.py (SearchRequest), tests/security/test_search_request_bounds.py

**Reproduction / context:**
POST /api/v1/search with {"query": "A"*100000} against the pre-fix service: accepted (HTTP 200) and dispatched to the tracker fan-out. Same for {"trackers": ["t"]*10000}.

**Acceptance criteria:**
Oversized values are refused with HTTP 422 AND realistic values still return HTTP 200 (§11.4.201 both directions), proven against the live service over real HTTP.

## BOB-140 — Upstream the healthcheck-covers-served-ports gate into constitution/scripts/gates/ and thin boba's copy to a delegator (§11.4.177)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-140/closure-evidence.md
**Severity:** Medium
**Created-By:** Claude

**Reported-Via:** §11.4.202 reporting directive `task` on 2026-08-20T14:56:38Z
**Reported-By:** Claude

**What (the report, verbatim):**
scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh (landed with BOB-138)
implements a rule every project under this constitution needs: a container health
check MUST cover every port its service serves, because a check probing a subset
asserts a proxy signal instead of the real condition (§11.4.201).

Its detection logic already carries ZERO boba literals -- both the compose file and
the served-port manifest are inputs, defaulted from the project root. It therefore
belongs in constitution/scripts/gates/ and should be consumed BY REFERENCE by a thin
boba delegator holding only boba's scope DATA, exactly as
check_cm_killpg_pgid_guard.sh was restructured (§11.4.177 / §11.4.28 / §11.4.74).

WHY IT WAS NOT UPSTREAMED IMMEDIATELY: a concurrent agent was editing
constitution/scripts/gates/ at the time (upstreaming the killpg engine). Two writers
in one submodule directory risks losing work, so this was deferred deliberately and
filed rather than silently skipped (§11.4.197). This is a known-and-tracked
deviation from §11.4.177, not an oversight.

Two properties MUST survive the move:
  1. FAIL when zero services were checked -- a quiet zero from a blind instrument is
     indistinguishable from a clean tree (§11.4.201(6)).
  2. FAIL when python3+PyYAML is unavailable, rather than skipping, for the same
     reason.

Acceptance: the engine lives in constitution/scripts/gates/, boba's copy is a thin
delegator carrying only its manifest path, both directions still verified (a service
missing a served port FAILs; a fully-covered set PASSes), and no detection logic is
duplicated between the two.

**Affected scope / file-scope manifest:**
scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh, config/served_ports.yaml, constitution/scripts/gates/

**Reproduction / context:**
n/a — known deviation recorded at landing time, not a discovered defect.

**Acceptance criteria:**
Detection engine in constitution/scripts/gates/; boba ships a thin delegator with scope DATA only; zero duplicated detection logic; both polarity directions still verified after the move.

## BOB-139 — SSE _client_gone() swallows every exception into 'client still connected', so a raising disconnect probe streams forever (fail-open)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-139/closure-evidence.md
**Severity:** Medium
**Created-By:** Claude

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-20T14:47:35Z
**Reported-By:** Claude

**What (the report, verbatim):**
Both SSE generators in download-proxy/src/api/streaming.py (lines ~153 and ~351)
guard their `while True` loop with this helper:

    async def _client_gone() -> bool:
        if request is None:
            return False
        try:
            return await request.is_disconnected()
        except Exception:
            return False

The bare `except Exception: return False` means: if the disconnect check itself
ever raises, the generator concludes the client is STILL CONNECTED and keeps
streaming -- forever. That is fail-OPEN on the only condition that terminates the
loop, in a code path that holds a socket and a task.

This is the §11.4.252 fail-closed rule inverted: the safe default for "I cannot
determine whether the client is gone" is to treat it as gone and stop streaming
(the client can always reconnect -- SSE is designed for that), not to keep an
unbounded stream alive on an unresolvable signal.

It is also a §11.4.201(6) false-null: a raising probe and a genuinely-connected
client return the identical `False`, so the loop cannot distinguish "client is
here" from "I am blind".

Corroborating observation (2026-08-20): seven sockets held by the merge-service
process were sitting in CLOSE-WAIT with unread request bytes -- clients had hung
up and the server had not noticed. That is consistent with (though not yet proven
to be caused by) this fail-open, and it is the reason this is filed rather than
left as a style note.

HONEST BOUNDARY: not proven to be the cause of the 7187 wedge -- both loops DO
call `await asyncio.sleep(poll_interval)`, so they yield and would not busy-spin.
This is filed as a real defect on its own merits (an unbounded stream on an
unresolvable signal, plus a leaked socket and task), not as the wedge's root cause.

**Affected scope / file-scope manifest:**
download-proxy/src/api/streaming.py (_client_gone at ~line 153 and ~line 351)

**Reproduction / context:**
Monkeypatch Request.is_disconnected to raise, open an SSE stream, disconnect the client, and observe the generator never terminates (the loop keeps yielding and the task is never reclaimed).

**Acceptance criteria:**
A raising disconnect probe terminates the stream (fail-closed per §11.4.252) rather than continuing it, AND a normally-connected client still streams uninterrupted (§11.4.201 both directions). Guard: a unit test for each SSE generator covering raise -> terminate and connected -> continue.

## BOB-147 — Triage all 36 §11.4.252 fail-open hits: 9 real defects fixed, 14 correct idioms, 14 vendored

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/fail-open-triage-20260820/triage.md
**Severity:** Medium
**Created-By:** Claude

**Reported-Via:** §11.4.202 reporting directive `task` on 2026-08-20T16:15:03Z
**Reported-By:** Claude

**What (the report, verbatim):**
All 36 §11.4.252 fail-open hits classified with zero left unclassified, 9 real
defects fixed RED-first, 2 stale gates reconciled per §11.4.120, and the phantom
count in invariant 39 removed.

  (A) real defect      9   fixed
  (B) correct idiom   14   single-capability, or the primary failure is already
                           logged/re-raised
  (C) vendored        14   upstream headers + byte-identical community/ twin

Fixed: env_loader.py:30, iptorrents.py:77, rutor.py:303/324/121,
rutracker.py:349/370, helpers.py:220, anilibra.py:75, plus
community/anilibra.py:75 (the §11.4.251 twin).

Evidence: docs/qa/fail-open-triage-20260820/{triage.md, test_fail_open_regression.py,
red_run.txt, green_run.txt}. RED 8 failed/18 passed -> GREEN 29 passed; each fix
reverted makes its own guard FAIL; a CONST-XII no-op stub the author did not
write keeps the structure but blanks the diagnostic and the guard STILL fails.

Two follow-ups are tracked separately and are NOT part of this item:
  BOB-146 — the constitution detector undercounts by 29% (30 vs 42 AST).
  Promotion of invariant 39 to BLOCKING — needs a §11.4.224(E) fence over the
  remaining 30, and the 10 unowned missed sites triaged first, or the fence is
  written against an undercount. Operator's call (§11.4.66).

**Affected scope / file-scope manifest:**
plugins/*.py, plugins/community/anilibra.py, download-proxy/src/api/theme_state.py, download-proxy/src/merge_service/scheduler.py, tests/unit/test_plugin_rutor.py, tests/unit/test_plugin_rutracker.py, scripts/pre_build_verification.sh

**Reproduction / context:**
n/a — planned triage of an advisory gate's output, not a discovered defect.

**Acceptance criteria:**
Every hit classified; bucket-A fixes RED-first with paired mutations; stale gates reconciled not fake-passed; the count reflects findings not the gate's summary line.

## BOB-081 — RD2-14: Author CONTINUATION.md Session 15 entry (currently 53 days / 24+ commits behind HEAD)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/CONTINUATION.md
**Severity:** High

RD2-14: Author CONTINUATION.md Session 15 entry (currently 53 days / 24+ commits behind HEAD)

[BOB-136 adoption audit 2026-08-21 -> Completed] e335dde. docs/CONTINUATION.md is at Revision 27, Last modified 2026-08-20T12:17:48Z, carrying a themed TERMINAL STATE entry over the 45 commits df7bc41->e0d60ab. Every element of this item's acceptance is present (Session-N entry by theme + Revision + Last modified). The entry itself states 'This entry closes BOB-081'. The commit additionally CORRECTED this ticket's own premise: the filed '53 days / 24+ commits' staleness figure was measured to be 45 commits / ~19 hours.

## BOB-083 — RD2-16: Regenerate browser_extension/features/codegraph Status.md + Summary/HTML/PDF siblings

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/codegraph/Status_Summary.md
**Severity:** Medium

RD2-16: Regenerate browser_extension/features/codegraph Status.md + Summary/HTML/PDF siblings

[BOB-136 adoption audit 2026-08-21 -> Completed] e335dde regenerated all three Status doc sets named here: browser_extension Status 15->16 + Summary 3->4, features Status 8->9 + Summary 7->8, and docs/codegraph/Status_Summary.md CREATED (it did not exist at all — a real §11.4.56 gap). docs/codegraph/Status.md was already current from e6162f7 (BOB-075 staleness refresh) so it needed no regeneration. HTML/PDF siblings landed in the same commit.

## BOB-086 — RD2-19: Fix BOB-009/BOB-010 evidence_path + backfill item_history for 56 silent closures

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-086/backfill_evidence
**Severity:** Medium

RD2-19: Fix BOB-009/BOB-010 evidence_path + backfill item_history for 56 silent closures

[BOB-136 adoption audit 2026-08-21 -> Completed] f78f383 delivers both halves with measured before/after: item_history 106->162 rows, 66->122 distinct atm_ids, 56->0 silent Fixed items, 56 backfill rows; and BOB-009/BOB-010 commit_ref=7d243cc + closure_date=2026-08-06 set. Each of the 56 carries a per-item captured-evidence artefact under docs/qa/BOB-086/backfill_evidence/ that resolves to a real file. Validator reported OK post-change. 0268771 landed the twin exports.

## BOB-089 — RD2-24: RED-first tests for start.sh reload_python/reload_plugins/recreate_stack (closes test-half of GA-27)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-089/GREEN_all_three.log
**Severity:** High

RD2-24: RED-first tests for start.sh reload_python/reload_plugins/recreate_stack (closes test-half of GA-27)

[BOB-136 adoption audit 2026-08-21 -> Completed] 2667be6 authored tests/integration/test_start_sh_reload_paths.py driving all three subcommands through the real invocation path against a live rootless podman fleet, each asserting a runtime property read from the target per §11.4.115(F): --reload-python (marker __pycache__ gone AND StartedAt bumped AND container id unchanged), --reload-plugins (StartedAt bumped, id unchanged, marker NOT auto-copied), --recreate (container id CHANGES — the discriminator). §11.4.115 RED captured at docs/qa/BOB-089/RED_reload_python_stub.log by stubbing reload_python()'s cache-clear to a no-op; GREEN at docs/qa/BOB-089/GREEN_all_three.log (105s, all PASS). e335dde added 4 further bash suites (32 assertions, zero container side effects).

## BOB-096 — RD2-31: Extend qBitTorrent-go jackett_db_test.go with real process-kill/resource-exhaustion fault injection

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-096/GREEN_after_restore.log
**Severity:** Medium

RD2-31: Extend qBitTorrent-go jackett_db_test.go with real process-kill/resource-exhaustion fault injection

[BOB-136 adoption audit 2026-08-21 -> Completed] 76d6b1f closes the exact gap named here — this item asks for resource-exhaustion injection on top of jackett_db_test.go's existing concurrency-only coverage. Added TestChaos_FileDescriptorExhaustion (bounded os.Pipe() FD pressure capped at min(RLIMIT_NOFILE/4,512) per §12.6) and TestChaos_ConcurrentContextCancelWrite. §11.4.115 RED-first: a phantom-name mutation produced 'confirmed-write KILL_PHANTOM lost after cancel'; restored, GREEN re-captured under identical race conditions. Race-clean under go test -race -count=3. Process-kill SIGKILL coverage already existed and still passes.

## BOB-098 — RD2-34: Parametrize 20 hardcoded /Volumes/T7 paths in helixqa banks with PROJECT_ROOT (closes GA-23)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** challenges/scripts/no_hardcoded_volumes_t7_challenge.sh
**Severity:** Medium

RD2-34: Parametrize 20 hardcoded /Volumes/T7 paths in helixqa banks with PROJECT_ROOT (closes GA-23)

[BOB-136 adoption audit 2026-08-21 -> Completed] 5670def parametrized the last remaining literal with ${HELIX_OTA_PROJECT_ROOT} (upstream HelixDevelopment/qa@c19ce2b, submodule pointer bumped) and shipped a §11.4.115-shape regression guard. Verified independently this session: grep -rn /Volumes/T7 submodules/helixqa/banks/ returns exit 1 / zero hits. Note the count in this item's title (20) had already been reduced by earlier waves; 5670def closed the final one, and the acceptance observable — zero hardcoded host-mount literals in the banks — now holds.

## BOB-105 — §11.4.238 followup: mechanical §11.4.227(B) anchor-block-integrity check

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** challenges/scripts/anchor_block_integrity_challenge.sh
**Severity:** Medium
**Created-By:** Claude

§11.4.238 followup: mechanical §11.4.227(B) anchor-block-integrity check

[BOB-136 adoption audit 2026-08-21 -> Completed] 7cd080c delivers exactly what this item asks for: scripts/anchor_block_integrity_check.sh enforcing §11.4.227(B) (exactly-once per anchor per file, lockstep sha256 divergence across the mirror set, lockstep gap, DUPLICATE-OR-COLLISION for one NNN heading two mandates, plus a §11.4.201(6) BLIND-EXTRACTOR guard and full dotted-id extraction so §11.4.10.A never prefix-matches §11.4.10), driven by a consumer-owned config per §11.4.35, with a §11.4.107(10) self-validated harness at challenges/scripts/anchor_block_integrity_challenge.sh over 5 fixtures (golden-good, negative-control, golden-bad-duplicated, golden-bad-diverged, golden-bad-collision). The 176 findings it then produced were triaged separately in bf985ab and are a distinct operator-owned §11.4.66 decision, not part of this item's acceptance.

## BOB-113 — BOB-074 followup: add wrk to dev tooling for DDoS/load challenges

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-112/wrk_evidence.log
**Severity:** Low
**Created-By:** Claude

BOB-074 followup: add wrk to dev tooling for DDoS/load challenges

[BOB-136 adoption audit 2026-08-21 -> Completed] c7dfdde landed scripts/install-dev-tools.sh (rootless-by-default per §11.4.161, --allow-sudo opt-in, Linux+macOS, wrk/hey/siege). Its 'Closes BOB-113 (code layer)' hedge is resolved by e2a2e3e, which records 'bash scripts/install-dev-tools.sh run live' and then used the resulting wrk for a real 4t/100c/30s load test with latency percentiles (baseline 97.1% timeouts / p99 2.67s vs post-fix 0.0% / 27049 req/s / p99 19.89ms). Verified this session: wrk resolves on PATH at /home/milosvasic/bin/wrk. The acceptance — a modern HTTP benchmarking tool with latency-percentile histograms available out of the box — is met and demonstrated in use.

## BOB-070 — RD2-41: pre-build mutation-marker scan carrier false-positive silently defeats entire pre-build gate

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** challenges/scripts/mutation_marker_scan_polarity_challenge.sh
**Severity:** High

RD2-41: pre-build mutation-marker scan carrier false-positive silently defeats entire pre-build gate

[BOB-136 adoption audit 2026-08-21 -> Fixed] 6e3b74a implements this item's stated 'Fix needed' — the marker scanner is now line-anchored with a guardrails:allow escape, killing the carrier false-positive class at BOTH sites the item names (pre_build_verification.sh invariant 23 and pre_code_review.sh). Proven by a §11.4.107(10) polarity harness over three fixtures: real-mutation.py -> HIT, carrier-comment.py -> NOHIT, carrier-string.py -> NOHIT. The practical impact this item flagged (the entire pre-build gate aborting before invariant 17 was ever reached) is resolved: pre_build_verification.sh reported 27/0 GREEN with INV23 PASS on a clean tree.

## BOB-099 — RD2-36: Fix guard-forbidden-commands.sh substring-match false-positive class + add const033-poweroff-signal-triage carrier to EXCLUDE_PATHS

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** constitution/scripts/hooks/test_guard_forbidden_commands.sh
**Severity:** Medium

RD2-36: Fix guard-forbidden-commands.sh substring-match false-positive class + add const033-poweroff-signal-triage carrier to EXCLUDE_PATHS

[BOB-136 adoption audit 2026-08-21 -> Fixed] The carrier-vs-thing class fix landed at constitution commit ee4d751 with the pointer bumped in 60dc3ba, covered by a 32/32 suite (11 golden-TRUE + 16 golden-FALSE carriers + 2 escape-hatch + 2 host-power). Verified this session: constitution/scripts/hooks/guard-forbidden-commands.sh carries token/word-boundary matching. Corroborated independently — BOB-071 (RD2-01, the same live-reproducible false positive) was closed as duplicate-of BOB-099 in 1685a2f citing this fix. The EXCLUDE_PATHS stopgap this item mentions was deliberately not added and is moot: the item itself specified 'word-boundary/token-aware matching, not another EXCLUDE_PATHS band-aid', and the class fix supersedes the stopgap.

## BOB-118 — README.md python-tests badge claims 585 passing; pytest --collect-only measures 5235 (9x stale/wrong)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/TESTING.md
**Severity:** High
**Created-By:** AI

README.md python-tests badge claims 585 passing; pytest --collect-only measures 5235 (9x stale/wrong)

[BOB-136 adoption audit 2026-08-21 -> Fixed] Both halves of this item's fix direction are met. f517eaa landed scripts/compute-badges.sh deriving counts from machine-readable sources (pytest --co, vitest --list, gate exit codes) per §11.4.259, with unit coverage and a §11.4.18 companion doc; a6f36fa then caught and fixed a SECOND bluff in the same file (challenges/pre-build badges printed a hardcoded 'cross-checked, matches existing badge' line while never being compared or updated — stale by 7 and 14) and widened the guard to every machine-derived badge. Verified this session: README.md now reads tests-5437 collected and tests-371 collected, and docs/TESTING.md line 327 carries the authoritative 5437 with its derivation command — so the cited authoritative source can now actually corroborate the badge, which was the specific defect reported.

## BOB-123 — 4th forced-logout incident 2026-08-19 00:37:11 — PAM/Linger contradiction breakthrough (retro-registered: id used in 6 commits with no tracker row)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/incidents/2026-08-19-4th-forced-logout.md
**Severity:** Critical
**Created-By:** Claude

RETRO-REGISTRATION, filed 2026-08-21 by the BOB-136 closure-seam adoption sweep. This id was declared in SIX commits (6c0b785, d635885, a9c2af9, 69de436, 8278a42, ad4b46a) yet NEVER had a row in docs/workable_items.db — verified against the last 8 committed revisions of the DB, all returning 0 rows for it. It is not a typo: the id was used consistently across multiple days and three rounds of §11.4.209 Fable review, and it slots exactly into the incident-chain numbering (BOB-116=2nd, BOB-120=3rd, THIS=4th on 2026-08-19 00:37:11, BOB-124=5th, BOB-125=6th, BOB-126=7th). The row is filed now to make the history-declared id resolvable; it is NOT backdated and does not claim the work was tracked at the time — the missing row is itself the §11.4.202/§11.4.210 intake escape being recorded.

WHAT LANDED UNDER THIS ID. 6c0b785 filed the 4th forced-logout incident doc (docs/incidents/2026-08-19-4th-forced-logout.md, with .html/.pdf/.docx twins). d635885 then implemented the out-of-scope system.slice watchdog for user@1000 SIGKILL forensics, iterated to a §11.4.134 zero-finding verdict across three review rounds (a9c2af9 round 1, 69de436 round 2 N1-N6, 8278a42 round 3 residuals).

RESOLUTION. The defect is closed by the BOB-126 root cause, not by this item's own remediation: ad4b46a ('CRITICAL — merge_service killpg guard closes 7-forced-logout chain') enumerates the seven incidents it closes and lists 'BOB-123 2026-08-19 00:37:11' explicitly among them. The root cause was pytest kill(-1, SIGKILL) reaching every UID-1000 process via MagicMock.__int__ == 1, generalised into universal anchor §11.4.263. This mirrors exactly how siblings BOB-124/BOB-125/BOB-126 were closed, each carrying its own incident doc as evidence.

STILL OPEN ELSEWHERE, DELIBERATELY NOT CLOSED HERE. The watchdog work-stream that also carried this id is tracked by BOB-121 ('External watchdog for the forced-logout architectural gap'), currently Ready for testing and explicitly NOT CLOSED — two operator decisions are owed and it remains UNTESTED AGAINST A REAL FORCED LOGOUT. The architectural gap BOB-120 names is likewise still Queued. Closing this row closes the 4th INCIDENT, nothing more.

## BOB-128 — killpg-carrier collision between CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID and sibling CM-KILLPG-PGID-GUARD (retro-registered: id used in 3 commits with no tracker row)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh
**Severity:** Medium
**Created-By:** Claude

RETRO-REGISTRATION, filed 2026-08-21 by the BOB-136 closure-seam adoption sweep. Commit d9955d6 ('BOB-127/128/129/130/131/132/133/135 registered/closed + regen exports') ASSERTS this id was registered, but it never was: BOB-127, BOB-129, BOB-130, BOB-131, BOB-132, BOB-133 and BOB-135 all have rows and BOB-128 does not, and no committed revision of docs/workable_items.db has ever contained it. The commit message is therefore inaccurate for exactly one of the eight ids. The row is filed now to make the history-declared id resolvable; it is NOT backdated.

WHAT THE DEFECT WAS. Part of the BOB-126 fallout. The new §11.4.263 static gate CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID collided with its sibling CM-KILLPG-PGID-GUARD: each matched the other's killpg literals as a carrier — the same carrier-vs-thing false-positive class as BOB-070 and BOB-099, this time between two freshly-landed gates.

WHAT LANDED. fa0fe63 added the gate plus its meta-test; be36f32 fixed the carrier collision; 29c33de wired the gate as pre-build invariant 29. Verified this session in the current tree: scripts/pre_build_verification.sh declares invariant 29 at lines 135 and 948-970, the gate script scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh is present and executable, and its meta-test exists at tests/pre_build/test_check_cm_test_mock_pid_patched_when_real_pid.sh. docs/CONTINUATION.md Rev 27 independently records this as 'BOB-128 (killpg-carrier guard collision with the new §11.4.263 gate — fixed be36f32; CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID landed as pre_build invariant 29)'. Note the invariant's own in-file comment credits BOB-127 rather than BOB-128 — a cosmetic mis-attribution, not a functional gap.

## BOB-084 — RD2-17: Reconcile BOB-008 DB/MD body drift via the workable-items tool

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-084/closure-evidence.md
**Severity:** High

RD2-17: Reconcile BOB-008 DB/MD body drift via the workable-items tool

## BOB-079 — RD2-12: Retroactive attributed history notes for GA-18/21/22/25/26/27 changes (never rewrite published history)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/history/BOB-079-attributed-auto-commit-history.md
**Severity:** Medium

RD2-12: Retroactive attributed history notes for GA-18/21/22/25/26/27 changes (never rewrite published history)

## BOB-092 — RD2-27: Remove test_live_stack_evidence.py:265 nnmclub SKIP-on-404 fallback + verify live 200 (closes GA-13)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-092/closure_run_20260821.log
**Severity:** Medium

RD2-27: Remove test_live_stack_evidence.py:265 nnmclub SKIP-on-404 fallback + verify live 200 (closes GA-13)

## BOB-136 — Closure seam does not bind: 4 tracker rows found stale in one sweep, and workable-items diff is blind to body_md drift

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-136/closure-evidence.md
**Severity:** High

Closure seam does not bind: 4 tracker rows found stale in one sweep, and workable-items diff is blind to body_md drift

## BOB-087 — RD2-20: Wire docs_chain / commit-seam sync hook per §11.4.106(F) so DB writes cannot land without MD mirror

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-20, P0] Wire (or fix) the docs_chain / commit-seam sync hook per §11.4.106(F) so a docs/workable_items.db write can never again land without its MD mirror in the same commit — this is the mechanical fix that prevents Root Cause 2 from recurring, not just a one-time catch-up. Priority: P0.

**Progress 2026-08-21:** MEASURED against all three seams §11.4.106(F) names, not one. COMMIT seam: COVERED — scripts/hooks/docs-sync-commit-seam.sh is invoked from scripts/commit-push-all.sh at BOTH commit call sites (the --scope branch and the git add -A branch) via _docs_sync_seam_check, after staging and before git commit, exiting 1 on refusal; there is no third path to git commit in that script. Proven in BOTH directions on temp copies with the real DB sha256 unchanged: an MD-side body edit is detected and named (self-test golden-bad, victim BOB-008), and a real engine DB write with the Markdown deliberately left stale is detected and named (golden-bad, BOB-084) — that second direction is the one the item's own text claims — while a clean tree stays silent (negative control, no §11.4.201(1) false positive). BUILD seam: COVERED — pre_build_verification.sh invariant 17 runs validate AND diff with --issues/--fixed passed explicitly (never the flagless form BOB-155 fixed), invariants 18/22 cover the export leg with a real-invocation assertion, invariant 24 runs the real docs_chain engine verify --all; RESIDUAL: no CHECK 3 equivalent there, so the build seam inherits diff's blindness to the body_md class (the BOB-136 class). CONSTITUTION-PULL seam: NOT COVERED — a grep for workable-items|docs-sync|docs_chain|11.4.106 returns 0 in BOTH constitution/scripts/post_update_hook.sh and scripts/verify-all-constitution-rules.sh, control-needled so the zeros are sight not blindness (needle 'skill' 38 hits, 'covenant_propagation_suite' 7 hits, negative control 0); of the 172 gates under constitution/scripts/gates/ only two mention the engines and both are anchor-literal presence gates that compare no DB against any Markdown, and config/constitution-sweep.conf adds no such check. So a constitution pull can be treated as canonical with the tracker never re-compared. REMAINS: wire the already-existing seam into scripts/verify-all-constitution-rules.sh BY REFERENCE (bash scripts/hooks/docs-sync-commit-seam.sh --files docs/Issues.md docs/Fixed.md docs/workable_items.db), reporting PASS/FAIL/SKIP-with-reason in the sweep's own vocabulary and never a silent pass on an absent tool — a wiring change, not a second implementation (§11.4.227). NOT DONE this round: that file sits outside the working brief's declared file scope, so the gap is named and the item stays open rather than the scope being exceeded (§11.4.6). EVIDENCE. docs/qa/BOB-087/seam-coverage-measurement.md.


## BOB-129 — Potential production slowapi/starlette defect flagged by Task 105 subagent

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** Medium

Task #105 subagent (fixing 9 slowapi test failures) reported honestly that the same slowapi/starlette incompatibility likely hits the production /search and /search/stream endpoints under real HTTP traffic — evidence: the FastAPI TestClient (which goes through the full ASGI middleware stack like real requests do) reproduces the same isinstance() failure pattern the 9 test failures exhibited. Not yet reproduced against the running boba stack because the qbittorrent-proxy container currently exposes no host ports (running on gluetun network stack). Recommended investigation: (1) confirm defect by triggering /search kickoff through gluetun network stack, (2) if reproduced, determine whether the fix belongs in production code (adding response: Response params) or a version pin (slowapi vs starlette compat) or a middleware refactor. §11.4.238 discovery-channel escape prevention: manual QA must NOT be the discoverer. §11.4.108 Layer 3 verification: needed on a clean deployment before any release.

## BOB-131 — qbittorrent-proxy podman conmon crash — pre-existing, surfaced during BOB-129 investigation

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** Medium

BOB-129 subagent found qbittorrent-proxy container DEAD mid-investigation (podman conmon crash). Recovery via ./start.sh --no-build worked. Pre-existing, unrelated to BOB-129 slowapi work but surfaced by it. Investigation needed: (a) how long was container dead before discovery? (b) what triggered the conmon crash? (c) is there a §11.4.144 always-follow / §11.4.128 always-record signal we should add to detect this class earlier? Post-recovery: container now unhealthy (see BOB-132). §11.4.238 discovery-channel escape: was originally found by a subagent investigating something else, not by dedicated container health monitoring.



**Closed 2026-08-21 — THE PREMISE OF THIS TICKET IS FALSE, and that is the finding.**

No `conmon` process crashed. This item conflated TWO UNRELATED EVENTS. Over the full 7.5-day journal retention the only conmon messages above warn are conmon REPORTING failures (`Failed to create container: exit status 1`, `Failed to write 137 to exit file`) — never crashing. A conmon crash would put conmon in a kernel segfault line; the only such line in a week is a `python3` one.

EVENT 1, once, 2026-08-20 17:56:26 CEST: `python3[314359]: segfault at 70 ... in libpython3.12.so.1.0`, with the container's own stdout ending mid-`"  File "` — the dumper died writing it. Proven at machine level rather than inferred: the kernel's `Code:` bytes at IP were byte-matched against the library INSIDE the running container (MATCH), decoding to `mov r14,[r12]` (frame->f_executable = NULL) then `mov rax,[r14+0x70]` (code->co_filename) -> fault; the preceding `lea` resolves to the literal `"  File "` with edx=7, its exact length and exactly the text the log truncated after. Self-healed in 0.03s via `restart: unless-stopped`. Zero recurrences since.

EVENT 2, the 14h06m43s absence: a HOST POWER-OFF (`systemd-logind: The system will power off now!`), container exited 0. `restart: unless-stopped` does not survive a power cycle, and `boba-stack.service` is linked but disabled.

ALL THREE LOOKALIKES EXCLUDED WITH EVIDENCE: cgroup OOM-kill (oom_kill 0, zero OOM lines in 7.5 days, flight recorder k_oom=0 across all 62 samples); cgroup memory-ceiling (REAL — memory.max=805306368 with 1584 memory.events in 48 min — but that is reclaim, not a kill, and cannot produce SIGSEGV); §12.12 thread exhaustion (ulimit -u 65536, peak 1559 = 2.4%, no EAGAIN / 'failed to create new OS thread' anywhere).

THE ACTIONABLE RESIDUAL IS SPLIT OUT AS BOB-157 (High): the crash vector is our OWN diagnostic — `download-proxy/src/main.py:135` calling `faulthandler.dump_traceback(all_threads=True)` — hitting upstream python/cpython#116008 / #128400, fixed and backported to 3.13/3.14 with NO 3.12 backport, on a container shipping 3.12.13. Still armed.

DELIVERED: `docs/guides/container-death-triage.md` (a 6-class decision table plus the three confusions above), `docs/incidents/2026-08-21-bob131-container-death-triage.md`, and `scripts/diagnostics/bob131_container_death_triage.sh` (TDD RED 7/8 -> GREEN 8/8, deterministic 5/5, both §1.1 mutations FAIL — collapsing oom_kill/ceiling breaks 5 fixtures including the negative control). The investigating agent caught its OWN selftest passing by race (an `awk '…; exit'` SIGPIPE) and fixed it before reporting.
## BOB-144 — /theme/stream calls the disconnect probe unguarded — fail-closed but via an uncaught traceback, inconsistent with the two SSE generators

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** Low
**Created-By:** Claude

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-20T15:53:57Z
**Reported-By:** Claude

**What (the report, verbatim):**
`/theme/stream` in download-proxy/src/api/routes.py:167 calls the disconnect probe
with NO guard at all:

    while True:
        if await request.is_disconnected():
            break

If that probe raises, the generator dies with an UNCAUGHT exception.

IMPORTANT — this is NOT the BOB-139 fail-open. The effect here is fail-CLOSED:
the stream stops, and the enclosing `finally: store.unsubscribe(queue)` still
runs, so the subscriber queue is released and nothing leaks. The outcome is
CORRECT; the manner is not.

What is wrong with it:
  - it terminates via an uncaught traceback rather than a clean SSE `close`
    event, so the client sees a truncated stream instead of a reason;
  - the failure is not logged as a probe failure, so a systematically raising
    probe would show up as recurring tracebacks with no diagnosis;
  - it is inconsistent with the two SSE generators in streaming.py, which after
    BOB-139 emit `event: close` with reason `disconnect_probe_failed` and log a
    warning. Three call sites of the same probe now behave two different ways.

The BOB-139 fix deliberately did not touch this file (ownership boundary,
§11.4.119), and flagged it honestly rather than fixing it out of scope.

Acceptance: /theme/stream uses the same probe-failure discipline as the
streaming.py generators — a clean close event with the `disconnect_probe_failed`
reason plus a logged warning — proven in BOTH directions (§11.4.201(1)): a
raising probe closes the stream cleanly AND a normally-connected client still
streams uninterrupted. Prefer reusing the shared helper introduced by BOB-139
rather than a third copy of the logic (§11.4.251).

Honest boundary (§11.4.6): the production probe-failure rate is UNKNOWN — nobody
has measured how often `is_disconnected()` actually raises. This is filed on the
inconsistency and the missing diagnosis, not on a measured incident rate.

**Affected scope / file-scope manifest:**
download-proxy/src/api/routes.py (~line 167, stream_theme)

**Reproduction / context:**
Monkeypatch Request.is_disconnected to raise, open /theme/stream, observe the generator dies with an uncaught traceback rather than emitting event: close with reason disconnect_probe_failed as streaming.py now does.

**Acceptance criteria:**
Same probe-failure discipline as streaming.py (clean close + disconnect_probe_failed reason + logged warning), verified both directions, reusing the BOB-139 helper rather than a third copy.

## BOB-145 — Fix the 7187 wedge: offload and/or memoise Deduplicator.merge_results so O(N^2) regex work stops blocking the asyncio event loop

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** High
**Created-By:** Claude

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-20T16:01:43Z
**Reported-By:** Claude

**What (the report, verbatim):**
BOB-137 established the root cause: Deduplicator.merge_results() is called as a
PLAIN SYNCHRONOUS CALL at merge_service/search.py:914 and therefore executes ON
the asyncio event-loop thread. While it runs, uvicorn's only loop runs no callback
— no accept, no read, no write — so port 7187 stops answering entirely. Measured
episodes of 9m37s and 5m56s, self-clearing, recurring under ordinary traffic.

This item is the FIX. BOB-137 is the diagnosis and stays separate per the
§11.4.102 Iron Law — the investigation deliberately applied no fix.

Three candidate directions, not yet chosen:

 (a) OFFLOAD — hand merge_results to a thread executor (asyncio.to_thread /
     run_in_executor). Smallest change, immediately unblocks the loop. Does NOT
     make the work cheaper, so a large enough merge still burns a core; and it
     introduces concurrency around self._last_merged_results and metadata, which
     must be checked for races before it is called safe.

 (b) MEMOISE — _normalize_name is called at FOUR sites per comparison, each
     running 5 re.sub, and _extract_identity_from_result twice more with a
     ~15-re.search chain. lru_cache has ZERO matches in that module today, so the
     seed's own normalisation is recomputed for every candidate. Caching the
     per-result normalisation is a large constant-factor win with no concurrency
     risk.

 (c) REDUCE THE COMPARISON SET — the O(N^2) shape itself (blocking/bucketing by a
     cheap key before pairwise comparison). Largest win, largest change, highest
     risk of altering dedup RESULTS — which would need its own correctness
     evidence, not just a speed measurement.

(b) then (a) is the likely order: (b) is risk-free and may alone bring the merge
under the threshold, and (a) guarantees the loop is never blocked regardless.

MANDATORY for whoever takes this:
 - RED FIRST (§11.4.43/§11.4.224): a test that FAILS on the current code by
   demonstrating the loop is blocked during a merge — e.g. assert a concurrent
   request to 7187 is served within a bounded time while a large merge runs. A
   pure speed benchmark is NOT the RED test; the defect is loop-blocking, not
   slowness.
 - BOTH POLARITIES (§11.4.201(1)): the loop stays responsive under a large merge
   AND dedup results are unchanged for the existing corpus. A fix that speeds up
   merging while changing which duplicates are detected is a different defect.
 - Use the existing instrument: scripts/diagnostics/bob137_soak.sh reproduced the
   wedge 22/26; it is the natural GREEN check.
 - Honest boundary carried from BOB-137: measured growth is SUPER-LINEAR but not
   fully quadratic at N<=400 (2.4-3.4x per doubling vs 4.0). Worst case is
   quadratic BY CODE STRUCTURE. Do not cite "measured N^2".

**Affected scope / file-scope manifest:**
download-proxy/src/merge_service/search.py:914, download-proxy/src/merge_service/deduplicator.py

**Reproduction / context:**
bash scripts/diagnostics/bob137_soak.sh — reproduced the wedge in 22/26 probes (7187 dead, 7186 alive throughout).

**Acceptance criteria:**
Port 7187 answers within a bounded time while a large merge runs (loop never blocked), AND dedup results are unchanged for the existing corpus. Proven with the soak repro flipping from 22/26-dead to 0/N-dead, plus a dedup-equivalence check.

## BOB-146 — Constitution §11.4.252 detector undercounts by 29% (30 vs 42 AST ground truth) — 4 distinct blind spots make its output a floor, not a census

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** High
**Created-By:** Claude

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-20T16:10:50Z
**Reported-By:** Claude

**What (the report, verbatim):**
The constitution's §11.4.252 detector (constitution/scripts/gates/
cm_dangerous_combination_fail_closed.sh) UNDERCOUNTS by 29%. Measured against an
independent AST instrument (structure, not text — a valid control needle per
§11.4.201(7)) on boba's plugins tree:

    gate reports        : 30
    AST ground truth    : 42
    missed              : 12
    false positives     : 0

A gate that misses 12 of 42 while reporting a confident number is a §11.4.201(6)
false-null: its output reads as a census when it is a FLOOR. Anyone fencing an
exclusion list against that number (§11.4.224(E)) would write the fence against
an undercount and lock the invisible sites out of scope permanently.

FOUR DISTINCT CAUSES, each independently falsifiable:

L1 — TRAILING COMMENT DEFEATS THE REGEX (10 of the 12).
  The pattern anchors the handler line with `…:[[:space:]]*$`, so
  `except Exception:  # noqa: S110` never matches. The irony is load-bearing:
  the sites a human consciously reviewed and annotated are exactly the ones the
  gate cannot see.

L2 — TUPLE CLAUSE DEFEATS THE REGEX (2 of the 12).
  The exception-type group is `[A-Za-z_.]+`, which cannot match `(`, so
  `except (OSError, ValueError):` is invisible.

L3 — A COMMENT BETWEEN `except` AND `pass` DEFEATS THE BODY CHECK.
  The detector reads exactly `lineno+1`. Zero current instances, but demonstrated
  live. This one has a nasty second-order effect: a well-intentioned reviewer
  adding an explanatory comment INSIDE a handler makes that site vanish from the
  gate. The triage agent hit this itself — its first patch put comments inside two
  handlers, and the resulting count would have read 28 while only 6 sites were
  genuinely eliminated. It caught and corrected that rather than reporting the
  better number, which is exactly the §11.4 discipline working.

L4 — THE SHAPE ITSELF, not the regex.
  The body must be exactly `pass`, so `except: return <default>` is out of scope
  BY CONSTRUCTION. 13 such sites remain in boba (12 vendored `community/`, 1
  `linuxtracker.py:51`), plus `plugins/rutor.py:121` (`except: return
  int(time.time())`) which a structural invariant found and which is now fixed.
  Returning a silent default is the SAME defect class as `pass` — arguably worse,
  because the caller receives a plausible value rather than nothing.

RECOMMENDED FIX: replace the text-matching detector with an AST-based one for
Python. `except` handlers are trivially enumerable from `ast.Try.handlers`, and
a handler whose body neither re-raises nor logs nor returns a distinguishable
failure signal is decidable structurally. Text matching cannot reach L1-L4
without accumulating epicycles; each of the four above is a separate regex patch
under the current design.

WHATEVER THE FIX, IT MUST BE FALSIFIABLE (§1.1): the paired mutation must include
one fixture per cause — trailing comment, tuple clause, comment-before-pass, and
`return <default>` — each of which the CURRENT detector passes and a correct one
must FAIL. A negative control is required too: a correctly-narrowed handler that
logs and re-raises must NOT fire (§11.4.201(1)).

CONSUMER-SIDE NOTE (already fixed, boba): pre_build_verification.sh invariant 39
counted the gate's own SUMMARY line as a finding, because that line also starts
with the failure marker. Each failing root added exactly one phantom, so the
reported total read 38 when the gate itself said 36. Fixed by matching the
finding STRUCTURE (a finding names " at <path>:<line>"; a summary never does)
rather than the marker glyph. That is a separate defect from the four above, in
the consumer, and is NOT part of this item.

**Affected scope / file-scope manifest:**
constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh (+ its paired mutation test)

**Reproduction / context:**
Run the gate over plugins/ and compare to an AST enumeration of ast.Try.handlers: gate=30, AST=42, 12 missed, 0 false positives. Each cause reproduces standalone: except Exception:  # noqa (L1); except (OSError, ValueError): (L2); a comment between except and pass (L3); except: return <default> (L4).

**Acceptance criteria:**
Detector finds all 42 AST-confirmed sites with zero false positives, with a paired §1.1 mutation carrying one fixture per cause (all four currently PASS the detector and must FAIL a correct one) plus a negative control that must NOT fire on a correctly-narrowed logging-and-re-raising handler.

## BOB-148 — Standing red unit test nothing tracked: test_no_credentials asserts has_session False, gets True — real defect or non-hermetic test, undecided

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** Medium
**Created-By:** Claude

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-20T16:28:57Z
**Reported-By:** Claude

**What (the report, verbatim):**
tests/unit/test_auth_coverage.py:303
  TestAllTrackersAuthStatus::test_no_credentials

    assert result["trackers"]["qbittorrent"]["has_session"] is False
    E   assert True is False

The test asserts that with NO credentials configured, qbittorrent reports
has_session=False. It reports True.

PROVEN PRE-EXISTING, by experiment rather than by reasoning: a detached worktree
at the session-start commit e335dde reproduces the identical failure. Nothing in
this session touched download-proxy/src/api/auth.py or this test file (git log
over the session range for both paths is empty). It was already red and nothing
was tracking it — which is the actual defect worth recording: a standing red unit
test that no item names will be re-discovered forever and attributed to whoever
touches the tree next. It was in fact attributed twice today before being pinned
down.

TWO HYPOTHESES, both plausible, NEITHER confirmed (§11.4.6 — do not pick one
without evidence):

 (H1) A REAL DEFECT: the auth-status path reports has_session=True on the
      strength of something other than a credential — a cached cookie, a
      default-constructed client, or a truthy default in the status assembler.
      If so, the operator-visible consequence is that the dashboard would show a
      tracker as authenticated when it is not.

 (H2) A NON-HERMETIC UNIT TEST (§11.4.27(A)): the test reads real state rather
      than a stub, and the live qBittorrent container at :7185 — which is UP and
      healthy on this host — supplies a genuine session. Under that hypothesis
      the test would PASS on a host with the stack stopped, which makes it
      environment-dependent, i.e. FLAKY, and §11.4.248 quarantine territory
      rather than a product bug.

DECISIVE EXPERIMENT (cheap, and it distinguishes them in one run): execute this
single test with the stack stopped, or with the qBittorrent host/port pointed at
a closed port. If it PASSES, H2 holds and the fix is to make the unit test
hermetic (mock the client) — the product is fine. If it still FAILS, H1 holds and
the fix is in the auth-status assembly path.

Do NOT stop the stack casually to run this — other work depends on it. Prefer
pointing the test at an unbound port via env override, which is reversible and
affects nothing else.

NOTE the §11.4.226 evidence-class consequence: if H2 holds, this test has been
asserting a RUNTIME condition from a unit-test layer all along, which is why it
reads red on a developer host and would read green in a clean CI container — the
worst possible polarity, since the environment that most resembles production is
the one where the test stays silent.

**Affected scope / file-scope manifest:**
tests/unit/test_auth_coverage.py:303, download-proxy/src/api/auth.py (auth-status assembly)

**Reproduction / context:**
timeout 300 .venv/bin/python -m pytest tests/unit/test_auth_coverage.py::TestAllTrackersAuthStatus::test_no_credentials -q --import-mode=importlib  -> assert True is False. Reproduces identically in a detached worktree at e335dde (session start).

**Acceptance criteria:**
The H1/H2 experiment is run and recorded. If H2: the unit test is made hermetic (no live-stack dependency) and passes with the stack both up and down. If H1: the auth-status path no longer reports has_session without a credential, with a RED test capturing it first.

## BOB-153 — Go profile cannot build: go.mod requires go 1.26.2 but the Dockerfile builder is golang:1.23-alpine

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** Medium
**Created-By:** AI

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-21T15:40:00Z
**Reported-By:** AI

**What (the report, verbatim):**
The Go backend profile is unbuildable. qBitTorrent-go/go.mod declares 'go 1.26.2' while qBitTorrent-go/Dockerfile builds with 'FROM golang:1.23-alpine', so the build aborts before compiling anything. Found while attempting feature 002 quickstart Scenario 6, which exercises the go profile to confirm the ownership fix covers every service (FR-016) - the scenario could not run at all, for a reason unrelated to ownership. Two consequences worth separating. First, this is a plain build defect and is pre-existing. Second, and more awkward, it means FR-016 coverage for the go profile currently rests on surface-equivalent measurement (its Dockerfile's final stage is alpine:3.19 with no USER directive, so it runs as container root and inherits the correct rootless mapping) rather than on a live running service. That reasoning is sound but it is not the same evidence as a probe against a real container, and it is recorded as the weaker evidence it is. Also noted while investigating: the go profile has no Hard-Stop-#3-compliant invocation path - start.sh has no --profile flag, so the only route is a raw compose command, and it would collide on port 7187 with the running Python proxy since both use network_mode host.

**Affected scope / file-scope manifest:**
qBitTorrent-go/go.mod, qBitTorrent-go/Dockerfile

**Reproduction / context:**
grep '^go ' qBitTorrent-go/go.mod -> 'go 1.26.2'; grep 'FROM golang' qBitTorrent-go/Dockerfile -> 'FROM golang:1.23-alpine AS builder'. Building the go profile fails: 'go: go.mod requires go >= 1.26.2 (running go 1.23.12; GOTOOLCHAIN=local)'.

**Acceptance criteria:**
The go profile builds. Either the builder image is raised to a toolchain satisfying go.mod, or go.mod's directive is lowered to what the builder provides - and whichever is chosen, a check ties the two together so they cannot drift apart again, because nothing currently compares them.

## BOB-155 — workable-items diff reports 'DB and Markdown are in sync' having opened zero Markdown files when --issues/--fixed are omitted

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** High
**Created-By:** AI

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-21T15:57:00Z
**Reported-By:** AI

**What (the report, verbatim):**
The flagless form of the sync checker is a false-null generator. Called without --issues/--fixed it prints the same reassuring 'DB and Markdown are in sync' it prints after a real successful comparison, while having read no Markdown whatsoever. A blind instrument and a genuinely clean tree return the identical quiet verdict, which is precisely the failure class the constitution's measurement-integrity rules exist to prevent - and here it lives inside the project's own sync-verification tool. This bit for real today: the flagless form was used to VERIFY a reconciliation of five tracker rows and reported 'in sync'. The reconciliation happened to be correct - re-checked afterwards with the path-ful form, which is clean on the current tree and correctly reports 2 differences against a planted divergence - so the conclusion was right and the evidence for it was worthless. Nobody would have noticed, because the output is indistinguishable from a real pass. Surfaced by the BOB-136 investigation. Not fixed there because the file lives in the constitution submodule, which carries its own review and commit discipline and was dirty with concurrent work at the time. The caller-side exposure was closed instead (a gate now asserts zero flagless callers), but the engine itself still ships the trap for every other consumer of that submodule.

**Affected scope / file-scope manifest:**
constitution/scripts/workable-items/cmd/workable-items/sync.go

**Reproduction / context:**
Plant a real divergence: change a **Status:** line in docs/Issues.md only. Then: workable-items diff --db docs/workable_items.db -> 'diff: DB and Markdown are in sync' (WRONG - it compared nothing). The same command WITH paths: workable-items diff --db docs/workable_items.db --issues docs/Issues.md --fixed docs/Fixed.md -> '2 difference(s)' (correct). Restored byte-identical after the test.

**Acceptance criteria:**
Omitting --issues/--fixed either REFUSES with a non-zero exit naming the missing input, or defaults to the conventional paths and says which files it read. What must never happen again is a confident 'in sync' verdict from a comparison that opened no Markdown at all - the verdict must always name its inputs so a reader can tell a real check from a vacuous one.



**Closed 2026-08-21** — constitution commit `16b67b0`, pushed to 8 upstreams. Chose REFUSE plus an explicit `--db-only` opt-in, because the alternative (defaulting to conventional paths) is NOT implementable in a shared submodule without baking one consumer's `docs/Issues.md` layout into it. Sibling precedent settled it: `sync md-to-db` and `sync db-to-md` in the same file ALREADY refuse when every path flag is absent, so `diff` was the exception. Every verdict now NAMES ITS INPUTS — "compared 152 Markdown item(s) against 152 DB item(s); read <p>/Issues.md, <p>/Fixed.md" — which is the property that makes the failure class impossible rather than merely unlikely.

ROOT CAUSE WITH HISTORY: this defect was INTRODUCED BY THE FIX FOR ITS OWN MIRROR IMAGE. Before 2026-08-10 the flagless form ran the absent-in-Markdown loop against an EMPTY parsed set and flagged every DB row — a FAIL-bluff. The fix added a `haveMarkdown` gate that correctly silenced the noise, then fell through to the unconditional success verdict. Same seam, opposite polarity: a FAIL-bluff traded for a PASS-bluff. Worth recording, because "we fixed the false positives" is exactly how a false negative gets installed.

TWO ADJACENT DEFECTS SURFACED, both worse than the one filed: (1) BOB-155 was ALREADY being caught by a test's GREEN branch — a standing red nobody saw because the suite is evidently never run in GREEN mode, a coverage escape where the check existed and nothing executed it; (2) the suite was RED IN BOTH POLARITY MODES beforehand, and one test's GREEN branch had begun ASSERTING THE DEFECT. Both reconciled to assert the new mechanism rather than fake-passed or reverted. One lesser instance fixed in passing: `md-to-db` printed the hardcoded label `Issues.md:` even when reading a renamed tracker — a verdict misnaming its input AND a baked-in filename in a shared submodule.

Siblings audited EMPIRICALLY, not assumed: md-to-db and db-to-md refuse; `validate` has no optional inputs and names its item count, so it cannot be blind. Commit seam verified against a purpose-built PRE-FIX binary and the fixed one — identical behaviour, because all three of its checks already pass --issues/--fixed. Zero project literals among added lines, control-needled.
## BOB-157 — Our own BOB-137 stall watchdog can segfault the merge service: faulthandler dump_traceback(all_threads=True) hits an unpatched CPython 3.12 defect

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Severity:** High
**Created-By:** AI

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-21T17:18:18Z
**Reported-By:** AI

**What (the report, verbatim):**
Our own diagnostic is a crash vector, and it is still armed. download-proxy/src/main.py:135 calls faulthandler.dump_traceback(file=sink, all_threads=True) on a live 18-thread process; three further registrations at 214/217/219 use all_threads=True as well. Upstream python/cpython#116008 and #128400 are the same NULL f_executable in dump_frame() at Python/traceback.c:1190 - FIXED and backported to 3.13/3.14, with NO 3.12 backport listed. The container ships Python 3.12.13. Container logs still show 'BOB-137 stall watchdog armed: stall>20.0s'. It has not fired again only because BOB-137's root cause was improved enough that the loop rarely stalls past the threshold - but BOB-137 is NOT closed, and its live verification the same day measured the loop still blocking, with 18.4% of probes stalled 1-5s and two dead events in 15 minutes. So this is latent, not resolved: one 20s stall away. Note the perverse shape - the worse the wedge gets, the more likely the tool built to diagnose it is to kill the process, destroying the evidence it exists to capture. Found while investigating BOB-131, whose own premise (a conmon crash) turned out to be false: no conmon process crashed; the ticket conflated this python3 segfault with an unrelated 14-hour absence caused by a host power-off.

**Affected scope / file-scope manifest:**
download-proxy/src/main.py:135 (and the registrations at 214/217/219)

**Reproduction / context:**
2026-08-20 17:56:26 CEST, one occurrence: kernel 'python3[314359]: segfault at 70 ... in libpython3.12.so.1.0' plus the container's own truncated dump ending mid-'  File '. The kernel Code: bytes at IP were byte-matched against the library inside the running container (MATCH), decoding to mov r14,[r12] (frame->f_executable = NULL) then mov rax,[r14+0x70] (code->co_filename) -> fault; the preceding lea resolves to the literal '  File ' with edx=7, its exact length. The watchdog had fired 17 times in 16 minutes that day; dump 17 completed to the file sink, then the stderr pass crashed.

**Acceptance criteria:**
The diagnostic cannot crash the service it diagnoses. Either all_threads=True is dropped for the periodic dump, or the dump is gated behind something that cannot fault on a live multi-threaded process, or the runtime moves to a Python where the upstream fix is present - and whichever is chosen, the choice is recorded against the upstream issue so a later runtime bump does not silently re-arm it.

## BOB-183 — Served dashboard bundle is stale and no gate checks its freshness, so contrast fixes never reach users

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-183/runtime_served_bundle_evidence.log
**Severity:** High
**Created-By:** Claude
**Assigned-To:** Claude

The compiled Angular bundle shipped at download-proxy/src/ui/dist/frontend/browser still carries the BOB-164 colour-contrast defect verbatim: scanned 2026-08-23 it reports 21 violation nodes on darcula/dark and 1 on darcula/light, while the same sources built to a scratch path report 0 across all 16 palette x mode combinations. The fix is therefore correct at the SOURCE layer and absent at the ARTIFACT layer, so §11.4.108 layer 2 is NOT closed and end users still see the low-contrast dashboard. Two compounding facts make this silent rather than obvious: dist/ is gitignored, so the divergence never shows in a diff; and scripts/install.sh:133 asserts only that the directory EXISTS, never that it is newer than the sources it was built from, so a stale bundle passes install unchallenged. Acceptance: install (or an equivalent gate) FAILS on a bundle older than its sources, the bundle is rebuilt, and docs/qa/BOB-164/axe_contrast_scan.py run against download-proxy/src/ui/dist/frontend/browser exits 0 with zero violation nodes and zero blocking incomplete nodes.

## BOB-120 — 3rd forced-logout incident 2026-08-18 23:45:49 — SIGKILL user@1000 + preventive-timer-inside-user-slice architectural gap

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-120/closure_via_bob126_root_cause.log
**Severity:** Critical
**Created-By:** AI

3rd forced-logout incident 2026-08-18 23:45:49 — SIGKILL user@1000 + preventive-timer-inside-user-slice architectural gap

## BOB-166 — update --status accepts a terminal status without migrating the row, so 10 closed items sit in the open tracker while validate/diff/closure-seam all report green

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-166/runtime_guard_refuses_evidence.log
**Severity:** High
**Created-By:** Claude
**Assigned-To:** Claude

WHAT. §11.4.19 requires closure migration to be ATOMIC: a resolving item moves to Fixed.md, DISAPPEARS from Issues_Summary (open-only) and APPEARS in Fixed_Summary (closed-only). Ten rows violate all three properties right now — they carry a terminal status yet current_location='Issues', so they render in docs/Issues.md and are listed in docs/Issues_Summary.md with a status that literally reads '(→ Fixed.md)', while appearing 0 times in Fixed_Summary.md. Any reader of the canonical open tracker is told these are open work.

MANIFEST (measured 2026-08-21): BOB-087 (Completed), BOB-129, BOB-131, BOB-144, BOB-145, BOB-146, BOB-148, BOB-153, BOB-155, BOB-157 (all 'Fixed (→ Fixed.md)'). Confirmed rendering: BOB-155/087/157 each grep 1 in Issues.md, 0 in Fixed.md, present in Issues_Summary.md, 0 hits in Fixed_Summary.md.

ROOT CAUSE (reproduced at runtime, not inferred). 'close' performs the atomic migration and REQUIRES --evidence. 'update --status' sets any §11.4.15 closed-set value with NO evidence and NO migration — and it knows the location, because it prints it. On a COPY of the real DB:
    $ workable-items update --id BOB-065 --db repro.db --status 'Fixed (→ Fixed.md)'
      update: BOB-065 updated in Issues (status=Fixed (→ Fixed.md), type=Task)
    $ sqlite3 repro.db 'SELECT atm_id,status,current_location ...'
      BOB-065|Fixed (→ Fixed.md)|Issues
So the seam that is supposed to be the ONLY closure path (close, evidence-gated per §11.4.146(D3)) has a parallel unguarded path that reaches the same status while skipping BOTH the evidence requirement and the migration.

WHY NOTHING CAUGHT IT (§11.4.238 coverage-escape audit). Three standing checks stay GREEN on a DB holding the forbidden row, verified on the poisoned copy from the repo root so no cwd artifact is involved: (1) 'validate' → 'OK — 164 items, all invariants satisfied' (it has no status↔location coherence invariant); (2) 'diff' → 'in sync' (DB and Markdown agree — on the WRONG state; agreement is not correctness); (3) CM-CLOSURE-SEAM-BINDS CHECK A → PASS (it flags NON-terminal rows whose id appears in a work commit; these rows are terminal, so they are outside its predicate by construction). This was found by reading a status tally, not by the automated regime — a §11.4.238 discovery-channel escape, which is itself a defect of equal standing to the mis-located rows.

ACCEPTANCE. (a) 'update' REFUSES a terminal status and names 'close' as the correct path, with a paired §1.1 mutation proving the refusal (removing the guard must make the mutation pass). (b) 'validate' grows a status↔location coherence invariant that FAILS on the forbidden state, with a golden-bad fixture and a negative control (a legitimately terminal row in Fixed must NOT fire — §11.4.201(1)). (c) The 10 existing rows are drained to Fixed with class-matched evidence per row, or, where a row's evidence cannot be produced, honestly re-opened rather than migrated on a bare assertion. (d) Honest boundary: this closes the update-path hole and the detection gap; it does not claim every historical status write was evidence-backed.

NOT CLAIMED. No fix is implemented by this filing. The 10 rows are untouched; draining them is acceptance (c) and each needs its own evidence, not a bulk UPDATE.

## BOB-158 — tests/conftest.py cannot run on the production interpreter: binds asyncio.events._get_event_loop_policy, a 3.13+ private API, while production is 3.12.13

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-158/runtime_both_interpreters.log
**Severity:** High
**Created-By:** AI

tests/conftest.py cannot run on the production interpreter: binds asyncio.events._get_event_loop_policy, a 3.13+ private API, while production is 3.12.13

## BOB-190 — Host site-packages holds cpython-313 ABI wheels under Python 3.14, breaking the CLAUDE.md-documented 'python3 -m pytest' path

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-190/documented_command_now_runs.log

WHAT: ~/.local/lib/python3/site-packages contains binaries built for the cpython-313 ABI while the interpreter is Python 3.14, so pydantic_core and rpds fail to import and every test importing FastAPI dies at import time. CONFIRMED NOT OURS: an untouched test file fails identically, so this is environmental and pre-existing. WHY IT MATTERS: CLAUDE.md documents 'python3 -m pytest tests/unit/ -v --import-mode=importlib' as the canonical invocation and that documented command currently cannot run - docs and host disagree, the §11.4.99 misguidance class at the environment layer. scripts/run-tests.sh already sidesteps it by selecting .venv/bin/python, so a working path exists and simply is not what the docs tell a reader to type. IMPACT: anyone following CLAUDE.md literally concludes the suite is broken; worse, an agent could chase green by rewriting tests. ACCEPTANCE: either repair the host site-packages so the documented command works, or correct CLAUDE.md + docs/TESTING.md to name the venv interpreter as canonical - decided explicitly, not left to whoever hits it next. Discovered out-of-band by the fail-open triage agent, so per §11.4.238 this also owes a coverage-escape note: no automated check asserts the documented test invocation actually runs.

## BOB-186 — workable-items diff reports "in sync" on a partial read: 77 Markdown items compared against 184 DB items, exit 0

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-186/investigation_20260826.md

workable-items diff returned exit 0 and the verdict "DB and Markdown are in sync" on a PARTIAL read: invoked with --issues but without --fixed it compared 77 Markdown items against 184 DB items and called that in sync, printing both mismatched counts in its own output while 107 DB items were never compared against anything. Measured 2026-08-25: (A) no markdown paths -> correctly REFUSES exit 1; (B) --db-only -> honest, "no Markdown compared"; (C) --issues alone -> exit 0, "in sync (compared 77 Markdown item(s) against 184 DB item(s))". The 11.4.201(6) false-null: a partially blind instrument returned the same quiet green a genuinely-synced corpus returns.

IMPACT — CORRECTED 2026-08-25, my original filing OVERSTATED this. I wrote that CHECK 2 of the 11.4.106(F) commit seam was exposed. It was NOT. scripts/hooks/docs-sync-commit-seam.sh:277 passes BOTH --issues and --fixed, and a repo-wide sweep found NO executable caller that breaks: the two real callers (that seam and pre_build_verification.sh:549) both pass both paths; the single-path hits are prose evidence files plus a static-scan test fixture. So the defect was real and latent, never live in this project. The corrected claim is: any FUTURE single-path caller would have been silently mis-told.

PROVENANCE, twice corrected. A subagent first attributed the false-null to the no-paths form, which actually refuses correctly; the conductor re-measured and relocated it to the partial read. Then the fixing agent corrected the conductor on impact. Both corrections are recorded so neither wrong version propagates.

FIXED (uncommitted, constitution submodule, fetched to upstream tip 7f16739 before edit per 11.4.26). Design: refuse by default (11.4.201(4)); the narrow per-tracker comparison PRESERVED behind an explicit --partial-scope rather than deleted (deleting an existing documented capability would be an 11.4.122 silent removal), mirroring how --db-only preserved the no-Markdown shape. Keyed on MEASURED DB content, never on flag presence — a DB with zero Fixed rows IS fully accounted for by --issues alone and still passes, so flag-keying would have traded the false-null for an 11.4.201(1) false-positive refusal. Resulting property: "in sync" is reachable only when the two printed counts account for each other. RED 4 fail/5 pass -> GREEN 9/9; paired 1.1 mutation is the fixs own revert, killing exactly the 4 defect-guarding tests while the 5 preservation tests stay green. Case C now refuses naming "107 item(s) located in Fixed (supply --fixed)", the 107 confirmed against an independent sqlite3 count (107 Fixed + 78 Issues = 185). Incidentally closed an 11.4.238 gap: case As refusal had no test anywhere; TestDiffCmd_NoPathsStillRefuses now guards it.

OPEN: --partial-scope is the agents naming choice, not an operator decision, and renaming is cheap now and expensive after other consumers adopt it. Other consumers of this shared submodule were not swept.

CLOSED 2026-08-26. Already fixed 2026-08-25 21:06 by constitution commit 5979128 ("fix(workable-items): diff claimed 'in sync' while 107 DB rows went uncompared") - only this tracker row was stale; no code work was owed.

ROOT CAUSE, proven from pre-fix source (11.4.6 - fact, not inference): two individually-reasonable pieces of sync.go. (a) sync.go:852-863, the reverse "absent in Markdown" pass, carried `if d.CurrentLocation == "Fixed" && *fixedPath == "" { continue }` - its own comment declares the intent, suppress false positives for trackers the caller never supplied, correct in isolation - but the continue ALSO dropped those rows out of `differences`, and nothing compensated. (b) sync.go:894-897, the verdict, printed len(parsed) and len(dbItems) - the two MISMATCHED numbers - then decided purely on `differences`. THE VERDICT PRINTED BOTH NUMBERS AND NEVER COMPARED THEM. In one line: an 11.4.201(1) false-positive guard silently narrowed comparison SCOPE while the verdict stayed scope-unaware, so the fix for a false positive created its 11.4.201(6) mirror image.

CLOSED ON BEHAVIOURAL EVIDENCE, not on reading the commit (11.4.226 evidence-class-at-closure): the shipped binary now REFUSES a partial-scope verdict instead of reporting "in sync" - "refusing to report a DB-vs-Markdown verdict that would silently exclude part of the DB - the supplied Markdown path(s) do not account for 122 item(s) located in Fixed (supply --fixed)", exit 1; with opt-in --partial-scope it reports "PARTIAL SCOPE - N difference(s) ... 122 of 201 DB item(s) were NOT compared", exit 1. The phrase "in sync" is structurally unreachable on a partial read. Regression suite sync_diff_partial_scope_test.go (9 tests) landed with the fix.

INSTRUMENT VALIDATED BOTH WAYS (11.4.201(7)(b)): negative control - regenerating Markdown from a copy DB yields "in sync (201 against 201)" exit 0, so the checker is not stuck-on-FAIL. Needle A (flip BOB-008 status, Issues leg) detected exit 1. Needle B (delete BOB-067 on the FIXED leg - the exact leg this defect was blind to) detected as "present in DB, absent in Markdown" (200 vs 201), exit 1. Each needle byte-verified applied before running.

HONEST GAP (11.4.6): UNKNOWN whether the shipped binaries are byte-reproducible from HEAD source - they were not rebuilt. Both were proven to carry the guard and behave identically on the real corpus, which is the behavioural evidence this closure rests on. No claim is made about classes `diff` does not compare (revision headers, *_Summary.md).

## BOB-206 — probe_location() may return ok on a uid-flattening filesystem that cannot express ownership at all — and the download root IS such a mount

**Status:** Obsolete (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-206/dismissal_evidence_20260826.md
**Severity:** critical
**Obsolete-Details:** Since: 2026-08-26; Reason: not-reproducible; Superseding-item: BOB-207 (the real defect underneath), BOB-208, BOB-209, BOB-210, BOB-211; Triple-check evidence: docs/qa/BOB-206/dismissal_evidence_20260826.md

STATUS: UNCONFIRMED — surfaced by the T041 review-scope preflight (docs/qa/T041/review_scope_map_20260826.md), which stated it as "factor 6 is unguarded as far as I could tell". That hedge is preserved deliberately per §11.4.6: this item exists to DRIVE the verification, and MUST NOT be cited as a confirmed defect until a runtime probe settles it either way.

WHAT (the hypothesis to test): probe_location()'s verdict is a product of >=7 independent terms — the §11.4.194(1) multi-factor shape where ANY degenerate term triggers the failure and verifying one while assuming the rest is the exact forbidden gap. Factor 6 is the filesystem's ability to EXPRESS per-file ownership. On a uid-flattening filesystem (vfat / exfat / ntfs mounted with a uid= option) every file reports the MOUNT's uid regardless of what any chown did or did not do. If probe_location() reads that uid and concludes ownership is correct, it returns 'ok' on a filesystem structurally incapable of holding the property being probed — a §11.4.201(6) FALSE-NULL at the feature's own core: the probe and a genuinely-correct filesystem return the identical quiet success.

WHY CRITICAL RATHER THAN THEORETICAL: the download root is a HOST-SPECIFIC MOUNT. Whether this fires is a property of the operator's actual mount table, not of our source — so it cannot be settled by reading code alone, and a green probe on the developer's ext4/btrfs proves nothing about an operator whose media lives on exfat or ntfs. This is precisely the class §11.4.108 layer-3 exists for.

ADJACENT UNGUARDED TERMS the same preflight surfaced (verify together — they share the tri-state): the precondition has FOUR refusal triggers, of which R4 is itself a THREE-WAY product (measured-rootless AND non-root user-spec AND mounts-a-declared-location) that the source states has no second line of defence; R3 and R4 both consume detect_rootless()'s tri-state whose DOCKER branch the source itself admits is documented-not-measured.

VERIFICATION PLAN (§11.4.115 RED-first, §11.4.262 machine evidence): (1) enumerate the real mount table and record which declared locations sit on uid-flattening filesystems — that measurement alone may confirm or dismiss the whole item; (2) construct a loopback vfat/exfat image mounted with a uid= option, point a declared location at it, run probe_location() and capture the verdict — if it returns ok, that IS the RED; (3) fix by detecting the filesystem's ownership-expressiveness and refusing-with-reason rather than reporting ok (§11.4.252 fail-closed: a probe that cannot resolve its condition refuses and says so, never passes); (4) golden-FALSE fixture on ext4/btrfs proving the new guard does NOT refuse a healthy location (§11.4.201(1) — a false-positive refusal here would break every normal operator).

BLAST RADIUS: this is the ownership feature's own correctness core — the subject of spec 002-user-owned-downloads. A false ok here means the feature reports success while the operator still has to chown by hand, which is the ORIGINAL reported problem the spec exists to solve.

DISCOVERY CHANNEL (§11.4.238): found by an agent mapping the T041 review scope, NOT by the automated QA regime — a coverage escape in its own right. The escape audit owed: no existing check exercises a uid-flattening filesystem, so no automated surface could have caught it.

NOTE ON THIS RECORD: the first write of this description was corrupted by shell backtick expansion (three terms silently emptied). This is the repaired text; the corruption is recorded here rather than quietly overwritten, per §11.4.6.

## BOB-205 — cmd/boba-ctl (947 LOC container orchestrator, shell-exec + mutation surface) is absent from DANGER_ROOTS — never scanned at all

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-205/danger-roots-scope-evidence.md
**Severity:** major

WHAT: the §11.4.252 fail-closed scanner is driven per-root by invariant 39 at scripts/pre_build_verification.sh:1481-1544 over a hand-maintained DANGER_ROOTS list. `cmd/boba-ctl/` — 4 files, 947 LOC — is NOT in that list, so it is never scanned by any arm. It is the container orchestrator: a shell-exec plus state-mutation surface, precisely the §11.4.252 dangerous-combination class the gate exists for.

DISTINCT FROM BOB-191: BOB-191 is a MATCHER hole (the root IS scanned; the Go files inside it are structurally unanalysable while counted as analysed — a false null that prints green). This is a SCOPE hole (the root is not scanned at all). Different failure shapes, different fixes; per §11.4.214 they are distinct-but-similar, deliberately not merged.

WHY BOTH EXIST: the root list is hand-maintained, so a new first-party root joins the tree without joining the gate. §11.4.251 (role-as-data-pack) points at the fix direction — replace the hand-maintained list with a declared manifest derived from the same source of truth the build uses, so a root cannot exist without being enumerated.

ACCEPTANCE: (1) cmd/boba-ctl is scanned — either by being added to DANGER_ROOTS or by the manifest replacing it; (2) whichever is chosen, a RED fixture proves a planted fail-open inside cmd/boba-ctl is SEEN pre-fix-absent / post-fix-present (§11.4.115); (3) if the manifest route is taken, a fixture proves a NEWLY-ADDED first-party root is picked up without a hand edit — that is the invariant that stops this recurring; (4) the honest-blindness path (§11.4.3 SKIP-with-reason, which the gate already implements correctly for unenumerated extensions) is preserved, never converted into a silent PASS.

DISCOVERY CHANNEL (§11.4.238): found by an agent auditing the scanner's own root list during the BOB-191 investigation, NOT by the automated QA regime — a coverage escape; BOB-191 carries the escape audit.

=== VERIFICATION COMPLETE 2026-08-26 — CONFIRMED, with three corrections and a far larger gap ===

CONFIRMED: DANGER_ROOTS=(download-proxy/src plugins scripts qBitTorrent-go frontend/src) at scripts/pre_build_verification.sh:1511 (conductor-verified verbatim). Invariant 39 spans :1481-1541, skips non-existent roots at :1514, calls the gate once per root at :1517, and the gate is invoked from exactly ONE place (:1507) — so a root absent from that array is scanned by NO arm. cmd/boba-ctl re-measured: 4 tracked .go files, 947 LOC — the filed numbers hold, no drift.

CORRECTION 1 (§11.4.6): this item said boba-ctl is a "shell-exec" surface. There is NO exec.Command in main.go — exec is one hop away via digital.vasic.containers/pkg/compose (main.go:13). The §11.4.252 threshold is still met several times over (5 of 6 capabilities: mutation :34,36,95-105,121 · untrusted input :21,33,53,110,144,170,302,453-465 · credentials :432-440,496-509 · external side effect :239,323,430 · irreversible :36,142) — but the specific word was wrong.

CORRECTION 2 (§11.4.6): this item's acceptance criterion (4) asserted the gate "already implements correctly" an honest SKIP for unenumerated extensions. WRONG. That honest-skip path exists for the PYTHON ARM's degradations only. An extension absent from the ext list is a SILENT false-null. Filed separately as the LANGUAGE HOLE item.

CORRECTION 3: the gap is not one root. FULL ENUMERATION — 266 files in scope / 512 OUT of scope = 66% of the gate-visible first-party corpus never scanned. tests/ 324 (excluded-by-intent but UNDECLARED) · extension/ 108 · docs/ 51 · challenges/ 18 · cmd/boba-ctl 4 · frontend/e2e+configs 5 · tools/ 1 (CONCEALS 3 REAL HITS: plugin_update_automation.py:189,198,215) · repository ROOT 1 (CONCEALS 1 REAL HIT: webui-bridge.py:295). Filed separately as the ROOT-SCOPE item.

boba-ctl IS a genuine §11.4.252 surface, but the hole around it is LATENT: main.go has no `_ = err`, no empty `if err != nil {}`, no silent `return nil` today (grep control-needled against qBitTorrent-go/internal/config/config.go). It hides nothing live; it guarantees a future one lands unseen. One real semantic finding WAS spotted by reading: authMethod()'s default branch — filed separately.

BOB-205 != BOB-191, AND THEY COMPOUND — measured, one temp root, both needles: go-needle 0 hits, py-needle 1 hit. Go-blindness independently reconfirmed (gate routes only *.py to the AST arm). The real cmd/boba-ctl scanned DIRECTLY returns "PASS — no anti-patterns found" over 947 LOC it cannot analyse. THEREFORE: fixing BOB-205 ALONE moves the root from never-looked-at to LOOKED-AT-AND-FALSELY-GREEN — the §11.4.201(6) FALSE-NULL, the WORSE state, because it then counts as covered. Both must land, and the language hole with them.

THE RED: tests/pre_build/test_bob205_danger_roots_scope.sh. Oracle (§11.4.245) = METAMORPHIC + INVARIANT with a control needle: two BYTE-IDENTICAL Python fail-open needles (sha equality asserted at runtime, 8d8bd909...), one in a root that IS in DANGER_ROOTS (control), one in cmd/boba-ctl (probe), scanner driven exactly as invariant 39 drives it. Identical input, two locations, must give identical verdicts — matcher/language/gate-version held constant so SCOPE is the only free variable. Independent of the code under test: the expectation comes from the relation, not from reading DANGER_ROOTS. Shape (a) chosen; shape (b) included as an explicitly-labelled WEAKER secondary (it would pass on a typo'd list entry the [[ -d ]] guard silently skips).
CONFOUND DELIBERATELY AVOIDED: the needle is PYTHON, not Go — a Go needle would stay unseen post-fix and the RED would never go green, which is itself a §11.4.201(1) FAIL-bluff. Fixing BOB-191 will NOT turn this green; only widening scope will.
BLIND-INSTRUMENT GUARD: control needle not found -> exit 3 ABORT, never RED. The test parses DANGER_ROOTS from the real driver so it flips with zero edits, and never runs pre_build_verification.sh.
MEASURED: RED exit 1 (evidence docs/qa/BOB-205/red_run_live_gate.log, gate sha256 c5752428...) — CONTROL 1 hit "instrument PROVEN seeing", PROBE 0 hits. GREEN polarity proof exit 0 against a SCRATCH copy of the driver with the root appended (real driver git diff --stat empty). Determinism 3/3 RED exit 1, 3/3 GREEN exit 0.

FIX DIRECTION (assessed, not applied): §11.4.251 manifest feasible, but the source of truth matters — docker-compose.yml build contexts MISS plugins/, frontend/src, cmd/boba-ctl, webui-bridge.py; language markers (go.mod/package.json) MISS plugins/ and webui-bridge.py. ONLY derive-from-git-tracked-source-extensions minus a declared §11.4.224(E) exclusion fence reaches every gap. The derivation must be built either way: if the operator keeps the hand list, the omission-guard is the SAME computation — the only question is whether it drives the scan or audits the list. The tests/ question (324 files) is an operator §11.4.66 decision; production-only is defensible but currently UNDECLARED.

## BOB-204 — Credential DELETE reports 204 success while the .env plaintext delete error is discarded — credential survives on disk

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-204/closure_evidence_20260922.md
**Severity:** critical

WHAT: internal/jackettapi/credentials.go:234-253 (boba-jackett, port 7189). The DELETE credential handler checks the DB delete, then discards the errors of BOTH `_ = envfile.Delete(...)` (line 240) and `_ = d.Jackett.DeleteIndexer(id)` (line 249), then returns an UNCONDITIONAL 204 No Content. If the .env delete fails, the plaintext credential variables REMAIN ON DISK while the API reports the credential deleted. Second instance, same file: credentials.go:166-176 returns the error code `env_write_failed_db_rolled_back` while the rollback's OWN error is discarded (`_ =` at :169 and :171) — the response body asserts a rollback that was never confirmed, a §11.4 bluff in the API contract itself.

SCOPE: 4 combined dangerous capabilities on one path (credential access + filesystem mutation + external side effect + irreversible delete) where §11.4.252 fail-closed-on-dangerous-combination requires only 2. Composes §11.4.10 (credentials must never leak — a credential the operator believes deleted, still on disk, IS the leak class) and §11.4.252.

REPRODUCTION: read the cited lines; the discard is syntactic and unconditional. A runtime repro drives DELETE with the .env path made unwritable (chmod 0444 or a directory-level deny) and observes 204 while the variable persists in .env.

WHY IT WAS NOT CAUGHT: the CM-DANGEROUS-COMBINATION-FAIL-CLOSED gate (constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh) enumerates .go at line 243 but gates its ast analyser on *.py at line 537, so Go falls to two text matchers that key on `catch` — a keyword Go does not have. All 106 .go files are structurally unanalysable while being counted as analysed. That blindness is BOB-191; this item is the DEFECT it hid.

ACCEPTANCE: (1) both discard sites either handle the error or the handler returns a non-2xx naming the unresolved precondition per §11.4.252(2); (2) the env_write_failed_db_rolled_back code is only emitted when the rollback actually succeeded, else a distinct honest code; (3) a RED test drives the unwritable-.env path and observes the pre-fix 204, flips GREEN post-fix (§11.4.115); (4) a golden-FALSE fixture proves the new guard does not refuse the healthy path (§11.4.201(1)).

DISCOVERY CHANNEL (§11.4.238): found by an agent reading source during the BOB-191 investigation, NOT by the automated QA regime — this is itself a coverage escape and BOB-191 carries the escape audit.

=== VERIFICATION COMPLETE 2026-08-26 — BOTH DEFECTS CONFIRMED, RED AUTHORED AND WATCHED FAIL ===

Line numbers re-derived, NO drift from the filing: :234-237 DB delete checked (500 on error) · :240-244 envfile.Delete error DISCARDED · :249 DeleteIndexer error DISCARDED · :253 unconditional 204.

NOT AN OVERSIGHT — THE GODOC BLESSES IT. :210-211 reads: ".env and Jackett deletes are best-effort ...; failures are silently swallowed. The 204 status reflects DB success." Any fix MUST delete that sentence or it will read as authorizing the defect (§11.4.120 — the doc asserting the old behaviour is part of what must be reconciled).

MEASURED END STATE when the .env write fails: DB row GONE, plaintext RUTRACKER_USERNAME/RUTRACKER_PASSWORD STILL ON DISK, API says 204. WORSE THAN THIS ITEM ORIGINALLY FRAMED IT: the ENCRYPTED canonical copy is destroyed while the PLAINTEXT copy survives UNMANAGED — the system's own record of the credential is gone, so nothing will ever clean it up.

DEFECT (2) IS WORSE THAN FILED — CHECKING THE ERROR WOULD NOT FIX THE LIE. The rollback calls Repo.Upsert(..., ifSet(prior.Username), ...); ifSet("") returns nil; repos/credentials.go Upsert maps nil to COALESCE(excluded.username_enc, username_enc) = LEAVE UNCHANGED. So when the prior row had an empty field and the failed request set one, the compensating Upsert returns nil — it SUCCEEDS — and leaves the new value in place. The DB is not rolled back, there is NO error to check, and the API asserts a rollback anyway. Verified live by the third RED case. This means defect (2) is NOT one-line-ish: it needs the repo surface to express "set this field back to NULL" (delete-and-reinsert the prior row, or a tri-state in Upsert). Scope it separately from defect (1).

THE RED: qBitTorrent-go/internal/jackettapi/bob204_failclosed_test.go (297 lines, NEW file, gofmt clean, deliberately isolated from credentials_test.go so it cannot widen the T041/T042 diff).
Failure injection is REAL, not mocked: envfile.mutate writes through <path>.tmp, so the test pre-creates that path as a DIRECTORY -> os.OpenFile returns EISDIR (errno 21 probed) -> envfile.Delete fails WHILE .env stays byte-identical with the credential in it. Chosen over chmod deliberately: opening a directory for writing fails for root too, whereas a chmod mechanism would silently no-op under uid 0 and turn the RED into a FALSE GREEN. A CONTROL NEEDLE inside breakEnvWrites calls the real envfile.Delete and t.Fatal's if it unexpectedly succeeds — a blind instrument cannot produce a conclusion.
Measured: 3 FAIL (all three defect cases) + 1 PASS (the §11.4.201(1) golden-FALSE proving the REDs are not tautological and that the fix must not refuse the healthy path). Package-wide exactly 3 failures, all this stream's, zero skips. §11.4.10 honoured: no assertion or message prints a credential VALUE — names and booleans only, fixtures are fake-not-a-real-*.

HONEST BOUNDARY (§11.4.6): the GREEN half of the flip is OWED, NOT CLAIMED. The stream was forbidden from editing credentials.go, so RED was watched, GREEN was not.

THE FIX, SCOPED (not applied): defect (1) IS one-line-ish twice — replace the two `_ =` with checked errors returning 5xx naming the unresolved precondition (env_delete_failed, jackett_cascade_delete_failed) and DELETE the :210-211 GoDoc sentence. Defect (2) is a repo-surface change, separate scope.

ADJACENT FINDINGS: (a) credentials.go is strictly WEAKER than its own sibling — indexers.go:207-209 handles the identical DeleteIndexer error and at least LOGS it; credentials.go:249 does not even log. Same package, same call, two standards. (b) Repo is a concrete *repos.Credentials, not an interface, so a rollback-FAILURE path cannot be driven deterministically — relevant to §11.4.240/§11.4.241 if the fix wants that path testable. (c) The .gitignore false-null that nearly ate this deliverable is filed separately.

SPOT-CHECKS of the discards this item called benign — BOTH CONFIRMED BENIGN: client.go:140,153 `_ = resp.Body.Close()` closes a body already being discarded before a retry; runs.go:112 `_, _ = w.Write(...)` is post-WriteHeader, same class as credentials.go:274. Bonus: runs.go:43 `_ = json.Unmarshal(...)` is benign but mildly lossy — a corrupt ErrorsJSON silently reports error_count=0, documented as deliberate degradation in its GoDoc. Cosmetic under-report, not an integrity issue; recorded so it is not re-investigated.

## BOB-149 — Managed-plugin count diverges 43/42/48 across constitution, CLAUDE.md and the README badge; the badge is hand-maintained and unguarded

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-149/closure_evidence_20260922.md
**Severity:** Low
**Created-By:** Claude

Managed-plugin count diverges 43/42/48 across constitution, CLAUDE.md and the README badge; the badge is hand-maintained and unguarded

## BOB-221 — Invariant 30 has no RED-test allowance: a correctly-authored failing RED (mandated by §11.4.115/§11.4.224) makes the blocking gate FAIL — the constitution's own test-first discipline is gated against itself

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-221/closure_evidence_20260922.md
**Severity:** critical

WHAT: scripts/pre_build_verification.sh invariant 30 (CM-BASH-UNIT-TESTS-EXECUTED) enumerates suites by FILESYSTEM GLOB (:1196) and calls fail() on any non-zero exit. It therefore RUNS untracked suites, and it has NO concept of a test that is SUPPOSED to fail.

MEASURED: tests/pre_build/test_bob205_danger_roots_scope.sh exits 1 — correctly, because it is a RED test for BOB-205, an unfixed defect. Invariant 30 counts that as a gate failure. The predicted T042 verdict is FAIL, and this is one of its three blocking causes.

THE STRUCTURAL PROBLEM: §11.4.115 and §11.4.224 REQUIRE a RED authored FIRST and OBSERVED TO FAIL before the fix exists. §11.4.135 requires the RED to persist as the permanent regression guard. So the discipline mandates that failing tests exist in the tree between authoring and fixing — and the blocking gate treats their existence as a defect. Following the constitution correctly makes the gate refuse the commit. That is a §11.4.120 wrong-seam problem: the gate asserts "no suite fails" when the invariant it should assert is "no suite fails UNEXPECTEDLY".

WHY IT SURFACED NOW: this session authored FOUR REDs across parallel streams (BOB-204, BOB-205, BOB-207, BOB-212) — the first time the discipline was applied at this volume. Previously REDs were flipped GREEN within the same round, so the window never spanned a gate run. The defect is not new; the exposure is.

THE FORBIDDEN RESPONSES (§11.4.120): do NOT delete the RED to make the gate green; do NOT weaken invariant 30 to ignore failures; do NOT mark the RED skipped without a tracked reason. Each converts a real signal into silence.

FIX DIRECTION — this is §11.4.248's quarantine mechanism, which the constitution already specifies and this project has not wired: a RED declares its expected-failing status and its tracked item (a header marker, a naming convention, or a manifest), invariant 30 reads that declaration, and a declared-RED failure is reported as EXPECTED (not a fail) while an UNDECLARED failure still blocks. Crucially the declaration must EXPIRE or be tracked — §11.4.248 pairs quarantine with a stabilisation deadline precisely so "expected to fail" cannot become permanent cover. A RED whose item closes must flip GREEN or the gate should FAIL on the stale declaration.

ACCEPTANCE: (1) a declared RED does not block; (2) an UNDECLARED failing suite still blocks (the §11.4.201(1) guard — a fix that ignores all failures is strictly worse than the defect); (3) a declared RED whose tracked item is CLOSED blocks, so declarations cannot rot; (4) a paired §1.1 mutation removing the declaration-check makes the gate accept an undeclared failure -> gate FAILs.

DISCOVERY CHANNEL (§11.4.238): found by the T042 readiness preflight, before the endgame rather than during it. Not by the automated QA regime — the regime IS the thing that would have blocked.

=== CORRECTED 2026-08-26 — MY FIX DIRECTION IN THIS ITEM WAS WRONG, AND THE BLOCKER IS WIDER (§11.4.6) ===

CORRECTION 1 — §11.4.248 IS NOT THE MECHANISM. I wrote "this is §11.4.248's quarantine mechanism, which the constitution already specifies and this project has not wired." That is half right and the wrong half matters. §11.4.248(A) QUARANTINE targets FLAKY tests — its trigger is literally "two-consecutive-run-different-verdict OR rerun-after-red", and its remedy is to MOVE the suite to tests/quarantine/ and run the blocking suite WITHOUT it "so green means green". §11.4.248(B) PROTECTED-SPEC is a tag plus a required-reviewer gate on MODIFYING a regression test; it never says a test may fail.
A RED is DETERMINISTIC and MUST STILL BE RUN — §11.4.115(F) and §11.4.226 require the RED verdict to be PRODUCED as the evidence. Excluding it destroys the very artifact the discipline mandates. Merging the two would also let a genuinely flaky suite hide behind a RED declaration and vice versa. What §11.4.248 legitimately supplies, and what should be INHERITED rather than re-invented (§11.4.227), is the SHAPE: a by-name list + a tracked item + a deadline + a must-only-shrink ratchet.

CORRECTION 2 — THIS IS A LANGUAGE-PARITY GAP, NOT A DESIGN VACUUM. Conductor-verified: the project ALREADY runs this mechanism on the PYTHON side. pytest.mark.xfail(strict=True) is used deliberately for OPEN defects at tests/scaling/test_scaling_envelope.py:907 (BOB-167, documented in tests/scaling/README.md:64) and tests/stress/test_plugin_parsers_stress_chaos.py:90 — whose own comments carry the ratchet discipline verbatim ("it stays visible as xfailed in every report", "then remove this xfail"). So "declared expected-failure, strict so an unexpected pass fails" is ALREADY accepted policy in one language. The BASH side has no equivalent. That is the real gap.

CORRECTION 3 — BOB-221 IS NOT SUFFICIENT TO UNBLOCK T042. A full replication of invariant 30 measured RAN=38 FAILED=4 SKIPPED=2:
  rc=124 300s test_compute_badges_carrier_match.sh  <- a HANG, not a RED. Blocks independently. Filed separately.
  rc=1     3s test_ownership_gid_agreement.sh       <- BOB-207's RED (a SECOND in-glob RED; this item assumed one)
  rc=1     1s test_bob205_danger_roots_scope.sh     <- BOB-205's RED
  rc=127   9s test_check_cm_lan_routes_authenticated.sh <- CONTAMINATED: a sibling stream was writing lan_route_auth_analyzer.py during and after the run (§11.4.119 — the surveying stream did not own that resource and correctly declined to adjudicate). rc=127 is the §11.4.1 script-internal FAIL-bluff signature, not a product verdict either way. Returned to its owning stream.
ALSO: BOB-204's and BOB-212's REDs share tests/security/test_gitignore_swallow_is_loud.sh, which is OUTSIDE invariant 30's glob and executed by NOTHING (BOB-222) — they do not block today, and widening the glob would immediately add another blocker.

THE DESIGN, RECOMMENDED: two-place declaration + SSoT expiry + strict semantics. THREE independent facts must agree before a failure is excused — (1) the suite is listed in scripts/lib/expected_red.sh, a file the PRODUCING streams do not own; (2) the suite file itself carries `# EXPECTED-RED: <ID>` with the SAME id; (3) <ID> is OPEN in docs/workable_items.db, FAIL-CLOSED on unreadable store or unknown id (§11.4.252). Plus STRICT-XFAIL PARITY: a declared suite that PASSES blocks, which mechanically forces the ratchet to shrink in the same commit as the fix.

EXIT-CODE CONVENTION REJECTED ON MEASURED EVIDENCE — and I had flagged it as promising. The non-{0,1} exit space is ALREADY CLAIMED IN THIS REPO FOR THE OPPOSITE MEANING: test_gitignore_swallow_is_loud.sh uses exit 2 = "INSTRUMENT BROKEN or SECRET LEAK — verdict void", and test_bob205_danger_roots_scope.sh uses exit 3 = ABORT (instrument blind). Both were chosen precisely so a blind harness can never be read as a verdict. Overloading either for "expected red" would make a genuinely BLIND INSTRUMENT INDISTINGUISHABLE FROM A DECLARED RED — the gate would swallow exactly the failure class those codes exist to make loud. It also fails acceptance (4) (an integer carries no item id) and (3) (nothing to rot-check), and it puts the declaration inside the PRODUCER, collapsing producer!=gate (§11.4.240/§11.4.249).

HONEST BOUNDARY ON THE DESIGN (§11.4.240): it achieves separation by LOCATION and MULTI-PLACE AGREEMENT, not by true CAPABILITY, which §11.4.240 prefers. There is no PR/CODEOWNERS seam here to enforce capability — CLAUDE.md Hard Stop #1 removed all CI/PR gates, so the CODEOWNERS half of §11.4.248(B) is STRUCTURALLY UNENFORCEABLE in this project. What the design buys is that silencing a failure requires a coherent three-place story visible in a diff, instead of one comment line.

THE RED: tests/pre_build/test_bob221_expected_red_declaration.sh. It extracts invariant 30's loop and its blocking predicate VERBATIM FROM THE LIVE GATE BY CONTENT MARKER (never line number) and RUNS them against a hermetic scratch PROJECT_ROOT — so the logic under test is the gate's own text, not a paraphrase (§11.4.226 anti-echo). Measured RED: 3 of 5 properties unmet, exit 1. P3 is asserted on the blocking REASON, not merely on "it blocked" — today everything blocks, so a bare did-it-block check would pass FOR THE WRONG REASON and keep passing if the anti-rot half were never built. Polarity flip proven with the BYTE-IDENTICAL test file against a sandbox carrying the patch: exit 0, all five properties met. Four paired §1.1 mutations each kill exactly ONE property, one-to-one, no cross-talk.

THE PATCH: 72 lines, 4 hunks + one new file scripts/lib/expected_red.sh, `git apply --check` clean, NOT APPLIED. Operational note the landing commit must not miss: the table names test_bob205_danger_roots_scope.sh and test_ownership_gid_agreement.sh, but NEITHER carries an `# EXPECTED-RED:` marker today (verified 0 in both) — without those two one-line additions the gate blocks them with "declared but the file carries no matching marker", which is the fail-closed design working as intended, not a bug.

SEQUENCING RECOMMENDATION: (iii), a bounded variant of (i) — land the mechanism declaring exactly BOB-205, BOB-207 and this item's own suite, add the two missing markers, triage the rc=124 hang as its own item, return the rc=127 to its owner, THEN run T042.
THE HONEST COST, STATED NOT HIDDEN: this modifies the blocking gate BEFORE that gate has ever run clean, so the mechanism's first full-gate exercise IS the T042 run. The circularity is unavoidable and IS this item (§11.4.120 — a gate whose precondition is produced by the work it gates): a clean T042 run is impossible while any RED exists, so "validate the gate before changing it" cannot be satisfied. Risk reduced as far as possible without running the gate (proven-applicable patch, proven polarity flip, four biting mutations, P2 undeclared-failures-still-block asserted and mutation-proven) but NOT eliminated.
Against (ii) fix-the-four-defects-first: all four are Queued and genuinely deferred; BOB-212's fix direction is an explicitly unresolved §11.4.66 OPERATOR decision whose own test was deliberately written fix-direction-agnostic so as not to prejudge it — choosing (ii) means making that decision on the operator's behalf, plus four implementations and four reviews, and it STILL leaves the hang and the rc=127 blocking.

RECURSION NOTE: this item's own RED is in-glob and failing, so it is itself a 5th blocker until the mechanism lands — at which point its already-present marker and table row clear it. The mechanism is its own first customer.

## BOB-215 — boba-ctl authMethod() default branch silently resolves a typo'd or empty auth: key to SSH-key authentication instead of refusing

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-215/closure_evidence_20260922.md
**Severity:** major

WHAT: cmd/boba-ctl/main.go:498-509, authMethod(). Its default branch (:507) returns remote.AuthSSHKey. A deploy-registry entry whose auth: key is misspelled, empty, or set to an unrecognised value therefore resolves SILENTLY to SSH-key authentication rather than refusing to act.

WHY IT IS A §11.4.252 VIOLATION: this is a credential-selection decision on a path that also performs remote mutation and external side effects. §11.4.252 requires a path combining >=2 dangerous capabilities to FAIL CLOSED — verify every precondition, refuse when any is unverifiable, and name the unresolved precondition. Silently substituting a default credential MECHANISM for an unreadable declaration is the textbook fail-open shape: the operator's intent was not determined, and the code proceeded anyway using a method they may not have chosen.

WHY NO GATE CAUGHT IT: three independent reasons, each sufficient on its own — (a) cmd/boba-ctl is in no DANGER_ROOT (BOB-205); (b) even in scope, .go files are structurally unanalysable by the current gate (BOB-191); (c) this shape is a semantic default-branch decision, not one of the two text patterns the non-Python arms match. It was found by a human-equivalent read, which is precisely the §11.4.238 escape class.

HONEST QUALIFICATION (§11.4.6): cmd/boba-ctl/main.go has NO `_ = err`, NO empty `if err != nil {}`, and NO silent `return nil` today — grep-verified with a control needle against qBitTorrent-go/internal/config/config.go. This finding is the exception, not one of many; the scope hole around boba-ctl is otherwise LATENT (it hides nothing else live, it guarantees a future one lands unseen).

ACCEPTANCE: (1) an unrecognised/empty auth: value REFUSES with an error naming the offending key and its declared value, never silently defaults; (2) a RED driving a typo'd auth: and asserting today's silent SSH-key resolution, flipping to refusal post-fix; (3) golden-FALSE proving every LEGITIMATE auth: value still resolves correctly — a false refusal here would break real deploys (§11.4.201(1)).

DISCOVERY CHANNEL (§11.4.238): found by the BOB-205 verification stream while confirming boba-ctl qualifies as a §11.4.252 surface.

## BOB-207 — probe_location() is GID-BLIND: precondition verifies uid only while the repair fixes uid AND gid — false ok demonstrated live on this host, no privileges, no exotic filesystem

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-207/closure_evidence_20260922.md
**Severity:** critical

WHAT: scripts/lib/ownership.sh:299-320 probe_location() reads stat -c '%u' and compares against ownership_operator_uid (id -u). It NEVER reads '%g'. Meanwhile ownership_operator_gid is defined at scripts/lib/ownership.sh:50 and consumed ONLY by scripts/ownership_repair.sh:360 — so the REPAIR establishes uid AND gid, while the PRECONDITION that verifies the repair worked checks uid ONLY. The precondition can therefore report ok while exactly half the property the repair exists to establish is wrong.

MEASURED, LIVE ON THIS HOST, UNPRIVILEGED (a setgid directory is all it takes — no loopback, no mount, no sudo):
  dir: uid=1000 gid=10 mode=2755   (chgrp wheel + chmod g+s, both unprivileged)
  real file created there: uid=1000 gid=10
  probe_location verdict = ok  rc=0     <-- operator gid is 1000, file gid is 10

SEVERITY RATIONALE: this is the SAME CLASS that BOB-206 alleged (a probe reporting ok while ownership is only partly held) but on an axis that is LIVE rather than hypothetical, needs no unusual filesystem, and reproduces with two unprivileged commands. BOB-206 was dismissed; this is the real defect that investigation surfaced underneath it.

ACCEPTANCE: (1) probe_location reads and compares gid as well as uid, OR the asymmetry is deliberately justified in-source with the reason (if only uid matters to the user-visible goal, say so and explain why the repair sets gid at all); (2) a RED fixture builds the setgid directory above, observes ok pre-fix, flips to a refusal post-fix (§11.4.115); (3) a golden-FALSE fixture proves a correct uid+gid location is still ok (§11.4.201(1)); (4) whichever way it is resolved, precondition and repair agree on WHICH property they are talking about — that disagreement is the primitive defect (§11.4.250).

DISCOVERY CHANNEL (§11.4.238): found by the BOB-206 verification stream, not by the automated QA regime. No existing test exercises a gid mismatch.

=== CONFIRMED 2026-08-26, RED AUTHORED — AND THE FIX DIRECTION IS THE OPPOSITE OF WHAT THIS ITEM ASSUMED ===

CONFIRMATION (re-derived against the dirty tree; line numbers happen to match): probe_location() at scripts/lib/ownership.sh:299-320 reads stat '%u' twice (:308 file branch, :314 dir branch), compares against want at :301, and NEVER reads '%g'. ownership_operator_gid is defined at :50 and has EXACTLY ONE consumer — ownership_repair.sh:360 — verified across tracked AND untracked files, needle-proven (needle ownership_operator_uid -> 13 files, negative control -> 0; untracked sweep needle -> 8 files, ownership_operator_gid -> 0); every other hit is a docs/DB carrier or comment.
THE REPAIR SETS GID AT TWO SITES, not one: :719 chown -h "${OP_UID}:${OP_GID}" WRITES both, and :963 find_args selects on ( ! -uid OR ! -gid ).
FALSE ok REPRODUCED unprivileged (chgrp to a group from id -G + chmod g+s): dir uid=1000 gid=10 mode=2755, a REAL file created inside lands uid=1000 gid=10, probe_location verdict = ok rc=0. Needle arm: an absent path returns 'absent' rc=1 — the probe CAN refuse, so the ok is real.

DESIGN QUESTION ANSWERED: **NARROW THE REPAIR. gid is NOT load-bearing.** This item was filed assuming the PROBE was deficient. Measured, that is backwards.
 - With correct uid and gid=10: edit, read, rename, move, chmod, utime, delete are ALL PERMITTED — including recovery from chmod 000 with NO elevation. Owner-class bits are selected by uid match and chmod is owner-only, so the operator can always restore access.
 - Every FR-001 / FR-002 / FR-003 / FR-010b is phrased as "owned by the account". NO requirement mentions gid.
 - DECISIVE, conductor-verified in spec.md: the Constraints section blesses "Group-based workarounds (shared groups, permissive modes, access-control lists) are acceptable implementation routes", and Dependencies makes "shared group plus inherited permissions" NECESSARY if the container platform cannot map the in-container account to the operator's identity.
 => WIDENING THE PROBE would make FR-010 REFUSE TO START on a configuration the spec explicitly sanctions — a §11.4.201(1) false-positive refusal, the exact failure class this project keeps finding in its own gates.
 => AND THE REPAIR IS ALREADY DOING HARM: measured, after repair a new file inherits gid 1000 instead of 10 with the setgid bit still set and NO diagnostic. The repair silently dismantles a spec-sanctioned shared-group setup.

THE RED: tests/unit/test_ownership_gid_agreement.sh (NEW file, 253 lines, bash -n clean). It deliberately does NOT assert "the probe must call stat %g" — that is an implementation assertion that survives a cosmetic fix AND hard-wires one fix direction. It asserts the user-observable invariant: probe_location(L) == ok IFF ownership_repair.sh --dry-run selects ZERO items under L. Measured: 4 passed / 1 failed / EXIT=1, the failure being "the PRECONDITION certifies it (ok) while the REPAIR reports it broken (selects:2)".
VALIDATED AGAINST BOTH CANDIDATE FIXES from patched COPIES (production untouched): baseline FAIL(1) · narrow-the-repair PASS(0) · widen-the-probe PASS(0). Golden-FALSE passes in all three, so neither direction can go green by refusing everything. That is what makes this RED fix-direction-agnostic rather than a vote.

THE FIX, NOT APPLIED — scripts/ownership_repair.sh:963:
  -    find_args+=(\( ! -uid "${OP_UID}" -o ! -gid "${OP_GID}" \) -printf '%U\t%G\t%m\t%p\0')
  +    find_args+=(! -uid "${OP_UID}" -printf '%U\t%G\t%m\t%p\0')
KEEP chown OP_UID:OP_GID at :719 — one syscall, it gives a resolvable gid for the real 100999:100999 defect, and gid 1000 is a user-private group (milosvasic:x:1000:, no other members) so writing it NARROWS rather than widens, consistent with FR-015. Add a bounded justification in BOTH files stating the agreed property is uid.

HONEST COST (§11.4.120 reconciliation owed, NOT fake-passing): the entire existing repair suite uses gid mismatch as its proxy fixture (test_ownership_repair.sh:19-54, asserts at :445 and :1392) precisely because a foreign UID is not constructible unprivileged. Narrowing BREAKS those cases. They must be RE-BASED onto "the chown writes uid:gid", never fake-passed. Test-suite rework is not a reason to ship a runtime false refusal.

BOB-208 and BOB-209 both CONFIRMED by the same stream — see their items.

## BOB-208 — probe_location() does not check the want side: a failing id(1) yields a FALSE REFUSAL whose message names the correct uid as wrong (§11.4.201(1))

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-208/closure_evidence_20260922.md
**Severity:** major

WHAT: scripts/lib/ownership.sh:301 sets want="$(ownership_operator_uid)" with NO exit-code check and NO emptiness guard. The file runs under set -uo pipefail but NOT set -e, so a failing id(1) leaves want empty and execution continues.

MEASURED (id shimmed to fail): verdict = wrong-owner:1000 on a perfectly healthy location. The refusal message NAMES THE CORRECT UID AS WRONG, which is worse than a bare failure — it sends the reader to fix a value that is already right.

WHY IT MATTERS: §11.4.201(1) — a false-positive refusal is a FAIL-bluff of exactly equal severity to a false-negative pass. It halts real work and teaches operators to bypass the guard. And §11.4.201(4): on an unresolvable signal the guard must take the conservative-safe default AND SAY SO HONESTLY. 'Could not resolve the operator uid' is honest; 'wrong-owner:1000' when 1000 is correct is not.

LIKELIHOOD: low (id(1) rarely fails) — but unguarded, and it fails toward a misleading refusal rather than toward an honest unknown.

ACCEPTANCE: (1) the want side is checked for both rc and emptiness; (2) an unresolvable want yields a distinct honest verdict naming the unresolved precondition, never a wrong-owner claim; (3) a RED fixture shims id to fail and observes wrong-owner:1000 pre-fix, the honest verdict post-fix; (4) golden-FALSE: a healthy location with a working id is still ok.

DISCOVERY CHANNEL (§11.4.238): found by the BOB-206 verification stream reading the probe, not by the automated QA regime.

=== CONFIRMED 2026-08-26 ===
ownership.sh:301 has no rc guard and no emptiness guard, and the file runs without set -e. With id(1) shimmed to fail, on a location GENUINELY OWNED by uid 1000: verdict="wrong-owner:1000" rc=1 — the refusal NAMES THE CORRECT UID AS WRONG. Reproduced directly; not inferred from reading.

## BOB-209 — probe_location() stat guards are asymmetric halves, a stat failure is mislabelled unwritable, and the probe temp file has no EXIT trap (§11.4.14)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-209/closure_evidence_20260922.md
**Severity:** major

THREE DEFECTS IN ONE FUNCTION, scripts/lib/ownership.sh:299-320.

(1) ASYMMETRIC GUARDS. The file branch (:308) checks stat's EXIT CODE but not output emptiness. The directory branch (:314-316) checks EMPTINESS but not the exit code. Neither checks both. Each branch is blind to exactly the failure mode the other guards against.

(2) MISLABELLED VERDICT. A stat failure on an EXISTING file is reported as 'unwritable'. That is semantically wrong — stat failing is not a writability fact, and it sends the reader to check permissions on a path whose permissions may be fine. §11.4.6: state the real condition or state that it could not be resolved; do not substitute a different condition.

(3) UNTRAPPED CLEANUP (§11.4.14). rm -f "${probe}" at :315 is a plain statement, not a trap. An interrupt between mktemp and rm strands a .ownership-probe.XXXXXX file INSIDE A DECLARED LOCATION — and the declared set includes the git-tracked download-proxy/ tree, so the stranded file lands in version control's path. §11.4.14 requires cleanup on EVERY exit path via trap.

ACCEPTANCE: (1) both branches check rc AND emptiness; (2) a stat failure yields a verdict naming stat-failed, not unwritable; (3) cleanup moves into a trap covering interrupt paths; (4) a RED per defect — including one that interrupts between mktemp and rm and asserts no residue survives; (5) golden-FALSE proving the healthy path still returns ok.

DISCOVERY CHANNEL (§11.4.238): found by the BOB-206 verification stream. The verifying agent confirmed it left zero residue itself, needle-proven that its find could see.

=== CONFIRMED 2026-08-26 — ALL THREE ===
(1) ASYMMETRIC GUARDS: :308 checks rc ONLY (|| { echo unwritable; }); :314 + :316 check emptiness ONLY. Each branch is blind to exactly the failure mode the other guards.
(2) MISLABEL REPRODUCED: stat shimmed to fail on an EXISTING, demonstrably WRITABLE file -> verdict "unwritable", from BOTH branches.
(3) UNTRAPPED CLEANUP REPRODUCED: no trap anywhere in :299-320 (needle-proven — `trap` appears once ELSEWHERE in the same file, so the zero is real, not a blind instrument). An interrupt via timeout between mktemp and rm STRANDED a real file: .ownership-probe.c2noxU. And the exposure is confirmed material: download-proxy IS a declared location (config/owned_paths.yaml:142-146) containing 32 GIT-TRACKED files, so a stranded probe file lands inside the version-controlled tree.

## BOB-220 — ownership_repair setuid/setgid strip is a NO-OP on directories: GNU chmod 755 preserves setgid, so the in-source comment claims a strip that does not happen

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-220/closure_evidence_20260922.md
**Severity:** minor

WHAT: scripts/ownership_repair.sh:891-895 runs chmod 755 intending to strip setuid/setgid bits. Traced live: the chmod RUNS and SUCCEEDS, yet the mode stays 2755. Root cause measured — GNU chmod with a 3-DIGIT symbolic-equivalent octal PRESERVES the setgid bit on DIRECTORIES; only a 4-digit form (00755) or an explicit g-s clears it. The comment at :868-884 describes a strip that does not occur for directories.

EFFECT: benign today — the surviving setgid bit is not itself harmful, and no defect is known to follow from it. This is filed as a §11.4.6 accuracy defect: an in-source comment asserting behaviour the code does not perform. That matters because the next reader will trust it, and because a future security-relevant strip written against the same pattern would silently fail the same way.

RELATION TO BOB-207: the same stream measured that after repair a new file inherits gid 1000 with THE SETGID BIT STILL SET — the two facts compound. If BOB-207 is resolved by narrowing the repair (the recommended direction), the setgid survival becomes moot for that path but the misleading comment remains.

ACCEPTANCE: (1) either the strip is made real (00755 or g-s) or the comment is corrected to state that directories retain setgid — code and comment must agree; (2) if made real, a RED asserting mode 2755 -> 0755 on a directory, since the current form silently no-ops; (3) golden-FALSE proving a directory that SHOULD keep its mode is not gratuitously changed.

DISCOVERY CHANNEL (§11.4.238): found by the BOB-207 stream while tracing an unrelated behaviour. Not by the automated QA regime.

## BOB-210 — detect_rootless() header promises an unverified reading can never manufacture a refusal, but :413 emits a CONFIDENT rootful that reaches the R3 refusal — and the shim oracle shares the code's unvalidated premise (§11.4.245)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-210/closure_evidence_20260922.md
**Severity:** major

WHAT: scripts/ownership_precondition.sh:342-348 documents the docker branch of detect_rootless() as documented-not-measured (accurate — verified verbatim). The header then claims the branch is built so that 'an unverified reading can never manufacture a refusal'. IT CAN. Line :413 emits a CONFIDENT rootful verdict whenever docker info succeeds with non-empty output containing no name=rootless field. Only the FAILURE modes fall through to unknown (:387-394).

THE PATH TO HARM: PUID=0 is declared in docker-compose.yml:32 (and again for jackett — deliberate per project policy). With a confident rootful verdict, that reaches the R3 refusal at :517. So a genuinely ROOTLESS Docker host whose docker info output SHAPE differs from the documented one gets a FALSE REFUSAL produced by a branch the source itself admits was never measured — precisely the outcome the header promises is impossible.

THE ORACLE PROBLEM (§11.4.245 independence): the shim tests DO cover this path (tests/unit/test_ownership_rootless_detection.sh:283) — but the shim's output shape was authored from the SAME documentation as the code. Oracle and code share the unvalidated premise, so the test cannot discover that the premise is wrong. It confirms the code matches the doc; nobody has confirmed the doc matches Docker.

ACCEPTANCE: (1) either the header claim is corrected to match :413's real behaviour, or :413 is changed to yield unknown when the reading is unverified — the two must agree (§11.4.6); (2) the docker branch's premise is validated against REAL docker info output from a real rootless daemon, or the branch is honestly marked unmeasured at the point of USE, not only in the header; (3) if validation is operator-gated (needs a rootless Docker host), record it as such per §11.4.21 rather than leaving the header's promise standing.

ALSO VERIFIED GOOD, recorded so it is not re-investigated: the unknown branch is handled IDENTICALLY at both consumers (R3 :519-531, R4 :832-836 — both a named SKIP, both return 0, neither refuses), ROOTLESS_VERDICT is cached at :487 so both read ONE measurement, and the carrier-trap golden-FALSE fixture EXISTS (test_ownership_rootless_detection.sh:279-308 drives name=rootless-lookalike inside a profile path and must NOT read rootless; structural guard at :396-411 uses exact field equality, not substring).

DISCOVERY CHANNEL (§11.4.238): found by the BOB-206 verification stream.

## BOB-202 — ownership_repair tab-delimited scope read collapses an empty field - an omitted 'kind' silently shifts every later field and turns optional:true into non-optional

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-202/closure_evidence_20260922.md
**Severity:** Medium

WHAT: scripts/ownership_repair.sh:493 reads parsed scope rows with 'while IFS=$'\t' read -r e_path e_kind e_opt e_pres e_rec'. A scope entry that OMITS 'kind' emits the row '<path>\t\t1\t0\t1'. TAB is an IFS-WHITESPACE character in bash even when IFS is set to it explicitly, so a RUN of consecutive tabs collapses into ONE delimiter instead of delimiting an empty field. Every field after the omission shifts left by one.

MEASURED 2026-08-26 on GNU bash 5.2.37, control-needled (the with-field case was run FIRST and produced output, proving the instrument sees; an earlier probe of mine returned nothing for BOTH cases because printf lacked a trailing newline - an 11.4.201(7)(b) false-null I discarded rather than reported):

  kind PRESENT: path=[P] kind=[dir] opt=[1] pres=[0] rec=[1]
  kind EMPTY:   path=[P] kind=[1]   opt=[0] pres=[1] rec=[]

CONSEQUENCE: 'optional' is read out of 'preserve_mode's slot. An entry declared 'optional: true' is therefore treated as NON-optional, so an absent path that should skip honestly instead becomes a hard failure - and 'preserve_mode'/'recursive' are likewise read from the wrong slots, with 'recursive' arriving EMPTY. The shift is silent: no parse error, no diagnostic, no refusal.

REACHABILITY: NOT reachable from the shipped config/owned_paths.yaml - all six declared entries carry 'kind' (verified). This is a latent defect in the reader, not a live misbehaviour of the product today.

PROVENANCE: surfaced out-of-band by the T028 round-5 remediation agent while isolating an unrelated instrument slip, and deliberately left unfixed and unfiled by it because (a) ownership_repair.sh had to stay at hash ae025b74602414ca for that round's do-not-regress set, (b) it was outside that round's two-NIT remit, and (c) it had not root-caused whether the repair belongs in the parser, the consumer, or the schema. That judgement was correct; this item is the filing it deferred. Independently re-measured by the conductor before filing - not accepted on report.

11.4.238 COVERAGE-ESCAPE NOTE: no automated check found this. It was found by a human-directed agent isolating a different problem. Per 11.4.238 the coverage gap is itself a defect of equal standing to the bug, and closing only the bug is the violation.

ACCEPTANCE: (1) root-cause the correct layer - parser (never emit a row with an empty field), consumer (read with a delimiter that is not IFS-whitespace, or read positionally), or schema (make 'kind' mandatory and REFUSE an entry lacking it, consistent with the whole-run refusal already landed for empty expansions); the choice is operator-owned per 11.4.66 because it changes the scope-file contract; (2) a fixture with an omitted 'kind' and 'optional: true' asserting the entry is treated as OPTIONAL (or the row refused), RED-first against current code; (3) a golden-FALSE proving a fully-specified row still parses identically - 11.4.201(1), the reader must not start refusing valid scopes; (4) paired 1.1 mutation restoring the collapsing read so the fixture FAILs; (5) an automated check that would have caught it, per 11.4.238.

PRECEDENT FOUND 2026-08-26 (surfaced by the T028 round-5 reviewer, independently verified before recording): the SIBLING script scripts/ownership_precondition.sh ALREADY documents this exact collapse class at lines 565-578 and already ships the repair as split_tsv() at line 579 (used at 437, 699, 775). Its in-source note carries a real forensic measurement dated 2026-08-21: the FIRST version of that script used the collapsing read and reported "no compose service mounts this location" for config/ and for the download root WHILE FIVE SERVICES MOUNT THEM - a false statement about what was checked, produced by the instrument rather than the system, which its own comment classifies as the 11.4.201(7)(c) 'the path is part of the instrument' failure. It also records why the unit suite could not see it: the fixture scope has no compose service at all, so only running the real invocation against the real scope surfaced it.

WHAT THAT CHANGES FOR THIS ITEM: (a) acceptance-criterion (1) 'root-cause the correct layer' now has a PRECEDENT rather than an open design question - the consumer layer, via a split_tsv-style reader that does not use tab-as-IFS; adopting the sibling's existing function is preferable to inventing a second dialect (11.4.251 - two answers to one question across two files that read the SAME scope rows is exactly the divergence that produced the round-1 'two readers of one scope file disagree' finding); (b) this is a RECURRENCE of a class already diagnosed and closed once in this codebase, not a novel discovery - the fix landed in one reader on 2026-08-21 and the sibling reader kept the collapsing form, which is the 11.4.238 escape shape at the code layer: the lesson was captured in a comment instead of in a check; (c) the 11.4.238 coverage-escape note above is SHARPENED - the sibling's own comment already states that a fixture-scope suite cannot see this class, so the required automated check must exercise a row with a genuinely empty middle field, not merely a well-formed one.

## BOB-198 — qbittorrent-proxy-go registers CORS, Logger and rate-limit middleware but no auth at all — 22 LAN-bound routes open including download and hook deletion

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-198/closure_evidence_20260922.md
**Created-By:** Claude
**Assigned-To:** milos85vasic

**OPERATOR DECISION (2026-08-26, §11.4.66): REFUSE TO START LAN-BOUND**

The Go profile gets a boot-time guard: bind loopback only, or refuse to start. It does NOT get auth middleware in this cycle. Rationale carried with the decision: the profile is opt-in via --profile go, was not running when measured, and is used for development — so closing the exposure costs a guard rather than a parity implementation. Options not chosen: write auth middleware to parity with the Python route set (real work, and it would partially un-defer BOB-101); document dev-only with no guard (rejected — nothing would enforce it, and the next --profile go run on this network silently re-opens 22 routes). ACCEPTANCE: a boot-time check that resolves the listener's bind address and refuses to start when it is not loopback, with a paired §1.1 mutation proving the check FAILs on a 0.0.0.0 bind, and a golden-FALSE proving a loopback bind is NOT refused (§11.4.201(1)). Scope reminder recorded so it is not lost: this is NOT covered by BOB-101's parity deferral, which was about ports; folding it in would be a §11.4.112(5) verdict leak.

Recorded as consumer DATA per §11.4.35 — the operator's stated choice, not an agent inference. Options not chosen are named so a future reader does not re-litigate a settled call.

--- prior item text follows ---

MEASURED, conductor-verified independently of the reporting subagent. qBitTorrent-go/cmd/qbittorrent-proxy/main.go registers exactly three middlewares, at lines 62, 63 and 68: middleware.CORS, middleware.Logger, middleware.GinRateLimit. There is NO authentication middleware and no per-route auth dependency. main.go:119-121 binds addr=":<port>" which is ALL interfaces, so every route is LAN-reachable when the profile runs.

SCOPE: 22 routes, of which the mutating ones matter most - POST /api/v1/download, POST /api/v1/magnet, DELETE /api/v1/hooks/:id, POST and DELETE /api/v1/schedules. A LAN peer can queue downloads and delete webhook configuration with no credential.

PARITY GAP, stated as fact: PUT /api/v1/theme is auth-gated in the Python service and open in Go. The same asymmetry holds for the download, hooks and schedules mutations. Two implementations of one advertised surface disagree about whether it needs a credential.

RELATIONSHIP TO BOB-101 (Go parity deferred past v1.0.0, operator decision 2026-08-26): that deferral covered PORT parity - the Go container binding :7186 and :7188 as well as :7187. It did NOT cover an authentication hole, and the operator was not asked about one, because the hole had not been measured when the question was posed. Treating this as covered by the deferral would be a 11.4.112(5) verdict leak: citing a bounded decision outside the scope its evidence supports. This item stands separately and its severity is NOT settled by BOB-101.

MITIGATING FACT, so severity is not overstated: the Go profile is opt-in via --profile go and was NOT running at measurement time (the container list showed qbittorrent-proxy, the Python service, with no Go sibling). The exposure is latent, not live.

ACCEPTANCE: either auth middleware landed in the Go service with parity to the Python route set, or an explicit operator decision recording the Go profile as dev-only that must refuse to start LAN-bound - with a guard enforcing whichever is chosen.

## BOB-171 — TRUST_FORWARDED_FOR keys rate-limit buckets on the LEFTMOST X-Forwarded-For element, which is client-forgeable, so header rotation mints unlimited budgets and defeats the LRU cap on both :7186 and :7187

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-171/closure_evidence_20260922.md
**Severity:** Low
**Created-By:** Claude
**Assigned-To:** Claude

WHAT. Both rate limiters key their per-client bucket on the LEFTMOST element of X-Forwarded-For when TRUST_FORWARDED_FOR is enabled: download-proxy/src/api/rate_limit.py:117-123 (:7187) and the new stdlib limiter in plugins/download_proxy.py (:7186), which was deliberately built to exact policy parity with it.

That element is CLIENT-SUPPLIED. An honest reverse proxy APPENDS the peer address to the RIGHT of whatever arrived, so the leftmost entry is whatever the client sent — attacker-controlled by construction, not by misconfiguration. Consequences with the flag on: (1) rotating a forged leftmost value mints an unlimited sequence of fresh buckets, which is total bypass of the limit the flag is supposed to make MORE accurate; (2) it also defeats the LRU/idle-reap cap, since each forged identity is a distinct key — the bucket map is a memory-growth surface bounded only by the cap, and the cap's eviction then discards the budgets of REAL clients to make room for forged ones.

NOT EXPLOITABLE AS DEPLOYED TODAY, and that is why this is Low, not High. TRUST_FORWARDED_FOR defaults OFF at both sites, and the deployed stack runs network_mode host with no reverse proxy in front (verified across all five compose services), so peer addresses are real client IPs and no NAT collapse occurs. The defect is latent: it arms the moment someone puts a proxy in front and turns the flag on to recover real client IPs — which is exactly the situation the flag exists for. The failure mode is therefore 'correct-looking configuration change silently disables the limiter', not 'currently broken'.

PROVENANCE. Raised as MINOR-3 by the independent reviewer of the BOB-111 rate-limiter work and independently confirmed by the implementing agent, which noted it at BOTH source sites as a tracked follow-up rather than fixing it in that change. Filed here because neither agent has write access to the tracker.

WHY IT COVERS BOTH PORTS. :7186's limiter was built to deliberate policy parity with :7187's, including this parsing. Fixing one and not the other would leave the two surfaces disagreeing on client identity — worse than the shared defect, because it becomes surface-dependent and untestable as a single invariant.

ACCEPTANCE. (a) Replace leftmost-element parsing with a trust-aware resolution at BOTH sites: either rightmost-minus-N-trusted-hops, or a trusted-proxy CIDR allowlist where only a peer inside the allowlist may assert XFF at all — the choice is a deployment-topology decision and should be recorded, not assumed. (b) A test that forges a rotating leftmost element and asserts the bucket key does NOT rotate, per site. (c) Paired §1.1 mutation: restore leftmost parsing and the test must FAIL. (d) Negative control (§11.4.201(1)): with TRUST_FORWARDED_FOR OFF, the header must be ignored entirely and keying must fall back to the peer address — a guard that starts honouring XFF when the flag is off would be a worse defect than the one being fixed. (e) Honest boundary: this closes header-forgery bypass; it does not make per-IP limiting fair behind NAT, where many real users legitimately share one address.

NOT CLAIMED. No change made. Both sites still parse leftmost; the flag still defaults off.

## BOB-217 — plugin_update_automation downloads executable plugin code from third-party personal GitHub repos and gates it with a SYNTAX check only — no signature, no pinned commit, no hash allowlist

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-217/closure_evidence_20260922.md
**Severity:** critical

WHAT: tools/plugin_update_automation.py update_plugin() combines three §11.4.252 dangerous capabilities and is gated by nothing that could stop a hostile payload:
 - UNTRUSTED INPUT: 14 URLs across four GitHub repositories, THREE of which are third-party PERSONAL repos, not the official qbittorrent organisation.
 - MUTATION: writes plugins/<name>.py.
 - DEFERRED CODE EXECUTION: qBittorrent EXECUTES those engine files. The bytes fetched over the network become running code on the operator's host.
The ONLY validation is compile(content, "<string>", "exec") at tools/plugin_update_automation.py:213 — conductor-verified as the sole compile call. That is a SYNTAX check. A syntactically valid file is exactly what a hostile payload is. There is NO signature verification, NO pinned commit SHA, NO hash allowlist, NO provenance check of any kind.

§11.4.252 requires a path combining >=2 dangerous capabilities to FAIL CLOSED — verify every precondition, refuse when any is unverifiable. This path combines THREE and verifies none of them. §11.4.246's supply-chain clause is the direct counterpart: dependencies are either vendored hash-verified, provenance-attested, or mirrored through a hash-pinning registry — an unattested public source is an integrity risk, and here the unattested public source becomes EXECUTED CODE.

THE SHARPEST FACT ABOUT THIS FINDING: the fail-closed gate produced THREE FALSE POSITIVES in this same file (:189, :198, :215 — all triaged FALSE POSITIVE, see BOB-214's correction) while MISSING this, the one genuine dangerous combination in it. That is the §11.4.201 both-directions failure — false-positive and false-negative — demonstrated inside a single file. It is the strongest available evidence that the detector classifies by local syntactic shape and never consults semantic role (the §11.4.250 primitive named in BOB-191/BOB-216).

REACHABILITY, STATED HONESTLY (§11.4.6): the script is invoked by NOTHING — control-needle-proven (91 needle hits, 0 negative control) it is referenced only by its own README, its own docstring, and a tracker note; zero hits across *.sh / *.yml / *.py / Makefile outside tools/. Its own README self-declares "not invoked by the normal start/stop flow". Last functional commit 2026-04-12. So this is NOT live in any automated path. It IS reachable by a hand-run --update, which is exactly what the tool exists for. Severity is Critical on the capability combination, bounded by that reachability — not on an active exploitation path.

ACCEPTANCE: (1) plugin sources are pinned (commit SHA or content hash) and verified before write; (2) an unverifiable source REFUSES and names which check failed (§11.4.252) rather than proceeding on a syntax pass; (3) the compile() call is documented in-source as a syntax check that is NOT a safety gate, so nobody reads it as one; (4) a RED serving a syntactically-valid hostile payload and asserting it is REFUSED pre-fix-absent / post-fix-present; (5) golden-FALSE proving a legitimate pinned update still succeeds (§11.4.201(1)).

DISCOVERY CHANNEL (§11.4.238): found by the concealed-hits triage stream while establishing that the gate's four hits in this area were false positives. Not by the automated QA regime — and the regime that WAS pointed here reported the wrong three lines.

## BOB-224 — tests/unit/test_compute_badges_carrier_match.sh HANGS to the full 300s timeout (rc=124) and blocks invariant 30 independently of any RED-test question

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-224/closure_evidence_20260922.md
**Severity:** critical

WHAT: a replication of invariant 30 (same glob, same skip list, same BOBA_PREBUILD_NESTED=1, same timeout 300) measured RAN=38 FAILED=4 SKIPPED=2. One of the four failures is tests/unit/test_compute_badges_carrier_match.sh exiting **rc=124 after the FULL 300 seconds** — it does not fail, it HANGS.

WHY IT IS FILED SEPARATELY AND URGENTLY: it blocks invariant 30, and therefore T042, INDEPENDENTLY of BOB-221. The assumption in BOB-221 that landing an expected-RED mechanism unblocks T042 is FALSE as stated — two of the four failures are REDs, one is this hang, one is contaminated. Landing the mechanism alone leaves T042 blocked by this suite.

IT MUST NOT BE SILENCED BY A DECLARATION. A hang is a §11.4.232(C) liveness failure, not a verdict: a wedged op and a progressing op both look like "not finished yet", and marking it expected-to-fail would convert a §11.4.201(6) false-null into permanent cover. That is exactly the abuse the expected-RED design property (2) exists to prevent, so it must be triaged as its own defect.

INVESTIGATION DIRECTION (§11.4.102 first, no guessing): rc=124 is the timeout(1) signature. Determine WHERE it wedges — a consumer blocked on an unclosed producer write-end is the documented shape here (§11.4.201(12) records that a background watchdog spawned inside a $(...) command-substitution inherits the pipe write-end, and an early disarm orphans its sleep grandchild, so the substitution stalls for the FULL budget while every verdict and exit code stays CORRECT). That signature — full budget, correct verdicts — matches rc=124 exactly and should be the FIRST hypothesis tested, not the last. The countermeasure is documented: redirect the watchdog subshell fds away from the cmd-subst pipe, or have the probe write to a file.
Do NOT assume that is the cause; it is the highest-prior hypothesis given the recorded precedent.

ACCEPTANCE: (1) the wedge point is identified with captured evidence, not inferred; (2) the suite completes deterministically well inside the budget; (3) a RED reproducing the hang, so a regression cannot silently re-wedge (a timeout-based assertion, since the failure IS the duration); (4) NOT closed by a declaration or by raising the timeout — raising the budget hides it.

FILE DATE: the suite is dated 2026-08-21, so the hang predates this session.

DISCOVERY CHANNEL (§11.4.238): found by the BOB-221 design stream while surveying invariant 30 more widely than its brief required — the T042 preflight had verified only 3 of 38 suites and stated that boundary honestly, which is what prompted the wider survey.

## BOB-165 — Every documented python3 -m pytest command fails at collection: user-site rpds carries a 3.13 ABI extension under python 3.14

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-165/closure_evidence_20260923.md
**Severity:** High
**Created-By:** surfaced while capturing closure evidence for BOB-092; diagnosed rather than worked around

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-21T20:00:08Z
**Reported-By:** surfaced while capturing closure evidence for BOB-092; diagnosed rather than worked around

**What (the report, verbatim):**
This is a STALE-ABI-AFTER-INTERPRETER-UPGRADE defect, not a missing package. The package is installed; its compiled half is built for the previous interpreter. That distinction matters because 'pip install rpds-py' style advice can appear to succeed while leaving the 313 artefact in place.

WHY IT WAS NOT NOTICED EARLIER, stated as fact: the paths that DO work all avoid system python3. ci.sh selects an interpreter through _select_python; the long-running suites in this session ran .venv/bin/python -m pytest and passed. So the automated regime is green while the DOCUMENTED operator command is broken -- an 11.4.238-shaped gap, since the escape was found by an agent capturing evidence rather than by the regime.

WORKAROUND (measured, not theorised): PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 with the needed plugins passed explicitly (-p pytest_timeout ...) avoids the schemathesis autoload that drags in jsonschema -> referencing -> rpds. That is a workaround, NOT the fix: it silences the import path rather than repairing the install, and it will surprise the next person who runs the documented command verbatim.

RELATED, and worth deciding together rather than twice: BOB-154 wants .venv rebuilt on 3.12 to match the container (which runs CPython 3.12.13 while both system and venv run 3.14.6). There are therefore THREE interpreters in play. Whoever rebuilds the venv should confirm rpds resolves for the TARGET interpreter afterwards, or this same class reappears one directory over.

HONEST BOUNDARY (11.4.6): this item does NOT claim any test is wrong or any product code is broken. The product and the venv-run suites are unaffected. What is broken is the documented entry point.

**Affected scope / file-scope manifest:**
host user site-packages (~/.local/lib/python3/site-packages/rpds/); every CLAUDE.md-documented 'python3 -m pytest ...' invocation; any tooling that uses system python3 rather than .venv/bin/python

**Reproduction / context:**
python3 -m pytest tests/e2e/test_live_stack_evidence.py -q --import-mode=importlib  ->  ModuleNotFoundError: No module named 'rpds.rpds', raised during collection via the schemathesis plugin autoload -> jsonschema -> referencing._core -> rpds. MEASURED root cause: system python3 is 3.14.6, but ~/.local/lib/python3/site-packages/rpds/ ships rpds.cpython-313-x86_64-linux-gnu.so -- an extension built for 3.13. rpds/__init__.py does 'from .rpds import *', and a 313-tagged .so is not importable by 3.14, so the submodule genuinely does not exist for this interpreter. The venv is CORRECT and unaffected: .venv/lib64/python3/site-packages/rpds/ ships rpds.cpython-314-x86_64-linux-gnu.so and '.venv/bin/python -c import rpds' succeeds.

**Acceptance criteria:**
python3 -m pytest tests/unit/ -v --import-mode=importlib -- the command CLAUDE.md documents -- reaches collection without ModuleNotFoundError, OR CLAUDE.md is corrected to document the supported runner explicitly. Either way the documented command and the working command agree (11.4.99: a guide that misleads is the documentation-layer equivalent of a PASS-bluff).

WORKAROUND SIDE EFFECTS MEASURED 2026-08-21 — the recipe is not free, and the item previously implied it was. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 disables ALL plugin autoload, not just the broken one, so anything the suite silently relied on must be re-enabled by hand:

  - It BREAKS 5 pre-existing env-dependent tests in tests/unit/test_plugin_rutracker.py — TestConfig::test_default_mirrors, test_env_mirrors_override, test_get_env_with_default, test_get_mirrors_from_env_empty, test_get_mirrors_from_env_whitespace — which need an autoloaded env plugin. PROVEN not caused by any in-flight change: running HEAD's OWN copy of that file under identical flags produces the same 5 failures.
  - It makes --timeout=60 (set in pyproject.toml) an UNKNOWN ARGUMENT unless -p pytest_timeout is passed explicitly, so pytest.mark.timeout is silently inert under the naive recipe — a test believed to be time-bounded is not.
  - With autoload ON and only schemathesis disabled (-p no:schemathesis), that same file is 96/96 green.

CONSEQUENCE FOR ANYONE USING THE WORKAROUND: `-p no:schemathesis` alone is strictly better than blanket autoload-disabling where it suffices, because it removes only the broken plugin. Where the blanket form IS used, -p pytest_timeout must be added or timeouts are inert, and the 5 env-dependent failures must be recognised as workaround artifacts rather than filed as defects. That last point is the real risk: the workaround manufactures failures that look exactly like product defects.

This does not change the root cause (the venv's rpds ships a cpython-313 ABI tag CPython 3.14 cannot import) or the fix (rebuild the venv — BOB-154). It documents that the interim recipe has a blast radius, so nobody reads a workaround artifact as a regression.

## BOB-181 — Export generator silently ignores a path argument and always scans the whole tree

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-181/closure_evidence_20260923.md
**Severity:** High
**Created-By:** Claude
**Assigned-To:** Claude

WHAT: scripts/generate_markdown_exports.sh accepts no arguments. It unconditionally scans PROJECT_ROOT/*.md, docs/ recursively and scripts/ recursively (scan loops at lines 105/111/116 as of 2026-08-23; they were 96-109 when this was filed — line numbers shifted with the BOB-169 fix, the substance is unchanged and was independently verified by execution: invoking the generator with an explicit path produced an out-of-scope export and NOT the requested one), and PROJECT_ROOT is derived from BASH_SOURCE (line 17). A caller who writes 'bash scripts/generate_markdown_exports.sh docs/qa/SOME/file.md' gets a WHOLE-TREE run with the argument silently discarded.

WHY IT MATTERS: the caller reasonably believes the run was scoped to one file. It was not. In a shared checkout with parallel work streams this regenerates any export whose .md is newer than its derived files anywhere in the tree -- landing artifacts in other streams' scopes and, with the BOB-068 auto-commit hazard, into another stream's commit.

CLASS: a false affordance -- the script's interface implies a capability it does not have (11.4.201: an interface must mean what it claims).

FIX DIRECTION: either accept optional path arguments and honour them (scoping the run to exactly those files), or REFUSE with a clear message when arguments are passed. Silently discarding them is the one option that must not remain.

ACCEPTANCE: passing a path either scopes the run to it, or exits non-zero naming the unsupported argument. A RED capturing today's silent-discard behaviour first (11.4.115).

LIVE INSTANCE, MEASURED 2026-08-23 (this is no longer hypothetical):
During the BOB-169 fix the conductor invoked the generator with an explicit path to regenerate ONE document. The argument was discarded and the whole tree was scanned. It generated docs/qa/BOB-174/DESIGN_DECISION.{html,pdf,docx} at 11:50 -- a SIBLING STREAM's document, while that stream's author was still editing the source (.md mtime 12:00). The exports were therefore stale on arrival, and additionally carried the pre-fix BOB-169 charset defect. The sibling author independently reported them as stale in its own hand-off, having no idea another stream had created them.

SECOND-ORDER LESSON worth keeping with this item: the conductor's attempt to verify the blast radius ALSO failed, and failed silently. 'git status --porcelain | grep -E "\.(html|pdf)$"' returned only its own files and read as clean -- but docs/qa/BOB-174/ is an UNTRACKED DIRECTORY, which porcelain collapses to a single line, so the grep was structurally incapable of seeing the files inside it (11.4.201(7)(a): matched the wrong surface; the quiet zero read as absence). The instrument that DOES see it is 'find <dir> -newermt <t>'. Any future verification of 'which files did this run touch' must not use porcelain output as the corpus.

## BOB-193 — SSE result loss is add-before-yield: a raising emit permanently drops a result and the dedup set already recorded it

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-193/closure_evidence_20260923.md

WHAT: in download-proxy/src/api/streaming.py the dedup set is written BEFORE the yield — seen_hashes.add() / seen_hashes_local.add() execute at :317 and :356 ahead of emitting. If format_event raises, the result is never sent AND its hash is already recorded, so it is permanently dropped. Independently verified by the §11.4.209 reviewer at both sites: mid-search the hash persists across subsequent polls so the result never re-emits; at completion the stream breaks immediately after, so there is no later chance either. Results later in the SAME batch are not yet added and do re-emit on the next poll, which is why the observed symptom is partial loss rather than total. WHY IT IS FILED SEPARATELY: the §11.4.252 fail-open pass made this loss OBSERVABLE by adding a log line, which is the right first move — but observability is not repair. The underlying at-most-once semantics remain, and per §11.4.226(5) a mitigation cannot close the defect it mitigates. THE DECISION IS A REAL TRADE, not an oversight to correct blindly: moving to add-after-successful-yield gives at-least-once, but a DETERMINISTIC serialization failure would then retry the same result on every poll forever — trading silent loss for a hot loop. Options are (a) keep at-most-once and treat the log line as the contract, (b) add-after-successful-yield with a bounded per-hash retry budget, (c) add-before-yield but remove the hash on emit failure so exactly one retry occurs. ACCEPTANCE: an explicit decision recorded, implemented, and covered by a test that drives a raising emit and asserts the chosen semantics — with a RED observed first per §11.4.115. Raised as MINOR-1 by the independent review of the fail-open batch; filed rather than absorbed so the residual defect is not retired along with the logging that revealed it.

## BOB-229 — Two qBittorrent-WebUI-credentials gate/test files never committed since 2026-09-01 — silently swallowed by .gitignore's *credentials* glob

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-229/closure_evidence_20260923.md
**Severity:** Critical
**Created-By:** AI

Caught live by scripts/pre_build/check_gitignore_swallow.sh (BOB-212's new invariant 56), the very first real-repo run after it was wired in. scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh and tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh existed on disk (executable, dated 2026-09-01) and were in DAILY FUNCTIONAL USE by pre_build_verification.sh invariant 53 (CM-QBITTORRENT-WEBUI-CREDENTIALS, passing every run this session) yet were NEVER tracked by git: git ls-files returned nothing, git status --short returned nothing (the exact BOB-212 false-null), git check-ignore confirmed .gitignore:31:*credentials* was the blocking rule. Both files existed ONLY on this local checkout — a fresh clone, any other environment, or any disk loss would have silently lost an entire gate implementation plus its self-validated paired-mutation meta-test with zero signal. FIX: added explicit ! negation lines for both exact paths to .gitignore (matching the existing hand-maintained allowlist pattern at lines 34-50), confirmed git status now shows them as untracked-and-visible, confirmed scripts/pre_build/check_gitignore_swallow.sh now reports OK, confirmed both files are still functional (bash -n clean, and the meta-test's own 8-case paired-mutation self-check passes 8/8). This item exists to record the incident per this project's own §11.4.202 reporting-directive discipline (every discovered defect lands as a tracked item) even though it is being closed in the same session it was found.

## BOB-201 — ownership_repair lexical fence does not resolve intermediate symlink components - a static symlink can steer the walk outside the declared scope

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-201/closure_evidence_20260923.md
**Severity:** Medium

WHAT: scripts/ownership_repair.sh fences declared scope entries LEXICALLY (string normalisation + prefix/traversal refusal). A lexical fence cannot see a symlink sitting at an INTERMEDIATE path component. A static (already-present, no race required) symlink in the middle of an otherwise-legal declared path steers the recursive walk at a tree the operator never declared. Measured by the T028 round-2 independent reviewer as surviving mutation M5.

WHY IT IS FILED SEPARATELY: the in-source honest-boundary note and Case 24 fixture assert this reach is 'tracked as BOB-159'. It is NOT. VERIFIED 2026-08-26 by direct query: BOB-159's description is 4685 chars with ZERO occurrences of 'symlink' or 'intermediate' (control-needled - the body is readable through the same query path), and no item in the tracker recorded this reach at all. A dangling tracker citation means a real defect is recorded NOWHERE - the 11.4.214 lost-defect shape, where the pointer looks like coverage and is not. This item IS that record; the in-source note must now cite THIS id.

SCOPE / SEVERITY BOUNDS, stated honestly (11.4.6): the reach is BOUNDED, not arbitrary. It requires an attacker or accident to have already placed a symlink inside a declared scope path. It is NOT reachable from the shipped config/owned_paths.yaml as it stands (shipped-scope control needle: 6 rows, RC=0). It is a real widening of what a recursive chown can touch, not a theoretical one - the reviewer measured it, no race needed.

WHAT THIS ITEM DOES NOT CLAIM: that the lexical fence is broken. The fence does what it says - it refuses lexical escapes ('/', system trees, '..' climbs) and was verified doing so under 12 reviewer-authored mutations. This is a documented LIMIT of lexical fencing, now recorded as a real item instead of a citation to an unrelated one.

ACCEPTANCE: (1) decide deliberately and record the decision - resolve components (realpath/-P semantics) and re-fence the resolved path, OR keep the lexical fence and state the limit as an accepted operator-owned risk; the choice is operator-owned per 11.4.66 because resolving makes the fence depend on filesystem state at check time, which has its own failure modes; (2) if resolution is chosen, a golden-FALSE set proving legitimate symlinked-but-in-scope download roots still walk (11.4.201(1) - a fence that over-refuses is a FAIL-bluff of equal severity); (3) the in-source note and the Case 24 fixture cite THIS item, not BOB-159; (4) paired 1.1 mutation: restore the un-resolved behaviour and the fixture MUST fail.

## BOB-212 — .gitignore deny-all *credentials* glob plus a hand-maintained allowlist silently swallows NEW credential-named source files — a false-null in the commit path itself

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-212/closure_evidence_20260923.md
**Severity:** critical

WHAT: .gitignore:31 is a deny-all glob *credentials*, followed by a HAND-MAINTAINED per-file allowlist of ! exceptions (lines 34-50). Any NEW source file whose name contains 'credentials' (or 'creds') is silently ignored: git add refuses it and git status shows NOTHING. The author gets no signal at all — the file simply does not exist as far as the commit path is concerned.

HOW IT SURFACED: the BOB-204 stream authored a RED test named credentials_failclosed_test.go. It vanished. The agent noticed only because it went looking for the file it had just written. It renamed to bob204_failclosed_test.go to escape both *credentials* and *creds*, and the file became visible. A silent deliverable loss, caught by luck rather than by any gate.

INDEPENDENTLY RE-CONFIRMED BY THE CONDUCTOR, control-needle proven:
  git check-ignore -v --no-index qBitTorrent-go/internal/jackettapi/credentials_failclosed_test.go
    -> .gitignore:31:*credentials*   (IGNORED)
  git check-ignore -v --no-index qBitTorrent-go/internal/jackettapi/zzz_probe_test.go
    -> no match (NOT ignored)  <-- the needle: instrument proven seeing, so the hit above is real
  git check-ignore -v --no-index frontend/e2e/credentials.spec.ts
    -> .gitignore:31:*credentials*   (IGNORED)
  git ls-files --error-unmatch frontend/e2e/credentials.spec.ts -> tracked

SECOND, LATENT INSTANCE: frontend/e2e/credentials.spec.ts is matched by the same rule and survives ONLY because it is already tracked (git honours the index over .gitignore for tracked paths). Delete-and-re-add it — an ordinary refactor, a branch operation, a file move — and it disappears silently. It is one routine operation away from being lost.
(For contrast, credential-edit-dialog.component.spec.ts is genuinely safe: it is covered by the DIRECTORY rule !frontend/src/app/jackett/credentials/ at line 43, not by a per-file entry.)

WHY THIS IS A §11.4.201(6) FALSE-NULL, NOT MERELY AN INCONVENIENCE: the blind instrument and the clean tree return the identical quiet zero. git status showing nothing means BOTH 'no new files' AND 'a new file exists but is invisible'. There is no signal that distinguishes them. The commit path — the thing every other gate's output eventually has to travel through — cannot see its own blindness.

WHY IT IS NOT SIMPLY 'ADD ANOTHER ! LINE': that is the mechanism that produced the defect. A hand-maintained allowlist against a deny-all glob has the §11.4.251/§11.4.205 shape — every future legitimate credential-named source file needs a hand edit nobody will remember to make, and the failure mode of forgetting is SILENT. The same shape as BOB-205's hand-maintained DANGER_ROOTS: a list that must be edited in lockstep with the tree, with no guard that notices when it was not.

TENSION TO RESOLVE HONESTLY (§11.4.10 vs §11.4.201(1)): the glob exists for a real reason — §11.4.10 forbids credential material reaching git, and a broad deny-all is the conservative-safe default. Narrowing it carelessly would re-open a genuine leak channel. So the fix is NOT 'delete the glob'. Candidate directions, operator decision (§11.4.66): (a) narrow the deny to what actually carries secrets — extensions and directories (*.env, secrets/, *credentials*.json|yaml|yml|txt|enc) rather than every path containing the word; (b) keep the deny-all but add a GATE that FAILS when an untracked file matches an ignore rule AND lives under a first-party source root AND has a source extension, so the swallow becomes loud instead of silent; (c) both. (b) alone closes the false-null even if the glob stays exactly as it is, and is the smaller change.

ACCEPTANCE: (1) a NEW credential-named source file under a first-party source root either commits normally or produces a LOUD refusal naming the rule that blocked it and the remedy — never silence; (2) a RED that creates such a file and asserts the current silence, flipping to the loud path post-fix (§11.4.115); (3) a golden-FALSE proving real secret material (a .env, a key) is STILL ignored — the §11.4.201(1) guard, because a fix that leaks credentials to close a false-null is strictly worse than the defect; (4) frontend/e2e/credentials.spec.ts is made safe by rule rather than by the accident of already being tracked.

DISCOVERY CHANNEL (§11.4.238): found by the BOB-204 stream when its own deliverable disappeared — NOT by the automated QA regime, and not by any gate. Nothing in the repo checks that an authored file actually became visible to git. Coverage-escape audit: no surface exists for this class at all.

=== SCOPED AND MEASURED 2026-08-26 — RECOMMENDATION (b), AND (a) IS DISPROVEN NOT MERELY DISFAVOURED ===

TASK 1a — TRACKED FILES SURVIVING ONLY BY BEING TRACKED: **3, not 157.** A raw sweep of all 2795 tracked paths hit 157 ignore rules — but **154 of those are NEGATIONS** (! lines), i.e. explicitly re-included and safe BY RULE. Reporting 157 as the blast radius would have been a §11.4.201(1) false positive; the investigating stream caught this itself. Two independent instruments (check-ignore -v filtered on non-negated patterns, and bare check-ignore which emits only truly-excluded paths) produced IDENTICAL sets.
  1. frontend/e2e/credentials.spec.ts — .gitignore:31 *credentials* — HAZARD (the known one, 109-line Playwright spec)
  2. tests/security/test_jackett_autoconfig_secrets.py — .gitignore:51 *secrets* — HAZARD, **NOT NAMED IN THIS ITEM WHEN FILED**. Conductor-verified: matched by :51, currently tracked. It is a 113-line SECURITY / PEN TEST asserting no credential value reaches an HTTP body, traceback, or log. Losing it silently would remove the test that guards §11.4.10 — the deny-all glob's own purpose. That is the sharpest instance available: the rule protecting credentials is one refactor away from deleting the test that proves credentials are protected.
  3. submodules/jackett — .gitignore:260 — NOT a hazard: mode 160000 gitlink, and that entry is documented as deliberately inert for git (it steers CodeGraph per §11.4.79).

THE MECHANIC THAT DECIDES THE FIX: the directory negation at :43 re-includes the DIRECTORY ONLY. A new frontend/src/app/jackett/credentials/credentials.guard.ts is STILL swallowed by :31, because *credentials* contains no slash and is therefore BASENAME-scoped — the allowlisted directory buys nothing for new files. Of the 154 safe files, 124 are held by ONE robust glob negation (!docs/qa/**/*.log) and **13 by fragile hand-maintained per-file entries** (all 13 currently live, none stale — but each is a future silent loss).

TASK 1b — ALREADY-SWALLOWED UNTRACKED FILES: 5 of 60,217 ignored+untracked paths. Two are real losses (the tracker-credentials export twins and the BOB-124 .txt evidence — filed as their own item); set_password.py is recorded UNKNOWN: provenance and deliberately NOT called lost work; download-proxy/qbittorrent_creds.json is the POSITIVE CONTROL — shape-inspected keys-only (never values) as [password, username], genuinely credential-bearing, CORRECTLY ignored.

TASK 2 — MEASURED IN A SCRATCH TREE, 10 source paths x 15 secret paths:
  baseline (full 316-line file)      swallows 10 | leaks 0
  (a) EXACTLY AS THIS ITEM WORDED IT swallows  0 | **leaks 3**
  (a) repaired to plug those 3       swallows  1 | leaks 1
  (b) deny-all unchanged + loud gate swallows  0 | **leaks 0**
(a) LEAKS download-proxy/qbittorrent_creds.json — A REAL CREDENTIAL FILE SITTING IN THE TREE TODAY — because *credentials*.json does not match "creds". It also leaks my_password.txt and service_credentials. Repairing those still leaves service_credentials: **an extension-scoped deny cannot cover EXTENSIONLESS secret files without collapsing back into the deny-all it was meant to replace.** So (a) as this item worded it is DISPROVEN, not merely disfavoured — and I wrote (a) first in the candidate list, which was wrong.
**WHAT (b) NEWLY ALLOWS INTO GIT: NOTHING — the set is EMPTY.** No pattern changes, so the §11.4.10-vs-§11.4.201(1) proof obligation discharges trivially. No variant of (a) can make that argument.

TASK 3 — THE RED: tests/security/test_gitignore_swallow_is_loud.sh (filename verified not swallowed BEFORE writing — the joke this item is about). It asserts the acceptance DISJUNCTION (commits normally OR refuses loudly), so it is FIX-DIRECTION-AGNOSTIC and leaves the direction an operator decision.
The load-bearing assertion is A3: git status is BYTE-IDENTICAL with and without the file — world A (authored) 330ceb52074cdbbe, world B (never made) 330ceb52074cdbbe. That is the false-null proven directly, not argued.
Proven NOT a tautology: RED_MODE=1 -> exit 0; guard stand-in -> exit 0; narrowed glob -> exit 0; and the §1.1 mutation DELETING the globs -> **exit 2 with 11 leaks caught**, which is what makes the golden-FALSE load-bearing rather than decorative. Exit 2 is deliberately distinct from exit 1 so a blind harness can never read it as "defect present".

BEYOND WHAT THIS ITEM FRAMED: it is not a *credentials*/*creds* problem. **secrets*, *_password* and *_user* have EACH already swallowed something real.** *_user* is the broadest — it will match any future *_user*.txt / .json evidence or fixture. The fix must be evaluated against the whole rule set, not the one glob that surfaced first.

=== SECOND LIVE TRAP HIT, SAME SESSION (2026-08-26) ===
The BOB-207 stream chose the natural filename tests/unit/test_ownership_user_owned_gid.sh for its RED. Conductor-verified: that path is SWALLOWED by .gitignore:60 *_user*. The stream checked before writing (having been warned) and renamed to test_ownership_gid_agreement.sh, which is clean.
That is the SECOND deliverable in one session that the deny-all globs would have silently eaten — the first (BOB-204's credentials_failclosed_test.go) was caught only after the fact. It also confirms this item's own "beyond the item" warning empirically: *_user* is the broadest of the four globs and it caught a file whose name contains no secret and no credential — merely the word 'user' inside 'user_owned', which is the FEATURE'S OWN NAME (spec 002-user-owned-downloads). Any test named after this feature is a candidate for silent loss.
Two hits in one session, from two independent streams, is not a coincidence rate — it is the defect operating normally.

## BOB-218 — tools/README documents a rollback that does not exist: the plugin writer truncates on open and never restores the .bak, leaving a corrupt plugin while reporting the update FAILED

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-218/closure_evidence_20260923.md
**Severity:** major

WHAT: tools/README.md:30 states "the backup is restored" on validation failure. Conductor-verified: shutil.copy2 appears EXACTLY ONCE in tools/plugin_update_automation.py and copies FORWARD only — a reverse-direction restore has ZERO occurrences (grep control-needle-proven seeing: needle 2 hits, negative control 0). The plugin write opens in mode "w", which TRUNCATES IMMEDIATELY.

USER-OBSERVABLE HARM (the reason this is not merely a doc defect): a failure part-way through the write leaves a TRUNCATED, NON-IMPORTABLE plugin on disk. The operator is told the update FAILED and reasonably concludes the previous file survived — because the README says it was restored. It was not. The next ./install-plugin.sh copies the corrupt file into config/qBittorrent/nova3/engines/ and that search engine SILENTLY STOPS WORKING. The .bak needed to recover DOES exist on disk; the tool never mentions it and never uses it.

This is a §11.4 documentation-layer bluff with a real downstream consequence: the doc asserts a safety property the code does not implement, and the operator's recovery decision is made on that false assertion.

SECOND, SMALLER DOC DIVERGENCE: the README claims JSON goes to stdout; :274 writes it to a FILE (open(args.output, "w")).

THIRD, SEPARATE MINOR DEFECT in the same file (recorded here rather than as its own item because it shares the file and the fix window): _extract_version at ~:198 uses a BARE `except:`, so a Ctrl-C during the 14-URL sweep is SWALLOWED. That is a signal-handling defect, not a fail-open — the gate flagged this line, but for the wrong reason (it read the silent default return; the real issue is the bare except catching KeyboardInterrupt).

ACCEPTANCE: (1) either the rollback is IMPLEMENTED (restore the .bak on failure) or the README claim is DELETED — the doc and the code must agree (§11.4.6); if implemented, write to a temp file and rename atomically rather than truncating in place; (2) the stdout-vs-file claim corrected; (3) the bare except narrowed so KeyboardInterrupt propagates; (4) a RED that fails the write mid-way and asserts the previous plugin is intact (post-fix) / truncated (pre-fix).

REACHABILITY: same as the sibling item — hand-run only, not in any automated path, last functional commit 2026-04-12. Severity Major on the harm shape, bounded by that reachability.

DISCOVERY CHANNEL (§11.4.238): found by the concealed-hits triage stream. Not by the automated QA regime.

## BOB-230 — Verify config/lan_route_auth_policy.yaml recognizes the new qbittorrent-proxy-go apitoken middleware (BOB-203 follow-up)

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-230/closure_evidence_20260923.md
**Severity:** Minor
**Created-By:** AI

BOB-203 added qBitTorrent-go/internal/middleware/apitoken.go, wired via a scoped Gin route group covering the routes with a Python-side Depends(require_api_token) counterpart. config/lan_route_auth_policy.yaml's exemption entries for this service's hooks/schedules/theme routes were deliberately NOT updated by that fix, since the implementing subagent was not certain of scripts/pre_build/check_cm_lan_routes_authenticated.sh's analyzer's exact resolution semantics for a .Use()-on-a-named-group Gin idiom, and did not want to guess at a checked-in security-gate data file. This service is not currently running in this deployment (--profile go is opt-in) and is already loopback-bound by a prior BOB-198 operator decision, so this is NOT an active exposure -- it is a policy-file accuracy follow-up. ACCEPTANCE: (1) re-run scripts/pre_build/check_cm_lan_routes_authenticated.sh against the current tree; (2) if it reports a new finding for the Go service that is a false positive (the analyzer not recognizing the .Use()-on-a-named-group pattern) or a stale-looking known-gap entry for a route that is now actually protected, update config/lan_route_auth_policy.yaml's qbittorrent-proxy-go.auth_markers / exemption entries to match reality; (3) if the gate already passes cleanly with no change needed, close this item noting that verification, no edit required.

## BOB-203 — LIVE: unauthenticated mutating LAN routes accepted on ports 7186 and 7187, and the armed BOBA_API_TOKEN is inert

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-203/closure_evidence_20260923.md
**Severity:** Critical

MEASURED LIVE 2026-08-26 against the running stack from LAN 192.168.1.90 (NOT loopback - qBittorrent's localhost bypass would have exercised a different code path). Evidence: docs/qa/BOB-198/runtime_auth_verification_20260826.md.

VERDICT: unauthenticated mutating LAN requests ARE currently accepted. Two live services, four named routes:
  1. POST   /api/v2/torrents/stop      port 7186  -> HTTP 200 with NO credentials (real torrent control)
  2. POST   /api/v1/hooks              port 7187  -> 422 field-validation (request REACHED FastAPI body validation, which runs AFTER middleware)
  3. POST   /api/v1/schedules          port 7187  -> 422 (same)
  4. DELETE /api/v1/hooks/<id>         port 7187  -> 404 'Hook not found' (the handler EXECUTED A LOOKUP)

The 422/404 responses are the decisive evidence, not the 200: a 401 never appears anywhere, and reaching body validation or a handler lookup proves no auth middleware intervened.

THE ARMED TOKEN IS INERT. BOBA_API_TOKEN was armed in .env earlier this session on an operator decision. Port 7187 returns BYTE-IDENTICAL responses with and without it across three header shapes. Port 7189 does not open for it in five header shapes. Root cause identified: docker-compose.yml injects BOBA_API_TOKEN into EXACTLY ONE service - download-proxy (line 237) - and into neither qbittorrent-proxy-go nor boba-jackett. And even on 7186, where it IS injected, POST /api/v2/torrents/stop returned 200 unauthenticated, so injection alone is not enforcement.

PER-SERVICE POSTURE (measured):
  7185 qbittorrent-nox   LIVE, binds *      - same mutating surface visible from LAN as via the proxy
  7186 download-proxy    LIVE, binds 0.0.0.0 - mutating control accepted unauthenticated
  7187 merge service     LIVE, binds 0.0.0.0 - 34 routes via openapi.json, NO auth layer at all
  7188 bridge            NOT BOUND          - honest SKIP
  7189 boba-jackett Go   LIVE, binds *      - writes 401-gated, reads OPEN incl. /api/v1/jackett/credentials
  9117 jackett           LIVE, binds *
EVERY live service binds all interfaces. None is loopback-only.

RELATIONSHIP TO BOB-198 (its named subject was NOT running): qbittorrent-proxy-go is profiles:-gated (opt-in --profile go) and absent from the container set, so its '22 unauthenticated routes' is neither confirmed nor refuted - honest 11.4.3 SKIP. The exposure recorded HERE is a DIFFERENT and ADDITIONAL surface on the Python service and the proxy. Do not treat this item as closing BOB-198.

11.4.238 COVERAGE ESCAPE - first class, equal standing to the bug: the automated QA regime did NOT find this. The static gate check_cm_lan_routes_authenticated went through SIX independent review rounds proving routes are statically wired to auth middleware, and its own honest boundary (tracked BOB-197) states it asserts static wiring ONLY. Nobody had measured runtime until a directed agent did. This is precisely the 11.4 covenant's founding failure shape: a green gate over a broken-for-the-user reality. The owed remedy is an automated runtime check that would have caught it, with a RED capturing this exact exposure - not merely a fix to the routes.

ANTI-BLUFF PROVENANCE: control needle - Jackett returned a real 401 through the SAME instrument, so the 200s are not instrument blindness; port 7188 returned exit-7, so absences are real. Negative control - a deliberately wrong token still got 401 on 7189. Decisive probes 3/3 deterministic. Mutating probes used non-existent ids against a provably EMPTY torrent list ([] before and after), so effect was nil and verified on both sides. Token referenced by name only, never printed (11.4.10); the report was leak-scanned with a needle proving the scanner fires on a known leak.

ACCEPTANCE: (1) operator decision (11.4.66) on the intended posture per service - loopback-only bind, real auth middleware, or accepted-LAN-risk-with-rationale; (2) whichever is chosen, an automated runtime check per 11.4.238 that fails RED against today's exposure; (3) 11.4.108 layer-3/4 evidence on a clean deployment, not static analysis; (4) paired 1.1 mutation.

=== RELATED MEASUREMENT 2026-08-26 — A THIRD LAN-BOUND PORT (§11.4.6, recorded not merged) ===
This item covers unauthenticated mutating routes on 7186 and 7189. A separate triage stream measured, and the conductor verified, that port 7188 is ALSO LAN-bound: webui-bridge.py:447 binds ThreadingHTTPServer(("", BRIDGE_PORT)) — the empty host string is INADDR_ANY, so it listens on ALL INTERFACES rather than loopback.
NOT merged into this item per §11.4.214 (distinct-but-similar): this is a BIND-SCOPE fact about a different service, not a demonstrated unauthenticated mutating route on 7188. Whether 7188 exposes mutating routes without authentication is UNVERIFIED and is the open question this note raises. Recorded here so the 7188 surface is not overlooked when this item's scope is settled — and so nobody later "discovers" it as new.

## BOB-222 — tests/security/ is executed by no invariant — the third occurrence of the same orphan-directory class, and the driver's own comment records the previous two

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-222/closure_evidence_20260923.md
**Severity:** major

WHAT: scripts/pre_build_verification.sh:1196 enumerates bash suites with a glob covering EXACTLY three directories:
  "${PROJECT_ROOT}"/tests/unit/test_*.sh · "${PROJECT_ROOT}"/tests/pre_build/test_*.sh · "${PROJECT_ROOT}"/tests/hooks/test_*.sh
tests/security/ is NOT among them. Conductor-verified verbatim. So tests/security/test_gitignore_swallow_is_loud.sh — a RED authored this session with a golden-FALSE guard proving real secrets stay ignored — is executed by NOTHING. It is a guard that guards nothing, and its silence is indistinguishable from success.

THIS IS THE THIRD OCCURRENCE OF ONE CLASS. The driver's OWN comment at :1030 records the history: the same defect class "existed for tests/pre_build/test_*.sh" and was fixed by adding that directory to the glob. It then recurred one directory over (tests/hooks), fixed the same way. Now tests/security. Each fix was a new glob entry; none addressed why a new test directory is invisible by default.

§11.4.250 APPLIES DIRECTLY: three symptoms, one primitive. The primitive is a hand-maintained enumeration that must be edited in lockstep with the tree, whose failure mode is SILENT. It is the identical shape as BOB-205's DANGER_ROOTS and BOB-212's .gitignore allowlist — three separate hand-maintained lists in this repo, all three measured to have silently missed something. Adding tests/security to the glob would be the fourth instance of layer N+1.

NOTE THE GATE ALREADY HAS THE RIGHT INSTINCT at :1220: it fails when the glob matches NOTHING ("the glob is blind"). That guard catches a TOTALLY blind glob but not a PARTIALLY blind one — the more common and more dangerous case, because a partially blind glob still reports a healthy count.

FIX DIRECTION (§11.4.251 role-as-data-pack): derive the suite set from the tree — every tests/**/test_*.sh — minus a DECLARED §11.4.224(E) exclusion fence with a justification per entry. Then a new test directory cannot be invisible, and a deliberate exclusion is visible and reasoned. If a hand list is kept, the omission-guard is the same computation, so the derivation must be built either way.

ACCEPTANCE: (1) tests/security suites execute; (2) a NEWLY CREATED tests/<newdir>/test_x.sh is picked up with no hand edit — that is the invariant that stops the recurrence, and without it this is just the fourth patch; (3) a RED creating such a directory and asserting it runs; (4) the :1220 blind-glob guard is extended to catch PARTIAL blindness, not only total.

DISCOVERY CHANNEL (§11.4.238): found by the T042 readiness preflight. Not by the automated QA regime — and notably not by the two previous fixes of this same class, neither of which asked why it happened.

## BOB-227 — The LAN-route auth gate ships UNTRACKED: analyzer, wrapper and its 197-assertion harness exist only in one working tree

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-227/closure_evidence_20260923.md
**Severity:** critical
**Created-By:** Claude
**Assigned-To:** Claude

WHAT: three of the four artifacts of the CM-LAN-ROUTES-AUTHENTICATED pre-build gate are untracked in git. MEASURED 2026-08-27 with git ls-files --error-unmatch, control-needled against a known-tracked file: scripts/pre_build/lan_route_auth_analyzer.py UNTRACKED, scripts/pre_build/check_cm_lan_routes_authenticated.sh UNTRACKED, tests/pre_build/test_check_cm_lan_routes_authenticated.sh UNTRACKED; only docs/scripts/check_cm_lan_routes_authenticated.md is TRACKED. IMPACT: (1) losing this checkout loses an entire security gate plus 197 assertions; (2) no round-over-round diff claim across review rounds 8 through 14 was ever checkable, because no committed baseline exists - the same §11.4.226 evidence-custody failure the BOB-195 chain hit independently; (3) a fresh clone runs a pre-build gate whose implementation is absent. ACCEPTANCE: all four artifacts tracked and committed, and a gate asserting that every executable a pre-build invariant invokes is itself tracked. Surfaced by the BOB-102 round-13 remediation and independently verified 2026-08-27.

## BOB-225 — *.docx is globally gitignored while the §11.4.65 exporters generate .docx twins — every DOCX artifact this project produces is untrackable by construction

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-225/closure_evidence_20260923.md
**Severity:** major

WHAT, conductor-verified: .gitignore:266 ignores *.docx globally. The §11.4.65 export pipeline GENERATES .docx twins — the workable-items export produces Issues.docx / Fixed.docx / Issues_Summary.docx / Fixed_Summary.docx, and the doc exporter produced docs/scripts/check_cm_lan_routes_authenticated.docx during round 9. Every one of them is untrackable by construction: they exist on disk, git will never see them, and no gate can notice because the absence is silent.

WHY THIS IS THE BOB-212 CLASS, NOT A DUPLICATE OF IT: BOB-212 is a deny-all glob plus a hand-maintained per-file ALLOWLIST, where new files leak through the gaps in the list. This is a deny-all glob with NO allowlist at all for a file type the project MANDATES producing. The mechanism differs; the false-null is identical — git status stays silent, so the exporter appears to succeed and the artifact appears to exist. It is filed separately per §11.4.214 (distinct-but-similar), with BOB-212 and BOB-219 as siblings.

THE TENSION TO RESOLVE HONESTLY: §11.4.153 mandates a FOUR-format export (HTML + PDF + DOCX) for its document class, and §11.4.65 governs the twins generally. So the constitution requires producing an artifact the repository is configured to refuse. One of the two is wrong and the resolution is an operator decision (§11.4.66): (a) the .docx mandate applies here and the glob must carve out generated doc twins; (b) .docx is deliberately untracked as a heavy binary derivative regenerable per §11.4.77 from its .md, in which case the EXPORTERS should stop producing it, or produce it into an explicitly untracked location, and the §11.4.153 four-format requirement should be recorded as consciously not-adopted rather than silently unmet.
What is NOT acceptable is the present state: generate it, ignore it, and let both the mandate and the glob appear satisfied.

MEASURED SCOPE (CORRECTED — my first write of this item said 'tracked .docx files = 0', which is FALSE; recorded here per §11.4.6 rather than silently amended): **2** .docx files ARE tracked and **1140** exist repo-wide, so **1138** are untracked-and-ignored. (A second correction, also recorded rather than amended: my first correction said 344, which counted only the docs/ subtree. Two numeric errors in a row on one item — the pattern is that each was measured with a narrower instrument than the claim it supported, which is the §11.4.201(7)(c) path-is-part-of-the-instrument failure applied to my own reporting.) AND THE TWO SURVIVORS ARE THE INTERESTING PART: they are docs/features/Status.docx and docs/features/Status_Summary.docx — precisely the pair §11.4.153 explicitly mandates as a FOUR-format export. So the only two DOCX artifacts git can see are the two a specific anchor named, and they survive not by rule but because they are already in the index. That makes this a PARTIAL condition, not a total one, and the two survivors are the interesting part — they are in the same position as frontend/e2e/credentials.spec.ts under BOB-212: alive only because they are already in the index, since git honours the index over .gitignore for tracked paths. One delete-and-re-add, one file move, and they vanish silently like any other. So the state is worse than a clean 'we never track docx': it is an inconsistent one where two artifacts appear to prove the format IS tracked while 342 prove it is not.

ACCEPTANCE: (1) the operator decision above is taken and recorded; (2) whichever way, the exporter and the ignore rule AGREE — if .docx is not tracked, nothing should silently generate one into a tracked doc directory; (3) if carved out, a check that a generated twin is actually trackable, so this cannot recur silently; (4) §11.4.153 compliance is either met or recorded as an honest gap, never left implicitly failing.

DISCOVERY CHANNEL (§11.4.238): found by the BOB-102 round-9 remediation stream when it regenerated its own guide twins and noticed the .docx could not be added. Not by the automated QA regime — and the regime cannot see it, which is the point.

## BOB-160 — tests/pre_build/ and tests/ownership/ ran by nothing — closed by extending invariant 30 + wiring ci.sh

**Status:** Completed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-160/closure_evidence_20260923.md
**Severity:** Medium
**Created-By:** AI

**Reported-Via:** §11.4.202 reporting directive `task` on 2026-08-21T19:02:48Z
**Reported-By:** AI

**What (the report, verbatim):**
Independent §11.4.209 review (IMPORTANT-3) found two of the feature's strongest automated checks were never executed by any runner: (1) tests/ownership/test_container_writes_owned_files.py — the §11.4.115 RED-turned-regression-guard for FR-011/FR-007, proven via a docker-compose.yml revert mutation — was moved out of tests/integration/ (commit 58d340a, to escape an autouse fixture hang) but no runner (ci.sh, test.sh, run-all-tests.sh) was ever extended to cover tests/ownership/. (2) tests/pre_build/test_*.sh, the §1.1 paired-mutation meta-tests for the scripts/pre_build/check_cm_*.sh gate family, was executed by NOTHING — self-reported honestly in commit 04742d7's own message ('STILL OPEN (reported, not fixed): tests/pre_build/ is executed by NOTHING') but never tracked as a workable item (a §11.4.197 loss-of-requirements gap) and never wired into scripts/pre_build_verification.sh invariant 30, which globbed only tests/unit/test_*.sh.

**Affected scope / file-scope manifest:**
ci.sh; scripts/pre_build_verification.sh invariant 30 (CM-BASH-UNIT-TESTS-EXECUTED)

**Reproduction / context:**
grep -rn test_container_writes_owned_files ci.sh test.sh run-all-tests.sh scripts/ returned zero runner hits (only docs/specs mentioned the path); grep in scripts/pre_build_verification.sh showed invariant 30's for-loop globbing only tests/unit/test_*.sh, never tests/pre_build/test_*.sh.

**Acceptance criteria:**
ci.sh gains a runtime-gated pytest tests/ownership/ stage (skips honestly, rc=0, when no podman/docker present); scripts/pre_build_verification.sh invariant 30's glob covers both tests/unit/test_*.sh and tests/pre_build/test_*.sh, verified by an extracted standalone run of the invariant's exact block reporting a non-zero RAN count that includes files from both directories.

## BOB-156 — BOB-145 event-loop regression guard is load-sensitive and flaky: 8786ms under host load vs a 900-1500ms ceiling calibrated on a quiet host

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-156/closure_evidence_20260923.md
**Severity:** Medium
**Created-By:** AI

BOB-145 event-loop regression guard is load-sensitive and flaky: 8786ms under host load vs a 900-1500ms ceiling calibrated on a quiet host

## BOB-177 — Four of five private-tracker HTTP-refusal guards are invisible to the test suite

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-177/closure_evidence_20260923.md
**Severity:** High
**Created-By:** Claude
**Assigned-To:** Claude

WHAT: BOB-172 wired an identical 4-line HTTP-refusal guard at five private-tracker fetch sites in download-proxy/src/merge_service/search.py (rutracker cookie :1390, rutracker credential :1468, kinozal :1648, nnmclub :1761, iptorrents :1934). Only the rutracker COOKIE path is exercised by tests.

EVIDENCE (reviewer-authored mutation R1, per 11.4.194(6)(d), during the BOB-172 independent review): deleting ONLY the kinozal guard wiring (search.py:1655-1658) while leaving the classifier intact left the full merge_service suite at 883 passed, ZERO failures. The suite cannot see four of the five sites.

FAILING SCENARIO: a refactor drops or subtly breaks the wiring at kinozal, nnmclub, iptorrents, or rutracker-credential. A 403 at that site silently folds back to status=empty with error=None -- the exact BOB-172 signature -- and no test reddens.

FIX DIRECTION (reviewer preferred): collapse the five duplicated wirings into one shared helper, e.g. _check_search_response(tracker_name, status, body) -> bool, so there is ONE copy to test and a sixth site cannot be added unguarded (11.4.251 byte-identical-fork extraction). Alternative: parametrise the guard tests across all five sites with per-site stub sessions.

ACCEPTANCE: mutating the wiring at ANY of the five sites reddens at least one test. Prove it by running the same R1 deletion at each site in turn.

## BOB-176 — A cookies-only rutracker configuration never enables the tracker, because the enablement gate checks username/password while the search path prefers cookies

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-176/closure_evidence_20260923.md
**Severity:** Medium
**Created-By:** Claude
**Assigned-To:** Claude

WHAT. _get_enabled_trackers() in download-proxy/src/merge_service/search.py gates rutracker on RUTRACKER_USERNAME and RUTRACKER_PASSWORD only. It never consults RUTRACKER_COOKIES. So an operator configured with cookies alone — no username, no password — never has rutracker enabled at all, and the tracker is silently absent from every fan-out rather than failing visibly.

WHY THAT IS INCOHERENT WITH THE REST OF THE CODE. _search_rutracker treats COOKIES as the PREFERRED auth path, not a fallback. And the nnmclub sibling DOES check its own *_COOKIES variable. So the same codebase holds three positions at once: cookies preferred at the search site, cookies ignored at the enablement gate, and cookies honoured for a sibling tracker.

WHY IT MATTERS MORE THAN IT LOOKS. CLAUDE.md documents a standing operator mandate (2026-08-15) that per-tracker Netscape cookies files at ${TRACKER_COOKIE_DIR}/cookies_<tracker>.txt are auto-loaded into .env as <TRACKER>_COOKIES before every boba-svc up, restart, install Stage 6 and start.sh boot — and rutracker is named in that set. So the SANCTIONED, documented configuration path for this tracker produces exactly the state this gate ignores. An operator who follows the documented instructions gets a tracker that never runs, with no error to explain it.

FAILURE MODE. Silent absence, not a visible failure — the same §11.4.201(6) false-null shape as BOB-172, one layer earlier. BOB-172 fixes a tracker that RAN and was REFUSED being reported as empty; this is a tracker that never ran at all, and the merged result simply has one fewer contributor with nothing to indicate it.

PROVENANCE. Found by the BOB-172 implementing agent while tracing the enablement path to locate the status-handling defect. Recorded here rather than fixed in that change: it is a separate defect on a separate seam with its own oracle, and folding it in would have widened BOB-172 past its captured evidence.

ACCEPTANCE. (a) The enablement gate honours RUTRACKER_COOKIES as an independently sufficient credential, matching what _search_rutracker already prefers and what the nnmclub sibling already does. (b) A test asserting that a cookies-only configuration ENABLES rutracker, driving the real _get_enabled_trackers rather than a replica. (c) Paired §1.1 mutation restoring the username/password-only gate — the test must go red. (d) NEGATIVE CONTROL (§11.4.201(1)): a configuration with NO credentials at all must still leave rutracker DISABLED. A fix that enables an unauthenticated tracker is worse than the gap, because it produces failing searches instead of absent ones. (e) Audit the other trackers' gates for the same asymmetry rather than fixing only the one that was noticed — three positions in one codebase suggests nobody has checked them together (§11.4.118).

HONEST BOUNDARY. Not verified against a live cookies-only deployment; read from source by the BOB-172 agent and recorded on its report. The reading is specific and checkable, but whoever takes this should confirm by invocation before relying on it.

## BOB-178 — Kinozal login-leg HTTP failure sets no diagnostic, reproducing the BOB-172 false-null one leg over

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-178/closure_evidence_20260923.md
**Severity:** Medium
**Created-By:** Claude
**Assigned-To:** Claude

WHAT: download-proxy/src/merge_service/search.py:1638-1640 handles a failed kinozal LOGIN response with if login_resp.status not in (200, 301, 302): logger.error(...); return [] -- and sets NO diagnostic.

FAILING SCENARIO: Cloudflare returns 403 on takelogin.php. The kinozal chip reads status=empty, error=None. That is the BOB-172 signature exactly: a refusal reported to the user as an empty result set.

CONTRAST establishing this is an oversight, not a design choice: the rutracker and nnmclub login failures DO set diagnostics (upstream_captcha / auth_failure), and the iptorrents login failure falls through to the search fetch where BOB-172's new guard catches it. Kinozal is the one leg with neither.

FIX DIRECTION: stash _classify_upstream_http_status(login_resp.status, "") before the early return, or an auth_failure diag for the status-in-(200,301,302)-but-no-cookie case.

ACCEPTANCE: a stubbed 403 on the kinozal login endpoint produces a non-None error on the kinozal chip, with a RED captured against the pre-fix code first (11.4.115).

## BOB-213 — LANGUAGE HOLE: sh is absent from the fail-closed gate's extension list, so 71 of 74 source files in the scripts/ DANGER_ROOT are silently invisible while the driver prints a clean verdict

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-213/closure_evidence_20260923.md
**Severity:** critical

WHAT: the §11.4.252 fail-closed gate's extension list omits shell entirely. Measured verbatim by the conductor at constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh:457 —
  exts="${DANGEROUS_COMBO_EXT:-py go rs c cc cpp h hpp java cs js ts jsx tsx php rb}"
No sh. No bash.

THE CONSEQUENCE, MEASURED: scripts/ IS a declared DANGER_ROOT (scripts/pre_build_verification.sh:1511). It contains 71 tracked .sh files and 3 .py files. So 71 of 74 source files in a root the gate is explicitly pointed at are SILENTLY INVISIBLE — while invariant 39's driver prints "no fail-open anti-pattern across N first-party source root(s)". Project-wide there are 198 tracked .sh files (negative control *.zzz = 0, instrument proven seeing).

WHY THIS IS THE WORST OF THE THREE HOLES: BOB-205 is a scope hole (root never looked at). BOB-191 is a matcher hole (Go enumerated but unanalysable). THIS one is worse than either, because the root IS declared, IS scanned, IS counted as covered, and 96% of what is in it was never examined. The count in the driver's own summary is an under-count presented as a census.

AND SHELL IS THE HIGHEST-RISK LANGUAGE HERE, not the lowest: the project's orchestration, credential handling, container control and gates are shell. start.sh alone is 1288 LOC and is, per CLAUDE.md, THE orchestrator. Fail-open in shell is also unusually easy to write — a bare `cmd || true`, an unchecked `$?`, a `set +e` region, a swallowed `2>/dev/null` — and §11.4.67(6) already records one live instance of exactly this class (a bare exec redirection silencing an interactive shell for its lifetime).

CORRECTION TO A PREVIOUSLY-STATED ACCEPTANCE CRITERION (§11.4.6): I asserted, when filing BOB-205, that "the honest-blindness path (§11.4.3 SKIP-with-reason, which the gate already implements correctly for unenumerated extensions) is preserved". THAT IS WRONG. The gate's honest SKIP-with-reason exists for the PYTHON ARM's degradations, NOT for extensions absent from the ext list. An unenumerated extension is a SILENT false-null, not an honest skip. The distinction is load-bearing and I stated it backwards.

NOTE ON LINE NUMBERS: the BOB-205 stream cited the ext list at :318; the conductor measured it at :457. Both are correct at their read times — a sibling stream (BOB-195 r7) is actively editing this file. Re-derive before acting.

ACCEPTANCE: (1) either shell is added to the ext list WITH an arm that can actually analyse it, or unenumerated extensions produce an explicit UNANALYSED verdict per file — never a silent pass (this is the same analyser-registry fix BOB-191 needs, and doing it once covers both); (2) the driver's summary reports files ANALYSED, not files present, so an under-count cannot masquerade as a census; (3) a RED planting a shell fail-open under scripts/ and asserting it is SEEN; (4) golden-FALSE per §11.4.201(1) — a correctly fail-CLOSED shell guard must NOT be flagged; §11.4.67's own brace-scoped exec form is the natural fixture.

COMPOSES: BOB-191 (matcher hole — same primitive: classify by local shape, never consult semantic role; and the analyser-registry fix closes both) and BOB-205 (scope hole). Per §11.4.250 these are three symptoms of one primitive defect; per §11.4.214 they stay three items because the fixes differ.

DISCOVERY CHANNEL (§11.4.238): found by the BOB-205 verification stream, confirmed independently by the conductor. Not by the automated QA regime.

## BOB-214 — REPOSITORY ROOT is in no DANGER_ROOT: webui-bridge.py (live HTTP service, :7188) carries a REAL fail-open the gate reports on sight, and start.sh + the credential scripts are unscanned

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-214/closure_evidence_20260923.md
**Severity:** critical

WHAT: DANGER_ROOTS = (download-proxy/src plugins scripts qBitTorrent-go frontend/src) at scripts/pre_build_verification.sh:1511. The REPOSITORY ROOT itself is not among them (conductor-verified: no "." entry). Everything living at the top level is scanned by no arm.

THE LIVE HIT: webui-bridge.py — tracked at root (conductor-verified), 466 LOC, a live HTTP service on port 7188 (BaseHTTPRequestHandler:85, do_GET/do_POST:92-97, request path read at :103, outbound urlopen at :273, environment credentials read at :55-74). The gate REPORTS A REAL HIT AT :295 when pointed at it directly. This is not a hypothetical gap: the existing gate, unmodified, finds a genuine defect in this file the moment scope reaches it.

ALSO UNSCANNED AT ROOT: 13 first-party shell scripts including start.sh (1288 LOC — per CLAUDE.md the project's orchestrator and the sole sanctioned container-control entry point), stop.sh, ci.sh, install-plugin.sh, and the credential-handling init-qbit-password.sh / fix-qbit-password.sh. (These are additionally invisible for the separate LANGUAGE-hole reason — shell is not in the gate's ext list — so root files get missed twice over, by scope AND by extension.)

THE SCALE THIS SITS IN: 266 files in scope / 512 out of scope — 66% of the gate-visible first-party corpus is never scanned. Other unscanned roots measured: tests/ (324 files, excluded-by-intent but UNDECLARED — an undeclared exclusion is exactly what §11.4.224(E) fences against), extension/ (108, shipped browser extension), docs/ (51), challenges/ (18), tools/ (1, and it CONCEALS 3 REAL HITS at plugin_update_automation.py:189,198,215), frontend/e2e + 2 configs (5).

SO THE SCOPE HOLE CONCEALS AT LEAST 4 REAL HITS the gate itself finds when pointed at them (1 in webui-bridge.py, 3 in tools/). Invariant 39's reported count is an under-count, not a census.

ACCEPTANCE: (1) repository root and tools/ are scanned, or explicitly fenced with a stated reason per §11.4.224(E) — silence is not an exclusion; (2) the 4 concealed hits are triaged (each is either a real defect to fix or a false positive to fix in the gate — both are findings); (3) tests/ (324 files) gets an OPERATOR decision per §11.4.66 — production-only is defensible but must be DECLARED; (4) a RED proving a root-level fail-open is seen; (5) golden-FALSE proving genuine build artefacts and vendored trees stay excluded.

FIX DIRECTION (measured by the BOB-205 stream, not guessed): a §11.4.251 manifest is feasible but the source of truth must be chosen carefully — docker-compose.yml build contexts MISS plugins/, frontend/src, cmd/boba-ctl and webui-bridge.py; language markers (go.mod/package.json) MISS plugins/ and webui-bridge.py. Only derive-from-git-tracked-source-extensions minus a declared §11.4.224(E) exclusion fence reaches every gap. Note the derivation must be built either way — if the operator prefers keeping a hand list, the omission-guard that audits it is the SAME computation; the only question is whether it drives the scan or audits the list.

DISCOVERY CHANNEL (§11.4.238): found by the BOB-205 verification stream while enumerating the full gap list — the item it was verifying named only one missing root. Not by the automated QA regime.

=== CORRECTION 2026-08-26 — THE "4 CONCEALED REAL HITS" CLAIM IN THIS ITEM IS REFUTED (§11.4.6) ===

When I filed this item I wrote that the scope hole "conceals at least 4 real hits the gate itself finds when pointed at them". A dedicated triage stream ran the UNMODIFIED gate against scratch copies, reproduced all four hits exactly, and triaged them: **4 of 4 are FALSE POSITIVES.** The instrument was control-needle-proven in BOTH directions first (fired on a planted `except: pass`, stayed silent on a clean log-and-reraise), so this is evidence, not a null.

All four are the SAME detector class — shape (A2) "silent default return" — which is precisely the BOB-189 false-positive shape: the returned literal IS the function's designed refusal value, consumed by a caller that checks it.
 - webui-bridge.py:295 (_is_root_liveness_probe): False -> send_error(502) at :438. The except DENIES the lenient 200 path. Fail-CLOSED. Combines ZERO of the six §11.4.252 capabilities — a pure classifier over self.path/self.command.
 - tools/...:189 (_download_url): None -> :110 handles it explicitly (warn + continue), no write. Handler BOUNDED to (URLError, HTTPError); anything else propagates.
 - tools/...:198 (_extract_version): "unknown" gates nothing — the update decision is the HASH compare at :116. (It IS a bare `except:` though, so Ctrl-C is swallowed — a separate signal-handling defect, filed with the README item.)
 - tools/...:215 (_validate_plugin): False -> :151 returns BEFORE the write at :165. This IS the refusal. Canonical BOB-189 shape.

WHAT THIS DOES AND DOES NOT CHANGE. The scope hole itself is UNCHANGED and still real — the repository root and tools/ are in no DANGER_ROOT, verified verbatim at scripts/pre_build_verification.sh:1511. What changes is the ARGUMENT: I justified this item partly on "it hides four known defects", and that justification is wrong. The correct justification is narrower and does not depend on any current hit: webui-bridge.py is a LIVE, LAN-BOUND HTTP service (see below) handling request paths, outbound calls, and environment credentials — a surface that belongs in scope on its capabilities, whether or not it currently contains a defect.

NEW FACT RAISING THE STAKES — 7188 IS LAN-REACHABLE. webui-bridge.py:447 binds ThreadingHTTPServer(("", BRIDGE_PORT)) — conductor-verified. The empty host string is INADDR_ANY, so port 7188 listens on ALL INTERFACES, not loopback. Neither localhost-only nor internet-exposed (internet only if forwarded). No severity is assigned to :295 because it is fail-closed — but this is the argument for putting the root in scope: a live LAN-bound service should be scanned on principle, not after a defect is found in it.

webui-bridge.py IS LIVE, DECISIVELY (§11.4.124 never engages — do NOT treat it as superseded): 142 tracked files reference it, including config/served_ports.yaml and the credential-leak-audit challenge; download-proxy actively probes it via bridge_health() at download-proxy/src/api/__init__.py:198; newest of 12 commits is a real functional fix (6e3da73, 2026-06-14). Critically, served_ports.yaml:66-69 records that the Go webui-bridge is a SEPARATE binary the qbittorrent-proxy-go container never starts — so NOTHING ELSE BINDS 7188 and this Python file is the only thing serving that port.

tools/ RECOMMENDATION (§11.4.224(E)): FENCE IT OUT, DECLARED — exclusion class "non-shipping developer utility". Evidence: 2 tracked files, neither gitignored; the script is invoked by NOTHING (control-needle-proven: 91 needle hits, 0 negative control — referenced only by its own README, its own docstring, and a tracker note; zero hits across *.sh/*.yml/*.py/Makefile outside tools/); its README self-declares "not invoked by the normal start/stop flow"; last functional commit 2026-04-12. Because it is FIRST-PARTY, §11.4.224(E) requires the exclusion carry a tracked §11.4.197 item — and the two REAL defects found in it must be tracked regardless of scope, since a hand-run --update still executes them.

## BOB-216 — MODE-INDEPENDENT carrier classes: the fail-closed gate's PRIMARY (AST) mode reports comments and docstrings as live defects — the parser-is-immune claim was over-broad

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-216/closure_evidence_20260923.md
**Severity:** major

WHAT: three carrier classes fire in the gate's PRIMARY mode, not only its degraded text fallback. Measured ast_rc=1 AND text_rc=1 (both modes report the hit):
 (a) a COMMENT or DOCSTRING quoting the credential anti-pattern is reported as a LIVE credential default — both spellings;
 (b) a // comment or a string constant holding `try { x(); } catch (e) { }` is reported as an empty catch, once per carrier line.
Shape (b), and the C-family half of shape (a), are LANGUAGE-AGNOSTIC GREPS with NO structural counterpart in any mode — so there is no parser to be immune.

WHY IT MATTERS: the gate's header carried a blanket claim that "A parser is immune to both by construction". That is OVER-BROAD and now corrected in place, scoped to the Python Try/With shapes where it is actually true. Everything else — every non-Python extension, and the credential/empty-catch text matchers even on Python — has no AST arm at all, so the immunity never applied there. A §11.4.201(1) false refusal in the PRIMARY mode is materially worse than one in a fallback nobody expects to be exact: it refuses provably-healthy code on the path the gate is trusted on.

THE CONTROL NEEDLE THAT SHARPENS IT (recorded so the next reader inherits the measurement): a #-COMMENTED import does NOT poison the licensing table (text=0), because those regexes are line-anchored. So the blindness is to STRINGS specifically, not to non-code generally. That distinction is what makes the comment-strip fix tractable for one class and not for the others.

WHY IT WAS NOT FIXED IN THE ROUND THAT FOUND IT (§11.4.6 honest boundary, and this is the right call): closing these needs a PER-LANGUAGE comment-and-string model across every configured extension. That model's failure direction is the UNDER-reporting one — a mis-parsed string region silently swallows real violations for the remainder of the file. The same reasoning made the round DECLINE the triple-quote fence counter for OVER-1 while ACCEPTING the comment strip for OVER-A: the comment strip's ambiguity resolves toward KEEPING text (proven by three control needles — real violation + comment, # inside a string, escaped quote before # — all 1/1), whereas a fence counter's ambiguity resolves toward DROPPING text. Direction of failure, not difficulty, is the discriminator. Building a full lexer here would import the under-reporting failure mode this gate refuses everywhere else.

OPERATOR DECISION (§11.4.66 / §11.4.197): whether to build per-language comment-and-string models is a consumer call, not a default this gate should pick unilaterally. Options: (a) accept the over-reports and DISCLOSE them per class (what the round did — a new MODE-INDEPENDENT CARRIERS section now enumerates all three); (b) build the models per language and own the under-report risk with a fixture per language; (c) narrow the language-agnostic greps so they only fire where a structural arm exists, trading coverage for precision.

RELATION TO SIBLINGS (§11.4.214 distinct-but-similar, deliberately not merged): BOB-189 is the gate flagging a fail-CLOSED SSRF guard — a semantic-role miss in the PYTHON arm. This is a CARRIER miss (comment/string read as code) that is MODE-INDEPENDENT. BOB-213 is a language absent from the ext list entirely. All three share the primitive §11.4.250 named in BOB-191: classify by local syntactic shape, never consult semantic role — but the fixes differ, so the items stay separate.

ACCEPTANCE: (1) the operator decision above is taken and recorded; (2) whichever path is chosen, each of the three classes has a fixture proving current behaviour, so a future change cannot silently alter it; (3) if (b) is chosen, a golden-FALSE per language proving a REAL violation adjacent to a carrier is still caught — the under-report guard, which is the whole risk.

DISCOVERY CHANNEL (§11.4.238): found by the BOB-195 round-7 remediation stream while closing a different finding, NOT by the automated QA regime and NOT by the independent reviewer that audited the same file in round 6.

## BOB-173 — Hook create and delete return HTTP success even when persistence fails, because _save_hooks swallows every exception — a user is told their webhook exists when it does not

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-173/closure_evidence_20260923.md
**Severity:** High
**Created-By:** Claude
**Assigned-To:** Claude

WHAT. download-proxy/src/api/hooks.py:96-102:

    def _save_hooks(hooks: list[dict[str, Any]]) -> None:
        try:
            os.makedirs(os.path.dirname(HOOKS_FILE), exist_ok=True)
            with open(HOOKS_FILE, 'w') as f:
                json.dump(hooks, f, indent=2)
        except Exception as e:
            logger.error(f'Failed to save hooks: {e}')

It catches EVERY exception, logs, and returns None. The signature returns None, so the caller has no channel to learn the write failed. Both call sites then report success unconditionally:

    :152  _save_hooks(hooks)                     :174  _save_hooks(hooks)
    :154  logger.info('Created hook: ...')       :175  logger.info('Deleted hook: ...')
    :156  return HookResponse(hook_id=..., ...)  :176  return {'message': 'Hook deleted', ...}

USER-VISIBLE CONSEQUENCE, which is why this is High and not a code-hygiene nit. A user POSTs a webhook, receives HTTP 200 and a hook_id, and the hook was never written — their automation silently never fires, and the API told them it exists. Symmetrically, a user DELETEs a hook, is told 'Hook deleted', the file still holds it, and it fires again after the next restart. In both directions the product reports the opposite of what happened, and the only trace is a log line nobody is watching.

THIS IS THE §11.4.252 SHAPE. The path combines two dangerous capabilities from that anchor's taxonomy — MUTATION of a shared resource (a filesystem write) and EXTERNAL SIDE EFFECT (hooks are outbound calls the system will or will not make) — so it is required to FAIL CLOSED: verify the precondition, refuse when it cannot be satisfied, and surface the refusal. Instead it fails open, and a bare 'except Exception:' that only logs is the exact anti-pattern §11.4.252 enumerates. At the product layer it is also a §11.4.201(6) false-null: a successful write and a swallowed failure are indistinguishable to the caller.

PROVENANCE. Surfaced as an out-of-scope observation by the independent reviewer of the BOB-135 test-isolation work — this swallow is what turned that defect into an 'assert 0 == 1' mystery, because the EACCES on /config was logged and discarded while the endpoint kept returning 200. Verified here directly from source before filing (the function body and both call sites read above), not taken on report. Recorded as a §11.4.238 discovery-channel escape: found by an agent reading code during an unrelated investigation, not by the automated QA regime — the coverage gap is a defect of equal standing to the defect itself.

ACCEPTANCE. (a) _save_hooks propagates failure — raise, or return a status the callers must consume. (b) Both endpoints translate a persistence failure into an HTTP error (500-class), never a success body; a create that did not persist must not return a hook_id. (c) A test drives each endpoint with the hooks file unwritable (read-only dir or a patched open raising OSError) and asserts a non-2xx status AND that a subsequent GET does not list the phantom hook — assert on the user-observable outcome, not on the log line. (d) Paired §1.1 mutation: restore the swallow; the test must FAIL. (e) Audit the same file for sibling swallows — this is a pattern, and one instance is rarely alone. (f) Honest boundary: this does not claim the write currently fails in production; it claims that WHEN it fails the user is told the opposite, and the BOB-135 investigation shows it does fail in at least one real environment.

NOT CLAIMED. No change made. No assessment of how often the write fails in the operator's deployment.

RECORDING A SHELL ERROR OF MY OWN (§11.4.6): the first version of this description was written with the anti-pattern snippet inside backticks in a double-quoted shell argument, so the shell ran it as command substitution and the text was replaced by nothing — the stored description read 'and  is the exact anti-pattern'. This is the SECOND time this session that backticks-inside-double-quotes has corrupted content (the first mangled a commit message). Fixed here by editing through a Python client with no shell quoting in the path. Noted because a silently-truncated defect description is exactly the kind of quiet corruption §11.4.201(7)(c) warns about — the path is part of the instrument, and it failed without erroring.

## BOB-174 — A corrupt hooks file reads as zero hooks and the next create silently destroys every existing hook, while the non-atomic write manufactures the corruption

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-174/closure_evidence_20260923.md
**Severity:** High
**Created-By:** Claude
**Assigned-To:** Claude

WHAT. A corrupt hooks file is silently indistinguishable from "no hooks configured", and the next create then DESTROYS every existing hook while returning HTTP 200. Three defects on one path, filed together because fixing any one alone leaves the data loss reachable.

A1 — download-proxy/src/api/hooks.py:104-112. _load_hooks wraps the read in `except Exception: logger.error(...)` and falls through to `return []`. A truncated or malformed hooks.json is therefore reported to every caller as an empty, healthy hook list. Confirmed at source.

A2 — the consequence, and the reason this is High. create_hook loads, appends, saves. Given a corrupt file that load turns into [], the save writes a one-element list over the top. Every previously-configured hook is gone. Measured by the implementing agent against the ALREADY-FIXED tree, so this survives the BOB-173 write-failure fix:

    BEFORE  on disk : ['prod-hook-0', 'prod-hook-1', 'prod-hook-2']
    GET     reports : 200 {'hooks': [], 'count': 0}    <- claims ZERO hooks configured
    DELETE  reports : 404 {'detail': 'Hook not found'} <- for a hook that IS in the file
    POST    reports : 200 hook_id=3c8a5930-...
    AFTER   on disk : ['3c8a5930-...']

Three prod hooks destroyed, HTTP 200 throughout, nothing surfaced to the user.

A5 — _save_hooks writes with a plain `open(path, "w")`. A crash, ENOSPC, or a kill mid-write truncates the file in place. That is precisely the corruption A1 then reads as "no hooks" and A2 overwrites. The same codebase already has the correct pattern: theme_state.py:115-126 uses tmp-file + os.replace.

WHY THE THREE ARE ONE ITEM. A5 manufactures the corrupt file, A1 misreads it as empty, A2 destroys the contents. Fixing only A1 leaves truncation reachable; fixing only A5 leaves an existing corrupt file a data-loss trigger; fixing only A2 leaves the API lying about what is configured. The chain is the defect.

DELIBERATELY NOT FIXED UNDER BOB-173, and the reasoning is sound. The implementing agent identified all three while auditing sibling swallows as that item required, and declined to fix them in the same change because: they change GET semantics on an endpoint the frontend consumes (200 -> 5xx); they need a CORRUPT-file reproduction rather than the UNWRITABLE-file one BOB-173 built; and they need a design decision that is genuinely not obvious — a MISSING hooks file legitimately means "no hooks configured", while a CORRUPT one does not, and today's code cannot tell those apart. Expanding BOB-173's scope to cover them would have meant shipping that decision unexamined.

ACCEPTANCE. (a) Distinguish MISSING from CORRUPT: a missing file remains an empty list; a corrupt one is an error, never silently []. (b) Decide and RECORD what GET does on corruption — 5xx, or 200 with an explicit degraded marker the frontend can render. This is the design decision, and it should be stated rather than inferred from whatever the patch happens to do. (c) create/delete MUST NOT overwrite a file they could not parse — refuse, do not clobber (§11.4.252: mutation plus external side effect must fail closed). (d) Make the write atomic via tmp + os.replace, reusing theme_state.py's existing pattern rather than re-inventing it (§11.4.28). (e) Tests asserting the USER-OBSERVABLE outcome, not log lines: seed a corrupt file, assert GET does not claim zero hooks, assert a create refuses rather than destroying, and assert the file still holds the original hooks afterwards. (f) Paired §1.1 mutation per guard. (g) NEGATIVE CONTROLS (§11.4.201(1)): a MISSING file must still yield an empty list and a working create; a VALID file must behave exactly as today. A fix that makes every load fail closed by failing always is not a fix.

A3, RECORDED SEPARATELY, NOT PART OF THIS CHAIN. VALID_EVENTS and HookEventType are two sources of truth for one closed set. Verified identical today, unguarded against drift: if they diverge a hook registers successfully and then silently never fires. One assertion pinning them would close it.

NOT CLAIMED. No change made. The BOB-173 write-failure fix is real and orthogonal — it makes a FAILED write honest; it does nothing about a SUCCESSFUL write of wrong data derived from a misread file.

## BOB-163 — Now that :7187 really rate-limits, the DDoS challenge's cross-endpoint isolation assertion reads a sibling 429 as endpoint-degraded

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-163/closure_evidence_20260923.md
**Severity:** Medium
**Created-By:** BOB-114 remediation, pre-existing defect surfaced by BOB-111 landing a real limiter

**OPERATOR DECISION (2026-08-26, §11.4.66 interactive clarification): YES — 429 IS RESPONSIVE IF Retry-After IS WELL-FORMED**

A 429 carrying a VALID Retry-After header counts as the sibling endpoint being RESPONSIVE. Assertion (c) of the DDoS challenge accepts 2xx OR a well-formed 429 (positive integer seconds or valid HTTP-date — PARSED, not merely present/non-empty). DEGRADED remains: connection failure, timeout, any 5xx, and a 429 with absent or malformed Retry-After. RESIDUAL RISK, accepted knowingly and to be stated in the script source per §11.4.6: a genuinely wedged endpoint that happens to answer 429-with-Retry-After would pass — the Retry-After parse narrows that window, it does not close it. Options (b) limiter-aware drain and (c) exempt healthz probe were both offered and NOT chosen. STILL OPEN, not covered by this decision: the detector counts 429 only, not 503, though the script header says '429 (or equivalent)'; counting 503 would collide with the crash detector's 5xx tally. Decide when BOB-111 lands limiters on :7185 and :7189.

This answer is recorded as consumer DATA per §11.4.35 — it is the operator's stated choice, not an agent inference, and supersedes any prior agent-chosen default on this question. Options not chosen are named above so a future reader does not re-litigate a settled call (§11.4.112(5) bounded-verdict discipline applied to decisions).

--- prior item text follows ---

**Reported-Via:** §11.4.202 reporting directive `bug` on 2026-08-21T19:41:08Z
**Reported-By:** BOB-114 remediation, pre-existing defect surfaced by BOB-111 landing a real limiter

**What (the report, verbatim):**
PRE-EXISTING, NOT INTRODUCED -- and proven so rather than asserted: git diff shows assertion (c) is BYTE-IDENTICAL to HEAD, and the failure reproduces against the unmodified HEAD script. What changed is not the challenge but the SYSTEM: BOB-111 appears at least partially delivered, because :7187 now returns real 429s where it previously returned none. :7185 and :7189 still produce zero 429s.

This is a 11.4.248-class corrosion risk and that is why it is filed rather than left as a footnote: run_all_challenges.sh will now fail INTERMITTENTLY, and an intermittent red trains everyone to re-run until green, at which point a real regression is dismissed as 'probably the flaky rate-limit one'.

THE DECISION, which is an operator call under 11.4.66 and which I deliberately did NOT invent:

  Does a 429 from a WORKING limiter count as the sibling endpoint being RESPONSIVE?

  (a) YES -- a 429 proves the endpoint is alive and correctly protecting itself. Assertion (c) accepts 2xx OR 429, and only a connection failure / 5xx / timeout counts as degraded. Risk: a genuinely wedged endpoint that happens to answer 429 would pass.
  (b) NO -- keep requiring 2xx, but make the challenge limiter-aware: drain or wait out the window before the sibling probe (retry-after is served, so the budget is knowable rather than guessed).
  (c) Probe siblings on a path the limiter exempts (a healthz-class route), so the isolation question is asked without spending the bucket.

Recommendation with reasoning, not just a pick: (a) composed with a bounded liveness check -- a 429 carrying a well-formed Retry-After IS evidence of a live, correctly-behaving service, and (b) makes the challenge slower and couples it to a window value that will drift. But the semantics of 'responsive' here are a product judgement, so the answer is recorded, not assumed.

RELATED, stated as fact rather than folded in: the detector counts 429 only, not 503, though the script header says '429 (or equivalent)'. Counting 503 would collide with the crash detector's 5xx tally. Worth deciding when BOB-111 lands limiters on :7185 and :7189.

**Affected scope / file-scope manifest:**
challenges/scripts/ddos_resilience_challenge.sh assertion (c) cross-endpoint isolation; run_all_challenges.sh which invokes it

**Reproduction / context:**
Assertion (c) requires a sibling-endpoint probe to answer ^2 (a 2xx). :7187 now enforces a real limiter (measured live: x-ratelimit-limit: 120, x-ratelimit-remaining: 86, retry-after: 45, server: uvicorn). A full challenge run sends roughly 250 requests to :7187, so sibling probes fired during the OTHER endpoints' tiers land on an exhausted bucket and receive 429 -- which assertion (c) scores as 'endpoint degraded'. Timing-dependent: one run measured PASS=5 FAIL=2; the UNMODIFIED HEAD script against the same live stack ~30s later measured PASS=7 FAIL=0 SKIP=2.

**Acceptance criteria:**
The operator has answered the classification question below, the answer is recorded as consumer DATA, and assertion (c) implements it. The challenge then produces the same verdict across 3 consecutive runs against a rate-limited stack (11.4.50 deterministic consistency), and the fix ships a paired 1.1 mutation proving assertion (c) still catches a genuinely degraded sibling endpoint -- narrowing it must not blind it (11.4.201(1)).

## BOB-167 — Two SSE routes, one rate-limit class: /search/stream carries @_rl('sse_stream') but the sibling /theme/stream carries no limiter and falls to the 120/min default

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-167/closure_evidence_20260923.md
**Severity:** Medium
**Created-By:** Claude
**Assigned-To:** Claude

WHAT. download-proxy exposes two Server-Sent-Events routes. They are the same expensive class — long-lived connections that hold a worker and a generator for their lifetime — but only one is rate-limit classed:

  routes.py:801  @router.get('/search/stream/{search_id}')
                 @_rl('sse_stream')                          <- classed
  routes.py:150  @router.get('/theme/stream')
                 async def stream_theme(...)                 <- NO limiter decorator

_rl(cls) resolves to limiter.limit(limit_for(cls)), so /search/stream is bound to the sse_stream class while /theme/stream falls through to the application default. Measured live on the running stack: /api/v1/theme/stream reports x-ratelimit-limit 120.

PROVENANCE + A CORRECTION WORTH KEEPING (§11.4.6). This was surfaced by the BOB-109 scaling agent, whose report framed it as: 'sse_stream_limit_decorator is defined and imported/applied nowhere ... SSE falls through to the 120/minute default: 24x less protected'. That framing is WRONG and was NOT filed as given. The agent searched for one symbol NAME; the wiring uses a different mechanism (@_rl('sse_stream')), and it IS applied — to /search/stream. Verified by reading routes.py:795-806 and the _rl helper at routes.py:46-51, with a control needle confirming other *_limit_decorator symbols show real usage in api/__init__.py so the zero-hit was not a blind search. The agent's MEASUREMENT (120 on /theme/stream) was correct and is what makes this a real finding; its MECHANISM was not. Both halves are recorded so the next reader does not re-derive the same wrong cause.

WHY IT MATTERS. An unclassed SSE endpoint is the cheapest way to pin server resources: each connection is held open, and the default class permits 120/min of them. The declared sse_stream class exists precisely because this route shape needs a tighter bound than ordinary GETs.

ACCEPTANCE. (a) A decision, recorded, on whether /theme/stream belongs in the sse_stream class or genuinely warrants the default — this is a policy question, not automatically a bug to patch. (b) If it belongs in sse_stream, the decorator is applied and a test drives BOTH SSE routes and asserts each returns its INTENDED class limit from x-ratelimit-limit, so a future route added without a class is caught. (c) A guard that enumerates SSE-shaped routes and fails on any that carries no explicit rate-limit class — the general form, so the third SSE route does not repeat this. (d) Honest boundary: this does not claim 120/min is exploitable in this deployment; with network_mode host and no reverse proxy every caller shares the 127.0.0.1 bucket, which BOB-111 measured and recorded separately.

NOT CLAIMED. No change made. The limit values were read from headers, never driven to exhaustion — the limiter is per-IP and shared with concurrent agents on this host (§11.4.119).

## BOB-180 — Zero-result search with any captcha-flavoured diagnostic emits a RuTracker-specific headline

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-180/closure_evidence_20260923.md
**Severity:** Low
**Created-By:** Claude
**Assigned-To:** Claude

WHAT: download-proxy/src/api/routes.py:727-745 sets status=captcha_required with a hardcoded message naming RuTracker: 'RuTracker requires CAPTCHA. Use /api/v1/auth/rutracker/captcha'.

FAILING SCENARIO: a whole search returns zero results and the captcha-flavoured diagnostic came from NNMClub's Turnstile, not RuTracker. The user is told to visit a RuTracker captcha endpoint for an NNMClub problem.

SEVERITY BOUNDED: the full errors[] and tracker_stats travel in the same response payload, so the truth is present and a client that reads them is not misled -- only the headline is wrong. The branch was revived by BOB-172's error propagation (correctly: suppressing that propagation would recreate the same false-null one layer up, 11.4.247) and is already covered at the routes layer by tests/unit/api_layer/test_routes_coverage.py:782.

FIX DIRECTION: derive the message from the tracker(s) that actually erred rather than hardcoding one.

SCOPE NOTE: api/ was owned by a sibling stream during BOB-172; the author was correct not to touch it.

ACCEPTANCE: an NNMClub-only captcha diagnostic on a zero-result search produces a headline naming NNMClub.

## BOB-199 — Fail-open scanner flags narrow try/except/pass but not narrow contextlib.suppress — SIM105 still moves those sites out of scope

**Status:** Fixed (→ Fixed.md)
**Type:** Task
**Evidence:** docs/qa/BOB-199/closure_evidence_20260923.md
**Created-By:** Claude
**Assigned-To:** milos85vasic

**OPERATOR DECISION (2026-08-26, §11.4.66): FLAG NARROW SUPPRESS ONLY WITH AN IRREVERSIBLE CAPABILITY**

The scanner flags a narrow contextlib.suppress ONLY when combined with an irreversible capability (delete / truncate / kill) — the shape that actually causes harm. Idiomatic narrow tolerances stay quiet, so the gate keeps its credibility and no false-positive storm trains readers to ignore it. Options not chosen: accept the asymmetry permanently with a header statement; flag all narrow suppress and absorb existing sites via a justified exemption list. MEASUREMENT CORRECTED TWICE, and the second correction explains the first: the original '37 narrow sites, all idiomatic' was propagated by this conductor without verification, then re-measured by the authoring agent as OBSERVER CONTAMINATION (§11.4.201(10)) — 27 vendored third-party + 9 sibling-agent worktree COPIES of the very tree being measured + 1 real = 37. The instrument was counting other agents' duplicates of its own subject. Reproducible figures, each with its scope stated: constitution repo 0 narrow with-suppress; boba DANGER_ROOTS 0 narrow with-suppress and 23 narrow except-pass; boba repo minus vendored 1 narrow with-suppress (a suppress(OSError)); narrow except-pass RETRACTED-AND-RESTATED 2026-08-26 per 11.4.201(9): the figure 97 previously recorded here reproduces under NO scope and is withdrawn. Measured replacements, each with its scope and both independently reproduced: 34 narrow except-pass git-tracked first-party (canonical); 50 narrow except-pass on-disk minus scratch dirs (the 'minus vendored' scope this sentence states). Brackets that explain the bad number: 87 ALL-except-pass git-tracked and 113 ALL-except-pass on-disk-minus-scratch straddle 97, so 97 was a class-scope conflation (narrow-vs-all), not a corpus-scope one. The 35 cited later in this record is the same measurement at git-tracked scope and agrees with 34 within one site. The 'every one idiomatic' claim was also false — the except-pass census contains SystemExit x2 (tests/unit/test_plugin_torrentscsv.py:305,328), which is not a benign tolerance. CORRECTION 2026-08-26: a 'KeyboardInterrupt x1' previously written in this sentence was itself unsourced and is WITHDRAWN — it reproduces at NEITHER stated scope. Independent AST count over git-tracked *.py: ZERO genuine 'except KeyboardInterrupt: pass'. The only genuine instance in the checkout is .worktrees/ci-split-workflows/tests/unit/test_main.py:63 — a sibling-agent scratch worktree, i.e. the exact observer-contamination class (11.4.201(10)) this very record teaches to exclude — and the only main-tree textual match (tests/unit/test_graceful_shutdown.py:165) sits inside a triple-quoted string literal, a carrier not code (11.4.201(7)(a)). Recorded because the error is instructive: it was introduced BY the retraction that removed the 97, so a correction is not exempt from the discipline it applies.

Recorded as consumer DATA per §11.4.35 — the operator's stated choice, not an agent inference. Options not chosen are named so a future reader does not re-litigate a settled call.

--- prior item text follows ---

RESIDUAL ASYMMETRY surfaced by the BOB-195 fix, reported rather than silently closed. After teaching the scanner With nodes, a BROAD suppress (Exception / BaseException) is detected with the same severity as try/except/pass. A NARROW suppress (suppress(FileNotFoundError)) is not - but the semantically identical narrow try/except FileNotFoundError: pass IS flagged. So ruff SIM105 rewriting a narrow handler still moves that site out of the gate's scope, a smaller version of the exact mechanism BOB-195 was filed to close.

WHY IT WAS NOT CLOSED IN THAT PASS, with the measurement that decided it: the authoring agent reported 37 narrow suppress sites, all idiomatic. CORRECTION (2026-08-26, independent review): that figure DOES NOT REPRODUCE and this conductor propagated it into this item as fact without verifying - the error is mine, not the reviewer's. Measured: the constitution repo has 0 narrow `with suppress(X)` sites; boba first-party has exactly 1 (a suppress(OSError)). The nearest corpus match is 35 narrow `except X: pass` handlers in boba first-party - a DIFFERENT construct - and their class census (OSError x7, ImportError x7, BrokenPipeError x3, RuntimeError x3, ValueError x2, FileNotFoundError x2, IndexError x2, SystemExit x2) contradicts 'every one idiomatic': a bare `SystemExit: pass` is not a benign tolerance. The two populations must not be conflated, and the distinction is the whole substance of this item. The false-positive-storm argument therefore rests on the 35 narrow except-handlers, not on 37 suppress sites, and its strength should be re-judged on that basis, which under 11.4.201(1) is a FAIL-bluff of equal severity to the gap it would close, and worse in practice because it trains readers to ignore the gate. The subagent recorded the asymmetry in the gate header as a known gap rather than shipping the storm. That was the right call, and is why this is a separate tracked item rather than an unfinished one.

THE DECISION IS THE OPERATOR'S, mirroring BOB-195 itself: (a) accept the asymmetry permanently, with the gate header stating it so no reader mistakes the count for a census; (b) flag narrow suppress ONLY when combined with an irreversible capability (delete / truncate / kill), catching the shape that actually matters and leaving the 37 idiomatic sites quiet; (c) flag all narrow suppress and absorb the 37 via a justified exemption list like the LAN-route guard uses.

RELATED FACT worth carrying: the five newly-visible production sites in download-proxy/src/merge_service/search.py (1294, 1303, 1322, 1329, 1333) wrap proc.kill / os.killpg / proc.wait in the BOB-126 cleanup path. The conductor verified the 11.4.263 pgid guard IS present and correct at both killpg sites - _pid and _pgid each checked isinstance(int) and > 1 before the syscall, with the BOB-126 forensic reasoning inline - so those sites are true-by-the-scanner's-definition but SAFE in fact, and want a justified exemption entry rather than a code change.

## BOB-200 — cm_dangerous_combination_fail_closed gate reads a dead find(1) as a topology SKIP (exit 0) instead of failing closed

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Evidence:** docs/qa/BOB-200/closure_evidence_20260923.md
**Severity:** Medium

WHAT: scripts/gates/cm_dangerous_combination_fail_closed.sh builds its scan file list with find(1). If find itself DIES (permission error, resource exhaustion, interrupted), the gate receives an EMPTY file list and interprets that as 'no files in scope' -> honest topology SKIP -> exit 0. The failure IS loud on stderr but SILENT in the exit code, so any caller gating on exit status reads a dead instrument as a clean corpus.

WHY IT MATTERS: this is a textbook 11.4.201(6) FALSE-NULL -- a blind instrument and a clean artifact return the identical quiet zero. It is also a 11.4.252 fail-OPEN on exactly the 'cannot enumerate the corpus' condition where the gate's own stated discipline is to fail CLOSED. A gate that cannot see must refuse, not pass.

AFFECTED SCOPE: constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh (the find invocation and the empty-list branch). PRE-EXISTING -- NOT introduced by the BOB-195 change; found by the independent round-2 reviewer while reviewing that change and explicitly scoped OUT of its remediation.

REPRODUCTION: make find(1) fail during the gate run (unreadable scan root, or a find stub returning non-zero with empty stdout) and observe the gate exit 0 with a topology-SKIP message, indistinguishable from a genuinely empty corpus.

ACCEPTANCE: (1) the gate distinguishes 'find succeeded and found zero files' from 'find failed' -- check find's exit status, not only its output; (2) a failed enumeration is a FINDING (non-zero exit) naming the unresolved precondition, never a SKIP; (3) a genuinely empty scan root still SKIPs honestly at exit 0 -- the 11.4.201(1) golden-FALSE guard, so the fix does not become a false-positive refusal; (4) paired 1.1 mutation: restore the swallow-find-failure behaviour and the new fixture MUST fail.

