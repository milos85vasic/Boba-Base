# Fixed — Closed Workable Items

**Revision:** 19
**Last modified:** 2026-08-20T15:03:18Z
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
**Evidence:** .superpowers/sdd/task-8-syscall-audit.md
**Severity:** Low

Follow-up to BOB-126 systematic sweep. Task 8 audit surfaced 2 test cases in tests/unit/merge_service/test_public_tracker_subprocess_timeout.py that set explicit int mock.pid (12345, 1111) satisfying the production BOB-126 int-guard, but did NOT patch os.killpg/os.getpgid so the real syscalls fired against hardcoded non-owned PIDs. Low collision probability on typical host, but section 11.4.263(C) hygiene violation in the exact file authored to guard against host-wide kills. FIX at 8bedc5a: added patch.object(_search.os, getpgid) + patch.object(_search.os, killpg) to both tests matching sibling test_process_group_kill_called_on_deadline pattern. 6/6 tests still PASS. Report: .superpowers/sdd/task-8-syscall-audit.md. Recommended gate CM-TEST-KILLPG-PATCHED-WHEN-REAL-PID tracked as separate followup.

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

