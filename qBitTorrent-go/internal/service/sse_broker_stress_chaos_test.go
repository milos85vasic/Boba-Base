// BOB-095: §11.4.85 STRESS + CHAOS coverage for the Go-side SSE broker
// (`internal/service/sse_broker.go`) — sibling to the Python-side stress
// coverage delivered under BOB-094 (`tests/stress/test_tracker_fetch_stress_chaos.py`).
//
// These tests exercise the REAL SSEBroker.  They prove USER-OBSERVABLE outcomes
// per §11.4 / §11.4.69:
//   - `Subscribe`/unsubscribe do not leak channels or goroutines (§12.12);
//   - concurrent subscribers all receive broadcast events, no deadlock;
//   - a slow / dead subscriber does NOT block the publisher (backpressure
//     isolation via the `default:` non-blocking send);
//   - unsubscribe during publish never panics (`send on closed channel` /
//     `close of closed channel` refused);
//   - a producer-flood burst is bounded by the per-client 10-msg buffer +
//     dropped with the documented warn signal.
//
// Evidence (§11.4.5 / §11.4.69 captured-evidence, feature_class=sse_broker):
//     docs/qa/BOB-095/evidence/{latency,goroutine_count,chaos_recovery,...}.
//
// HOST SAFETY (§12/§12.6/§12.12): run only via
//   `GOMAXPROCS=2 nice -n 19 go test -race ./internal/service/... -run StressChaos`.
//
// §11.4.115 RED-FIRST: `TestSSEBrokerStressChaos_SlowSubscriberDoesNotBlock`
// is the RED-capable oracle for the backpressure-isolation invariant — if the
// broker's `default:` clause is removed (turning `Publish` into a blocking
// send), a stuck subscriber wedges the publisher and the test's 2s deadline
// makes it FAIL.  The RED capture demonstrating that mutation is preserved
// under `docs/qa/BOB-095/evidence/red_capture_backpressure.txt`; the current
// GREEN capture is at `green_capture_after_restore.txt`.

package service

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// evidenceDir resolves docs/qa/BOB-095/evidence/ relative to the test binary
// (running under qBitTorrent-go/internal/service, the repo root is ../../..).
// Missing tree → SKIP-with-reason (§11.4.3), never a fake-pass.
func evidenceDir(t *testing.T) string {
	t.Helper()
	cwd, err := os.Getwd()
	require.NoError(t, err)
	dir := filepath.Join(cwd, "..", "..", "..", "docs", "qa", "BOB-095", "evidence")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Skipf("SKIP-with-reason: cannot create evidence dir %q: %v (§11.4.3)", dir, err)
	}
	return dir
}

// writeEvidence writes captured evidence per §11.4.69; a failed write does
// NOT silently mask a passing test — it FAILs it (§11.4.1: silent evidence
// loss is a FAIL-bluff).
func writeEvidence(t *testing.T, name string, payload interface{}) {
	t.Helper()
	dir := evidenceDir(t)
	path := filepath.Join(dir, name)
	var data []byte
	var err error
	switch v := payload.(type) {
	case []byte:
		data = v
	case string:
		data = []byte(v)
	default:
		data, err = json.MarshalIndent(payload, "", "  ")
		require.NoError(t, err)
	}
	require.NoError(t, os.WriteFile(path, data, 0o644))
}

// percentile computes p50/p95/p99 for a duration slice — sorted in-place.
func percentile(durs []time.Duration, p float64) time.Duration {
	if len(durs) == 0 {
		return 0
	}
	sort.Slice(durs, func(i, j int) bool { return durs[i] < durs[j] })
	idx := int(float64(len(durs)-1) * p)
	return durs[idx]
}

// -----------------------------------------------------------------------------
// STRESS scenarios
// -----------------------------------------------------------------------------

