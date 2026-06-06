package service

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestNewMergeSearchService(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	assert.NotNil(t, svc)
}

func TestMergeSearchService_StartSearch(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)
	assert.NotEmpty(t, meta.SearchID)
	assert.Equal(t, "ubuntu", meta.Query)
	assert.Equal(t, "pending", meta.Status)
}

func TestMergeSearchService_GetSearchStatus_NotFound(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.GetSearchStatus("nonexistent")
	assert.Nil(t, meta)
}

func TestMergeSearchService_GetSearchStatus_Exists(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)
	found := svc.GetSearchStatus(meta.SearchID)
	assert.NotNil(t, found)
	assert.Equal(t, meta.SearchID, found.SearchID)
}

func TestMergeSearchService_AbortSearch(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)
	result := svc.AbortSearch(meta.SearchID)
	assert.Equal(t, "aborted", result)
}

func TestMergeSearchService_AbortSearch_NotFound(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	result := svc.AbortSearch("nonexistent")
	assert.Equal(t, "not_found", result)
}

func TestMergeSearchService_IsSearchQueueFull(t *testing.T) {
	svc := NewMergeSearchService(nil, 2)
	assert.False(t, svc.IsSearchQueueFull())

	// Two rapid StartSearch calls must yield two distinct active entries.
	// generateID() now appends an atomic counter, so back-to-back calls in the
	// same nanosecond no longer collide on the same map key (regression guard
	// for the UnixNano-only collision bug).
	svc.StartSearch("q1", "all", true, true)
	svc.StartSearch("q2", "all", true, true)
	assert.True(t, svc.IsSearchQueueFull())
}

func TestGenerateID_UniqueUnderBurst(t *testing.T) {
	// 10k IDs minted in a tight loop (same-nanosecond bursts) must all be
	// unique — proves the atomic-counter fix for the UnixNano collision.
	const n = 10000
	seen := make(map[string]struct{}, n)
	for i := 0; i < n; i++ {
		id := generateID()
		_, dup := seen[id]
		assert.Falsef(t, dup, "duplicate id %q at iteration %d", id, i)
		seen[id] = struct{}{}
	}
	assert.Len(t, seen, n)
}

func TestSearchMetadata_ISO8601Timestamps(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("test", "all", true, true)
	assert.NotEmpty(t, meta.StartedAt)
	_, err := time.Parse(time.RFC3339, meta.StartedAt)
	assert.NoError(t, err)
}

func TestSSEBroker_SubscribePublish(t *testing.T) {
	broker := NewSSEBroker()
	ch, unsub := broker.Subscribe()
	defer unsub()

	broker.Publish("test", `{"hello":"world"}`)

	select {
	case msg := <-ch:
		assert.Contains(t, msg, "event: test")
		assert.Contains(t, msg, `{"hello":"world"}`)
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for message")
	}
}

func TestSSEBroker_MultipleSubscribers(t *testing.T) {
	broker := NewSSEBroker()
	ch1, unsub1 := broker.Subscribe()
	ch2, unsub2 := broker.Subscribe()
	defer unsub1()
	defer unsub2()

	broker.Publish("test", "data")

	select {
	case <-ch1:
	case <-time.After(time.Second):
		t.Fatal("ch1 timed out")
	}
	select {
	case <-ch2:
	case <-time.After(time.Second):
		t.Fatal("ch2 timed out")
	}
}

func TestSSEBroker_Unsubscribe(t *testing.T) {
	broker := NewSSEBroker()
	ch, unsub := broker.Subscribe()
	unsub()

	_, ok := <-ch
	assert.False(t, ok, "channel should be closed")
}

func TestFormatSSEEvent(t *testing.T) {
	msg := FormatSSEEvent("results", `{"id":1}`)
	assert.Contains(t, msg, "event: results\n")
	assert.Contains(t, msg, "data: {\"id\":1}\n")
	assert.Contains(t, msg, "\n\n")
}
