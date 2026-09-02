# QA evidence — qBittorrent WebUI login repair + themed-overlay removal

**Revision:** 2
**Last modified:** 2026-09-02T05:50:00Z

Captured evidence for the 2026-09-01 repair of "cannot log in to the qBittorrent
WebUI with admin/admin", plus the boot failure, the themed-WebUI overlay
removal, and the systemd reboot-survival work.

Revision 2 (2026-09-02) adds the round-2 exhaustive root-cause sweep — see the
final section. The original round-1 text above is preserved unedited; every
status change is recorded as a change rather than rewritten in place, so the
document shows what was believed when (§11.4.6).

Image under test: `lscr.io/linuxserver/qbittorrent:latest` → **qBittorrent
v5.2.3 / WebAPI 2.15.1** (measured, not assumed).

## The defect chain (all proven, none inferred)

| # | Defect | How it was proven |
|---|---|---|
| RC-1 | Credentials authored into `config/qBittorrent/config/qBittorrent.conf`, but the image reads `/config/qBittorrent/qBittorrent.conf` and launches `qbittorrent-nox` with **no `--profile`** | Read the image's own `init-qbittorrent-config/run` and `svc-qbittorrent/run` |
| RC-2 | `WEBUI_USERNAME` / `WEBUI_PASSWORD` in compose are **inert** — the image implements neither | Control needle: same grep over the image found `WEBUI_PORT`, found nothing for those two |
| RC-3 | qBittorrent 5.x therefore mints a random temporary password every boot | `runs/RED_temporary_password_capture.log` |
| RC-4 | `start.sh` `_ensure_webui_credentials` was **replace-only** (`grep -q … && sed`), so it wrote nothing into a config lacking the keys | `runs/start_sh_boot_integrity.txt` (D2), RED then GREEN |
| RC-5 | Every password path detected success by body `== "Ok."`; 5.2.3 returns **204 + empty body + `QBT_SID_<port>`** | Measured live; `runs/live_verification.txt` |
| RC-6 | Go client required 200 **and** `"Ok."` **and** cookie `SID` — could never authenticate | `qBitTorrent-go/internal/client/auth_qbt5_test.go`, RED then GREEN |
| RC-7 | **Boot abort**: `((attempt++))` with `attempt=0` returns exit 1 under `set -euo pipefail`, killing `start.sh` at the first retry | `runs/start_sh_boot_integrity.txt` (D1) |
| RC-8 | `cleanup_stale_config` deleted the live config every boot — its predicate matched qBittorrent's own normalised `SavePath=/downloads/` | 3 accumulated `.backup.*` files; predicate matched twice |
| RC-9 | **Security regression caught during the repair**: enforcing `LocalHostAuth=false` + `AuthSubnetWhitelistEnabled=true` disables auth for loopback and all RFC1918. A wrong password returned **204 (accepted)** | Negative control in `runs/live_verification.txt` |
| RC-10 | Angular dashboard never built → `_angular_available=False` → `:7187/` served `{"dashboard":"not found"}` under HTTP 200 | `runs/final_verification.txt` before/after |

## Files

| File | What it holds |
|---|---|
| `runs/RED_temporary_password_capture.log` | The original qBittorrent boot log showing the temporary password being minted |
| `runs/start_sh_boot_integrity.txt` | GREEN run of the D1–D4 boot-integrity guard |
| `runs/cm_gate.txt` | `CM-QBITTORRENT-WEBUI-CREDENTIALS` gate result |
| `runs/cm_gate_mutation.txt` | Paired §1.1 mutation meta-test — gate fires on 4 broken arms, clean on 3 good arms |
| `runs/full_boot.log` | Complete `./start.sh` boot, ANSI-stripped, with every warning |
| `runs/live_verification.txt` | Login matrix + vanilla-WebUI integrity immediately after the fix |
| `runs/final_verification.txt` | Full-stack sweep: containers, ports, login, dashboard, security posture, systemd |

## Honest boundary (§11.4.6)

