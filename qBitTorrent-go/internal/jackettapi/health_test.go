package jackettapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/db"
	"github.com/milos85vasic/qBitTorrent-go/internal/jackett"
)

// healthHarness wires a real DB + a stub Jackett HTTP server so we can
// drive both subsystems independently. The atomic counter is the
// CONST-XII falsification guard for TestHealthAllOK: a hardcoded
// `JackettOk: true` would never increment it.
type healthHarness struct {
	deps         *HealthDeps
	server       *httptest.Server
	catalogCalls int32
	catalogFail  bool
}

func newHealthHarness(t *testing.T) *healthHarness {
	t.Helper()
	dir := t.TempDir()
	conn, err := db.Open(filepath.Join(dir, "t.db"))
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	if err := db.Migrate(conn); err != nil {
		t.Fatalf("Migrate: %v", err)
	}
	h := &healthHarness{}
	h.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/UI/Dashboard":
			w.WriteHeader(302)
		case "/api/v2.0/indexers":
			atomic.AddInt32(&h.catalogCalls, 1)
			if h.catalogFail {
				w.WriteHeader(500)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`[]`))
		default:
			w.WriteHeader(404)
		}
	}))
	h.deps = &HealthDeps{
		DB:        conn,
		Jackett:   jackett.NewClient(h.server.URL, "k"),
		Version:   "test-1.0",
		StartTime: time.Now().UTC(),
	}
	t.Cleanup(func() {
		h.server.Close()
		_ = conn.Close()
	})
	return h
}

