package service

import (
	"context"
	"testing"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/stretchr/testify/assert"
)

func TestMergeSearchService_AddAndGetLiveResults(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)

	// Empty initially.
	assert.Empty(t, svc.GetLiveResults(meta.SearchID))

	svc.AddTrackerResult(meta.SearchID, models.TorrentResult{Name: "Ubuntu 24.04", Seeds: 10})
	svc.AddTrackerResult(meta.SearchID, models.TorrentResult{Name: "Ubuntu 22.04", Seeds: 5})

	live := svc.GetLiveResults(meta.SearchID)
	assert.Len(t, live, 2)
	assert.Equal(t, "Ubuntu 24.04", live[0].Name)
	assert.Equal(t, 10, live[0].Seeds)
	assert.Equal(t, "Ubuntu 22.04", live[1].Name)
}

func TestMergeSearchService_GetLiveResults_UnknownID(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	assert.Nil(t, svc.GetLiveResults("does-not-exist"))
}

func TestMergeSearchService_SetAndGetMergedResults(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)

	// Nothing stored yet.
	merged, all := svc.GetMergedResults(meta.SearchID)
	assert.Nil(t, merged)
	assert.Nil(t, all)

	mergedIn := []models.TorrentResult{{Name: "merged-1", Seeds: 3}}
	allIn := []models.TorrentResult{{Name: "all-1"}, {Name: "all-2"}}
	svc.SetMergedResults(meta.SearchID, mergedIn, allIn)

	mergedOut, allOut := svc.GetMergedResults(meta.SearchID)
	assert.Len(t, mergedOut, 1)
	assert.Equal(t, "merged-1", mergedOut[0].Name)
	assert.Equal(t, 3, mergedOut[0].Seeds)
	assert.Len(t, allOut, 2)
	assert.Equal(t, "all-2", allOut[1].Name)
}

func TestMergeSearchService_GetMergedResults_UnknownID(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	merged, all := svc.GetMergedResults("unknown")
	assert.Nil(t, merged)
	assert.Nil(t, all)
}

func TestMergeSearchService_RunSearch_NilClient(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)

	err := svc.RunSearch(context.Background(), meta.SearchID, "ubuntu", "all")
	assert.NoError(t, err)

	// With a nil client RunSearch flips status to running then returns early.
	found := svc.GetSearchStatus(meta.SearchID)
	assert.Equal(t, "running", found.Status)
}

func TestMergeSearchService_RunSearch_UnknownIDNilClient(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	// Unknown searchID + nil client: must not panic and returns nil.
	err := svc.RunSearch(context.Background(), "missing", "q", "all")
	assert.NoError(t, err)
}

func TestMergeSearchService_FetchTorrent_NotImplemented(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	data, err := svc.FetchTorrent("rutracker", "https://example.com/t")
	assert.Nil(t, data)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "rutracker")
}

func TestMergeSearchService_Stats_Counts(t *testing.T) {
	// Insert distinct-keyed entries directly to avoid generateID() timestamp
	// collisions across rapid successive StartSearch calls.
	svc := NewMergeSearchService(nil, 10)
	svc.mu.Lock()
	svc.activeSearches["a"] = &SearchMetadata{SearchID: "a", Status: "pending"}
	svc.activeSearches["b"] = &SearchMetadata{SearchID: "b", Status: "completed"}
	svc.activeSearches["c"] = &SearchMetadata{SearchID: "c", Status: "aborted"}
	svc.mu.Unlock()

	stats := svc.Stats()
	assert.Equal(t, 1, stats["active_searches"])
	assert.Equal(t, 1, stats["completed_searches"])
	assert.Equal(t, 1, stats["aborted_searches"])
	assert.Equal(t, 3, stats["total_searches"])
}

func TestMergeSearchService_IsSearchQueueFull_CompletedFrees(t *testing.T) {
	svc := NewMergeSearchService(nil, 1)
	m := svc.StartSearch("q1", "all", false, false)
	assert.True(t, svc.IsSearchQueueFull())

	// Completing the only running search frees the queue.
	meta := svc.GetSearchStatus(m.SearchID)
	meta.Status = "completed"
	assert.False(t, svc.IsSearchQueueFull())
}

func TestMergeSearchService_IsSearchQueueFull_AbortedFrees(t *testing.T) {
	svc := NewMergeSearchService(nil, 1)
	m := svc.StartSearch("q1", "all", false, false)
	assert.True(t, svc.IsSearchQueueFull())
	svc.AbortSearch(m.SearchID)
	assert.False(t, svc.IsSearchQueueFull())
}

