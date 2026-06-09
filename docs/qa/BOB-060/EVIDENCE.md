# BOB-060 — Degenerate-input crash guards for public-tracker plugins

**Revision:** 1
**Last modified:** 2026-06-09T00:00:00Z
**Type:** Bug · **Severity:** Low · **Status:** Fixed
**Mandate:** §11.4.43 TDD (RED→GREEN), §11.4.115 RED-on-broken-artifact,
§11.4.118 discovery-pressure, §11.4.135 permanent regression guard,
§11.4.83 QA transcript.

Four public-tracker plugins raised **unhandled exceptions** on degenerate /
empty / malformed upstream responses. Each was reproduced (RED) on the
pre-fix code, fixed with a minimal guard mirroring sibling-plugin patterns,
and re-verified (GREEN). All inputs that did *not* crash were added as
passing regression guards rather than fabricated as fixes (anti-bluff
§11.4.6). One gap (piratebay) was found by a §11.4.118 discovery audit, not
by the original report.

---

## tokyotoshokan — `re.search(None)` TypeError on `retrieve_url → None`

Root cause: `search()` / `handle_more_pages()` call `re.search(data)` on the
`retrieve_url` result; a network/SSL failure yielding `None` raised
`TypeError: expected string or bytes-like object` before the `if not match`
guard ran. Fix: `if not data:` early-return/break before the regex.

```
RED  → TypeError: expected string or bytes-like object  (plugins/tokyotoshokan.py:143)
GREEN→ 4 passed in 0.06s
```
Files: `plugins/tokyotoshokan.py`, `tests/unit/test_plugin_tokyotoshokan_guards.py` (new).

## kickass — `None.startswith` AttributeError in `download_torrent`

Root cause: `download_torrent(url)` called `url.startswith("magnet:")` before
any guard; `download_torrent(None)` raised
`AttributeError: 'NoneType' object has no attribute 'startswith'`. Fix:
falsy/non-str guard emitting the qBittorrent fallback `<url> <engine_url>`
shape. (A separate `while True` pagination/loop concern was honestly noted as
out-of-scope.)

```
RED  → AttributeError: 'NoneType' object has no attribute 'startswith'  (plugins/kickass.py:75)
GREEN→ 21 passed in 0.40s
```
Files: `plugins/kickass.py`, `tests/unit/test_plugin_kickass_guards.py` (+8 tests).

## yts — `AttributeError` on non-dict / null-`data` JSON

Root cause: `j.get("data", {}).get("movie_count")` assumed `j` was a dict and
`data` non-null; non-dict array, bare `null`, `{"data": null}`, and
error-shaped JSON raised `AttributeError: 'list'/'NoneType' object has no
attribute 'get'`. Fix: validate `j` is a dict, coerce `data` to `{}` when not
a dict. Positive control proves well-formed responses still yield rows.

```
RED  → 4 failed (AttributeError, plugins/yts.py:41)
GREEN→ 9 passed in 0.24s   (incl. positive control)
```
Files: `plugins/yts.py`, `tests/unit/test_plugin_yts_guards.py` (new).

## piratebay — `TypeError: string indices must be integers` on `{"data": null}`

Found by the §11.4.118 discovery audit
(`docs/research/bob015_plugin_degenerate_input_audit/REPORT.md`). Root cause:
`json.loads('{"data": null}')` → dict `{"data": None}` (len 1, so the empty
check never fires); `for result in response_json:` iterates dict **keys** and
`result["info_hash"]` indexes a str with a str. Fix: mirror anilibra —
`if not isinstance(response_json, list): return` before the len-check, plus a
per-element `if not isinstance(result, dict): continue`. Positive control
proves well-formed arrays still yield rows.

```
RED  → 3 failed (TypeError: string indices must be integers, plugins/piratebay.py:91)
GREEN→ 7 passed in 0.18s   (incl. positive control)
```
Files: `plugins/piratebay.py`, `tests/unit/test_plugin_piratebay_guards.py` (new).

---

## Consolidated regression-guard run (§11.4.132 risk-ordered, §11.4.135)

```
.venv/bin/python -m pytest \
  tests/unit/test_plugin_tokyotoshokan_guards.py \
  tests/unit/test_plugin_kickass_guards.py \
  tests/unit/test_plugin_yts_guards.py \
  tests/unit/test_plugin_piratebay_guards.py \
  tests/unit/test_plugin_crash_guards.py \
  tests/unit/test_plugin_parser_guards.py -q --import-mode=importlib
→ 55 passed in 0.91s
```

These guard tests are the permanent regression suite for this defect class
(§11.4.135): each `RED_MODE`-equivalent reproduced the crash on the pre-fix
code and now asserts its absence.