**PROVEN by captured runtime evidence:**
- `admin`/`admin` authenticates on both `:7185` and `:7186` (HTTP 204 + `QBT_SID`)
- A wrong password is **rejected** (401) and an unauthenticated API call is Forbidden — authentication is real, not bypassed
- No temporary password is minted
- All four containers healthy; vanilla qBittorrent WebUI served with zero overlay
- Angular dashboard serves with assets resolving
- systemd units installed, `boba.target` enabled, `Linger=yes`

**NOT PROVEN — stated as owed, not claimed:**
- **Reboot survival end-to-end.** Units are installed, enabled, valid, and linger is on — necessary, *not sufficient*. A real reboot is the only proof and host power operations are hard-banned here (CONST-033). Operator-attended verification required.
- **Firefox / WebKit.** The browser proof ran on Chromium only.
- **`docs/qa/` historical twins.** 698 `.html`/`.pdf` files were re-rendered by
  a `pandoc 3.10 → 3.11` upgrade even though their `.md` sources never changed;
  320 of those are historical evidence artifacts. Included at operator
  instruction after the alternative was raised.

**RESOLVED SINCE THIS FILE WAS FIRST WRITTEN** (recorded rather than silently
edited, so the record shows what was true when):
- ~~pytest not installed~~ — `uv` was available all along; a venv exists at
  `.venv` and the full unit sweep runs. My earlier "needs `python3-venv` +
  sudo" conclusion was wrong: I had checked one mechanism, not the alternatives.
- ~~Playwright not installed~~ — it arrived with the frontend `npm install`.
  The vanilla-WebUI claim now rests on a REAL Chromium render: `window.qBittorrent`
  live with 27 members and 17 `Client` functions, zero console errors, and live
  sync data (`Free space: 1.533 TiB`, `DHT: 122 nodes`) visible in the captured
  screenshot — not on HTML-integrity assertions.
- ~~doc-twin exporter not runnable~~ — `scripts/generate_markdown_exports.sh`
  existed and was already wired into pre-build; it was gated on a
  `from weasyprint import HTML` import while execing the weasyprint **CLI**, so
  it printed "PDF support: not available" and exited 0 having written nothing.

---

## Owed tracked items (§11.4.197) — ALL THREE NOW RESOLVED (2026-09-02)

**Status change.** These three were staged here on 2026-09-01 because the
mandated minting path was unavailable (no built `workable-items` binary, no
consumer config for `constitution/scripts/reporting/report_item.sh`), and
hand-writing rows into `docs/Issues.md` would desynchronise the SQLite
single-source-of-truth (§11.4.93/§11.4.95).

On 2026-09-02 the operator directed that **everything discovered be
systematically investigated and fixed at root cause — nothing parked as a
ticket.** All three were therefore closed rather than tracked. Their original
text is preserved below unedited, each followed by its resolution, so the
record shows what was true when (§11.4.6 — resolution recorded, not silently
rewritten).

The `workable-items` binary was subsequently built during this work (it is
gitignored), which is also why the docs-sync commit seam's CHECK 1-3 had not
been running at all.

**Resolution summary:**

| Item | Resolution |
|---|---|
| OWED-1 shared add-success predicate | **CLOSED** — `download-proxy/src/merge_service/qbit_add.py`; one mutation now fails BOTH consumers (5 tests across the bridge and routes halves), verified and `sha256`-restored |
| OWED-2 stress-suite torrent purge | **CLOSED** — diff-scoped to `after - before`; loud on failure; blocking gate 55 `CM-NO-UNSCOPED-LIVE-DESTRUCTION` + 11-arm meta-test + 5 hermetic regression tests |
| OWED-3 two standing test reds | **CLOSED** — `test_no_runtime_service_skips` (3 fixture gates + 2 `# allow-skip:` annotations, the latter carrier-matched `merge_service/` as a service); `test_bob129_slowapi_response_contract` (import-alias duplicate registration under `api_routes`, fixed in two independent layers) |



### OWED-1 — Extract a shared `_qbit_add_succeeded` predicate  (Type: Task)