func TestNewMergeSearchService_DefaultsMaxConcurrent(t *testing.T) {
	// maxConcurrent <= 0 should default to 5. Drive the running count by
	// inserting distinct-keyed running entries directly into the map so the
	// assertion does not depend on generateID() producing unique timestamps.
	svc := NewMergeSearchService(nil, 0)
	svc.mu.Lock()
	for i := 0; i < 4; i++ {
		id := "k" + string(rune('a'+i))
		svc.activeSearches[id] = &SearchMetadata{SearchID: id, Status: "running"}
	}
	svc.mu.Unlock()
	assert.False(t, svc.IsSearchQueueFull(), "4 running < defaulted limit of 5")

	svc.mu.Lock()
	svc.activeSearches["ke"] = &SearchMetadata{SearchID: "ke", Status: "running"}
	svc.mu.Unlock()
	assert.True(t, svc.IsSearchQueueFull(), "5 running == defaulted limit of 5")

	// Negative also defaults to 5.
	svc2 := NewMergeSearchService(nil, -3)
	svc2.mu.Lock()
	for i := 0; i < 4; i++ {
		id := "n" + string(rune('a'+i))
		svc2.activeSearches[id] = &SearchMetadata{SearchID: id, Status: "running"}
	}
	svc2.mu.Unlock()
	assert.False(t, svc2.IsSearchQueueFull(), "4 < defaulted 5 (negative input)")
}

func TestTrackerRunStat_ToDict(t *testing.T) {
	s := &TrackerRunStat{
		Name:          "rutracker",
		Status:        "ok",
		Results:       42,
		DurationMS:    1234,
		Error:         "",
		Authenticated: true,
	}
	d := s.ToDict()
	assert.Equal(t, "rutracker", d["name"])
	assert.Equal(t, "ok", d["status"])
	assert.Equal(t, 42, d["results"])
	assert.Equal(t, int64(1234), d["duration_ms"])
	assert.Equal(t, true, d["authenticated"])
}

func TestSearchMetadata_ToDict(t *testing.T) {
	now := time.Now().UTC().Format(time.RFC3339)
	m := &SearchMetadata{
		SearchID:         "sid-1",
		Query:            "ubuntu",
		Status:           "completed",
		TotalResults:     7,
		MergedResults:    5,
		TrackersSearched: []string{"rutracker", "kinozal"},
		Errors:           []string{"boom"},
		TrackerStats: map[string]*TrackerRunStat{
			"rutracker": {Name: "rutracker", Status: "ok", Results: 3},
		},
		StartedAt:   now,
		CompletedAt: &now,
	}
	d := m.ToDict()
	assert.Equal(t, "sid-1", d["search_id"])
	assert.Equal(t, "ubuntu", d["query"])
	assert.Equal(t, "completed", d["status"])
	assert.Equal(t, 7, d["total_results"])
	assert.Equal(t, 5, d["merged_results"])
	assert.Equal(t, []string{"rutracker", "kinozal"}, d["trackers_searched"])
	assert.Equal(t, []string{"boom"}, d["errors"])
	stats, ok := d["tracker_stats"].([]map[string]interface{})
	assert.True(t, ok)
	assert.Len(t, stats, 1)
	assert.Equal(t, "rutracker", stats[0]["name"])
	assert.Equal(t, &now, d["completed_at"])
}

func TestSSEBroker_Publish_DropsSlowClient(t *testing.T) {
	broker := NewSSEBroker()
	ch, unsub := broker.Subscribe()
	defer unsub()

	// Buffer is 10; overfill so the 11th publish hits the default (drop) branch
	// without blocking. The test must complete (no deadlock) which proves drop.
	for i := 0; i < 15; i++ {
		broker.Publish("ev", "payload")
	}

	// Channel should hold exactly its buffered capacity worth of messages.
	count := 0
	draining := true
	for draining {
		select {
		case <-ch:
			count++
		default:
			draining = false
		}
	}
	assert.Equal(t, 10, count, "buffered messages capped at channel capacity; rest dropped")
}

func TestSSEBroker_Publish_NoSubscribers(t *testing.T) {
	broker := NewSSEBroker()
	// Publishing with zero subscribers must not panic / block.
	broker.Publish("ev", "data")
}

func TestSSEBroker_UnsubscribeRemovesFromBroadcast(t *testing.T) {
	broker := NewSSEBroker()
	ch1, unsub1 := broker.Subscribe()
	ch2, unsub2 := broker.Subscribe()
	defer unsub2()

	unsub1() // ch1 closed + removed.

	broker.Publish("ev", "data")

	// ch2 still receives.
	select {
	case msg := <-ch2:
		assert.Contains(t, msg, "event: ev")
	case <-time.After(time.Second):
		t.Fatal("ch2 should still receive after ch1 unsubscribed")
	}

	// ch1 is closed: a receive returns the zero value with ok=false.
	v, ok := <-ch1
	assert.False(t, ok)
	assert.Equal(t, "", v)
}