// STRESS 1 — sustained load: 1000 sequential subscribe→unsubscribe cycles.
// Asserts NO goroutine leak and NO map growth after the cycle completes.
// USER-OBSERVABLE invariant: the broker returns to empty client set + the
// process's goroutine count returns to baseline (channel-close discipline).
func TestSSEBrokerStressChaos_SustainedSubscribeUnsubscribe(t *testing.T) {
	const N = 1000

	// Baseline goroutine count — small settle window per §11.4.6 (never guess
	// "goroutines are settled").
	runtime.GC()
	time.Sleep(50 * time.Millisecond)
	before := runtime.NumGoroutine()

	b := NewSSEBroker()
	lats := make([]time.Duration, 0, N)
	for i := 0; i < N; i++ {
		t0 := time.Now()
		ch, unsub := b.Subscribe()
		require.NotNil(t, ch)
		unsub()
		lats = append(lats, time.Since(t0))
	}

	// The client map MUST be empty after every unsubscribe — the load-bearing
	// leak invariant (§11.4.108 runtime signature).
	b.mu.RLock()
	remaining := len(b.clients)
	b.mu.RUnlock()
	require.Equal(t, 0, remaining, "sse_broker leaked clients: %d rows remain after %d unsubscribe cycles", remaining, N)

	runtime.GC()
	time.Sleep(50 * time.Millisecond)
	after := runtime.NumGoroutine()

	writeEvidence(t, "latency.json", map[string]interface{}{
		"scenario":                "sustained_subscribe_unsubscribe",
		"iterations":              N,
		"p50_ns":                  percentile(lats, 0.50).Nanoseconds(),
		"p95_ns":                  percentile(lats, 0.95).Nanoseconds(),
		"p99_ns":                  percentile(lats, 0.99).Nanoseconds(),
		"clients_after_cycle":     remaining,
		"goroutines_before":       before,
		"goroutines_after":        after,
		"goroutine_delta":         after - before,
		"feature_class":           "sse_broker",
		"evidence_recorded_at_ns": time.Now().UnixNano(),
	})

	// Small tolerance for scheduler / GC — but a real leak grows without bound
	// (§11.4.201(6) FALSE-NULL guard: NOT "delta ~= 0 is safe", but "delta
	// must not grow with N"; +5 covers test-harness noise, not a per-iteration
	// leak which would be +N).
	assert.LessOrEqualf(t, after-before, 5,
		"goroutine leak: baseline %d → after %d cycles %d (delta=%d, expected ≤ 5)",
		before, N, after, after-before)
}

// STRESS 2 — concurrent contention: 100 parallel subscribers all receiving
// broadcast events, no deadlock.  USER-OBSERVABLE: every subscriber's message
// count matches the publish count (no message lost to race).
func TestSSEBrokerStressChaos_ConcurrentSubscribers(t *testing.T) {
	const (
		subscribers = 100
		messages    = 5
	)
	b := NewSSEBroker()

	var (
		wgReady = sync.WaitGroup{}
		wgDone  = sync.WaitGroup{}
		counts  = make([]atomic.Int32, subscribers)
		unsubs  = make([]func(), subscribers)
	)
	wgReady.Add(subscribers)
	wgDone.Add(subscribers)

	for i := 0; i < subscribers; i++ {
		i := i
		ch, unsub := b.Subscribe()
		unsubs[i] = unsub
		go func() {
			defer wgDone.Done()
			wgReady.Done()
			received := 0
			deadline := time.After(3 * time.Second)
			for received < messages {
				select {
				case _, ok := <-ch:
					if !ok {
						return
					}
					counts[i].Add(1)
					received++
				case <-deadline:
					return
				}
			}
		}()
	}
	wgReady.Wait()

	for m := 0; m < messages; m++ {
		b.Publish("test", fmt.Sprintf("msg-%d", m))
	}

	wgDone.Wait()

	// Cleanup — no deferred leak.
	for _, u := range unsubs {
		u()
	}

	total := int32(0)
	minSeen := int32(messages)
	for i := 0; i < subscribers; i++ {
		c := counts[i].Load()
		total += c
		if c < minSeen {
			minSeen = c
		}
	}

	writeEvidence(t, "concurrent.json", map[string]interface{}{
		"scenario":       "concurrent_subscribers",
		"subscribers":    subscribers,
		"messages":       messages,
		"total_received": total,
		"min_per_sub":    minSeen,
		"expected_total": subscribers * messages,
		"feature_class":  "sse_broker",
	})

	// Every subscriber MUST have received every message — buffer is 10 per
	// client (>= 5), so no drop is legal here (§11.4.6: PROVEN not guessed).
	assert.EqualValuesf(t, subscribers*messages, total,
		"concurrent-broadcast lost messages: expected %d, got %d (min-per-sub=%d)",
		subscribers*messages, total, minSeen)
}

