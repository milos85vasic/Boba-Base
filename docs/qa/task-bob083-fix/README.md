# BOB-122 (reported as "BOB-083") — IPTorrents seed/leech parsing evidence

**Revision:** 1
**Last modified:** 2026-08-19T00:20:00Z

## Summary

Discovered via a §11.4.143 real-user-journey subagent (task-afe78327): IPTorrents
search results showed seed/leech as `0/0` despite qBittorrent's own swarm info
reporting real non-zero values for the same torrent. The dispatcher's task
brief referenced this as **BOB-083**, but the `docs/workable_items.db`
tracker — both the git-committed `HEAD` copy and the live working copy —
shows `BOB-083` is an unrelated, pre-existing `Task`
("RD2-16: Regenerate browser_extension/features/codegraph Status.md..."),
and no IPTorrents item was ever actually filed under any id. This is filed
at the next genuinely-free id, **BOB-122** (DB max was 121 at investigation
time), per §11.4.54 (ids are never reused/renumbered).

## Root cause — TWO independent parsers, TWO independent bugs

IPTorrents changed its results-table markup at some point after both of
these parsers were written. Neither had been updated to match.

### 1. `plugins/iptorrents.py` (native qBittorrent nova3 search plugin)

Four defects, all confirmed empirically against the live site
(`https://iptorrents.com`, fetched 2026-08-19):

1. **`_get_link()` never decompressed gzip.** IPTorrents always sends
   `content-encoding: gzip` regardless of the client's `Accept-Encoding`.
   `download_torrent()` already handled this; `_get_link()` (used by
   `search_parse()`) did not — so every "decoded" HTML string was actually
   still-compressed binary, and every downstream regex silently failed to
   match.
2. **Table regex required unquoted `<table id=torrents>`.** The live site
   now emits the quoted form `<table id="torrents">`.
3. **Row regex required `/details.php?id=...` desc links and
   `t_seeders="`/`t_leechers="` CSS classes.** The site now uses `/t/<id>`
   links, and the seed/leech/snatch cells carry **no CSS class at all** —
   they are three bare positional `<td>N` cells (Snatches, Seeders,
   Leechers, in that order per the table's own `<thead>`) immediately
   before `</tr>`.
4. **The search query was never URL-encoded.** A literal space in a
   multi-word query (e.g. `"The Bourne Legacy"`) raises
   `http.client.InvalidURL: URL can't contain control characters` under
   Python 3.14's stricter path validation — this is the EXACT exception the
   previous (killed) subagent hit and left as its last captured state.

### 2. `download-proxy/src/merge_service/search.py::_parse_iptorrents_html()`

This is the parser that reproduces the **exact reported symptom**
("rows appear, seed/leech literally `0/0`") — unlike bug #1 above, which
(pre-fix) produced **zero rows at all**, not `0/0` per row.

```python
td_values = re.findall(r"<td[^>]*>(?P<val>\d+)</td>", row_text)
seeds = int(td_values[0]) if len(td_values) > 0 else 0
leechers = int(td_values[1]) if len(td_values) > 1 else 0
```

IPTorrents renders its result rows with old-school **unclosed** `<td>`
tags — there is no `</td>` anywhere in the real response body. The regex
above requires a closing `</td>`, so `td_values` is **always empty** on
real markup, and `seeds`/`leechers` silently default to `0` — while
`name_match`/`dl_match`/`size_match` all succeed independently, so the row
DOES appear in results, with `0/0`.

The existing integration-test fixture for this function
(`tests/integration/test_iptorrents.py::test_parse_iptorrents_html_freeleech`)
used a synthetic, neatly-closed `<td>50</td><td>10</td>` shape that does
**not** match real markup — a classic bluff-test: it agreed with the buggy
code instead of catching the defect. Fixed to mirror the real
(unclosed-tag, 3-trailing-column) shape.

## Fix

- `plugins/iptorrents.py`: gzip-decompress in `_get_link()`; quoted-table
  regex; `/t/\d+` desc-link regex with positional (not class-based)
  Snatches/Seeders/Leechers extraction; `quote()` the search query in both
  `search()` and `search_freeleech()`.
- `download-proxy/src/merge_service/search.py`: replace the
  closing-`</td>`-dependent `findall` with a trailing-anchored
  `<td>(snatches)<td>(seeds)<td>(leech)\s*$` match on the unclosed markup.

## Evidence in this directory

- `iptorrents_real_table_excerpt.html` — the real `<table id="torrents">`
  markup captured live from `https://iptorrents.com` on 2026-08-19
  (gzip-decompressed; account username redacted; **no cookies/passwords
  present** — response bodies never contain the request's auth headers;
  leak-audited per §11.4.10.A before being written here).
- `live_search_freeleech_output.log` — real terminal output of
  `plugins/iptorrents.py`'s fixed `search_freeleech("The Bourne Legacy")`
  run against the live tracker (same multi-word query that crashed the
  pre-fix code with `InvalidURL`), showing 24 real results with correct,
  non-zero, varying seed/leech pairs (`92|2`, `50|0`, `35|3`, `23|0`, ...)
  in the exact pipe-delimited `prettyPrinter` format qBittorrent consumes.

## §1.1 mutation evidence (both fixes)

**`plugins/iptorrents.py`** (34 unit tests in
`tests/unit/test_plugin_iptorrents.py`): reverting the fix via
`git stash` and re-running the suite against the **new**, real-markup
fixtures fails **10 of 34** tests (table/row/seed-leech/gzip/URL-encoding
regressions all reproduce). Restoring the fix returns the suite to
34/34 green.

**`download-proxy/src/merge_service/search.py`**: calling
`_parse_iptorrents_html()` directly (bypassing the container-dependent
integration harness) against the SAME real captured page:

| | seeds/leech on 23 real rows |
|---|---|
| pre-fix (reverted) | **all 23 rows show `0/0`** — the exact reported symptom |
| post-fix (restored) | all 23 rows show their real non-zero swarm values |

## Honest boundary (§11.4.6)

- The merge-service integration test class
  (`TestIPTorrentsFreeleechDetection`) could not be run through `pytest`
  in this session because `tests/integration/conftest.py` has a
  session-scoped fixture that polls the merge service's
  `/api/v1/stats` endpoint for `active_searches == 0` and the
  `qbittorrent-proxy` container was not running in this sandbox — an
  honest §11.4.3 SKIP (infrastructure precondition, not a code defect).
  The fixed function was independently verified via direct invocation
  (see the `_parse_iptorrents_html` before/after run above) — real,
  non-mocked, live-captured HTML, same code path, same assertions,
  without going through the container-gated pytest harness.
- Pagination (`<a>Page <b>N</b> of <b>M</b>` in `plugins/iptorrents.py`)
  was investigated and found **not** broken — its markup is unchanged on
  the live site; verified against a real 999-result / 20-page search.