func TestHealthAllOK(t *testing.T) {
	h := newHealthHarness(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/healthz", nil)
	h.deps.HandleHealth(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	var got healthDTO
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("decode: %v body=%s", err, rec.Body.String())
	}
	if got.Status != "ok" {
		t.Fatalf("status: %s", got.Status)
	}
	if !got.DBOk || !got.JackettOk {
		t.Fatalf("subsystems: %+v", got)
	}
	if got.Version != "test-1.0" {
		t.Fatalf("version: %s", got.Version)
	}
	if got.UptimeS < 0 {
		t.Fatalf("uptime negative: %d", got.UptimeS)
	}
	// CONST-XII: confirm Jackett was actually probed. A handler that
	// hardcoded JackettOk:true without dialing the upstream would leave
	// this counter at zero.
	if atomic.LoadInt32(&h.catalogCalls) == 0 {
		t.Fatalf("Jackett /api/v2.0/indexers not hit: %d", h.catalogCalls)
	}
}

func TestHealthJackettDownDegraded(t *testing.T) {
	h := newHealthHarness(t)
	h.catalogFail = true
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/healthz", nil)
	h.deps.HandleHealth(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status: %d", rec.Code)
	}
	var got healthDTO
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if got.Status != "degraded" {
		t.Fatalf("status: %s", got.Status)
	}
	if !got.DBOk {
		t.Fatalf("db should be ok: %+v", got)
	}
	if got.JackettOk {
		t.Fatalf("jackett should be down: %+v", got)
	}
}

func TestHealthDBClosedUnhealthy(t *testing.T) {
	h := newHealthHarness(t)
	_ = h.deps.DB.Close() // simulate DB failure
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/healthz", nil)
	h.deps.HandleHealth(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status: %d", rec.Code)
	}
	var got healthDTO
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if got.Status != "unhealthy" {
		t.Fatalf("status: %s", got.Status)
	}
	if got.DBOk {
		t.Fatalf("db should be down: %+v", got)
	}
}

func TestHealthVersionAndUptimeSurfaced(t *testing.T) {
	h := newHealthHarness(t)
	h.deps.Version = "v1.2.3"
	h.deps.StartTime = time.Now().UTC().Add(-90 * time.Second)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/healthz", nil)
	h.deps.HandleHealth(rec, req)
	var got healthDTO
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if got.Version != "v1.2.3" {
		t.Fatalf("version: %s", got.Version)
	}
	// CONST-XII falsification: a handler returning hardcoded UptimeS:0
	// would fail this range check; one returning the wrong sign would
	// also fail.
	if got.UptimeS < 89 || got.UptimeS > 95 {
		t.Fatalf("uptime ~90s expected, got %d", got.UptimeS)
	}
}

func TestHealthBothNilSafe(t *testing.T) {
	h := newHealthHarness(t)
	h.deps.DB = nil
	h.deps.Jackett = nil
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/healthz", nil)
	h.deps.HandleHealth(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status: %d", rec.Code)
	}
	var got healthDTO
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if got.DBOk || got.JackettOk {
		t.Fatalf("nil deps should report false: %+v", got)
	}
	if got.Status != "unhealthy" {
		t.Fatalf("status: %s", got.Status)
	}
}

// --- BOB-112: /healthz Jackett.GetCatalog() TTL-cache DDoS-amplification fix ---
//
// CONST-XII falsification note: every test below FAILS against a no-op
// stub of the fix (i.e. against the pre-BOB-112 health.go, which called
// d.Jackett.GetCatalog() unconditionally on every request) — that stub
// makes catalogCalls scale 1:1 with request count, which is exactly what
// TestHealthJackettCacheHitOnSecondCall and
// TestHealthCacheCollapsesConcurrentBurst assert did NOT happen. This is
// also the §11.4.115 paired §1.1 mutation: reverting HandleHealth's
// jackettOk() call back to a direct "_, err := d.Jackett.GetCatalog()"
// call makes these two tests fail immediately (catalogCalls jumps from
// 1 to N), proving the cache is load-bearing, not decorative.

// TestHealthJackettCacheHitOnSecondCall proves a second /healthz hit
// inside the TTL window does NOT touch Jackett again — the core of the
// fix. Fails against the pre-fix handler (catalogCalls would be 2).
func TestHealthJackettCacheHitOnSecondCall(t *testing.T) {
	h := newHealthHarness(t)
	for i := 0; i < 2; i++ {
		rec := httptest.NewRecorder()
		req := httptest.NewRequest("GET", "/healthz", nil)
		h.deps.HandleHealth(rec, req)
		if rec.Code != 200 {
			t.Fatalf("call %d: status %d", i, rec.Code)
		}
	}
	if got := atomic.LoadInt32(&h.catalogCalls); got != 1 {
		t.Fatalf("expected exactly 1 upstream GetCatalog() call across 2 /healthz hits inside the TTL window, got %d", got)
	}
	hits, misses := h.deps.CacheStats()
	if hits != 1 || misses != 1 {
		t.Fatalf("expected 1 hit + 1 miss (real counters, not invented), got hits=%d misses=%d", hits, misses)
	}
}

// TestHealthJackettCacheRefreshesAfterTTL proves the cache is NOT
// permanent — after CacheTTL elapses, /healthz makes a fresh upstream
// call. Uses an overridden short TTL so the test doesn't sleep 30s.
func TestHealthJackettCacheRefreshesAfterTTL(t *testing.T) {
	h := newHealthHarness(t)
	h.deps.CacheTTL = 20 * time.Millisecond

	rec1 := httptest.NewRecorder()
	h.deps.HandleHealth(rec1, httptest.NewRequest("GET", "/healthz", nil))
	if got := atomic.LoadInt32(&h.catalogCalls); got != 1 {
		t.Fatalf("first call: expected 1 upstream call, got %d", got)
	}

	time.Sleep(40 * time.Millisecond) // > CacheTTL

	rec2 := httptest.NewRecorder()
	h.deps.HandleHealth(rec2, httptest.NewRequest("GET", "/healthz", nil))
	if got := atomic.LoadInt32(&h.catalogCalls); got != 2 {
		t.Fatalf("after TTL expiry: expected a 2nd upstream call, got %d total calls", got)
	}
}

// TestHealthCacheCollapsesConcurrentBurst is the direct DDoS-amplification
// regression guard. It fires a burst of concurrent /healthz requests
// against a COLD cache (mirroring the real wrk/curl burst that produced
// 100% client-side timeouts pre-fix — see docs/testing/ddos_resilience.md
// and the BOB-112 commit evidence) and asserts the upstream Jackett
// catalog endpoint is hit AT MOST ONCE, never once per request.
//
// Against the pre-fix handler (unconditional GetCatalog() per request)
// catalogCalls would equal burstSize — this is the test that would have
// caught BOB-112 before it shipped.
func TestHealthCacheCollapsesConcurrentBurst(t *testing.T) {
	h := newHealthHarness(t)
	const burstSize = 90 // matches the c=90 burst that reproduced 100% timeouts pre-fix

	var wg sync.WaitGroup
	wg.Add(burstSize)
	for i := 0; i < burstSize; i++ {
		go func() {
			defer wg.Done()
			rec := httptest.NewRecorder()
			req := httptest.NewRequest("GET", "/healthz", nil)
			h.deps.HandleHealth(rec, req)
			if rec.Code != 200 {
				t.Errorf("burst request: status %d", rec.Code)
			}
		}()
	}
	wg.Wait()

	got := atomic.LoadInt32(&h.catalogCalls)
	if got != 1 {
		t.Fatalf("DDoS amplification regression: %d-way concurrent /healthz burst against a cold cache made %d upstream GetCatalog() calls (want exactly 1) — the cache did not collapse the burst", burstSize, got)
	}
	hits, misses := h.deps.CacheStats()
	if misses != 1 {
		t.Fatalf("expected exactly 1 real cache miss across the burst, got %d (hits=%d)", misses, hits)
	}
	if hits != int64(burstSize-1) {
		t.Fatalf("expected %d cache hits (real measured counters, not invented), got %d", burstSize-1, hits)
	}
}
