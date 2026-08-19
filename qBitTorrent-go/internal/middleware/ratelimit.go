// Package middleware — BOB-111: per-IP token-bucket rate limiter using
// golang.org/x/time/rate. Applied to the Gin router in
// cmd/qbittorrent-proxy/main.go and (via WithRateLimit) to the net/http
// handler chain in cmd/boba-jackett/main.go.
//
// The default budget is 30 requests/minute per client IP with a burst of 10 —
// tuned to comfortably cover the dashboard's polling loop (1 req/2s = 30/min)
// while cutting off a scripted `wrk -c 100` attack (BOB-112 forensic anchor)
// well below the point it starves the tracker fan-out.
//
// A rejected request returns HTTP 429 with a MINIMAL JSON body
// `{"error":"rate_limited"}` + a `Retry-After: 60` header — §11.4.10-clean
// (no client IP echoed, no bucket internals). Operator override via env:
//
//	RATE_LIMIT_RPM      integer, default 30    — sustained per-IP req/minute
//	RATE_LIMIT_BURST    integer, default 10    — allowed instantaneous burst
//	RATE_LIMIT_DISABLED "1"/"true"/"yes"       — bypass (RED baseline only)
//
// §11.4.6: the caller IP is resolved from RemoteAddr by default; when the
// service sits behind a reverse proxy the operator MUST opt in explicitly by
// setting TRUST_FORWARDED_FOR=1 — trusting X-Forwarded-For without that opt-in
// lets any caller forge their source IP and bypass the per-IP budget.
package middleware

import (
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"golang.org/x/time/rate"
)

const (
	defaultRPM   = 30
	defaultBurst = 10
	// idleReapAfter is how long a per-IP limiter may sit with no request
	// before it is garbage-collected. Keeps the map bounded under a large
	// IP fan-out without dropping active callers.
	idleReapAfter = 15 * time.Minute
)

// ipLimiter is one bucket + its last-use timestamp.
type ipLimiter struct {
	lim  *rate.Limiter
	last time.Time
}

// RateLimiter holds the per-IP token-bucket registry. Safe for concurrent use.
type RateLimiter struct {
	mu      sync.Mutex
	buckets map[string]*ipLimiter
	rate    rate.Limit
	burst   int
	lastGC  time.Time
	// disabled short-circuits Allow() to true — used by the RED baseline
	// and the RATE_LIMIT_DISABLED=1 operator escape.
	disabled bool
}

// NewRateLimiter builds a limiter with the given per-minute rate + burst.
// A non-positive rpm disables the limiter (never gates a request) — that is
// the RED baseline behavior, made explicit rather than silently defaulted.
func NewRateLimiter(rpm, burst int) *RateLimiter {
	disabled := rpm <= 0
	if burst <= 0 {
		burst = defaultBurst
	}
	// Convert requests/minute to a rate.Limit (per second).
	perSec := rate.Limit(float64(rpm) / 60.0)
	return &RateLimiter{
		buckets:  make(map[string]*ipLimiter),
		rate:     perSec,
		burst:    burst,
		lastGC:   time.Now(),
		disabled: disabled,
	}
}

// NewRateLimiterFromEnv reads RATE_LIMIT_RPM / RATE_LIMIT_BURST /
// RATE_LIMIT_DISABLED and returns a configured RateLimiter.
func NewRateLimiterFromEnv() *RateLimiter {
	if envTrue("RATE_LIMIT_DISABLED") {
		return NewRateLimiter(0, 0) // disabled
	}
	rpm := envInt("RATE_LIMIT_RPM", defaultRPM)
	burst := envInt("RATE_LIMIT_BURST", defaultBurst)
	return NewRateLimiter(rpm, burst)
}

// Allow reports whether a request from clientIP may proceed. It also lazily
// reaps stale buckets so the map does not grow unbounded.
func (r *RateLimiter) Allow(clientIP string) bool {
	if r.disabled {
		return true
	}
	r.mu.Lock()
	defer r.mu.Unlock()

	now := time.Now()
	if now.Sub(r.lastGC) > idleReapAfter {
		for ip, b := range r.buckets {
			if now.Sub(b.last) > idleReapAfter {
				delete(r.buckets, ip)
			}
		}
		r.lastGC = now
	}

	b, ok := r.buckets[clientIP]
	if !ok {
		b = &ipLimiter{lim: rate.NewLimiter(r.rate, r.burst)}
		r.buckets[clientIP] = b
	}
	b.last = now
	return b.lim.Allow()
}

// Disabled reports whether this limiter is a no-op.
func (r *RateLimiter) Disabled() bool {
	return r.disabled
}

// clientIPFromRequest returns the effective per-IP key. RemoteAddr is the
// default; when TRUST_FORWARDED_FOR is set to a truthy value the leftmost
// X-Forwarded-For entry (RFC 7239) is used instead. Never trust XFF by
// default — an attacker sets it trivially and bypasses per-IP budgets.
func clientIPFromRequest(r *http.Request) string {
	if envTrue("TRUST_FORWARDED_FOR") {
		if fwd := strings.TrimSpace(r.Header.Get("X-Forwarded-For")); fwd != "" {
			// Leftmost entry = the original client.
			return strings.TrimSpace(strings.Split(fwd, ",")[0])
		}
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

// writeRateLimited emits the minimal 429 response body — never echoes the
// client IP nor the bucket internals (§11.4.10).
func writeRateLimited(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Retry-After", "60")
	w.WriteHeader(http.StatusTooManyRequests)
	// Fixed opaque payload — no dynamic content that could leak.
	_, _ = w.Write([]byte(`{"error":"rate_limited"}`))
}

// GinRateLimit returns a Gin middleware enforcing per-IP rate limits.
func GinRateLimit(r *RateLimiter) gin.HandlerFunc {
	return func(c *gin.Context) {
		if r == nil || r.Disabled() {
			c.Next()
			return
		}
		ip := clientIPFromRequest(c.Request)
		if !r.Allow(ip) {
			c.Header("Retry-After", "60")
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{"error": "rate_limited"})
			return
		}
		c.Next()
	}
}

// WithRateLimit wraps a net/http Handler with per-IP rate limiting — used by
// boba-jackett (which does not use Gin).
func WithRateLimit(r *RateLimiter, next http.Handler) http.Handler {
	if r == nil || r.Disabled() {
		return next
	}
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		ip := clientIPFromRequest(req)
		if !r.Allow(ip) {
			writeRateLimited(w)
			return
		}
		next.ServeHTTP(w, req)
	})
}

// -- env helpers -------------------------------------------------------------

func envTrue(name string) bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv(name)))
	return v == "1" || v == "true" || v == "yes"
}

func envInt(name string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	if n, err := strconv.Atoi(raw); err == nil && n > 0 {
		return n
	}
	return fallback
}
