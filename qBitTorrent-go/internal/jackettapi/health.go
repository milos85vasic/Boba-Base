package jackettapi

import (
	"context"
	"database/sql"
	"log"
	"net/http"
	"sync"
	"sync/atomic"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/jackett"
)

// defaultJackettHealthCacheTTL is how long a Jackett liveness result (from
// GetCatalog) is trusted before /healthz issues a fresh upstream probe.
//
// BOB-112: without this cache, every /healthz hit made a synchronous,
// uncached call to Jackett's real catalog endpoint
// (GET /api/v2.0/indexers, ~600 indexer templates). A burst of health
// probes — a mis-tuned external monitor or an attacker — turned /healthz
// into a self-inflicted DDoS amplifier: probes queued behind Jackett
// round-trips and started timing out on their OWN 3s client budget, degrading
// boba-jackett's own health surface without ever touching Jackett directly.
// Measured (2026-08-18, cold boba-jackett restart, c=90 concurrent
// requests): 100% client-side timeouts. See
// docs/testing/ddos_resilience.md "Findings" #2 for the original discovery.
//
// 30s is well inside the "N = 30-60s is reasonable" range for a liveness
// probe interval and matches boba-svc.sh's own HEALTH_PROBES cadence.
const defaultJackettHealthCacheTTL = 30 * time.Second

// HealthDeps wires the readiness checkers for the /healthz endpoint.
//
// Version is the build version (set at link-time or at main.go init).
// StartTime is captured at process start so uptime can be reported.
//
// The handler always returns HTTP 200 even when a subsystem is down —
// monitors should watch the body fields. Flapping HTTP status is
// noisier than a stable JSON change.
type HealthDeps struct {
	DB        *sql.DB
	Jackett   *jackett.Client
	Version   string
	StartTime time.Time

	// CacheTTL overrides defaultJackettHealthCacheTTL when > 0. Exposed
	// so tests can force a short TTL and exercise the stale/refresh path
	// without a real 30s sleep. Zero value (the production default via
	// main.go's struct literal) falls back to defaultJackettHealthCacheTTL.
	CacheTTL time.Duration

	// jackettCacheMu guards jackettCacheOk/jackettCacheAt. Using ONE
	// mutex for both the staleness check and the refresh (rather than a
	// pair of independent atomics) is what collapses a concurrent burst
	// of stale-cache hits into exactly ONE upstream GetCatalog() call
	// instead of N — see jackettOk/refreshJackettOk below.
	jackettCacheMu sync.RWMutex
	jackettCacheOk bool
	jackettCacheAt time.Time

	// cacheHits / cacheMisses back BOB-112's "log the cache hit/miss
	// ratio" requirement. Atomic because HandleHealth runs concurrently
	// per-request; exported via CacheStats() so tests assert on REAL
	// observed counts (§11.4.6 — no invented hit ratios).
	cacheHits   int64
	cacheMisses int64
}

// healthDTO is the spec §8.6 response shape.
type healthDTO struct {
	Status    string `json:"status"`
	DBOk      bool   `json:"db_ok"`
	JackettOk bool   `json:"jackett_ok"`
	Version   string `json:"version"`
	UptimeS   int64  `json:"uptime_s"`
}

// HandleHealth handles GET /healthz.
//
// DB readiness: PingContext with a 2s deadline. Any error → DBOk=false.
//
// Jackett readiness: a cached GetCatalog result, refreshed at most once
// per CacheTTL (default 30s) — see jackettOk. NOTE: GetCatalog is the
// most lightweight readiness signal Jackett's public API offers today.
// If a dedicated low-overhead Ping endpoint is added upstream, this is
// the call to swap.
//
// Status mapping:
//   - both up        → "ok"
//   - DB up only     → "degraded" (Jackett is fixable without restart)
//   - DB down        → "unhealthy" (nothing else works without it)
func (d *HealthDeps) HandleHealth(w http.ResponseWriter, r *http.Request) {
	out := healthDTO{
		Version: d.Version,
		UptimeS: int64(time.Since(d.StartTime).Seconds()),
	}
	if d.DB != nil {
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		out.DBOk = d.DB.PingContext(ctx) == nil
		cancel()
	}
	if d.Jackett != nil {
		out.JackettOk = d.jackettOk()
	}
	switch {
	case out.DBOk && out.JackettOk:
		out.Status = "ok"
	case out.DBOk:
		out.Status = "degraded"
	default:
		out.Status = "unhealthy"
	}
	writeJSON(w, http.StatusOK, out)
}

