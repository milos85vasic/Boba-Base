# BOB-061 / BOB-062 — Suite stabilization + hang elimination

**Revision:** 1
**Last modified:** 2026-06-10T00:00:00Z
**Status:** Fixed · **Commits:** `6e15a8d`, `6230865`
**Mandate:** §11.4.50 (determinism), §11.4.98 (autonomous tests), §11.4.69/§11.4.102/§11.4.114.

## BOB-061 — Unit-suite hang + order-dependent test-pollution

Root causes (proven via §11.4.102 systematic debugging + §11.4.114 clean-HEAD isolation):
1. **enricher full-suite hang** — `_lookup_tvmaze/_openlibrary/_musicbrainz` did real
   `aiohttp` GETs with no timeout; musicbrainz throttling stalled the event loop
   (the 87% monolithic stall). Fixed: `ClientTimeout(total=10)` on all 6 sessions +
   `test_resolve_no_apis` stubs the lookups (offline/autonomous).
2. **test-pollution** (13–34 order-dependent failures; `pytest-randomly` active):
   - `tests/conftest.py` `_CORRECT_MS_PATH` used `.parent` (=`tests/`) not
     `.parent.parent` (=repo root) → a non-existent `tests/download-proxy/...` path
     corrupted `merge_service.__path__` → 11 victims (all 6 `scheduler_api`,
     `TestLifespan`, `routes_coverage`).
   - raw `sys.modules` stubs (helpers/env_loader/novaprinter/socks/tokyotoshokan/
     kinozal/rutor/iptorrents) leaked across files → extended `_POLLUTING_ROOTS`.
   - `socket.socket` (kinozal SOCKS) + `os.environ` (credential tests) leaked →
     snapshot/restore per unit test in the autouse fixture.

## BOB-062 — Unbounded loops + unbounded network I/O

- `kickass`/`bitsearch`/`torrentgalaxy` `while True:` search loops could run forever
  (index-ignoring upstream) → `MAX_PAGES=50` caps + RED loop-cap regression tests.
- `search.py fetch_torrent`, `routes.py` ×3 qbit sessions, `helpers.py`
  `retrieve_url`/`download_file`, `eztv.py` fallback → all given explicit timeouts
  (`aiohttp.ClientTimeout` 10/30 / `urlopen timeout=30`). Each with a RED-on-removal
  regression guard (mutation-verified by code review).
- `test_dashboard` qbit-auth test mocked (was a real `localhost:7185` connect).

## Rock-solid proof (captured)

```
# monolithic — previously stalled, now completes:
pytest tests/unit/ -q --import-mode=importlib --timeout=60
→ 4121 passed, 0 failed in 324.56s

# determinism (§11.4.50) — top-level scope, multiple random seeds:
seed 7      → 3150 passed, 0 failed
seed 42     → 3150 passed, 0 failed
seed 100    → 3150 passed, 0 failed
seed 31337  → 3150 passed, 0 failed
seed 12345  → 3150 passed, 0 failed
merge_service → 801 passed   api_layer → 170 passed
```

Clean-HEAD isolation (§11.4.114): HEAD `44f15b2` top-level = 34 failed/3070 passed;
this work = 0 failed → fixes are net-positive, introduce nothing. Two code-review
passes returned GO (zero findings, zero warnings) after remediation (§11.4.134).