Two implementations of qBittorrent's add-success contract now exist:
`download-proxy/src/api/routes.py:_qbit_add_succeeded` and
`webui-bridge.py:_qbit_add_succeeded`. Review #3 findings F2/F3/F4 all trace to
that duplication — the two copies drifted and briefly recorded *opposite* 409
verdicts. Extract one dependency-free module both import (§11.4.251).

Acceptance: a single mutation of the shared logic must make BOTH sites' tests
fail. Today a mutation of either copy leaves the other's tests green, which is
exactly how the divergence went unnoticed.

Measured contract the shared predicate must encode (qBittorrent v5.2.3 /
WebAPI 2.15.1, 2026-09-01):

| case | response | meaning |
|---|---|---|
| valid file add | `200 {"success_count":1}` | added |
| `.torrent` URL add | `202 {"pending_count":1}` | added, fetching async |
| magnet add | `200 {"success_count":1}` | added |
| duplicate add | `409 Conflict` | already present (success) |
| **no payload** | `409 Conflict` | **nothing added (failure)** |
| corrupt/truncated/empty file | `415` | rejected |

The 409 ambiguity is the load-bearing part: it means success OR failure
depending on whether a payload was sent, and the status alone cannot tell.
Empty URLs are now rejected at `DownloadRequest` validation so a 409 reaching
the predicate implies a genuine duplicate — the shared version must preserve
that invariant or restore the ambiguity explicitly.

### OWED-2 — Scope the stress suite's torrent purge  (Type: Bug)

`tests/stress/test_search_stress.py:18-54` `_purge_qbittorrent_torrents()`
lists **every torrent in the instance** via `torrents/info` — not diff-scoped —
and deletes them all with `deleteFiles=false`, from an `autouse` fixture that
runs before every stress test. On an operator's live instance that silently
de-registers their entire library (files survive; the session does not).

Pre-existing (landed `a684b2f`, 2026-04-20), so not caused by this batch, and
it did NOT cause the 2026-09-01 incident — that one's log signature is
staggered single removals with a WebUI page-load six seconds prior, whereas
this purge issues one batched delete. But the hazard is real and standing.

Fix: scope to test-added hashes only, as the bridge suite already does
(`added = hashes_after - before`). Never "delete everything the operator owns".

Also a §11.4.238 coverage escape: an agent found this, no gate did.

### OWED-3 — Two standing test reds  (Type: Task)

* `tests/unit/test_no_runtime_service_skips.py` — 5 service-availability skips
  in `tests/scaling/` and `tests/unit/test_plugin_rutracker.py` need converting
  to fixture gates. Pre-existing; fails at HEAD too.
* `tests/unit/test_bob129_slowapi_response_contract.py` — fails in the full
  sweep, PASSES in isolation. Order-dependent or flaky; cause UNKNOWN, needs
  §11.4.102 systematic debugging. §11.4.248 quarantine-or-stabilise candidate.

---

## Round 2 (2026-09-02) — exhaustive root-cause sweep

Operator instruction: *"everything discovered MUST BE exhaustively and
systhematically investigated, debugged and fixed by addressing the real root
causes of all issues!"*

Every item below was found DURING this work, not reported by the operator —
which per §11.4.238 makes each one a coverage escape in its own right. Each was
root-caused, fixed, and paired with a mutation proving the fix load-bearing.

### Security / data-safety

| Defect | Root cause | Proof |
|---|---|---|
| `ci.sh` secret scan structurally blind | PCRE `(?:…)` under `grep -E` (ERE), warning eaten by `2>/dev/null`; ALSO `["\x27]` in a bracket expression is five literal chars, so `'`-quoted secrets could never match | planted needle FAILs the step; both quote styles now detected; control needle assembled at runtime so ci.sh cannot match itself |
| `.env` truncation → master-key loss | `grep … \|\| true` then unconditional `mv -f`; empty temp published over `.env` | line-count + key-NAME-set invariants; aborts loudly, `.env` byte-identical; proven against the silent-drop case an exit-code check misses |
| Unscoped live destruction | `"\|".join(t["hash"] for t in torrents)` from an `autouse` fixture — every operator torrent, `deleteFiles=false` | diff-scoped to `after - before`; gate 55 + 11-arm meta-test; `None` baseline deliberately disarms teardown rather than degrading to `set()` (which would delete everything) |
| Jackett API key in `ps`-visible argv | key interpolated into a python `-c` command line | moved to `BOBA_JACKETT_KEY` env; key value appears 0 times in all output |
| `start.sh` two silent write paths | `\|\| true` on the plugin JSON, AND `sed_inplace` ending in `rm -f …bobabak` which succeeds after a failed `sed -i` | attempt → verify by read-back → report; `[SUCCESS]` no longer printable on a write that never landed |