// cacheTTL returns CacheTTL when the caller (main.go or a test) set a
// positive override, else the production default.
func (d *HealthDeps) cacheTTL() time.Duration {
	if d.CacheTTL > 0 {
		return d.CacheTTL
	}
	return defaultJackettHealthCacheTTL
}

// jackettOk returns the cached Jackett liveness signal, issuing a real
// GetCatalog() call only when the cache is empty or older than
// cacheTTL(). This is the BOB-112 fix for the synchronous-uncached-
// call-per-request DDoS amplification vector (see the package-level
// defaultJackettHealthCacheTTL doc comment for the measured before/after
// evidence).
//
// The read path takes only the cheap RLock, so N concurrent cache-hit
// requests never contend with each other or touch Jackett at all.
func (d *HealthDeps) jackettOk() bool {
	d.jackettCacheMu.RLock()
	hasCached := !d.jackettCacheAt.IsZero()
	fresh := hasCached && time.Since(d.jackettCacheAt) < d.cacheTTL()
	ok := d.jackettCacheOk
	d.jackettCacheMu.RUnlock()
	if fresh {
		atomic.AddInt64(&d.cacheHits, 1)
		return ok
	}
	return d.refreshJackettOk()
}

// refreshJackettOk performs the actual (bounded) upstream call. Double-
// checked locking under the SAME mutex the read path uses collapses a
// concurrent burst of stale-cache hits into exactly ONE upstream
// GetCatalog() call: every goroutine that lost the race to acquire the
// write lock first re-checks freshness once it's their turn — by then
// the winner has already refreshed the cache, so they return immediately
// without ever dialing Jackett. This is what turns a 90-way concurrent
// burst against a cold cache into 1 upstream call instead of 90 (proven
// by TestHealthCacheCollapsesConcurrentBurst).
func (d *HealthDeps) refreshJackettOk() bool {
	d.jackettCacheMu.Lock()
	defer d.jackettCacheMu.Unlock()
	if !d.jackettCacheAt.IsZero() && time.Since(d.jackettCacheAt) < d.cacheTTL() {
		// Another goroutine refreshed the cache while we were waiting
		// for the write lock.
		atomic.AddInt64(&d.cacheHits, 1)
		return d.jackettCacheOk
	}
	misses := atomic.AddInt64(&d.cacheMisses, 1)
	_, err := d.Jackett.GetCatalog()
	d.jackettCacheOk = err == nil
	d.jackettCacheAt = time.Now()
	hits := atomic.LoadInt64(&d.cacheHits)
	log.Printf("boba-jackett: /healthz Jackett cache refresh #%d (hits=%d misses=%d ratio=%.1f%% ok=%v)",
		misses, hits, misses, cacheHitRatioPct(hits, misses), d.jackettCacheOk)
	return d.jackettCacheOk
}

// cacheHitRatioPct returns hits/(hits+misses) as a percentage, 0 when
// nothing has been observed yet.
func cacheHitRatioPct(hits, misses int64) float64 {
	total := hits + misses
	if total == 0 {
		return 0
	}
	return float64(hits) / float64(total) * 100
}

// CacheStats exposes the real observed cache hit/miss counters (BOB-112
// anti-bluff requirement: never invent a ratio, always measure it).
func (d *HealthDeps) CacheStats() (hits, misses int64) {
	return atomic.LoadInt64(&d.cacheHits), atomic.LoadInt64(&d.cacheMisses)
}
