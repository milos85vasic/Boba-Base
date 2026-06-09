# Bugfix Log

**Revision:** 2
**Last modified:** 2026-06-09T12:00:00Z

Per CONST-MD-Bugfix-Documentation, every bug surfaced during
implementation gets a permanent entry below: title, root cause,
affected files, fix description, regression guard.

Entries are append-only; do not edit historical entries except to add
clarification footnotes.

---

## 2026-04-27 — boba-jackett implementation (plan 2026-04-27-jackett-management-ui-and-system-db.md)

### 1. Master-key two-step write silent data-loss window

**Severity:** HIGH (silent credential loss possible on crash mid-bootstrap).

**Root cause:** Initial implementation of `bootstrap.EnsureMasterKey`
generated `BOBA_MASTER_KEY` in memory, returned it to the caller,
and *then* wrote `.env` in a separate step. If the process crashed,
was killed, or the host lost power between those two operations, the
caller would proceed to encrypt credentials with a key that disk had
no record of — making them permanently undecipherable.

**Affected files:**
- `qBitTorrent-go/internal/bootstrap/bootstrap.go`
- `qBitTorrent-go/internal/envfile/write.go`

**Fix:** Collapse the generate + write into a single
`envfile.Atomic` write (`tmpfile + fsync + rename`) before the
function returns. Caller never sees a key that hasn't been durably
persisted. Commit `c0f20bc`.

**Regression guard:**
- `qBitTorrent-go/internal/bootstrap/bootstrap_test.go::TestEnsureMasterKeyDoesNotDuplicateHeader`
- `qBitTorrent-go/internal/envfile/write_test.go` atomic-write test layer

---

### 2. SQLite database file mode `0644` (world-readable credentials)

**Severity:** CRITICAL (any local user could read encrypted credentials
+ ciphertext-only attack surface).

**Root cause:** `modernc.org/sqlite` creates database files with the
process's default umask, which on the container yielded `0644`
(world-readable). The Go service's `.env` was already `0600` via
`envfile.Atomic`, but `boba.db` was leaking — a defense-in-depth
breach since the rows are encrypted, but still a violation of the
principle "the DB file should be readable only by the service owner".

**Affected files:**
- `qBitTorrent-go/internal/db/conn.go`

**Fix:** After the first `Open()` succeeds, `db.Open` calls
`os.Chmod(path, 0o600)` (and the `-wal` / `-shm` siblings if present),
collapsing the file mode to owner-only. Commit `8405167`.

**Regression guard:**
- Layer 4 security challenge `challenges/scripts/boba_db_file_perms_challenge.sh`
- `qBitTorrent-go/internal/db/credential_leak_test.go`

---

### 3. `AutoconfigResult` nil slices marshalled as JSON `null`

**Severity:** MEDIUM (silent client-breaking schema drift; UI rendered
"undefined" badges instead of "0 items").

**Root cause:** Go's `json.Marshal` serializes a nil slice as `null`,
not `[]`. When `Autoconfigure()` ran on a fresh DB with no discovered
credentials, the `discovered_credentials`, `configured_now`, and
`already_present` fields all marshalled as `null`. The OpenAPI 3.1
schema declared them as `array`, so clients (including the Angular
dashboard) treated `null` as a contract violation.

**Affected files:**
- `qBitTorrent-go/internal/jackett/autoconfig.go`

**Fix:** Pre-allocate empty slices (`[]string{}`) at the top of
`Autoconfigure()` so a "nothing to do" run still serializes as
`{...,"discovered":[],"configured_now":[],...}`. Commit `6f3dbaf`.

**Regression guard:**
- Layer 6 contract test `qBitTorrent-go/tests/contract/openapi_test.go`
  (validates each named field is `array` per OpenAPI schema even on
  empty runs).

---

### 4. Catalog `ReplaceAll` empty-input wipe risk

**Severity:** HIGH (would permanently wipe the indexer catalog if
Jackett returned an empty response; UI would show no indexers and
fuzzy matcher would have nothing to match against).

**Root cause:** `repos.IndexerCatalog.ReplaceAll(rows []Row)`
unconditionally `DELETE`d existing rows then `INSERT`ed the new ones.
If `rows` was empty (Jackett momentarily unhealthy, transient 502, or
catalog parse failure), the delete still happened, leaving an empty
catalog table. Next refresh would have nothing to compare against.

**Affected files:**
- `qBitTorrent-go/internal/db/catalog.go` (or equivalent repo file)