### Correctness

| Defect | Root cause |
|---|---|
| 7 rutracker tests order-dependent | `_load_rutracker()` set `sys.modules["rutracker"]` as a SIDE EFFECT; `plugins/` is not on `sys.path`, so bare imports resolved only by luck of the `pytest-randomly` seed. 12-seed swept after fix |
| `search_stream` false-positive | a test loaded `routes.py` under alias `api_routes`, re-running the rate-limit decorator and registering the SAME function twice; the allowlist keyed on module path missed the duplicate. Isolation saw 3 endpoints, sweep saw 4 — the 4th a duplicate, not a new endpoint |
| Tracker roster diverged 3 ways | `nnm-club.me` in the bridge only → merge service fell through to the UNAUTHENTICATED path, saving an HTML 401 body as a `.torrent` |
| 4 CORS defects | unset vs `""` took different code paths (unset DENIED `:4200` and all `127.0.0.1`); `MERGE_SERVICE_PORT` hardcoded; wildcard matched whole-string so an operator's `*` did nothing; whitespace input failed CLOSED to an empty allowlist |
| 11 bare `except:` across 8 live plugin files | caught `KeyboardInterrupt`/`SystemExit`; diagnostics now on stderr — fd 1 is the nova3 result stream |
| Cyrillic decode untested | existing tests fed cp1251 bytes but asserted only ASCII titles; `nnmclub` decodes `errors="ignore"`. 25 tests now assert exact equality against a real library title |

### Instrument integrity (detectors that could not do their job)

| Defect | Root cause |
|---|---|
| Verdict extractor substring-matched | `^` bound only the first alternation group; `tail -n1` then took a prose line. Measured: it flipped a PASS into a SKIP. **Blast radius corrected: 9 wired gates, 0 currently misreported, 19/267 latent** — not the 267 first claimed |
| Propagation gate bare-literal | `grep -qF '11.4.238'` satisfied by any mention; mirrors had 0 block-starts |
| Credentials clause prefix collision | `§11.4.109` CONTAINS `§11.4.10`, so the check passed even with §11.4.10 deleted |
| My own D1 check carrier-blind | grepped the raw file, so a truthful comment about the historical defect read as live code — it had already forced another agent to reword accurate documentation |

### Gates validated rather than assumed

`check_cm_no_production_mutation_residue` (16 arms) and
`check_cm_healthcheck_covers_served_ports` (15 arms) both proved SOUND under
mutation, gates left byte-identical. Notable: a mutation stripping the residue
scanner's string mask initially SURVIVED all five carrier arms — none had a
comment introducer inside a string literal. Five arms no mutation could break
were decoration; a sixth with the right shape now catches it (§11.4.194(6)(d)).

### Honest boundaries carried forward

- **Reboot survival** remains UNPROVEN end-to-end. Units installed, enabled,
  valid, linger on — necessary, not sufficient. Host power operations are
  hard-banned (CONST-033); operator-attended verification required.
- **Firefox / WebKit**: Playwright's bundled browsers were never installed
  (`~/.cache/ms-playwright` empty); the Chromium proof used the host snap via
  `executablePath`. Driving host Firefox HUNG for 120s, consistent with
  Playwright requiring its own patched build. Measured, not assumed.
- **Roster presence** is asserted by consumer-agreement, which cannot prove a
  domain is PRESENT (the test iterates the roster it validates). Being closed.
- **`tests/security/` tally is not deterministic** — 9 failed/14 failed/0 failed
  across three runs, flipping with live-stack availability. A §11.4.50 issue,
  proven NOT caused by this batch (stash-and-rerun gave an identical tally).