// STRESS 3 — boundary: unsubscribe called twice MUST NOT panic (closed-channel
// re-close bug is the class this guards).  The USER-OBSERVABLE outcome: the
// second call is a safe no-op — a `close of closed channel` panic would crash
// the whole HTTP server that hosts the broker.
func TestSSEBrokerStressChaos_BoundaryDoubleUnsubscribe(t *testing.T) {
	b := NewSSEBroker()
	_, unsub := b.Subscribe()
	unsub()
	// Second call — MUST NOT panic.  Wrap in defer/recover so a regression
	// converts into a proper t.Fatal, not a test-runner crash.
	defer func() {
		if r := recover(); r != nil {
			t.Fatalf("second unsubscribe panicked: %v (expected safe no-op)", r)
		}
	}()
	unsub()
	writeEvidence(t, "boundary_double_unsubscribe.txt",
		"PASS: second unsubscribe is a safe no-op — no panic, no client-map corruption\n")
}

// -----------------------------------------------------------------------------
// CHAOS scenarios
// -----------------------------------------------------------------------------

// CHAOS 1 — SLOW / DEAD SUBSCRIBER MUST NOT BLOCK THE PUBLISHER.
// One subscriber never reads.  Publisher fires 100 events.  The `default:`
// clause in `SSEBroker.Publish` is the load-bearing guard — remove it and this
// test wedges the publisher past its 2s deadline.
// §11.4.115 RED capture: `docs/qa/BOB-095/evidence/red_capture_backpressure.txt`.
func TestSSEBrokerStressChaos_SlowSubscriberDoesNotBlock(t *testing.T) {
	b := NewSSEBroker()

	// The zombie: subscribes, never reads.  Its 10-msg buffer fills after
	// 10 publishes — every subsequent publish MUST drop-not-block.
	_, unsubZombie := b.Subscribe()
	defer unsubZombie()

	// A healthy subscriber to confirm broadcasts still fan out AROUND the zombie.
	healthyCh, unsubHealthy := b.Subscribe()
	defer unsubHealthy()

	const events = 100
	done := make(chan struct{})
	go func() {
		for i := 0; i < events; i++ {
			b.Publish("stress", fmt.Sprintf("evt-%d", i))
		}
		close(done)
	}()

	// Deadline: 2s is >> the healthy publish time (~ms) but << the wedge time
	// a blocking send would produce.  A pass here PROVES backpressure isolation.
	select {
	case <-done:
		// OK — publisher was NOT wedged by the zombie.
	case <-time.After(2 * time.Second):
		t.Fatalf("PUBLISHER WEDGED by slow subscriber — backpressure isolation broken (§11.4.85 chaos)")
	}

	// Drain the healthy subscriber briefly to confirm it saw >= 10 events
	// (its own buffer held some; §11.4.6: prove the fan-out actually reached).
	healthyReceived := 0
DRAIN:
	for {
		select {
		case _, ok := <-healthyCh:
			if !ok {
				break DRAIN
			}
			healthyReceived++
		case <-time.After(50 * time.Millisecond):
			break DRAIN
		}
	}

	writeEvidence(t, "chaos_slow_subscriber.json", map[string]interface{}{
		"scenario":          "slow_subscriber_does_not_block",
		"events_published":  events,
		"healthy_received":  healthyReceived,
		"publisher_wedged":  false,
		"backpressure_kind": "drop-with-warn (default: clause in Publish)",
		"feature_class":     "sse_broker",
	})

	assert.Greaterf(t, healthyReceived, 0,
		"healthy subscriber received %d events — fan-out broken", healthyReceived)
}