**Fix:** Refuse the operation early with
`errors.New("repos: ReplaceAll refusing empty replacement")`. The
caller (autoconfig orchestrator) treats this as a soft error, logs it,
and leaves the previous catalog intact. Commit `8d71df1`.

**Regression guard:**
- `qBitTorrent-go/internal/jackettapi/catalog_test.go::TestRefreshCatalogAllTemplatesFailReturns200WithErrors`

---

### 5. `TestSearchHandler_QueueFull` pre-existing flake (NOT a boba-jackett bug)

**Severity:** LOW (test-only; flagged for follow-up).

**Status:** **NOT FIXED** in this plan. Confirmed unrelated to
boba-jackett work.

**Location:** `qBitTorrent-go/internal/api/api_test.go`

**Symptom:** Occasional intermittent failure under load when the
search queue fills before the test's `wait` returns.

**Action:** Logged here for traceability so future audits don't
mis-attribute it. Open issue suggestion: stabilise by injecting a
deterministic queue-full hook instead of racing against real
goroutine scheduling.

---

## 2026-06-09 — Session 7 fixes (env_loader, AsyncMock, gamestorrents)

### 6. env_loader flaky test: KEY2 leak across test ordering

**Severity:** LOW (test-only flake; not a production bug).

**Root cause:** `test_comment_lines_ignored` in `tests/unit/test_env_loader.py`
asserted `os.environ.get("KEY2") is None` after calling `load_env_files()` with a
config file where `KEY2=commented_out` was commented out. However,
`load_env_files` has a "first wins" policy — if `KEY2` was already present in
`os.environ` from a prior test's `load_env_files` call, the function would not
override it. Under `pytest-randomly` ordering, the test that sets `KEY2` sometimes
ran before the comment-line test, causing intermittent failure.

**Affected files:**
- `tests/unit/test_env_loader.py`

**Fix:** Added explicit `os.environ.pop("KEY1", None)` and
`os.environ.pop("KEY2", None)` at the START of the test (before calling
`load_env_files`), ensuring a clean env state regardless of test execution order.
The `finally` block was retained as a safety net.

**Regression guard:**
- `tests/unit/test_env_loader.py::test_comment_lines_ignored` — ran 2147/2147
  twice consecutively under random ordering with zero failures.

---

### 7. AsyncMock warning in search deep-coverage tests

**Severity:** LOW (test warning; not a production bug).

**Root cause:** `test_iptorrents_login_no_cookies` in
`tests/unit/merge_service/test_search_deep_coverage.py` used `AsyncMock()` for
`login_resp` and `mock_session`. These objects are used as context managers
(`async with session.post(...) as resp`), not as directly awaited coroutines.
`AsyncMock.__aenter__` returns a coroutine, but the test's mock setup didn't
properly wire `__aenter__`/`__aexit__`, causing "coroutine was never awaited"
RuntimeWarning.

**Affected files:**
- `tests/unit/merge_service/test_search_deep_coverage.py`

**Fix:** Changed `AsyncMock()` to `MagicMock()` with explicit `__aenter__` and
`__aexit__` stubs, matching the actual usage pattern (context manager, not
coroutine).

**Regression guard:**
- `tests/unit/merge_service/test_search_deep_coverage.py` — 0 AsyncMock warnings
  from this test (was 3).

---

### 8. gamestorrents `_parse_size` B-substring bug (documented, not fixed)

**Severity:** MEDIUM (plugin returns 0 for all realistic file sizes).

**Root cause:** Same class of bug as BOB-013 (torrentkitty). The `multipliers`
dict in `_parse_size` iterates in insertion order: `{"B": 1, "KB": 1024, ...}`.
Since `"B"` is a substring of `"KB"`, `"MB"`, `"GB"`, and `"TB"`, the check
`if unit in size_str` matches `"B"` first for all realistic sizes. Then
`size_str.replace("B", "")` leaves a trailing unit character (e.g. `"35.2 G"`)
which `float()` cannot parse, returning 0.

**Affected files:**
- `plugins/gamestorrents.py` (line 74-86)

**Fix:** NOT FIXED in this session. Documented via tests that assert actual
behavior (tests suffixed `_b_substring_bug`). Fix requires reordering the dict
keys to check longest units first (same approach as BOB-013).

**Regression guard:**
- `tests/unit/test_plugin_gamestorrents.py::TestParseSize` — 8 tests documenting
  the bug across GB/MB/KB/TB/commas/uppercase.
