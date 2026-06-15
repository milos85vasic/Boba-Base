# Python merge-service fixes — search-flow audit 2026-06-15

**Revision:** 1
**Last modified:** 2026-06-15T00:00:00Z

Anti-bluff (§11.4): every fix RED-first (test reproduces the defect on the
pre-fix code), permanent §11.4.135 regression guard added, GREEN proven by
pytest + LIVE curl against the running stack.

## BUG-1 — provider selection (CRITICAL)

Root cause: only "search all enabled providers" existed; no wire field, no
orchestrator param, no plugin filter for single/subset. Single/selected UI
modes silently behaved as "all".

Fix:
- `api/routes.py` — `SearchRequest` gains `trackers: list[str] | None = None`;
  `POST /search` and `POST /search/sync` pass `request.trackers` down.
- `merge_service/search.py` — new helper `_select_trackers(self, tracker_filter)`
  (calls `_get_enabled_trackers()`, then if filter non-empty keeps only trackers
  whose `.name` is in the case-insensitive filter set). `start_search(... trackers=None)`
  persists the filter on `SearchMetadata.tracker_filter`; `_run_search` reads it back
  via `_select_trackers`; `search(... trackers=None)` threads it through. Empty/None
  == all (back-compat).

RED tests: `tests/unit/merge_service/test_provider_selection.py`
- `test_single_provider_filters_fanout` — trackers=["rutracker"] → dispatched set == {"rutracker"}, metadata.trackers_searched == ["rutracker"].
- `test_subset_provider_filters_fanout` — two-element subset.
- `test_none_filter_fans_out_to_all` / `test_empty_filter_fans_out_to_all` — back-compat.
- `test_filter_is_case_insensitive` — "RuTracker" → {"rutracker"}.
- `test_unknown_name_yields_empty_fanout_gracefully` — unknown name → zero dispatch, no crash.
- `test_start_search_seeds_filtered_trackers` — async POST path seeds only the subset.
Asserts on actual dispatched tracker set + metadata.trackers_searched, not status codes.

## BUG-6 — integer-size crash in dedup fallback

Root cause: `deduplicator._parse_size_to_bytes` passed a raw int into `re.match`
(no `str()`), raising TypeError; unguarded `_update_best_quality`→`merge_results`
aborted the whole merge → zero results.

Fix: `merge_service/deduplicator.py` `_parse_size_to_bytes` coerces `str(size_str)`
after the falsy guard (mirrors the api.routes / `_parse_size` fix). `_fallback_quality`
signature widened to `object`.

RED tests: `tests/unit/merge_service/test_dedup_integer_size.py`
- `test_parse_size_to_bytes_accepts_integer` / `_accepts_negative_sentinel`.
- `test_fallback_quality_survives_integer_size`.
- `test_merge_survives_integer_size` — forces the api.routes ImportError branch, int+(-1) sizes; asserts non-empty merge.

## BUG-7 — all-tracker failure indistinguishable from empty

Root cause: every-provider-fail completed as status="completed", total_results=0 →
dashboard "No results found.", indistinguishable from genuinely empty.

Fix: `merge_service/search.py` `_run_search` — when merged==0 AND total_results==0
AND every searched tracker stat is error/timeout, set `status = "all_trackers_errored"`
(else "completed"). Per-tracker errors already accumulate in `metadata.errors`.

RED tests: `tests/unit/merge_service/test_all_trackers_error.py`
- `test_all_trackers_error_is_distinguishable` — all raise → status != "completed", len(errors)==3.
- `test_genuinely_empty_stays_completed` — no errors + 0 results stays "completed", errors==[].

## VERIFY

### pytest GREEN (the 3 new regression files)

```
$ .venv/bin/python -m pytest tests/unit/merge_service/test_provider_selection.py \
    tests/unit/merge_service/test_dedup_integer_size.py \
    tests/unit/merge_service/test_all_trackers_error.py -v --import-mode=importlib
...
============================== 13 passed in 0.78s ==============================
```

RED proof (pre-fix, same files): 12 failed / 1 passed — provider tests reject the
`trackers=` kwarg, BUG-6 raises `TypeError: expected string or bytes-like object, got 'int'`,
BUG-7 reports status=="completed".

### Full merge_service unit suite — no regression

```
$ .venv/bin/python -m pytest tests/unit/merge_service/ -q --import-mode=importlib
818 passed, 3 warnings in 84.99s
```

ruff: `All checks passed!` on the 3 source + 3 test files.
(Pre-existing, unrelated: tests/unit/test_plugin_yts_deep.py fails 45 on a pristine
stashed tree — collection error in the YTS plugin test, not touched by these fixes.)

### LIVE — running stack (podman VM, merge service :7187)

After editing: cleared `__pycache__`, `podman restart qbittorrent-proxy`, verified
served code matches committed edits (`_select_trackers`, `all_trackers_errored`,
`size_str = str(size_str)` all present in /config/download-proxy/...).

```
=== FILTERED trackers_searched (rutor only) ===
status: completed | total: 3 | trackers_searched: ['rutor']

=== NO-FILTER (all enabled providers) ===
status: completed | total: 1182 | n_trackers: 29 | trackers_searched:
['rutracker','kinozal','nnmclub','iptorrents','jackett','academictorrents',
'anilibra','bitsearch','gamestorrents','glotorrents','kickass','limetorrents',
'linuxtracker','megapeer','nyaa','piratebay','pirateiro','rockbox','rutor',
'snowfl','tokyotoshokan','torlock','torrentdownload','torrentgalaxy',
'torrentkitty','torrentproject','torrentscsv','yourbittorrent','yts']
```

Filtered search hits ONLY rutor (3 results); no-filter hits all 29 providers
(1182 results) — provider selection proven end-to-end through the real HTTP path.

Files changed: download-proxy/src/api/routes.py,
download-proxy/src/merge_service/search.py,
download-proxy/src/merge_service/deduplicator.py.
Tests added: tests/unit/merge_service/test_provider_selection.py,
test_dedup_integer_size.py, test_all_trackers_error.py.
NOT committed.
