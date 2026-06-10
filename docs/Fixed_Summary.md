# Fixed_Summary

Closed workable items (current_location = Fixed), regenerated from the SQLite single-source-of-truth (§11.4.53).

## Counts by Type × Status

| Type | Status | Count |
|---|---|---|
| Bug | Fixed (→ Fixed.md) | 15 |
| Feature | Implemented (→ Fixed.md) | 17 |
| Task | Completed (→ Fixed.md) | 9 |
| Task | Fixed (→ Fixed.md) | 4 |
| Task | Implemented (→ Fixed.md) | 17 |
| **TOTAL** | | **62** |

## Items

| ATM ID | Type | Status | Severity | Description |
|---|---|---|---|---|
| BOB-001 | Bug | Fixed (→ Fixed.md) | — | start.sh BSD-sed incompatibility aborted the boot |
| BOB-002 | Bug | Fixed (→ Fixed.md) | — | start.sh `podman unshare` incompatible with macOS remote podman |
| BOB-003 | Bug | Fixed (→ Fixed.md) | — | macOS tunnel port detection broken (ports never forwarded) |
| BOB-004 | Task | Completed (→ Fixed.md) | — | Private-tracker credentials stored securely + verified working |
| BOB-005 | Task | Fixed (→ Fixed.md) | — | Public-tracker plugins all raised an unhandled exception (systemic) |
| BOB-006 | Feature | Implemented (→ Fixed.md) | — | NNMClub username/password login wired — NNMClub now uses the operator's `NNMCLUB_USERNAME`/`NNMCLUB_PASSWORD` (in . |
| BOB-007 | Task | Completed (→ Fixed.md) | — | RuTor documented as public (no-auth) — RuTor is a public tracker with no login endpoint; `RUTOR_USERNAME/PASSWORD` are |
| BOB-009 | Task | Completed (→ Fixed.md) | — | Containers submodule integrated with Go wrapper |
| BOB-010 | Task | Completed (→ Fixed.md) | — | Workable-items SQLite DB integrated + pre-build gate wired (§11.4.93/§11.4.95) |
| BOB-011 | Feature | Implemented (→ Fixed.md) | — | DOCX export support added — `generate_markdown_exports. |
| BOB-012 | Task | Completed (→ Fixed.md) | — | Export-sync gate expanded to all docs (§11.4.65) |
| BOB-013 | Bug | Fixed (→ Fixed.md) | — | torrentkitty `_parse_size` reported 0 for every KB/MB/GB/TB size |
| BOB-014 | Bug | Fixed (→ Fixed.md) | — | Go `generateID()` collided under burst (UnixNano-only) |
| BOB-015 | Task | Fixed (→ Fixed.md) | — | Remaining public-tracker failures are external / non-deterministic |
| BOB-016 | Task | Fixed (→ Fixed.md) | — | Jackett plugin crashed (`Pool(0)`) when zero indexers are configured |
| BOB-017 | Bug | Fixed (→ Fixed.md) | — | NNMClub plugin self-heal crashed on invalid ICON |
| BOB-018 | Task | Completed (→ Fixed.md) | — | Jackett server image updated to latest |
| BOB-019 | Task | Completed (→ Fixed.md) | — | Jackett added as a reference submodule (latest release) |
| BOB-020 | Task | Completed (→ Fixed.md) | — | CodeGraph initialized + wired (§11.4.78/79/80) |
| BOB-021 | Bug | Fixed (→ Fixed.md) | — | env_loader flaky test: KEY2 leak across test ordering |
| BOB-022 | Bug | Fixed (→ Fixed.md) | — | AsyncMock warning in search deep-coverage tests |
| BOB-023 | Feature | Implemented (→ Fixed.md) | — | gamestorrents plugin deep-coverage tests + B-substring bug documented |
| BOB-024 | Bug | Fixed (→ Fixed.md) | — | gamestorrents `_parse_size` B-substring bug fixed |
| BOB-025 | Feature | Implemented (→ Fixed.md) | — | eztv.py deep-coverage tests (54 tests) — 54 tests covering MyHtmlParser (size units, date patterns, defaults, special chars), |
| BOB-026 | Feature | Implemented (→ Fixed.md) | — | piratebay.py deep-coverage tests + import-order bug documented |
| BOB-027 | Feature | Implemented (→ Fixed.md) | — | solidtorrents.py deep-coverage tests (37 tests) |
| BOB-028 | Feature | Implemented (→ Fixed.md) | — | limetorrents.py deep-coverage tests (52 tests) |
| BOB-029 | Feature | Implemented (→ Fixed.md) | — | torlock.py deep-coverage tests (55 tests) |
| BOB-030 | Feature | Implemented (→ Fixed.md) | — | nyaa.py deep-coverage tests + missing import re bug documented |
| BOB-031 | Feature | Implemented (→ Fixed.md) | — | kickass.py deep-coverage tests + comma-size gap documented |
| BOB-032 | Feature | Implemented (→ Fixed.md) | — | anilibra.py deep-coverage tests (49 tests) |
| BOB-033 | Bug | Fixed (→ Fixed.md) | — | kickass.py crash guards added (BOB-015 defense-in-depth) |
| BOB-034 | Feature | Implemented (→ Fixed.md) | — | torrentgalaxy.py + yts.py deeper coverage (80 new tests) |
| BOB-035 | Bug | Fixed (→ Fixed.md) | — | nyaa.py missing import re fixed — `download_torrent()` called `re. |
| BOB-036 | Bug | Fixed (→ Fixed.md) | — | kickass.py comma-separated size regex fixed |
| BOB-037 | Feature | Implemented (→ Fixed.md) | — | rutor.py deep-coverage tests (83 tests) — 83 tests covering date normalization, pagination math, config, proxy, |
| BOB-038 | Feature | Implemented (→ Fixed.md) | — | tokyotoshokan.py deep-coverage tests (60 tests) |
| BOB-039 | Feature | Implemented (→ Fixed.md) | — | snowfl.py deep-coverage tests (30 tests) |
| BOB-040 | Feature | Implemented (→ Fixed.md) | — | torrentdownload.py deep-coverage tests (35 tests) |
| BOB-041 | Feature | Implemented (→ Fixed.md) | — | linuxtracker.py deep-coverage tests (30 tests) |
| BOB-042 | Task | Implemented (→ Fixed.md) | — | audiobookbay.py deep-coverage tests + missing import re fixed |
| BOB-043 | Task | Implemented (→ Fixed.md) | — | one337x.py deep-coverage tests + B-substring fixed |
| BOB-044 | Task | Implemented (→ Fixed.md) | — | extratorrent.py deep-coverage tests + B-substring fixed |
| BOB-045 | Task | Implemented (→ Fixed.md) | — | torrentfunk.py deep-coverage tests + B-substring fixed |
| BOB-046 | Task | Implemented (→ Fixed.md) | — | torrentproject.py deep-coverage tests — 36 tests covering MyHTMLParser (handle_starttag/endtag/data), feed, fetch_magnet. |
| BOB-047 | Task | Implemented (→ Fixed.md) | — | therarbg.py deep-coverage tests + B-substring fixed |
| BOB-048 | Task | Implemented (→ Fixed.md) | — | academictorrents.py deep-coverage tests — 48 tests covering XML parsing, concurrent. |
| BOB-049 | Task | Implemented (→ Fixed.md) | — | ali213.py deep-coverage tests — 25 tests covering threaded gamepage handling, retry loop (20 ceiling), magnet extraction. |
| BOB-050 | Task | Implemented (→ Fixed.md) | — | yourbittorrent.py deep-coverage tests — 30 tests covering HTMLParser, download_file, 7 categories. |
| BOB-051 | Task | Implemented (→ Fixed.md) | — | glotorrents.py deep-coverage tests — 40 tests covering pagination, 9 categories, magnet extraction, sleep. |
| BOB-052 | Task | Implemented (→ Fixed.md) | — | pctorrent.py deep-coverage tests + B-substring pre-fixed |
| BOB-053 | Task | Implemented (→ Fixed.md) | — | rockbox.py deep-coverage tests — 32 tests covering datetime, sleep(3) pagination, kb/mb/gb sizes. |
| BOB-054 | Task | Implemented (→ Fixed.md) | — | bitru.py deep-coverage tests + B-substring fixed |
| BOB-055 | Task | Implemented (→ Fixed.md) | — | btsow.py deep-coverage tests — Tests covering data-list card parsing, search, download_torrent. |
| BOB-056 | Task | Implemented (→ Fixed.md) | — | torrentscsv.py deep-coverage tests — 33 tests covering CSV parsing, search, download_torrent. |
| BOB-057 | Task | Implemented (→ Fixed.md) | — | xfsub.py deep-coverage tests + B-substring fixed |
| BOB-058 | Task | Implemented (→ Fixed.md) | — | yihua.py deep-coverage tests + B-substring fixed |
| BOB-059 | Task | Fixed (→ Fixed.md) | — | bt4g.py tests fixed (was hanging) — 3 tests had bugs: infinite loop from constant `return_value` (should use |
| BOB-060 | Bug | Fixed (→ Fixed.md) | Low | tokyotoshokan/kickass/yts/piratebay raised unhandled exceptions on empty/None/non-dict-JSON upstream responses; added empty-response guards + RED→GREEN regression tests (§11.4.118 audit found piratebay). |
| BOB-061 | Bug | Fixed (→ Fixed.md) | High | Full pytest tests/unit/ stalled on an unbounded enricher network lookup; 13-34 order-dependent failures from sys.modules/socket/os.environ leakage across files. Fixed: enricher ClientTimeout + tests/conftest.py path/POLLUTING_ROOTS/socket/environ isolation. Now 4121 passed deterministic. |
| BOB-062 | Bug | Fixed (→ Fixed.md) | Medium | kickass/bitsearch/torrentgalaxy while-True search loops could run forever; search.py/routes.py/helpers.py/eztv.py network calls had no timeout. Fixed: MAX_PAGES=50 caps + aiohttp.ClientTimeout/urlopen timeout=30 across all sites. |
| BOB-063 | Task | Completed (→ Fixed.md) | Low | test_plugin_pirateiro.py injected sys.modules['pirateiro'] at module scope with no teardown; pirateiro was the one root not covered by conftest _isolate_download_proxy_modules, so it leaked into later tests. Fixed by caching+re-registering+purging the stub per unit test; added a standing isolation guard. RED 1-fail -> GREEN, full suite 4122 passed x2 seeds. |
