# Final System Proof — Boba Merge Service (live nezha @ e800ebd)

**Revision:** 1
**Last modified:** 2026-06-17T00:00:00Z
**Authority:** End-to-end live verification (read-only) against the deployed stack
**Scope:** Full-fleet ASCII + multi-word + Cyrillic searches; encoding-crash census; private-tracker auth; gamestorrents

---

## Headline

Three full-fleet searches (29-tracker fleet) ran sequentially against the live
deployed merge service on `nezha.local:7187` (HTTP 200 confirmed before testing).
All three returned large real result sets. The P0 system-wide query-encoding fix
holds for the core trackers — Cyrillic `Война и мир` returned correctly-decoded
Cyrillic titles from rutracker/nnmclub/rutor. Private-tracker authentication is
live (rutracker, nnmclub, kinozal, iptorrents all `authenticated=true`).
gamestorrents is fixed (returns results on relevant queries).

**Encoding-crash census across all 3 queries: ONE `plugin_bad_query_encoding`**
— the `yts` plugin only, only on the Cyrillic query. This is an isolated
per-plugin defect (yts builds its URL without URL-encoding), NOT the P0
system-level crash; it does not affect the core/private trackers. Reported
honestly below.

---

## Query results (live, async POST /api/v1/search → poll GET /api/v1/search/{id})

| Query | Type | total_results | merged_results | contributing trackers (>0) | plugin_bad_query_encoding | plugin_crashed |
|-------|------|--------------:|---------------:|---------------------------:|--------------------------:|---------------:|
| `ubuntu` | ASCII | 1578 | 489 | 21 | 0 | 1 (snowfl — transient upstream) |
| `the matrix` | multi-word | 2395 | 1127 | 23 | 0 | 0 |
| `Война и мир` | Cyrillic (P0) | 543 | 373 | 11 | 1 (yts) | 0 |

Query echoed back by the API on the Cyrillic POST as `Война и мир` — no mojibake
at the request boundary.

## Per-key-tracker status

| Tracker | ubuntu | the matrix | Война и мир | auth |
|---------|-------:|-----------:|------------:|------|
| rutracker | 50 | 50 | 50 | ✅ authenticated |
| nnmclub | 48 | 50 | 50 | ✅ authenticated |
| kinozal | 0 (empty) | 50 | 0 (empty) | ✅ authenticated |
| iptorrents | 49 | 49 | 0 (empty) | ✅ authenticated |
| gamestorrents | 0 (empty) | 6 | 0 (empty) | n/a (public) |

All four private trackers report `authenticated=true` on every query — auth is
live. Empty cells are genuine no-match results (e.g. iptorrents/kinozal have no
"Война и мир" matches), not auth failures or crashes.

### Cyrillic correctness proof (real decoded titles, P0)
From `Война и мир` results — rutracker returned correctly-decoded Cyrillic:
- `Война и мир (Сергей Бондарчук) [1965-1968, СССР, драма, ...]`
- `Толстой Л. - Война и мир (иллюстрации А.П. Апсита и Н.Н.Каразина) [2021, ...]`
- `Толстой Лев - Война и Мир [Некрасов Денис, 2008, 128 kbps, MP3]`

This is the direct end-user proof the P0 encoding fix works for the core trackers.

### gamestorrents
Fixed — returned 6 results on `the matrix` (relevant game/film title). Empty on
`ubuntu` / `Война и мир` (genuinely no matches), so the plugin runs cleanly
(status `empty`, no crash). No scoped GTA re-run needed: `the matrix` already
proves results_count > 0.

## Honest notes (§11.4.6 — facts, not bluff)

- **yts `plugin_bad_query_encoding` on Cyrillic** (`Война и мир`): the yts plugin
  built `/browse-movies/Война и мир/all/...` WITHOUT URL-encoding, so urllib
  rejected it (`URL can't contain control characters ... found ' '`). yts
  SUCCEEDED on `the matrix` (22 results), so this is a Cyrillic-specific yts-only
  defect — a per-plugin bug, NOT the P0 system crash. Core/private trackers are
  unaffected. This is a real residual finding; the task's "expect NONE" was not
  fully met for the yts plugin on the Cyrillic query.
  UPDATE (post-test, same session): a sibling fix to `plugins/yts.py` —
  percent-encoding each browse-movies path segment via `quote(..., safe="")` —
  landed in the working tree with a dedicated RED→GREEN test
  (`tests/unit/test_plugin_unicode_query_encoding.py::test_yts_browse_path_cyrillic_encoded`,
  44/44 GREEN, §1.1 mutation confirmed). It is NOT yet committed or deployed to
  the e800ebd live stack, so the numbers above reflect the live system as tested.
  Re-test after deploy to confirm the yts Cyrillic crash clears.
- **snowfl `plugin_crashed` on `ubuntu`**: stderr `Connection error: Service
  Unavailable` + non-JSON body → JSON-parse raise. Transient upstream flake, NOT
  an encoding crash. snowfl SUCCEEDED on `the matrix` (140 results), confirming
  it is upstream availability, not a code defect.
- **`deadline_timeout`** (tokyotoshokan, yourbittorrent, torlock on some queries)
  is a slow-upstream cutoff, NOT a crash — the tracker simply did not respond in
  the deadline window.
- **`upstream_http_403`** (kickass, yts-on-some) and `upstream_http_404`
  (megapeer on Cyrillic) are upstream HTTP responses, NOT plugin crashes.

## Method / environment

- Read-only against live stack: `ssh milosvasic@nezha.local 'curl localhost:7187/...'`
- Sequential searches (one at a time), async POST + poll GET to be gentle on the
  concurrent service.
- Proxy (7186) and merge service (7187) both HTTP 200 before testing.
- Raw evidence JSON captured under `/Volumes/T7/tmp/{ubuntu,matrix_final,cyr_final}.json`.

## Post-yts-fix re-verify (c05423e deployed)

After deploying the yts browse-path UTF-8 fix (c05423e), the Cyrillic full-fleet
`Война и мир` re-ran on nezha: **total=608, 29 trackers, `encoding-crashed/
plugin_crashed: NONE`**. yts no longer emits plugin_bad_query_encoding — it now
returns `upstream_http_403` (yts.mx is Cloudflare-gated, an UPSTREAM block like
kickass §11.4.112, not a code defect). Net: **zero encoding crashes across the
entire fleet on ASCII, multi-word, AND Cyrillic** — the residual is closed.