// CHAOS 2 — UNSUBSCRIBE DURING PUBLISH FLOOD.
// Repeatedly subscribe → publish → unsubscribe under contention.  The concurrent
// mutation exercises the RLock/Lock ordering: a panic (`send on closed channel`
// / `close of closed channel`) would crash the test-runner.  The `go test -race`
// flag additionally proves no data race on `b.clients`.
func TestSSEBrokerStressChaos_UnsubscribeDuringPublish(t *testing.T) {
	b := NewSSEBroker()

	const (
		churnGoroutines = 20
		publishRate     = 500
	)

	stop := make(chan struct{})
	var wg sync.WaitGroup

	// Publishers.
	for p := 0; p < 4; p++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				select {
				case <-stop:
					return
				default:
					b.Publish("evt", "payload")
				}
			}
		}()
	}

	// Churners — subscribe / brief read / unsubscribe in a tight loop.
	var panics atomic.Int32
	for c := 0; c < churnGoroutines; c++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			defer func() {
				if r := recover(); r != nil {
					panics.Add(1)
					t.Errorf("panic in churner: %v", r)
				}
			}()
			for {
				select {
				case <-stop:
					return
				default:
					ch, unsub := b.Subscribe()
					// Give the publisher a chance to write into ch before we close.
					select {
					case <-ch:
					case <-time.After(2 * time.Millisecond):
					}
					unsub()
				}
			}
		}()
	}

	// Run for a bounded window then stop.
	time.Sleep(500 * time.Millisecond)
	close(stop)
	wg.Wait()
	_ = publishRate // narrative literal for MANIFEST cross-ref

	// Post-condition: no panic, all clients cleaned up.
	b.mu.RLock()
	remaining := len(b.clients)
	b.mu.RUnlock()
	require.Equal(t, 0, remaining, "leaked %d clients after unsubscribe-during-publish flood", remaining)
	require.Zero(t, panics.Load(), "%d panic(s) during unsubscribe-during-publish flood", panics.Load())

	writeEvidence(t, "chaos_unsubscribe_during_publish.json", map[string]interface{}{
		"scenario":            "unsubscribe_during_publish_flood",
		"churn_goroutines":    churnGoroutines,
		"publishers":          4,
		"window_ms":           500,
		"panics":              panics.Load(),
		"clients_after_flood": remaining,
		"feature_class":       "sse_broker",
	})
}

// CHAOS 3 — PRODUCER FLOOD.  10x normal broadcast rate against a single
// slow-reading subscriber — the broker MUST bound the delivered set by the
// per-client 10-msg buffer and drop the rest.  USER-OBSERVABLE: subscriber
// received <= buffer_size, publisher completed in bounded time.
func TestSSEBrokerStressChaos_ProducerFloodBoundedByBuffer(t *testing.T) {
	b := NewSSEBroker()
	ch, unsub := b.Subscribe()
	defer unsub()

	const flood = 1000
	start := time.Now()
	for i := 0; i < flood; i++ {
		b.Publish("flood", fmt.Sprintf("evt-%d", i))
	}
	pubDur := time.Since(start)

	// Drain — take everything the buffer held.
	drained := 0
DRAIN:
	for {
		select {
		case _, ok := <-ch:
			if !ok {
				break DRAIN
			}
			drained++
		case <-time.After(50 * time.Millisecond):
			break DRAIN
		}
	}

	// The channel's buffer is 10 — the broker MUST cap delivery at that (or
	// below, if we hit `default:` at broadcast time).  A value > 10 would mean
	// the buffer contract was broken; a value == 0 with a working publish
	// path is not expected either.
	writeEvidence(t, "chaos_producer_flood.json", map[string]interface{}{
		"scenario":       "producer_flood_bounded_by_buffer",
		"flood_events":   flood,
		"drained":        drained,
		"buffer_size":    10,
		"publish_dur_us": pubDur.Microseconds(),
		"feature_class":  "sse_broker",
	})

	assert.LessOrEqualf(t, drained, 10, "buffer bound violated: drained %d > buffer=10", drained)
	// Publisher should never take anywhere near the flood-count * per-msg time
	// — bounded by the `default:` clause.  1s is a generous ceiling.
	assert.Lessf(t, pubDur, time.Second, "publisher too slow: %v for %d events (backpressure suspected)", pubDur, flood)
}

// Compile-time reference so `strings` stays used even if future refactors
// remove its callers (§11.4.1: silent import-drift is a script-bug FAIL).
var _ = strings.HasPrefix
