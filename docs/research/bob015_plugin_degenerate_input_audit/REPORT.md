# BOB-015 — Plugin degenerate-input crash audit

**Revision:** 1
**Last modified:** 2026-06-09T00:00:00Z
**Mandate:** §11.4.118 discovery-pressure (confirm known-issue-set completeness; surface unreported crash-on-degenerate-input gaps before end users hit them)
**Method:** read-only enumeration (no source/test edits); throwaway probe run from `/tmp`, then removed.

---

## Methodology

Reproduced the existing offline-isolation harness pattern from
`tests/unit/test_plugin_crash_guards.py` + `tests/unit/test_plugin_parser_guards.py`:
stub `novaprinter` (capture `prettyPrinter` rows) and `helpers`
(`retrieve_url`, `download_file`, `htmlentitydecode`, `unescape`,
`get_torrent_socks_proxy`) into `sys.modules`, `importlib`-load each plugin,
resolve its class by attribute match (nova2 contract), patch `retrieve_url`
to return each degenerate payload, call `search("linux")`, and record CRASH
vs OK. Run with `python3` 3.9.x. pytest suite NOT run. No `plugins/`,
`tests/`, or source files edited.

**Probed (15):** curated set that ships as files —
`eztv limetorrents piratebay solidtorrents torlock rutracker rutor kinozal
nnmclub` — plus broad public plugins
`anilibra bitsearch gamestorrents megapeer nyaa torrentgalaxy torrentkitty`.
Excluded the 3 already under active repair this session
(`tokyotoshokan`, `kickass`, `yts`). The curated names `jackett`,
`torrentproject`, `torrentscsv` do NOT ship as plugin files → out of scope.

**Input classes (9):** `empty_str`, `whitespace`, `truncated_html`,
`malformed_html`, `empty_json {}`, `empty_json_array []`, `malformed_json`,
`json_data_null '{"data": null}'`, `none (None)`.

---

## Result matrix (summary)

Every probeable plugin handled all 8 **string** input classes gracefully
(0 rows, no exception) — with ONE exception: `piratebay` on `json_data_null`.
The `none` input crashed several plugins but is **not reachable** in
production (see reachability note).

- All 14 string-probeable plugins: `empty_str / whitespace / truncated_html /
  malformed_html / {} / [] / malformed_json` → **OK** everywhere.
- `json_data_null` → **OK everywhere EXCEPT `piratebay` (CRASH)**.
- `none` → CRASH in eztv, limetorrents, piratebay, solidtorrents, torlock,
  bitsearch, nyaa, torrentgalaxy; OK in rutor, kinozal, nnmclub, anilibra,
  gamestorrents, megapeer, torrentkitty.
- `rutracker` → **SKIP-with-reason**: constructor performs a live login
  (`ValueError: Unable to connect using given credentials.`), cannot be
  driven offline. Not a crash.

## Reachability note (§11.4.6)

`plugins/helpers.py::retrieve_url` is typed `-> str` and every return path
returns a `str` (`""` on URLError; `dataStr` on success) — it NEVER returns
`None`. So the `none`-class crashes are **NOT reachable** via the production
helpers path; they are defensive observations, not user-facing defects.

---

## NEW reachable guard gap (beyond tokyotoshokan/kickass/yts)

### GAP-1 — `plugins/piratebay.py` crashes on realistic upstream `{"data": null}`

**Reachability: REAL** — `retrieve_url` can legitimately return a JSON
*object* instead of the expected array (same upstream-shape class `anilibra`
was already hardened against in `test_plugin_crash_guards.py`).

Root cause (`piratebay.py` `search()`): `json.loads('{"data": null}')` →
dict `{"data": None}`; the guard `if len(response_json) == 0` sees `len == 1`
and does NOT fire; `for result in response_json:` then iterates dict **keys**
so `result == "data"` (a str), and `result["info_hash"]` indexes a str with a
str.

Verbatim captured evidence (`retrieve_url -> '{"data": null}'`):

```
Traceback (most recent call last):
  File "<stdin>", line 23, in <module>
  File "plugins/piratebay.py", line 91, in search
    if result["info_hash"] == "0000000000000000000000000000000000000000":
TypeError: string indices must be integers
```

**Suggested fix direction:** after `json.loads`,
`if not isinstance(response_json, list): return` before the empty-check /
iteration — mirroring the existing anilibra non-list/null-data guard.

---

## Defensive observations (NOT reachable — no fix needed)

`none`-only crashers, verbatim messages:
eztv / limetorrents / solidtorrents / torlock / nyaa →
`TypeError: can only concatenate str (not "NoneType") to str`;
bitsearch / torrentgalaxy → `TypeError: expected string or bytes-like object`;
piratebay (none) → `TypeError: the JSON object must be str, bytes or
bytearray, not NoneType`.

---

## Bottom line

Exactly **one** additional reachable gap beyond the three already fixed:
**`piratebay` on `{"data": null}`**. No other reachable crash surfaced across
135 (plugin × input) cells. Honest coverage gaps: `rutracker`
(live-login constructor → SKIP) and the un-shipped `jackett` /
`torrentproject` / `torrentscsv` curated names were not exercised.
