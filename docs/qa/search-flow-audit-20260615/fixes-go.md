# Go merge-search fixes — BUG-3 + BUG-4

**Revision:** 1
**Last modified:** 2026-06-15T00:00:00Z

TDD per §11.4.43 / §11.4.115 (RED-on-broken-artifact → GREEN). Resource-limited
runs: `GOMAXPROCS=2 nice -n 19 go test -race`. Work scoped to `qBitTorrent-go/`.
No commit/push.

## Files changed
- `qBitTorrent-go/internal/service/merge_search.go` — RunSearch dedup + merged snapshot (BUG-3)
- `qBitTorrent-go/internal/api/search.go` — GetSearchHandler now returns merged Results (BUG-4)

## RED tests added
- `qBitTorrent-go/internal/service/runsearch_dedup_test.go`
  `TestRunSearch_NoDuplicateAccumulation` — httptest qbit stub returns the SAME
  single result on every poll (Running x3 → Stopped). Asserts
  `len(GetLiveResults)==1`, `MergedResults==1`, `len(GetMergedResults)==1`.
- `qBitTorrent-go/internal/api/getsearch_results_test.go`
  `TestGetSearch_ReturnsResults` — seeds a completed search with 2 merged via
  SetMergedResults, GET /api/v1/search/{id}, asserts `len(resp.Results)==2`.

## BUG-3 root cause + fix
RunSearch's 500ms ticker called GetSearchResults(id,100,0) at a FIXED offset 0
and appended ALL rows every tick; nothing deduped and SetMergedResults was never
called → MergedResults stayed 0. Fix: per-search `seen` map keyed on FileURL
(fallback name+size) skips duplicates; on Stopped, the deduplicated accumulation
is snapshotted into lastMergedResults and `meta.MergedResults` is set.

## BUG-4 root cause + fix
GetSearchHandler built SearchResponse WITHOUT Results → Go-profile grid empty on
every search_complete GET. Fix: `results,_ := svc.GetMergedResults(id)` (fallback
GetLiveResults), set `Results: results`.

## RED evidence (pre-fix, broken artifact)
```
--- FAIL: TestRunSearch_NoDuplicateAccumulation (2.01s)
    ... should have 1 item(s), but has 4
    ... BUG-3: MergedResults must reflect the merged count (1), got 0
    ... BUG-3: GetMergedResults must return the deduplicated merged set (1), got 0
FAIL	github.com/milos85vasic/qBitTorrent-go/internal/service
--- FAIL: TestGetSearch_ReturnsResults
    ... BUG-4: final GET must return the merged results, got 0  (panic index out of range)
FAIL	github.com/milos85vasic/qBitTorrent-go/internal/api
```

## GREEN evidence (post-fix)
```
ok  	github.com/milos85vasic/qBitTorrent-go/internal/service	3.239s   (TestRunSearch_NoDuplicateAccumulation)
ok  	github.com/milos85vasic/qBitTorrent-go/internal/api	1.315s   (TestGetSearch_ReturnsResults)
```

## Full suite (GOMAXPROCS=2 nice -n 19 go test -race ./internal/...)
```
ok  	.../internal/api	2.995s
ok  	.../internal/bootstrap	1.485s
ok  	.../internal/client	1.337s
ok  	.../internal/config	1.196s
ok  	.../internal/db	1.537s
ok  	.../internal/db/repos	3.581s
ok  	.../internal/envfile	2.251s
ok  	.../internal/jackett	1.589s
ok  	.../internal/jackettapi	3.589s
ok  	.../internal/logging	1.211s
ok  	.../internal/middleware	1.338s
ok  	.../internal/models	1.277s
ok  	.../internal/service	5.187s
```
