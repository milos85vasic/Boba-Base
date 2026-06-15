package service

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/client"
	"github.com/stretchr/testify/assert"
)

// newStubQbitClient spins up an httptest server emulating the qBittorrent
// Web API search endpoints. results is returned verbatim from
// /api/v2/search/results on EVERY poll; the search status returns "Running"
// for the first runningPolls polls then "Stopped".
func newStubQbitClient(t *testing.T, resultsJSON string, runningPolls int32) *client.Client {
	t.Helper()
	var polls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v2/auth/login":
			http.SetCookie(w, &http.Cookie{Name: "SID", Value: "test-sid"})
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("Ok."))
		case "/api/v2/search/start":
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"id":42}`))
		case "/api/v2/search/status":
			n := polls.Add(1)
			status := "Stopped"
			if n <= runningPolls {
				status = "Running"
			}
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"` + status + `"}`))
		case "/api/v2/search/results":
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(resultsJSON))
		case "/api/v2/search/stop":
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusOK)
		}
	}))
	t.Cleanup(srv.Close)

	c, err := client.NewClient(srv.URL, "admin", "admin")
	assert.NoError(t, err)
	return c
}

// TestRunSearch_NoDuplicateAccumulation is the §11.4.115 RED-on-broken-artifact
// regression guard for BUG-3: the 500ms ticker re-fetched offset-0 and appended
// the SAME rows on every poll, so the live result set grew unbounded with
// duplicates and MergedResults was never set. The stub returns ONE identical
// result on every poll across multiple Running ticks then Stopped. After the
// fix, the merged/live set must contain exactly ONE row (deduplicated) and
// MergedResults must reflect the merged count (1).
func TestRunSearch_NoDuplicateAccumulation(t *testing.T) {
	const oneResult = `{"results":[{"fileName":"Ubuntu 22.04","fileSize":4096,` +
		`"nbSeeders":10,"nbLeechers":2,"fileUrl":"magnet:?xt=urn:btih:ABC",` +
		`"descrLink":"http://example/desc"}],"total":1,"status":"Running"}`

	// Running for ~3 polls, then Stopped — exercises multiple ticker fires
	// against the same offset-0 page.
	qc := newStubQbitClient(t, oneResult, 3)
	svc := NewMergeSearchService(qc, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	err := svc.RunSearch(ctx, meta.SearchID, "ubuntu", "all")
	assert.NoError(t, err)

	live := svc.GetLiveResults(meta.SearchID)
	assert.Lenf(t, live, 1,
		"BUG-3: identical row returned every poll must dedup to exactly 1 live result, got %d", len(live))

	final, _ := svc.GetSearchStatus(meta.SearchID)
	assert.Equal(t, "completed", final.Status)
	assert.Equalf(t, 1, final.MergedResults,
		"BUG-3: MergedResults must reflect the merged count (1), got %d", final.MergedResults)

	merged, _ := svc.GetMergedResults(meta.SearchID)
	assert.Lenf(t, merged, 1,
		"BUG-3: GetMergedResults must return the deduplicated merged set (1), got %d", len(merged))
}
