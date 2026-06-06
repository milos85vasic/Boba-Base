# Fixed — Closed Workable Items

**Revision:** 3
**Last modified:** 2026-06-06T18:30:00Z
**Ticket prefix:** `BOB` (operator-mandated, 2026-06-06)
**Scope:** Closed items only. Open items live in [`Issues.md`](Issues.md).

> Closure statuses per §11.4.33: Bug → `Fixed`, Feature → `Implemented`,
> Task → `Completed`. Each carries captured-evidence (anti-bluff §11.4).

---

## §1. [BOB-001] start.sh BSD-sed incompatibility aborted the boot

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `c5cbd40`

GNU `sed -i SCRIPT` calls (6 sites) aborted `start.sh` on macOS/BSD sed with
"invalid command code", before `compose up` — the stack never started. Added a
portable `sed_inplace()` (`-i.bak` then drop backup; works GNU+BSD) and
converted all 6 sites (§11.4.67/§11.4.81).
**Evidence:** `tests/unit/test_sed_inplace_portable.sh` — 4 passed (RED before
fix); boot #2 then progressed past the config step.

## §2. [BOB-002] start.sh `podman unshare` incompatible with macOS remote podman

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `c5cbd40`

`podman unshare cp/chmod` (rootless-Linux-only) aborted plugin install on the
macOS remote podman client. Added `_podman_unshare_works()` self-detection;
falls back to plain `cp`/`chmod` on macOS (§11.4.81).
**Evidence:** boot #3 reached `compose up` and brought all 4 containers up.

## §3. [BOB-003] macOS tunnel port detection broken (ports never forwarded)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `c5cbd40`

`ensure-macos-tunnel.sh` parsed the connection NAME, not the SSH port ("Bad
port 'podman-machine-default'"), so container ports were never forwarded to
macOS localhost. Now uses `podman machine inspect {{.SSHConfig.Port}}` with a
URI-parse fallback.
**Evidence:** tunnel established (port 51347); `curl` localhost 7186→200,
7187→200, 7189→404, 9117→301 after the fix.

## §4. [BOB-004] Private-tracker credentials stored securely + verified working

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

## §5. [BOB-013] torrentkitty `_parse_size` reported 0 for every KB/MB/GB/TB size

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `14bc5c4`

`"B"` substring-matched inside KB/MB/GB/TB so all realistic sizes parsed to 0.
Fixed to match on the suffix, longest unit first.
**Evidence:** `tests/unit/test_plugin_search_engines.py` — torrentkitty size
tests assert correct byte values; 18 passed.

## §7. [BOB-005] Public-tracker plugins all raised an unhandled exception (systemic)

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

## §8. [BOB-016] Jackett plugin crashed (`Pool(0)`) when zero indexers are configured

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

## §6. [BOB-014] Go `generateID()` collided under burst (UnixNano-only)

**Status:** Fixed (→ Fixed.md)
**Type:** Bug
**Closed:** 2026-06-06 · **Commit:** `d46ea57`

`time.Now().UnixNano()` is not unique under rapid `StartSearch` calls →
dropped searches + broke `MAX_CONCURRENT_SEARCHES`. Fixed with an atomic
counter.
**Evidence:** `TestGenerateID_UniqueUnderBurst` (10k IDs unique) + queue-full
test via real `StartSearch`; `go test -race` green, deterministic.
