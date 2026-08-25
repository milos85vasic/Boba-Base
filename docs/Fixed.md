# Fixed — Closed Workable Items

**Revision:** 32
**Last modified:** 2026-08-25T20:29:07Z
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

